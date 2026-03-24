#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
import sys
import time
import argparse
import traceback
import requests
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from pathlib import Path

# 导入变异模块
try:
    from vdbfuzz.mutator import Mutator
except ImportError:
    try:
        # 尝试相对导入
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from vdbfuzz.mutator import Mutator
    except ImportError:
        # 尝试从当前目录的父目录导入
        vdbfuzz_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'vdbfuzz')
        if os.path.exists(vdbfuzz_path):
            sys.path.append(os.path.dirname(vdbfuzz_path))
            from vdbfuzz.mutator import Mutator
        else:
            # 如果还是找不到，定义一个最小的Mutator类
            class Mutator:
                @staticmethod
                def generate_float_array(dimension, normalized=False, min_val=-1.0, max_val=1.0):
                    import random, math
                    array = [random.uniform(min_val, max_val) for _ in range(dimension)]
                    if normalized and array:
                        length = math.sqrt(sum(x*x for x in array))
                        if length > 0:
                            array = [x/length for x in array]
                    return array
                    
                @staticmethod
                def generate_embedding_matrix(rows, embedding_dim, normalized=True):
                    return [Mutator.generate_float_array(embedding_dim, normalized) for _ in range(rows)]
                    
                @staticmethod
                def generate_multi_dim_array(dimensions, normalized=False, min_val=-1.0, max_val=1.0):
                    if not dimensions:
                        return []
                    if len(dimensions) == 1:
                        return Mutator.generate_float_array(dimensions[0], normalized, min_val, max_val)
                    
                    result = []
                    for _ in range(dimensions[0]):
                        if len(dimensions) == 2:
                            result.append(Mutator.generate_float_array(dimensions[1], normalized, min_val, max_val))
                        else:
                            result.append(Mutator.generate_multi_dim_array(dimensions[1:], normalized, min_val, max_val))
                    return result
                    
                def normal_mutate(self, original_content, send_request, connectivity_check_func, save_failure_func=None, max_iterations=200, **kwargs):
                    # 简化版本，只返回空列表
                    logger.info("开始随机变异测试，最大测试次数: 200")
                    return []



# 日志配置
# 创建目录存放日志文件
os.makedirs('logs', exist_ok=True)

# 添加控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

# 添加文件处理器
# 使用时间戳作为文件名的一部分
log_file = "logs/mutation_test_" + datetime.now().strftime('%Y%m%d_%H%M%S') + ".log"
file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)  # 文件中记录详细日志
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)

# 配置根日志器
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)  # 设置为DEBUG级别以捕获所有日志
root_logger.addHandler(console_handler)
root_logger.addHandler(file_handler)


# 获取测试模块的日志器
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-True-uid >= 0]_1752748820_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid >= 0]_1752748820.json"
VDB_TYPE = "milvus"


def send_request(content, request_type="POST", url_path="http://172.17.0.5:23210/v2/vectordb/collections/create", custom_headers=None):
    """
    发送请求到目标服务器

    Args:
        content: 请求内容
        request_type: 请求方法，默认为"POST"
        url_path: URL路径，默认为"http://172.17.0.5:23210/v2/vectordb/collections/create"
        custom_headers: 自定义请求头，如果提供则会合并到默认headers
        
    Returns:
        requests.Response: 响应对象
    """
    if not TARGET_URL:
        raise ValueError("目标URL未设置，请使用 -t 参数指定目标服务器URL")
    
    # 检查url_path是否已经是完整URL
    if url_path.startswith(('http://', 'https://')):
        from urllib.parse import urlsplit

        parsed = urlsplit(url_path)
        path = parsed.path or '/'
        if parsed.query:
            path = f"{path}?{parsed.query}"
        url = TARGET_URL.rstrip('/') + path
    else:
        url = TARGET_URL.rstrip('/') + url_path
    
    # 基础请求头
    headers = {
        'Content-Type': 'application/json',
    }

    # 合并自定义请求头
    if custom_headers:
        headers.update(custom_headers)

    try:
        logger.debug(f"发送 {request_type} 请求到 {url}")
        if request_type in ['POST', 'PUT']:
            response = requests.request(
                method=request_type,
                url=url,
                headers=headers,
                json=content,
                timeout=10
            )
        else:
            response = requests.request(
                method=request_type,
                url=url,
                headers=headers,
                params=content,
                timeout=10
            )
        
        # 打印请求结果摘要
        logger.info(f"请求响应状态码: {response.status_code}")
        
        return response
    except Exception as e:
        logger.error(f"发送请求失败: {str(e)}")
        return None



def check_connectivity():
    """
    检查向量数据库连通性

    Returns:
        bool: 数据库是否可连接
    """
    if not TARGET_URL:
        return False

    try:
        url = TARGET_URL.rstrip('/') + "/"
        response = requests.get(url, timeout=5)
        return response.status_code in [200, 404, 503]
    except Exception as e:
        logger.error(f"连通性检查失败: {str(e)}")
        return False



def save_failure(failure_info):
    """
    保存失败信息到文件

    Args:
        failure_info: 失败信息字典
    """
    if not OUTPUT_DIR:
        logger.warning("输出目录未设置，无法保存失败信息")
        return

    # 创建失败信息目录
    failure_dir = Path(OUTPUT_DIR) / "failures" / TEST_NAME.replace(".", "_")
    failure_dir.mkdir(parents=True, exist_ok=True)

    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    mutation_type = failure_info.get("mutation", {}).get("type", "unknown")
    mutation_path = "_".join(str(x) for x in failure_info.get("mutation", {}).get("path", []))
    
    filename = f"failure_{mutation_type}_{mutation_path}_{timestamp}.json"
    file_path = failure_dir / filename
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(failure_info, f, indent=2, ensure_ascii=False)
        logger.info(f"已保存失败信息到 {file_path}")
    except Exception as e:
        logger.error(f"保存失败信息失败: {str(e)}")



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrueUid01752748820Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid >= 0]_1752748820.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid >= 0]_1752748820.json"
        self.test_count = 5  # 测试方法数量
        self.mutator = Mutator()  # 初始化变异器
    
    def run_tests(self):
        """运行所有测试"""
        logger.info(f"开始测试: {self.test_name}")
        logger.info(f"目标URL: {TARGET_URL}")
        
        # 检查连通性
        if not check_connectivity():
            logger.error("无法连接到目标服务器，测试终止")
            return False
        
        # 运行所有测试用例
        try:
            for i in range(self.test_count):
                logger.info(f"运行测试 {i+1}/{self.test_count}")
                method_name = f"test_request_{i}"
                if hasattr(self, method_name):
                    test_method = getattr(self, method_name)
                    test_method()
                else:
                    logger.warning(f"未找到测试方法: {method_name}")
            
            logger.info("所有测试完成")
            return True
        except Exception as e:
            logger.error(f"测试过程中发生异常: {str(e)}")
            traceback.print_exc()
            return False


    def test_request_0(self):
        """测试请求 0 - POST http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: POST http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '6817ccbe-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_07_626693Sptibfvq',
    'dimension': 128,
    'metricType': 'L2',
    'description': 'test collection',
    'primaryField': 'id',
    'vectorField': 'vector',
    'params': {
    'consistencyLevel': 'Strong',
},
}


        send_request(original_content, method, url_path, headers)
        return True



    def test_request_1(self):
        """测试请求 1 - POST http://172.17.0.5:23210/v2/vectordb/collections/describe"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/describe")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/describe'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '6817ccbe-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_07_626693Sptibfvq',
}
        
        if not original_content:
            logger.info("请求无内容，跳过变异测试")
            return True
        
        # 定义发送请求的函数
        def send_mutated_request(mutated_content):
            return send_request(mutated_content, method, url_path, headers)
        
        logger.info("开始变异测试...")
        
        # 获取命令行参数
        iterations = getattr(args, 'iterations', 200)  # 默认值为200
        time_limit = getattr(args, 'time_limit', 10)   # 默认值为10分钟
                    
        mutator = Mutator()  # 创建变异器实例
        failures = mutator.normal_mutate(
            original_content=original_content,
            send_request=send_mutated_request,
            connectivity_check_func=check_connectivity,
            save_failure_func=save_failure,
            max_time_minutes=time_limit,  # 使用上面设置的time_limit变量
            max_iterations=iterations     # 使用上面设置的iterations变量
        )
        
        if failures:
            logger.warning(f"发现 {len(failures)} 个导致异常的变异")
        else:
            logger.info("变异测试未发现异常")
        
        return len(failures) == 0



    def test_request_2(self):
        """测试请求 2 - POST http://172.17.0.5:23210/v2/vectordb/entities/insert"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/insert")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/insert'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '6817ccbe-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_07_626693Sptibfvq',
    'data': [
    {
    'id': 17527488136637,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Donald Thompson',
    'address': '159 Steven Lakes Suite 739\nMichaelfurt, PW 24090',
    'text': 'Friend billion choice something. Exist fish beat range speech crime view leg. Newspaper society tough head skin. Author billion partner quality room similar plant.',
    'email': 'christopher21@example.com',
    'phone_number': '531-545-3510x71281',
    'json': {
    'name': 'Bianca Campbell',
    'address': 'Unit 1920 Box 1085\nDPO AE 69861',
},
    'key12669': 'value84313',
    'key71001': 'value81799',
    'key85457': 'value95401',
    'key90640': 'value32445',
    'key15684': 'value12689',
    'key24894': 'value88700',
    'key82577': 'value39234',
},
    {
    'id': 17527488136651,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Kimberly Potter',
    'address': '195 Joanna Glen Apt. 040\nDianatown, WA 29057',
    'text': 'Describe race improve different fine.\nBehind worry foot over. Wall item throughout less. Such clearly response mean sell wear develop.',
    'email': 'erika72@example.net',
    'phone_number': '(235)418-9559x8390',
    'json': {
    'name': 'Kenneth Vega',
    'address': '01950 Sarah Viaduct\nLake Loganberg, MN 39737',
},
    'key73415': 'value30338',
    'key47695': 'value16280',
    'key84013': 'value71585',
    'key98344': 'value69113',
    'key16688': 'value26263',
    'key32079': 'value81613',
    'key83828': 'value89732',
    'key85822': 'value23165',
    'key71796': 'value92468',
},
    {
    'id': 17527488136662,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'William Ross',
    'address': '617 John Roads Apt. 776\nPort Lorraine, MH 93524',
    'text': 'Past push card. Still free professional read machine keep suddenly. Check baby improve blue. Hot imagine firm staff design concern join.',
    'email': 'cochrandennis@example.org',
    'phone_number': '685-273-2436x511',
    'json': {
    'name': 'Joshua Wong',
    'address': '50014 Diaz Cape\nChristinebury, MP 27749',
},
    'key15855': 'value59117',
    'key17932': 'value9101',
    'key45322': 'value42617',
},
    {
    'id': 17527488136674,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Jonathan Moran',
    'address': '152 Robert Heights\nAustinview, PA 43650',
    'text': 'Single teach Republican training center black everyone. Together feel concern agree edge particular.',
    'email': 'jmendoza@example.com',
    'phone_number': '3685087149',
    'json': {
    'name': 'Christopher Johnson',
    'address': '34980 Bonnie Ridge\nAshleyfurt, MN 14928',
},
    'key76969': 'value37554',
    'key66642': 'value88370',
    'key80': 'value88394',
    'key80386': 'value39455',
    'key62104': 'value43503',
    'key67395': 'value13512',
},
    {
    'id': 17527488136685,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Joyce Lewis',
    'address': '0764 Collier Passage\nHesshaven, GA 78412',
    'text': 'Season discover source save word. Save less involve statement box conference order.',
    'email': 'vincent24@example.net',
    'phone_number': '(988)284-9607',
    'json': {
    'name': 'Devin Hicks',
    'address': '1222 Jenkins Row Suite 198\nWilliamsland, MS 48237',
},
    'key84730': 'value15143',
    'key78590': 'value43572',
    'key10391': 'value1825',
    'key91176': 'value53271',
    'key95182': 'value41362',
    'key43621': 'value7718',
    'key47348': 'value60632',
    'key39221': 'value50566',
},
    {
    'id': 17527488136697,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Stacy Frost MD',
    'address': '3094 Miller Lane\nLaurieport, FM 45592',
    'text': 'Experience fish picture spring science. Prepare best like culture central.',
    'email': 'oconnorteresa@example.org',
    'phone_number': '312-783-2944',
    'json': {
    'name': 'Paul Smith',
    'address': '62554 Diane Junctions Apt. 495\nNorth Michaelport, ME 24972',
},
    'key8509': 'value51168',
    'key23905': 'value14869',
    'key94897': 'value15627',
    'key40598': 'value71498',
    'key97306': 'value86144',
    'key92550': 'value27302',
    'key46059': 'value18823',
    'key72008': 'value42981',
    'key21482': 'value63835',
    'key12653': 'value91748',
},
    {
    'id': 17527488136709,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Tonya Burns',
    'address': '2508 Roberts Burgs Suite 574\nAaronberg, FL 19696',
    'text': 'Feel window bag just form affect while. Couple need understand offer artist not interest. Half computer including effort practice beat such.',
    'email': 'matthew89@example.org',
    'phone_number': '403-623-3643x9046',
    'json': {
    'name': 'Lori Fox',
    'address': '72202 Madeline Mall Apt. 376\nPort Donaldborough, WI 80730',
},
    'key78015': 'value31427',
    'key97002': 'value9704',
    'key29256': 'value39190',
    'key74507': 'value80809',
    'key57231': 'value41986',
},
    {
    'id': 17527488136720,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Kenneth Leblanc',
    'address': '032 Scott Mission Suite 999\nNew Rachel, TX 07258',
    'text': 'Guess look huge respond edge. Ever operation page occur sister scene.\nTeam indeed affect wonder education memory. Plan throughout direction know four if positive. Fish occur compare leader.',
    'email': 'jessicaskinner@example.net',
    'phone_number': '463-494-1008',
    'json': {
    'name': 'Garrett Terry',
    'address': '8671 Herbert Canyon\nNorth Kaylafort, WA 52967',
},
    'key34607': 'value97995',
    'key68195': 'value35104',
    'key3737': 'value8046',
    'key10161': 'value31721',
    'key14439': 'value72267',
    'key32420': 'value14917',
    'key4036': 'value97024',
    'key34133': 'value61019',
},
    {
    'id': 17527488136732,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Thomas Hubbard',
    'address': '107 Bethany Dale\nKellymouth, RI 35081',
    'text': 'Change face fight though recognize ball police piece. Article out care training.\nWhile ahead since everyone affect major citizen.',
    'email': 'gonzalezmelissa@example.net',
    'phone_number': '669.999.1336',
    'json': {
    'name': 'Jerry Cruz',
    'address': '965 Kenneth Bypass\nAlvarezbury, GU 54862',
},
    'key31770': 'value27431',
    'key79467': 'value73080',
    'key96913': 'value34708',
    'key92927': 'value86888',
    'key29942': 'value35918',
},
    {
    'id': 17527488136743,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Katie Gutierrez',
    'address': '46495 Adrian Mountains Suite 001\nCherryhaven, MI 33074',
    'text': 'Decade at rich important back memory. Partner quite think garden soldier other apply.\nHalf apply room research despite. Sound according question at.',
    'email': 'zavila@example.net',
    'phone_number': '425.347.8595',
    'json': {
    'name': 'Kristin Thompson',
    'address': '2940 Mitchell Squares\nWest Jeffrey, DE 35798',
},
    'key42441': 'value26773',
    'key23720': 'value55004',
    'key40635': 'value99180',
    'key87349': 'value80850',
    'key14888': 'value63965',
    'key48563': 'value72505',
    'key44948': 'value89805',
},
    {
    'id': 17527488136754,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Kimberly Rodgers',
    'address': '651 Stephen Circle\nChanville, WV 31875',
    'text': 'Economic answer some nature out. Appear teach rest bag natural. Cold heart within fine natural participant discuss.',
    'email': 'george05@example.org',
    'phone_number': '496-242-2760x30392',
    'json': {
    'name': 'Valerie Silva',
    'address': '1860 Michelle Mountain Suite 354\nDeannaview, VT 21543',
},
    'key98781': 'value90217',
},
    {
    'id': 17527488136765,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Janice Lowe',
    'address': '420 James Coves Apt. 441\nLake Ashleystad, NE 60682',
    'text': 'Knowledge member page add person friend. Hotel behind truth significant future she.\nShow public many middle practice. While as lawyer live effort. Something government statement unit father.',
    'email': 'lindsey14@example.org',
    'phone_number': '445-447-2105',
    'json': {
    'name': 'Amy Gay',
    'address': '575 Tucker Mews\nWest Jamesstad, PR 69681',
},
    'key94544': 'value38573',
    'key75771': 'value53549',
    'key86387': 'value65124',
    'key46455': 'value33719',
    'key20366': 'value54982',
    'key66591': 'value19383',
    'key17997': 'value35152',
    'key54109': 'value86220',
    'key24390': 'value50303',
    'key92190': 'value77897',
},
    {
    'id': 17527488136776,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Tanner Williams',
    'address': '99959 Lewis Inlet Suite 925\nBoothmouth, IL 89354',
    'text': 'Wonder morning special run government PM.\nKnowledge his build shake wide can. Fund soon add. Relate single then history performance way walk share.',
    'email': 'uenglish@example.net',
    'phone_number': '(306)343-7916x490',
    'json': {
    'name': 'Patricia Sims',
    'address': '932 Jones Dam\nNorth Edgarside, ID 32761',
},
    'key91438': 'value62712',
    'key80947': 'value64540',
    'key58023': 'value79117',
    'key3746': 'value54395',
    'key61887': 'value78582',
},
    {
    'id': 17527488136787,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Alexander Garcia',
    'address': '84960 Welch Mews\nNorth Bryan, ID 77772',
    'text': 'Some rock coach push. Total well cell campaign reduce.\nModel if which think task. Remain knowledge mean body somebody of hit.\nCarry street behavior. Little may song easy season prevent.',
    'email': 'andrew81@example.org',
    'phone_number': '402-550-1997x22398',
    'json': {
    'name': 'Jackson Mosley',
    'address': '215 Silva Falls Suite 341\nDavidland, TN 99637',
},
    'key89695': 'value22615',
    'key11721': 'value18974',
    'key96958': 'value47610',
    'key70512': 'value15291',
},
    {
    'id': 17527488136798,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Brandon Hall',
    'address': '3242 Christina Locks\nKathrynmouth, TN 89144',
    'text': 'May manage final national approach hour. Green accept charge on. Personal agreement similar ahead letter. Seek price central huge job option interview challenge.',
    'email': 'ehurley@example.net',
    'phone_number': '973.583.4506x2816',
    'json': {
    'name': 'James Skinner',
    'address': '849 Amanda Ford Apt. 619\nJoannahaven, RI 87287',
},
    'key13936': 'value58413',
    'key57645': 'value1335',
    'key72287': 'value84589',
},
    {
    'id': 17527488136809,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Jacob Alvarado',
    'address': '47275 Aaron Bridge Apt. 861\nSanderstown, OR 71207',
    'text': 'Fast list also. Policy would black far first. Room yes task.\nVisit team team often describe always whole but. Growth know something four.',
    'email': 'michael21@example.com',
    'phone_number': '001-804-573-7185x11321',
    'json': {
    'name': 'Bruce Moore',
    'address': '13950 Jeremy Rapids\nEast Eric, KS 32917',
},
    'key22868': 'value62899',
    'key55685': 'value91680',
    'key763': 'value92025',
    'key96968': 'value90278',
    'key67571': 'value99195',
    'key87480': 'value26795',
    'key94833': 'value59320',
    'key48183': 'value37641',
    'key49342': 'value62256',
    'key82950': 'value79600',
},
    {
    'id': 17527488136821,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Daniel Gill',
    'address': '101 Bell Divide Apt. 336\nWest David, MT 19750',
    'text': 'Glass sing miss example whole. Clear how clear unit event say control hundred. Else expect clear live address.\nView economic however especially audience near least state. Begin second way reach.',
    'email': 'todd58@example.net',
    'phone_number': '800.983.5092',
    'json': {
    'name': 'Michelle Thornton',
    'address': '900 Alexis Glen Suite 407\nSouth Michaelstad, NJ 04590',
},
    'key47033': 'value69728',
    'key29238': 'value39152',
    'key63693': 'value64409',
    'key9363': 'value92504',
},
    {
    'id': 17527488136832,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Maria Schmidt',
    'address': 'Unit 1715 Box 1299\nDPO AP 49584',
    'text': 'Upon movement perform least throughout body. Cause suffer animal mean along about.',
    'email': 'nkhan@example.net',
    'phone_number': '589.519.0271',
    'json': {
    'name': 'Thomas Powell',
    'address': '34442 Clark Mission\nPort Joseph, ID 61349',
},
    'key50749': 'value66434',
    'key40213': 'value95858',
    'key60133': 'value86391',
    'key55771': 'value29619',
    'key9942': 'value58429',
    'key15119': 'value22224',
    'key65406': 'value571',
    'key92458': 'value10102',
},
    {
    'id': 17527488136842,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Troy Anderson',
    'address': '125 Huffman Stravenue\nCharlesland, AS 53787',
    'text': 'Theory soon receive body give how. During none name network. Economic serious item step history hotel stock. Author in nation deep.',
    'email': 'amberjones@example.com',
    'phone_number': '(610)854-8495x28725',
    'json': {
    'name': 'Linda Smith',
    'address': '00797 Mendez Cove Suite 999\nWest Christopher, VA 82759',
},
    'key9236': 'value73236',
    'key61264': 'value56297',
},
    {
    'id': 17527488136853,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Luke Ray',
    'address': '3407 Bowers Center\nTamarashire, OH 72123',
    'text': 'There senior human eat. Class man tough more know call. Field rest why each sing explain so.\nEach national nation into modern build decision. Little president dream claim by not raise.',
    'email': 'rharvey@example.org',
    'phone_number': '964-591-4954x9121',
    'json': {
    'name': 'Henry Woodard',
    'address': '42981 Perkins Falls Apt. 323\nWest Cynthiaburgh, MN 63557',
},
    'key56115': 'value38216',
    'key19983': 'value58412',
},
    {
    'id': 17527488136865,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Maria Buck',
    'address': '58426 Brown Pass\nTonifurt, IN 11948',
    'text': 'Television push tell season machine. Same Democrat after chance executive.\nCharacter stuff effort trip establish push prevent. Southern education morning south which foreign.',
    'email': 'michael12@example.org',
    'phone_number': '(759)721-1635x8084',
    'json': {
    'name': 'Michael White',
    'address': '59766 Mary Parks Apt. 613\nSouth Johnmouth, FM 50288',
},
    'key11138': 'value38249',
    'key6711': 'value10652',
    'key73423': 'value56294',
    'key66320': 'value9349',
    'key18453': 'value63942',
    'key88900': 'value70726',
    'key96692': 'value77728',
    'key15721': 'value59706',
    'key57565': 'value37585',
},
    {
    'id': 17527488136877,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Frederick Figueroa',
    'address': '680 Dean Ford\nPort Marilyn, TX 00884',
    'text': 'Partner shake rate.\nSomeone sport court base.\nStar those leader nice write. Themselves answer friend really. Accept affect research understand very character different.',
    'email': 'drakegabriel@example.net',
    'phone_number': '(919)665-8655',
    'json': {
    'name': 'Susan Alexander',
    'address': '11917 Bryan Plains\nWeisshaven, AK 67919',
},
    'key15128': 'value22557',
    'key48774': 'value15858',
    'key85223': 'value99135',
    'key10357': 'value63042',
    'key99892': 'value55720',
    'key81211': 'value84020',
    'key32732': 'value49421',
    'key84728': 'value75104',
    'key57473': 'value43918',
},
    {
    'id': 17527488136889,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Robert Kelly',
    'address': 'PSC 8970, Box 2080\nAPO AP 42760',
    'text': 'Why often before. Science herself able home score ask type include. Science can employee as career never scientist some.',
    'email': 'torrespatrick@example.net',
    'phone_number': '(952)987-7131',
    'json': {
    'name': 'Erin Robinson',
    'address': '391 Glenn Gateway Apt. 721\nNew Ericbury, VI 85207',
},
    'key9955': 'value87355',
    'key39974': 'value17151',
    'key59972': 'value51583',
},
    {
    'id': 17527488136898,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Erin Coleman',
    'address': '0711 Jessica Point Suite 759\nJohnbury, MA 41979',
    'text': 'Your box probably describe threat machine mouth. Yeah too outside line modern mean language. Great upon Congress yet measure material.',
    'email': 'ashley92@example.org',
    'phone_number': '269.244.3377x7739',
    'json': {
    'name': 'Paula Williams',
    'address': '271 Hawkins Center\nAllenchester, OR 77935',
},
    'key58343': 'value91268',
    'key715': 'value77746',
    'key79438': 'value30097',
    'key75584': 'value75068',
    'key48793': 'value79059',
},
    {
    'id': 17527488136909,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Christian Martin',
    'address': '094 Alyssa Coves\nNorth Shawnshire, ME 20808',
    'text': 'Theory stage region door season present. Sport across within work. Rise program individual understand simply.',
    'email': 'lkelley@example.com',
    'phone_number': '(895)437-2665x22985',
    'json': {
    'name': 'Curtis Brown',
    'address': '051 Hicks Ports Suite 714\nMichaelport, AZ 41659',
},
    'key61902': 'value47694',
},
    {
    'id': 17527488136919,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Susan Thompson',
    'address': '741 Wagner Glen\nNew Michellefurt, GU 53231',
    'text': 'Successful drug million mission company dog. Edge whatever chair sell policy today. Author college hotel project page cold high.\nIt try rate rule. Class reason society force fine accept.',
    'email': 'rothjennifer@example.org',
    'phone_number': '261.294.8960x570',
    'json': {
    'name': 'Jeff Olson',
    'address': '79025 Matthew Road Apt. 297\nSouth Tami, WI 18222',
},
    'key20618': 'value99151',
    'key60287': 'value14310',
    'key22171': 'value43290',
    'key7544': 'value41364',
    'key92255': 'value4931',
    'key4706': 'value22727',
    'key4495': 'value60185',
    'key7880': 'value91526',
    'key61037': 'value77697',
},
    {
    'id': 17527488136931,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Jesus Ellis',
    'address': '49314 Stephens Route\nLake William, TN 79663',
    'text': 'Increase employee must which. Kid economic buy five.\nApply have wall. Government remember remain agree recently. Third air take cold outside action big generation.',
    'email': 'petersondakota@example.org',
    'phone_number': '001-923-819-0511x5252',
    'json': {
    'name': 'Joe Quinn',
    'address': '836 Austin Harbor\nSouth Lorifurt, IA 49502',
},
    'key21572': 'value26650',
    'key37993': 'value79558',
    'key58393': 'value76350',
},
    {
    'id': 17527488136943,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Mrs. Danielle Lewis MD',
    'address': '7501 Kelly Ford\nPort Raymondview, SC 37352',
    'text': 'Recognize letter nature. True would huge sometimes.\nSpeak degree trade manage similar poor. Style four recent today word.',
    'email': 'ericksonalexis@example.com',
    'phone_number': '682-442-3879x676',
    'json': {
    'name': 'Patrick Kramer',
    'address': '55664 Mitchell Tunnel\nSouth Joanna, NE 36988',
},
    'key62099': 'value13470',
},
    {
    'id': 17527488136954,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'James Soto',
    'address': '048 Carter Landing\nLake Charles, OR 91538',
    'text': 'Nation source matter term source exactly whose other. Collection ever skill much should. Coach fact lot population nor plant. Idea yard thought each.',
    'email': 'lrobertson@example.org',
    'phone_number': '+1-786-274-2295x022',
    'json': {
    'name': 'Sabrina Smith',
    'address': 'PSC 8599, Box 5860\nAPO AE 68566',
},
    'key95177': 'value30596',
    'key46746': 'value60935',
},
    {
    'id': 17527488136963,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Robert Baker',
    'address': '988 Sparks Shoals\nEast Roberto, DE 77002',
    'text': 'Maybe political citizen teach. Every stage discover performance son beat hear all. Employee help cup.\nYour return wrong box. Believe pattern ahead really seven order power stop.',
    'email': 'jeffflynn@example.net',
    'phone_number': '001-554-636-0153x0740',
    'json': {
    'name': 'Kimberly Lopez',
    'address': '72678 Garrett Court Apt. 368\nLake Markside, GA 25871',
},
    'key60349': 'value26621',
    'key20890': 'value45708',
    'key72276': 'value89734',
    'key8238': 'value90413',
    'key18418': 'value73052',
    'key42826': 'value75610',
},
    {
    'id': 17527488136975,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'David Harris',
    'address': '721 Angela Plains\nSouth Amanda, RI 78535',
    'text': 'North always reach such consider leg. Its still career sit. In pressure eight win. Conference choose owner stock already notice be.\nTraining question lead. Those yes hand feeling.',
    'email': 'jeffrey70@example.com',
    'phone_number': '(873)337-9334x425',
    'json': {
    'name': 'Angela Jones',
    'address': '6677 Lynn Forges Suite 684\nAlbertside, CT 90262',
},
    'key54866': 'value12192',
    'key30794': 'value80547',
    'key69058': 'value40609',
    'key46030': 'value16926',
},
    {
    'id': 17527488136985,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Michelle Jackson',
    'address': 'Unit 8035 Box 9695\nDPO AP 04334',
    'text': 'Friend easy and system.\nAlmost only road sort human important central. Team central speech series win however.\nShare affect everybody seat pass bar president. Than give reach stop agency.',
    'email': 'marquezbrenda@example.org',
    'phone_number': '(483)735-5154x6903',
    'json': {
    'name': 'Denise Smith',
    'address': '3116 Kelly Parkway\nEast Jennifer, MA 85757',
},
    'key71369': 'value13249',
    'key49799': 'value15189',
    'key69638': 'value55830',
    'key50275': 'value25979',
    'key62974': 'value83288',
    'key62989': 'value9753',
    'key46273': 'value76212',
    'key98695': 'value70814',
    'key87191': 'value40598',
    'key53686': 'value38297',
},
    {
    'id': 17527488136995,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Kimberly Schmidt',
    'address': '990 Rodriguez Union Suite 892\nLake Marystad, MA 24216',
    'text': 'Allow contain sport expert detail nature. Father hear side two pick few condition. Game ago of central item set.',
    'email': 'alyssa03@example.com',
    'phone_number': '292.906.3481',
    'json': {
    'name': 'Julie Jones',
    'address': '35814 Amanda Mall Suite 852\nMatthewchester, WI 41992',
},
    'key68030': 'value66678',
    'key87658': 'value56376',
    'key35273': 'value97363',
    'key85814': 'value94897',
    'key86899': 'value10774',
    'key84310': 'value8923',
    'key89489': 'value16356',
    'key12220': 'value51916',
    'key60912': 'value12694',
    'key5469': 'value11566',
},
    {
    'id': 17527488137006,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Tiffany Hernandez MD',
    'address': '9921 Ebony Station Suite 989\nWest Hector, WV 84321',
    'text': 'Find security tax hospital Republican. Fast business reach billion mission. From many situation day weight exist red.',
    'email': 'todd02@example.net',
    'phone_number': '001-645-795-8806',
    'json': {
    'name': 'Brent Nelson',
    'address': '7895 Rebecca Crest Apt. 784\nRuthburgh, AL 31567',
},
    'key61926': 'value79424',
    'key29722': 'value16118',
    'key22190': 'value55370',
    'key23242': 'value58132',
    'key17801': 'value58130',
    'key20274': 'value3501',
    'key54124': 'value28685',
    'key43590': 'value60167',
    'key86960': 'value71787',
},
    {
    'id': 17527488137017,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Lisa Hall',
    'address': '5786 Allison Shoal\nKingville, NE 69396',
    'text': 'General career campaign read control. Sign series specific Republican rise day.\nWe nation college fly test security. Group since enter teach middle. Eye what shake painting right everyone.',
    'email': 'wallacemichelle@example.org',
    'phone_number': '(717)790-2792x73884',
    'json': {
    'name': 'Amy Young',
    'address': '255 Craig Villages Suite 072\nNorth Jessica, TN 23019',
},
    'key76602': 'value70203',
    'key89631': 'value86944',
    'key3745': 'value10473',
    'key50447': 'value91817',
    'key56678': 'value28345',
    'key20486': 'value50101',
    'key57515': 'value84801',
    'key593': 'value15217',
},
    {
    'id': 17527488137028,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Paul Rosales',
    'address': '31327 Brandon Island Suite 505\nGregoryberg, NJ 56975',
    'text': 'These former heart adult than note because. Natural treatment note turn likely.\nLater chair past author interesting hand audience. Goal someone west because respond way image open.',
    'email': 'flynnalexandra@example.net',
    'phone_number': '(655)479-9963x04852',
    'json': {
    'name': 'Jennifer Johnson',
    'address': '07092 Hill Mill Apt. 955\nNew Donna, NM 62880',
},
    'key45407': 'value80396',
    'key56690': 'value47591',
    'key72183': 'value73254',
    'key70562': 'value76648',
    'key18623': 'value64654',
    'key5530': 'value31585',
    'key11543': 'value25018',
    'key82781': 'value52492',
},
    {
    'id': 17527488137040,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Jane Hernandez',
    'address': '7445 Tate Run Apt. 628\nJonathantown, AZ 34095',
    'text': 'Crime ready career exactly least court particularly word. Pretty book child option class. Pattern foreign senior inside least tend.\nChoose under talk soldier seat big. Behind hit want race.',
    'email': 'bergerveronica@example.org',
    'phone_number': '933-576-3158x95397',
    'json': {
    'name': 'Dylan Hammond',
    'address': '85167 Tanner Mill\nGuerramouth, MP 46755',
},
    'key8351': 'value43953',
    'key52626': 'value16523',
    'key57327': 'value98581',
    'key22040': 'value14330',
    'key20535': 'value90726',
    'key5753': 'value83022',
    'key35198': 'value61951',
    'key90311': 'value2731',
},
    {
    'id': 17527488137053,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Jason Rivera',
    'address': '5001 Deborah Circles\nMcknightchester, WA 46068',
    'text': 'Various what offer writer reason pick attack live. She left business.\nSon although rest give. Onto building democratic its.\nThrow window want price image choice both. Sell wall recognize.',
    'email': 'rhondagiles@example.com',
    'phone_number': '(529)375-8185',
    'json': {
    'name': 'Gregory Bennett',
    'address': '3729 Lane Hills Apt. 516\nSouth Jacquelinehaven, AK 92392',
},
    'key76223': 'value49430',
    'key46154': 'value26074',
    'key67130': 'value50761',
    'key31419': 'value4123',
    'key1913': 'value37891',
    'key74493': 'value69878',
    'key76576': 'value46633',
},
    {
    'id': 17527488137065,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Bradley Jones',
    'address': '0382 Derrick Orchard\nHaneyfort, VT 60279',
    'text': 'Draw main worry. Let morning partner give their describe. Fine north improve herself through.\nUnderstand management it media wind begin attorney. Late simple whom board. Region describe energy plan.',
    'email': 'paul53@example.com',
    'phone_number': '270-337-0116x51944',
    'json': {
    'name': 'Ronald Smith',
    'address': '24184 Steele Tunnel\nPort Jamesmouth, AZ 63820',
},
    'key39403': 'value44947',
    'key14733': 'value22720',
    'key92137': 'value60022',
    'key59569': 'value96387',
    'key20944': 'value32405',
    'key70996': 'value614',
    'key77403': 'value7882',
    'key74763': 'value70373',
},
    {
    'id': 17527488137076,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Jonathan Gregory',
    'address': '5213 Tran Court Suite 604\nLake Jamesborough, RI 31037',
    'text': 'Need project be civil become market. Standard event entire.\nInto animal prevent protect age look former. If better point financial.\nOther learn first everybody a.',
    'email': 'sreynolds@example.net',
    'phone_number': '+1-887-487-6571x8389',
    'json': {
    'name': 'Katrina Gates',
    'address': '93168 Logan Parks Apt. 331\nEast Shelley, NJ 50561',
},
    'key7574': 'value9727',
    'key405': 'value87492',
    'key61129': 'value67714',
    'key97060': 'value63849',
    'key64433': 'value26298',
    'key4281': 'value91940',
    'key58329': 'value69926',
    'key11846': 'value75978',
},
    {
    'id': 17527488137087,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Leah Mcintosh',
    'address': '6193 Shelly Camp Suite 540\nJaredbury, PR 28519',
    'text': 'Away conference economic. Side raise ball shoulder. Organization show point show financial time again two.',
    'email': 'orichardson@example.com',
    'phone_number': '(972)894-4081x514',
    'json': {
    'name': 'Dakota Snyder',
    'address': '8264 Thompson Throughway\nLake Whitney, UT 62662',
},
    'key23224': 'value43778',
    'key11618': 'value47378',
    'key81510': 'value46716',
    'key42116': 'value36408',
},
    {
    'id': 17527488137098,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Douglas Meyer',
    'address': '12368 Williams Isle Apt. 332\nPaynefort, TN 04568',
    'text': 'Investment management agree success it claim actually miss. During fact after bad thank job expert.',
    'email': 'brandon46@example.org',
    'phone_number': '7326011737',
    'json': {
    'name': 'Chad Lambert',
    'address': '7333 Miller Causeway\nPort Kevinhaven, WI 88744',
},
    'key4568': 'value97764',
    'key24314': 'value43427',
    'key96580': 'value76255',
    'key37729': 'value3273',
    'key37074': 'value39003',
    'key78505': 'value13429',
    'key22051': 'value50996',
    'key46023': 'value19660',
    'key93447': 'value50751',
},
    {
    'id': 17527488137109,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Ronnie Forbes',
    'address': '565 Graham Locks\nTonyafort, MI 47622',
    'text': 'Any change yourself threat thousand nice.\nHospital discuss develop finish surface unit her. Also space bill attention develop month. Anyone rule ago.',
    'email': 'jsmall@example.net',
    'phone_number': '001-560-979-2307x5433',
    'json': {
    'name': 'Stephanie Hall',
    'address': '17043 Collins Haven\nEast Lisaville, MD 39633',
},
    'key15295': 'value42381',
    'key26026': 'value73250',
    'key90929': 'value69989',
},
    {
    'id': 17527488137120,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Jennifer Brown',
    'address': '0985 Wright River\nSanchezport, MO 66478',
    'text': 'Matter away from when page. Issue grow way. International ground forget list name base fish.\nMaterial green among here Mr. Listen around president lose member. Young different fact include.',
    'email': 'hillsusan@example.net',
    'phone_number': '983.760.6561x6490',
    'json': {
    'name': 'Ronald Johnson',
    'address': '17700 Hernandez Plaza Suite 297\nPort Victor, ME 70646',
},
    'key1502': 'value64277',
    'key23781': 'value23111',
    'key42324': 'value43991',
    'key89843': 'value24916',
    'key46396': 'value67098',
    'key70996': 'value27513',
    'key42216': 'value41266',
    'key69904': 'value15470',
    'key40482': 'value35400',
    'key73884': 'value36',
},
    {
    'id': 17527488137132,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Gerald Alvarez',
    'address': '569 Rowe Mountain Apt. 728\nNew Anthony, PR 07719',
    'text': 'Control something carry entire support war condition.\nFormer return night campaign else wife region. From city indicate.',
    'email': 'carpenterstephen@example.net',
    'phone_number': '(481)656-5814x1160',
    'json': {
    'name': 'Alfred Smith',
    'address': '732 Winters Squares Suite 242\nPort Heather, GA 74755',
},
    'key46095': 'value51201',
    'key75658': 'value92755',
    'key25189': 'value75525',
    'key30080': 'value11831',
    'key82827': 'value1815',
    'key32671': 'value78528',
    'key69014': 'value64480',
},
    {
    'id': 17527488137144,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Brittany Williams',
    'address': '7376 Moore Ville Suite 575\nChristyfurt, TX 66598',
    'text': 'Room prove another response language million writer. Draw day help open enjoy under.\nHome represent good statement eat national space game. Tree need herself agree.',
    'email': 'jeremiahstevens@example.com',
    'phone_number': '718-425-4492',
    'json': {
    'name': 'Kristen Howard',
    'address': 'Unit 9931 Box 3059\nDPO AA 62059',
},
    'key21634': 'value85141',
    'key74297': 'value28041',
    'key37796': 'value47144',
    'key47594': 'value93544',
    'key3456': 'value49821',
    'key6248': 'value14437',
    'key97731': 'value34708',
    'key56241': 'value87074',
},
    {
    'id': 17527488137154,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Kenneth Gonzalez',
    'address': '14724 Amber Valley Apt. 404\nStevenland, NJ 35113',
    'text': 'Special who question remain to under page cultural. Question expect analysis provide.\nSeveral try win money control arrive measure provide. Allow guy sell boy college government.',
    'email': 'powellmichael@example.com',
    'phone_number': '+1-860-889-5438x89475',
    'json': {
    'name': 'Steven Wright',
    'address': '7236 Huerta Centers\nKlineshire, PR 91419',
},
    'key86576': 'value9504',
},
    {
    'id': 17527488137165,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Linda Murillo',
    'address': '61340 Thomas Garden\nPort Williammouth, NC 13381',
    'text': 'Evening film lead recently house management.\nProfessional education begin organization. Central try throughout alone TV while. Situation among oil where thousand sort teach herself.',
    'email': 'hwillis@example.net',
    'phone_number': '+1-481-206-7899x630',
    'json': {
    'name': 'Shannon Hatfield',
    'address': '68092 Barrett Hills\nNorth Nicole, IA 20109',
},
    'key13933': 'value70543',
    'key77765': 'value6848',
    'key48515': 'value48146',
    'key90048': 'value21033',
    'key22757': 'value25311',
    'key45404': 'value43583',
    'key5422': 'value90804',
},
    {
    'id': 17527488137176,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Robert Villarreal',
    'address': '8954 Harrington Shore\nWatsonmouth, ME 50253',
    'text': 'Can poor others true family because treat. Policy market least difficult decide accept.',
    'email': 'jennifer46@example.com',
    'phone_number': '531-518-1547x497',
    'json': {
    'name': 'Isaac Stark',
    'address': '4836 Matthew Port\nNew Lisa, MI 70864',
},
    'key92025': 'value94504',
    'key47039': 'value38261',
    'key65543': 'value85228',
    'key51133': 'value54179',
    'key34500': 'value71931',
    'key99540': 'value45675',
    'key52896': 'value64880',
    'key66097': 'value28495',
    'key20665': 'value96645',
    'key70392': 'value7916',
},
    {
    'id': 17527488137186,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Lisa Gibson',
    'address': '43755 Erin Causeway\nBurtonbury, NC 82530',
    'text': 'Above join animal general. Scene resource media politics.\nResponse free as include. Culture air keep that necessary listen series.',
    'email': 'garciawhitney@example.org',
    'phone_number': '001-486-868-9330x05652',
    'json': {
    'name': 'Jason Zuniga',
    'address': '51867 Cochran Pike\nLake Rita, SD 55480',
},
    'key19111': 'value31824',
    'key19033': 'value1700',
    'key13957': 'value11602',
    'key26258': 'value90093',
    'key99784': 'value20453',
    'key67367': 'value99032',
    'key79175': 'value31949',
},
    {
    'id': 17527488137198,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Dr. Jeffrey Morris',
    'address': '991 Moreno Viaduct\nWalterberg, WA 35166',
    'text': 'International local civil tough though begin back. Hand despite couple individual sea practice.',
    'email': 'mosskevin@example.com',
    'phone_number': '(767)678-5243',
    'json': {
    'name': 'Kristina Hawkins',
    'address': '917 Shannon Extension\nWest Nicole, MD 43130',
},
    'key49378': 'value90766',
    'key66074': 'value14982',
    'key71427': 'value75522',
},
    {
    'id': 17527488137210,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Jimmy Williams',
    'address': '0766 John Underpass Apt. 980\nSeanmouth, SC 44005',
    'text': 'Culture agree necessary Republican standard. Mouth task expect red. Return most receive traditional task technology.\nStatement also reality federal mother relate wrong. Gas herself act.',
    'email': 'derrick19@example.org',
    'phone_number': '(784)399-8335',
    'json': {
    'name': 'Susan Landry',
    'address': '799 Choi Burg\nMoorefurt, AL 27453',
},
    'key37389': 'value96937',
    'key13116': 'value1186',
    'key70077': 'value57802',
    'key96108': 'value63839',
    'key15672': 'value63378',
    'key84517': 'value96103',
    'key34174': 'value53049',
    'key3287': 'value56395',
    'key80360': 'value60211',
},
    {
    'id': 17527488137220,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Eric Hunter',
    'address': '0855 Pierce Coves Apt. 627\nLake Sherry, PW 11559',
    'text': 'Door several floor cultural nice who. We speech body. Treat smile once natural effort ten.',
    'email': 'fmonroe@example.com',
    'phone_number': '(381)691-5770',
    'json': {
    'name': 'Rachael Campbell',
    'address': '953 Natalie Heights Suite 122\nChambersfort, MD 14732',
},
    'key83947': 'value43282',
    'key55405': 'value68133',
    'key30537': 'value79990',
    'key24565': 'value46096',
    'key29502': 'value35025',
    'key77030': 'value92810',
    'key40359': 'value87876',
},
    {
    'id': 17527488137231,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Brian May',
    'address': 'Unit 8467 Box 1974\nDPO AE 33876',
    'text': 'Then themselves media Congress include. Ever anything her state look.\nSmile international left worker the ground event. Go tell goal language relationship.',
    'email': 'judithflores@example.net',
    'phone_number': '001-319-419-7863',
    'json': {
    'name': 'Kyle Mitchell',
    'address': '16346 Donald Wells\nGordontown, AK 11532',
},
    'key10965': 'value17520',
    'key91565': 'value61237',
    'key74234': 'value93054',
    'key7400': 'value67574',
    'key4682': 'value94258',
    'key84699': 'value28698',
},
    {
    'id': 17527488137241,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Charlotte Collins',
    'address': '483 Amanda Knolls\nKelseyhaven, OR 76225',
    'text': 'Future fine worry. Turn necessary wall guess idea them difference. Article form reach bed.',
    'email': 'bradleyholly@example.org',
    'phone_number': '001-469-845-3535x97942',
    'json': {
    'name': 'Jennifer Patterson',
    'address': '7935 Estrada Extension\nAshleybury, IA 60944',
},
    'key44185': 'value98392',
    'key2028': 'value33761',
    'key49725': 'value70138',
    'key55832': 'value85135',
},
    {
    'id': 17527488137252,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Edwin Baker',
    'address': '97733 Ruben Lock Apt. 413\nSouth Williambury, CA 52792',
    'text': 'Camera offer east. Strong most positive bag their. Believe social know finish seat side view civil.\nProve respond message.',
    'email': 'jimmy63@example.org',
    'phone_number': '630.952.1799x502',
    'json': {
    'name': 'Kathy Schroeder',
    'address': 'USS Keith\nFPO AP 27795',
},
    'key11243': 'value26545',
    'key3892': 'value59366',
    'key79494': 'value34384',
    'key44826': 'value19399',
    'key32954': 'value3465',
    'key94611': 'value16447',
    'key4987': 'value58903',
    'key17306': 'value41385',
    'key93810': 'value45786',
},
    {
    'id': 17527488137261,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Stephanie Downs',
    'address': '7941 Natalie Forge Suite 541\nNew Kaitlyn, NJ 86027',
    'text': 'Next bill law claim child meeting area. Anyone rather while discuss hand pressure respond.\nNor exist stay team land night building. Tree along such feeling.',
    'email': 'veronica18@example.net',
    'phone_number': '001-557-620-5207x73959',
    'json': {
    'name': 'David Parker',
    'address': '4592 Carolyn Plains\nSouth Theresaport, CT 27729',
},
    'key35928': 'value21801',
    'key70350': 'value3120',
    'key35649': 'value52339',
    'key16919': 'value36246',
    'key69760': 'value66367',
    'key21054': 'value50332',
    'key19466': 'value89417',
    'key524': 'value60186',
    'key50832': 'value82096',
    'key60608': 'value94229',
},
    {
    'id': 17527488137271,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Katherine Wood',
    'address': '9810 Nguyen Junctions Suite 281\nNew Jennifer, GA 71362',
    'text': 'Deep pull image rich necessary. Feel increase hand range maintain task. Size gun full become easy. Subject one war buy indicate season.',
    'email': 'hamptonpatricia@example.net',
    'phone_number': '(396)560-8765',
    'json': {
    'name': 'Lacey Sanders',
    'address': '98777 Joseph Views Suite 283\nNorth Rogermouth, OK 51428',
},
    'key66209': 'value51715',
    'key43403': 'value55643',
},
    {
    'id': 17527488137283,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Johnny Anderson',
    'address': '840 Joseph Causeway\nTaylorborough, OK 98751',
    'text': 'News article challenge lay sometimes cup represent organization. Outside religious analysis. Toward financial clearly forward ground teach participant.',
    'email': 'erikamccullough@example.net',
    'phone_number': '(222)333-7557',
    'json': {
    'name': 'Mary Gardner',
    'address': '87461 Hernandez Glen\nWilliamport, AS 08550',
},
    'key84576': 'value68965',
},
    {
    'id': 17527488137294,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Michael Scott',
    'address': '932 Sharp Path Apt. 981\nEast Suzanneside, MO 40011',
    'text': 'Environment soon return. Call my financial commercial value activity.\nOnce recently feeling hope. Center painting hear course final itself almost.',
    'email': 'fmorales@example.com',
    'phone_number': '300-304-9967x33214',
    'json': {
    'name': 'Jonathan Gray',
    'address': '142 Lawrence Street\nEast Brianfurt, VT 18442',
},
    'key64459': 'value34041',
    'key42296': 'value79936',
    'key25665': 'value9898',
},
    {
    'id': 17527488137305,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Samantha Richards',
    'address': '59188 Benjamin Park Apt. 539\nSusanhaven, MS 52661',
    'text': 'More expect later account day step. Foot minute like take run crime.\nOut cause former person baby. Up animal true tonight.',
    'email': 'westjennifer@example.com',
    'phone_number': '(858)327-7958',
    'json': {
    'name': 'Kendra Moore',
    'address': '542 Hoffman Lock Apt. 290\nMartinezmouth, CO 45688',
},
    'key93918': 'value12911',
    'key9010': 'value65501',
    'key55778': 'value87159',
    'key56660': 'value52249',
    'key91041': 'value14686',
    'key74650': 'value73889',
},
    {
    'id': 17527488137317,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Jennifer Hoover',
    'address': 'USNV Mccarthy\nFPO AA 65183',
    'text': 'Form change fine sort. Move can actually method big either rock. Word benefit method attention decision.',
    'email': 'herrerachristian@example.com',
    'phone_number': '+1-957-744-5539x7258',
    'json': {
    'name': 'Tricia Murphy',
    'address': '06796 Rodriguez Lake\nCollinfort, WV 38248',
},
    'key24298': 'value7423',
    'key31201': 'value25185',
    'key93462': 'value24048',
    'key19413': 'value13991',
    'key49844': 'value85281',
    'key26865': 'value8804',
    'key90175': 'value39220',
    'key10173': 'value76551',
    'key12378': 'value414',
    'key41796': 'value34630',
},
    {
    'id': 17527488137328,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Kenneth Rivera',
    'address': '72279 Hernandez Tunnel\nNorth Tyler, ND 47851',
    'text': 'Before after your coach some better attention put. Treatment that minute rock find.\nAct wait year how threat machine myself. Score left space we.',
    'email': 'hannah99@example.org',
    'phone_number': '868-375-8819x3067',
    'json': {
    'name': 'Jean Reid',
    'address': '04298 Dillon Falls Apt. 698\nYolandamouth, AR 94185',
},
    'key81169': 'value56127',
    'key41682': 'value38427',
    'key29531': 'value37241',
    'key93768': 'value9781',
},
    {
    'id': 17527488137339,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Miguel Perkins',
    'address': '225 Murray Prairie Suite 648\nSouth Wendy, CA 34955',
    'text': 'Human far away space focus just. Red sing then analysis. Hundred themselves learn phone concern heavy.',
    'email': 'michael62@example.com',
    'phone_number': '001-860-561-1928x0325',
    'json': {
    'name': 'Heather Foster',
    'address': '4804 Acosta Grove\nLake Brittany, DE 33298',
},
    'key56643': 'value11331',
    'key38898': 'value51837',
    'key68664': 'value33897',
    'key67105': 'value63149',
    'key51928': 'value85703',
    'key44884': 'value2573',
    'key71926': 'value80146',
},
    {
    'id': 17527488137349,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'William Glover',
    'address': 'USNV Booth\nFPO AP 05227',
    'text': 'Play participant religious standard senior happen. Room reflect special. Lot citizen perhaps picture. Product nothing only.\nCan night including production.',
    'email': 'lstuart@example.org',
    'phone_number': '6498396302',
    'json': {
    'name': 'Beverly Spencer',
    'address': '896 Martin Plains\nByrdbury, IA 62948',
},
    'key24509': 'value49392',
    'key99952': 'value88848',
    'key6864': 'value80457',
},
    {
    'id': 17527488137359,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Michelle Maxwell',
    'address': '6666 Warren Loaf\nSarahstad, ME 51308',
    'text': 'Recent together should song teacher father something tough. Individual democratic during recognize soon.\nListen president individual two popular yes. May make seat floor.',
    'email': 'gonzalezlauren@example.org',
    'phone_number': '001-218-218-4840x0401',
    'json': {
    'name': 'Christina Colon',
    'address': '725 Frazier Canyon\nJenniferside, CT 58833',
},
    'key60231': 'value932',
    'key3865': 'value83966',
    'key53417': 'value29076',
    'key11773': 'value39010',
    'key66761': 'value33338',
    'key52685': 'value33469',
    'key82251': 'value25894',
    'key20665': 'value2105',
},
    {
    'id': 17527488137371,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Chad Marsh',
    'address': '741 Williams Crescent\nEast Craig, VA 30326',
    'text': 'Whose attorney before fund. White employee ok energy somebody loss pick. Hotel current item pattern.\nWeek head perhaps. More break benefit.',
    'email': 'jenkinsamanda@example.com',
    'phone_number': '804-396-8538x154',
    'json': {
    'name': 'Kathy Burton',
    'address': '99041 Hernandez Stream Apt. 019\nShortside, WV 56016',
},
    'key66676': 'value60381',
    'key75682': 'value20681',
    'key43877': 'value35387',
    'key34905': 'value10559',
},
    {
    'id': 17527488137383,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Steven Johnson',
    'address': 'Unit 2488 Box 9129\nDPO AP 58343',
    'text': 'Wish image without score idea there fear. Court rock risk.\nReligious specific cell may east. Certainly certainly thus cell.',
    'email': 'curtiswarren@example.com',
    'phone_number': '001-974-870-7433x94822',
    'json': {
    'name': 'Katherine Mason',
    'address': '90217 Christopher Ridges Suite 765\nPort Jamesfort, MH 09564',
},
    'key72235': 'value36354',
    'key30947': 'value1095',
    'key85182': 'value40498',
    'key26895': 'value88431',
    'key35275': 'value34895',
    'key15606': 'value17108',
    'key58829': 'value93429',
    'key1672': 'value61075',
},
    {
    'id': 17527488137393,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Ethan Gordon',
    'address': '604 Schwartz Ville\nNorth Stephenmouth, WA 51206',
    'text': 'Mr anyone side kitchen cell. Picture movie center seat as few.',
    'email': 'victoriajackson@example.org',
    'phone_number': '224-570-4937x4874',
    'json': {
    'name': 'Jeremy Washington',
    'address': '089 Mclaughlin Key\nLake Jose, AL 69773',
},
    'key87794': 'value35166',
    'key40427': 'value49959',
    'key98425': 'value64359',
    'key82701': 'value62145',
},
    {
    'id': 17527488137403,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Jason Vasquez',
    'address': '3883 Andersen Trail Apt. 905\nNew James, OK 39102',
    'text': 'Strategy book nation minute glass administration too. Possible value than newspaper economy kitchen. Heart consider responsibility alone beautiful.\nThat them memory. Education pressure skill current.',
    'email': 'saradavis@example.com',
    'phone_number': '+1-543-629-0253x33629',
    'json': {
    'name': 'Becky Roberts MD',
    'address': '26773 Cook Street Suite 917\nPort Matthew, MH 12924',
},
    'key66382': 'value96917',
    'key31756': 'value73709',
    'key73746': 'value94774',
    'key49102': 'value5796',
    'key33824': 'value47587',
    'key43337': 'value89442',
},
    {
    'id': 17527488137415,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Anna Day',
    'address': '7634 George Avenue\nLindseyfort, MN 56517',
    'text': 'Recent forward bring. Memory structure avoid government day.',
    'email': 'zheath@example.com',
    'phone_number': '001-520-907-4561x3807',
    'json': {
    'name': 'Christy Dickson',
    'address': '32813 Young Meadows\nPort Christineburgh, MD 45537',
},
    'key6789': 'value45872',
    'key58497': 'value51473',
    'key29398': 'value45864',
    'key82130': 'value85956',
    'key47130': 'value58270',
    'key48739': 'value65715',
    'key97538': 'value26747',
    'key28539': 'value6268',
},
    {
    'id': 17527488137425,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Patrick Moore',
    'address': 'USCGC Gonzalez\nFPO AP 17772',
    'text': 'Girl discuss degree low. Film face great TV quality. Human out too education way. Beyond true article still letter vote control.\nRaise pattern adult believe. Off family develop role ago.',
    'email': 'danielle44@example.com',
    'phone_number': '(807)215-3054',
    'json': {
    'name': 'Sherri Horton',
    'address': '89554 Madeline Station Suite 177\nJasonview, SC 84110',
},
    'key82886': 'value95602',
    'key64730': 'value78419',
    'key27129': 'value33538',
    'key39348': 'value85881',
    'key35375': 'value76152',
    'key34177': 'value85246',
    'key90041': 'value44810',
    'key44871': 'value8119',
    'key21935': 'value27230',
},
    {
    'id': 17527488137435,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Michael Stewart',
    'address': '87741 Cabrera Springs Suite 650\nBeckfort, AR 66050',
    'text': 'Wish life movement edge successful. Receive last environmental scientist parent down table. Attention hard in most avoid policy.',
    'email': 'troy44@example.com',
    'phone_number': '001-623-250-0925x919',
    'json': {
    'name': 'Jody Gordon',
    'address': '657 Mandy Haven Suite 247\nAngelmouth, UT 87911',
},
    'key84679': 'value21361',
    'key17533': 'value93783',
    'key85856': 'value98099',
    'key16812': 'value77467',
},
    {
    'id': 17527488137445,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Sarah Contreras',
    'address': '7036 Jacob Vista Apt. 534\nKylemouth, NJ 56420',
    'text': 'Religious she hear remain act. End class rich sister. Only tend wrong perform. Control green hard exist like but some.',
    'email': 'usexton@example.com',
    'phone_number': '635-299-4063',
    'json': {
    'name': 'George Smith',
    'address': '478 Sandra Plain\nJeffview, AR 49138',
},
    'key96476': 'value33871',
    'key45565': 'value18057',
    'key11257': 'value68085',
    'key80951': 'value33016',
},
    {
    'id': 17527488137456,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Amanda Wood',
    'address': '272 Evans Stravenue\nSimpsonport, UT 26915',
    'text': 'Generation away modern attention course. Room some relate short. Expect could key item deep staff rate. Whom century Congress likely scene write tonight.',
    'email': 'johnherrera@example.com',
    'phone_number': '+1-448-329-2953',
    'json': {
    'name': 'Stacey Robbins',
    'address': '1970 Hannah Drive\nLeeberg, CA 49978',
},
    'key76242': 'value31654',
    'key17940': 'value62194',
},
    {
    'id': 17527488137467,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Jacob Travis',
    'address': '755 Alexander Alley\nEast Josephchester, MD 78824',
    'text': 'Meet quickly sing imagine customer feeling put. Rate friend watch remember people state southern. Property value car teach property around food.\nFund score other common safe. In short past indeed.',
    'email': 'victoria94@example.org',
    'phone_number': '(433)896-4869x3096',
    'json': {
    'name': 'Nina Mccoy',
    'address': '06236 Hunt Loaf Apt. 033\nKellymouth, GU 81059',
},
    'key98459': 'value54287',
    'key48878': 'value79806',
    'key55598': 'value61135',
},
    {
    'id': 17527488137479,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Sarah Adams',
    'address': '80046 Rogers Glens Suite 682\nWest James, PR 69084',
    'text': 'Prove so start find product expert. Blue significant possible seat.\nDiscover effort little return. Position one practice drop when process option.',
    'email': 'robertswilliam@example.com',
    'phone_number': '919-720-6240',
    'json': {
    'name': 'Alexander Nelson',
    'address': 'Unit 9484 Box 3185\nDPO AP 21628',
},
    'key30293': 'value50658',
    'key37242': 'value87586',
    'key39857': 'value72862',
    'key11649': 'value58674',
    'key98930': 'value13821',
    'key47549': 'value72712',
    'key26033': 'value55924',
    'key42024': 'value29791',
},
    {
    'id': 17527488137488,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Jane Ramirez',
    'address': '5864 Edwards Mountain\nWilliamton, RI 14707',
    'text': 'Range son continue. Next own meet per southern want professor.\nStill similar news in. Likely ready recognize federal. Company begin feeling painting. Even fear expect evening film say.',
    'email': 'krausebrent@example.com',
    'phone_number': '+1-282-640-7885',
    'json': {
    'name': 'Scott Jimenez',
    'address': '5997 Eddie Camp\nWest Laurenville, OR 80544',
},
    'key36535': 'value1511',
    'key36420': 'value46170',
    'key6248': 'value28750',
    'key9725': 'value92513',
    'key73338': 'value29938',
    'key8585': 'value6083',
    'key68187': 'value35597',
    'key52337': 'value23458',
    'key59664': 'value43326',
    'key5515': 'value36445',
},
    {
    'id': 17527488137499,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Sabrina Collins',
    'address': '514 Alicia Ferry Apt. 660\nLake Laurastad, MI 39742',
    'text': 'Few quickly deep. Subject material fill city. Light arrive house dog.\nBeyond above situation wall. Nation nice account to space. Road response with.',
    'email': 'erinwhite@example.org',
    'phone_number': '943-374-6389',
    'json': {
    'name': 'Julie Jones',
    'address': '72024 Davis Park Apt. 022\nTroyshire, NY 23896',
},
    'key18714': 'value68023',
    'key69314': 'value14537',
    'key61147': 'value26054',
    'key67308': 'value35917',
    'key2817': 'value88368',
    'key73201': 'value11283',
    'key50658': 'value75696',
    'key78863': 'value39480',
},
    {
    'id': 17527488137511,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Rebecca Diaz',
    'address': '6319 Villanueva Green Apt. 928\nLake Michelle, MN 62433',
    'text': 'Game in investment itself. Whose perhaps also sport live.\nTonight need claim purpose various despite material. Finally face determine could later suffer. Low hand similar would will none meeting.',
    'email': 'howellrachel@example.com',
    'phone_number': '3358550092',
    'json': {
    'name': 'Steven Combs',
    'address': 'Unit 1272 Box 2113\nDPO AP 18258',
},
    'key80858': 'value36399',
    'key47537': 'value89384',
    'key36720': 'value15412',
    'key43830': 'value98868',
    'key78539': 'value10965',
},
    {
    'id': 17527488137521,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Cynthia Snyder',
    'address': '28611 Fernandez Shoals Apt. 662\nWrightbury, ME 27555',
    'text': 'Investment group expect vote. Issue garden effort focus reflect available evening. Better tell cut police. Fine difficult positive personal avoid actually.',
    'email': 'zlogan@example.net',
    'phone_number': '+1-753-480-1819x14785',
    'json': {
    'name': 'Candice Brown',
    'address': '2592 Garcia Mountain\nPetersfurt, KS 34206',
},
    'key63145': 'value7233',
    'key78394': 'value68463',
    'key8680': 'value17132',
    'key2481': 'value6367',
    'key94119': 'value87322',
},
    {
    'id': 17527488137532,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Emily Lee',
    'address': '476 Morgan Ways Suite 553\nNew Paulborough, MD 90958',
    'text': 'Ago produce shake begin painting. Attention kind movement our memory.',
    'email': 'ocampbell@example.com',
    'phone_number': '001-297-341-8660x543',
    'json': {
    'name': 'Thomas Banks',
    'address': 'Unit 9477 Box 8089\nDPO AA 08835',
},
    'key17453': 'value57985',
    'key14039': 'value67173',
    'key55951': 'value3981',
},
    {
    'id': 17527488137540,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Patricia Brown',
    'address': '9754 John Road\nNorth Michealside, NJ 77049',
    'text': 'American all society dog care show national. Think ok southern help discuss no.\nCar soldier best pay shake study spend leg. Technology like player meeting six ahead it.',
    'email': 'kwade@example.org',
    'phone_number': '523-759-6362x80564',
    'json': {
    'name': 'Jennifer Thompson',
    'address': '5892 Peterson Cliff Apt. 303\nChristinafort, IA 56398',
},
    'key21027': 'value77317',
    'key64103': 'value12295',
    'key36338': 'value88519',
    'key45327': 'value11916',
},
    {
    'id': 17527488137551,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Manuel Orozco',
    'address': '63008 Melissa Pines\nNorth Tyler, OR 67467',
    'text': 'Late whole skin specific. Begin summer keep per.\nCost go quite mission. Energy speak very yard thus green spend.',
    'email': 'lcortez@example.net',
    'phone_number': '(955)626-7222x151',
    'json': {
    'name': 'Spencer Flores',
    'address': '7663 Stacy Trafficway Suite 691\nGarytown, NC 75349',
},
    'key35360': 'value13802',
},
    {
    'id': 17527488137562,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Brent Smith',
    'address': '523 Kevin Drive Apt. 177\nNorth Christopherbury, ND 54037',
    'text': 'Who pretty bad ability form. Example face writer.\nMr least chair image energy probably. May build now instead buy another.',
    'email': 'conniebennett@example.com',
    'phone_number': '001-913-967-8304x89523',
    'json': {
    'name': 'Chase Gregory',
    'address': '596 Davidson Union Apt. 635\nMarisachester, GU 82444',
},
    'key16358': 'value20878',
    'key93790': 'value63800',
},
    {
    'id': 17527488137573,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Sara Cowan',
    'address': 'USS Robinson\nFPO AE 82793',
    'text': 'Director young close trouble remain reason before window. Commercial leg clearly all red know.\nSomething after more thought nothing answer use.',
    'email': 'reneemills@example.com',
    'phone_number': '(280)865-1903x28768',
    'json': {
    'name': 'James Gibson',
    'address': '64926 Melinda Station\nNatalieside, NV 22254',
},
    'key66484': 'value34027',
    'key59081': 'value9387',
    'key86661': 'value48230',
    'key2903': 'value63108',
    'key79962': 'value77269',
    'key93418': 'value63752',
    'key44216': 'value72475',
    'key66139': 'value79265',
},
    {
    'id': 17527488137584,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Gabriel Ballard',
    'address': '6481 Watkins Brooks Suite 253\nSierraview, MP 15894',
    'text': 'After three full measure weight. Some really follow page which watch million. With good improve follow long technology simple interview.',
    'email': 'dyerpaula@example.com',
    'phone_number': '(205)374-0493x5743',
    'json': {
    'name': 'Cheryl Jenkins',
    'address': '5015 Melissa Road\nNorth Tracymouth, MH 79467',
},
    'key27131': 'value95033',
    'key82746': 'value29150',
    'key35751': 'value65132',
    'key42572': 'value81384',
    'key78572': 'value67385',
    'key1536': 'value68810',
    'key99019': 'value35003',
    'key74686': 'value41437',
    'key41309': 'value26375',
},
    {
    'id': 17527488137596,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Nicole Dean',
    'address': '43873 Tran Mountains\nWest Matthewburgh, WY 01074',
    'text': 'Seat later serious meeting everybody protect particularly note. Door increase nation role clear someone.\nPolice first easy hand its receive laugh.',
    'email': 'justinrodgers@example.com',
    'phone_number': '+1-831-998-3177',
    'json': {
    'name': 'David Whitney',
    'address': '811 Edwards Parkway\nEast Kayla, NY 41428',
},
    'key97728': 'value91249',
},
    {
    'id': 17527488137607,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Mackenzie Moore',
    'address': '97289 Rachel Passage\nCherylland, FM 76564',
    'text': 'Growth people wish ability certainly few. Actually early decide head report.\nBudget artist respond culture. Trip surface some activity data return degree. Right opportunity number.',
    'email': 'guerrajose@example.net',
    'phone_number': '407-789-5523x41607',
    'json': {
    'name': 'Miranda Miller',
    'address': '824 Hill Plaza\nWest Traceybury, CT 47498',
},
    'key20156': 'value84413',
    'key33233': 'value35672',
    'key57925': 'value96587',
    'key30398': 'value47834',
    'key61808': 'value85093',
},
    {
    'id': 17527488137619,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Stephen Barnes',
    'address': 'PSC 5706, Box 8631\nAPO AP 62445',
    'text': 'Outside food middle there could material how article. Even none weight probably out. Citizen short attention billion process recently from.',
    'email': 'jamesromero@example.org',
    'phone_number': '+1-466-480-2168',
    'json': {
    'name': 'Travis Perry',
    'address': '7546 Hernandez Shore\nNew Austin, NH 81207',
},
    'key60394': 'value11390',
    'key76808': 'value96383',
    'key54242': 'value32929',
    'key56931': 'value50023',
    'key33197': 'value47356',
    'key9299': 'value29076',
    'key69502': 'value55649',
    'key14741': 'value75068',
    'key32758': 'value14837',
    'key23398': 'value6227',
},
    {
    'id': 17527488137628,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Phillip Johnson',
    'address': '39739 Jasmine Turnpike\nPort Scott, IL 36078',
    'text': 'Yeah glass then herself. Middle serve none pressure. East official stock interview.\nFire decade sure force staff explain series generation. Collection while any sort item adult.\nNear but cut foreign.',
    'email': 'kcollins@example.com',
    'phone_number': '867-447-1907x5542',
    'json': {
    'name': 'Amanda Franco',
    'address': '225 Nunez Harbor Apt. 070\nNorth Jillchester, NC 36480',
},
    'key95509': 'value86461',
    'key58943': 'value24638',
    'key89085': 'value3114',
},
    {
    'id': 17527488137639,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Susan Kline',
    'address': '814 Angela View Suite 121\nHoltport, CT 91929',
    'text': 'Small stand since fight sense care although. American job human computer perhaps finally test. Back American grow cultural.\nDoor follow star process hospital.',
    'email': 'robertsonrichard@example.net',
    'phone_number': '451-292-0414',
    'json': {
    'name': 'Melissa Wolf',
    'address': '14936 Cabrera Cliffs Suite 309\nPort Tyler, PR 89010',
},
    'key29488': 'value36909',
    'key70500': 'value82246',
    'key61260': 'value55877',
    'key89804': 'value91281',
    'key39422': 'value23903',
},
    {
    'id': 17527488137651,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Joseph King',
    'address': '596 Haas Heights Apt. 457\nLake Williamshire, GA 97682',
    'text': 'Yourself question news dark prepare growth raise. South note science cut effort whole. Scene others likely hand compare never.',
    'email': 'eadams@example.com',
    'phone_number': '608.374.7655x648',
    'json': {
    'name': 'Timothy Taylor',
    'address': '3740 Reynolds Forge\nSouth Nicole, MD 05905',
},
    'key28878': 'value38936',
    'key99452': 'value49180',
    'key94853': 'value79042',
    'key97102': 'value7030',
    'key99997': 'value10284',
    'key419': 'value88152',
    'key56909': 'value27598',
    'key55081': 'value38755',
    'key29356': 'value18770',
},
    {
    'id': 17527488137662,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Richard Jones',
    'address': '10224 Krueger Estates\nSouth Shannon, MO 05922',
    'text': 'Thank somebody later. Officer thank who bag concern.\nFight hospital realize both old gas politics. City Mr cover example.',
    'email': 'robertsonstephanie@example.org',
    'phone_number': '2037508906',
    'json': {
    'name': 'John Aguilar',
    'address': '9424 Steele Viaduct Suite 858\nCodyfort, WI 67201',
},
    'key3108': 'value2448',
    'key19243': 'value14923',
    'key38682': 'value95400',
    'key45463': 'value20148',
    'key88494': 'value69513',
    'key18605': 'value63417',
    'key72052': 'value71552',
    'key33076': 'value32416',
    'key34417': 'value82870',
},
    {
    'id': 17527488137674,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Daniel Quinn',
    'address': '54295 Kristin Harbor\nNorth Mark, PA 19271',
    'text': 'Affect increase out. Must forget Congress stage real side offer. Five rest believe stand however former. Too season suffer our onto.',
    'email': 'janet50@example.com',
    'phone_number': '+1-355-394-0544',
    'json': {
    'name': 'Gilbert Wallace',
    'address': '2726 Bryce Stream Suite 101\nNicoleborough, AZ 37680',
},
    'key12663': 'value49995',
    'key10158': 'value22198',
    'key7269': 'value63292',
    'key39062': 'value21373',
    'key92574': 'value74842',
    'key24863': 'value68155',
    'key9765': 'value8170',
    'key46170': 'value99976',
    'key25873': 'value42923',
    'key53926': 'value19501',
},
    {
    'id': 17527488137685,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Jennifer Thompson',
    'address': '482 Shepherd Shoals\nLake Johnside, AR 31309',
    'text': 'Create music charge successful never five or. Behavior thought early safe sort. Suddenly street country forward now cover.\nMother relate car seven. Set hotel produce down company.',
    'email': 'xrobertson@example.net',
    'phone_number': '+1-739-788-4744x947',
    'json': {
    'name': 'Edgar Morrison',
    'address': '592 Robert Bypass\nWest Tasha, FL 05209',
},
    'key38908': 'value62214',
    'key64702': 'value86141',
    'key1307': 'value12567',
    'key22706': 'value45312',
    'key656': 'value76900',
    'key18537': 'value21942',
},
    {
    'id': 17527488137696,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Veronica Hunt',
    'address': '7713 Campbell Skyway\nDavidfurt, NE 47555',
    'text': 'Successful whole surface American agree. Message the start national. Attack someone environmental after toward. Total agreement your price force.',
    'email': 'kim49@example.com',
    'phone_number': '269.663.9282',
    'json': {
    'name': 'Kurt Yu',
    'address': '804 Dawn Brook\nWest Codyville, FL 87664',
},
    'key41163': 'value46640',
},
    {
    'id': 17527488137706,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Nicholas Armstrong',
    'address': '6496 Lauren Ports\nLopezfurt, FL 57027',
    'text': 'Candidate court pull want policy official. Defense probably authority peace. Stage than already owner environmental.',
    'email': 'chapmanjustin@example.org',
    'phone_number': '(918)324-8947x05951',
    'json': {
    'name': 'Jeffrey Bryant',
    'address': '108 Jennifer Corners Apt. 259\nHerreratown, CO 81174',
},
    'key76053': 'value64988',
    'key54211': 'value70195',
    'key15161': 'value86047',
    'key34690': 'value25167',
    'key66514': 'value60304',
    'key88865': 'value93676',
    'key38860': 'value74819',
    'key78809': 'value57202',
},
    {
    'id': 17527488137718,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Joe Arnold',
    'address': '770 Emily Crossroad\nJenkinston, OH 87864',
    'text': 'Position lot own beautiful all. State with end station type else mother.\nUntil drive all news win see yeah. Rule decision purpose side record across cut.',
    'email': 'cristian56@example.net',
    'phone_number': '6559957231',
    'json': {
    'name': 'Brittany Weaver',
    'address': '12259 Jeanette Stravenue Suite 907\nFergusonfort, WA 25180',
},
    'key59826': 'value2845',
    'key77599': 'value62697',
    'key23806': 'value72782',
    'key40526': 'value5090',
    'key59495': 'value64841',
    'key59070': 'value7643',
    'key85321': 'value23335',
},
    {
    'id': 17527488137729,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Jeremy Mills',
    'address': '7572 Allen Pine Suite 504\nPort Robertland, MA 20767',
    'text': 'Few PM past central thousand why voice. Down sort research. Organization live bad.\nExecutive mind car much experience. Again attention amount service.',
    'email': 'garciamarcus@example.org',
    'phone_number': '+1-812-682-4843x77904',
    'json': {
    'name': 'Stanley Harrell',
    'address': 'Unit 3346 Box 8300\nDPO AP 76734',
},
    'key48862': 'value68240',
    'key31869': 'value26086',
    'key88639': 'value43028',
    'key14989': 'value8169',
    'key67088': 'value3580',
},
],
}
        
        if not original_content:
            logger.info("请求无内容，跳过变异测试")
            return True
        
        # 定义发送请求的函数
        def send_mutated_request(mutated_content):
            return send_request(mutated_content, method, url_path, headers)
        
        logger.info("开始变异测试...")
        
        # 获取命令行参数
        iterations = getattr(args, 'iterations', 200)  # 默认值为200
        time_limit = getattr(args, 'time_limit', 10)   # 默认值为10分钟
                    
        mutator = Mutator()  # 创建变异器实例
        failures = mutator.normal_mutate(
            original_content=original_content,
            send_request=send_mutated_request,
            connectivity_check_func=check_connectivity,
            save_failure_func=save_failure,
            max_time_minutes=time_limit,  # 使用上面设置的time_limit变量
            max_iterations=iterations     # 使用上面设置的iterations变量
        )
        
        if failures:
            logger.warning(f"发现 {len(failures)} 个导致异常的变异")
        else:
            logger.info("变异测试未发现异常")
        
        return len(failures) == 0



    def test_request_3(self):
        """测试请求 3 - POST http://172.17.0.5:23210/v2/vectordb/entities/query"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/query")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/query'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '6817ccbe-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_07_626693Sptibfvq',
    'filter': 'uid >= 0',
    'limit': 100,
    'offset': 0,
    'outputFields': [
    'name',
    'text',
    'id',
    'phone_number',
    'email',
    'uid',
    'address',
    'vector',
    'json',
],
}
        
        if not original_content:
            logger.info("请求无内容，跳过变异测试")
            return True
        
        # 定义发送请求的函数
        def send_mutated_request(mutated_content):
            return send_request(mutated_content, method, url_path, headers)
        
        logger.info("开始变异测试...")
        
        # 获取命令行参数
        iterations = getattr(args, 'iterations', 200)  # 默认值为200
        time_limit = getattr(args, 'time_limit', 10)   # 默认值为10分钟
                    
        mutator = Mutator()  # 创建变异器实例
        failures = mutator.normal_mutate(
            original_content=original_content,
            send_request=send_mutated_request,
            connectivity_check_func=check_connectivity,
            save_failure_func=save_failure,
            max_time_minutes=time_limit,  # 使用上面设置的time_limit变量
            max_iterations=iterations     # 使用上面设置的iterations变量
        )
        
        if failures:
            logger.warning(f"发现 {len(failures)} 个导致异常的变异")
        else:
            logger.info("变异测试未发现异常")
        
        return len(failures) == 0



    def test_request_4(self):
        """测试请求 4 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '6817ccbe-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_40_07_626693Sptibfvq',
    'dimension': 128,
    'metricType': 'L2',
    'description': 'test collection',
    'primaryField': 'id',
    'vectorField': 'vector',
    'params': {
    'consistencyLevel': 'Strong',
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid >= 0]_1752748820.json')
    parser.add_argument('-t', '--target', type=str, default=TARGET_URL,
                        help='目标服务器URL，例如: http://localhost:6333')
    parser.add_argument('-o', '--output-dir', type=str, default=OUTPUT_DIR,
                        help='测试结果输出目录')
    parser.add_argument('-n', '--iterations', type=int, default=200,
                        help='变异测试的最大迭代次数')
    parser.add_argument('-l', '--time-limit', type=int, default=10,
                        help='变异测试的时间限制(分钟)')
    args = parser.parse_args()
    
    # 更新全局变量
    if args.target:
        TARGET_URL = args.target
    if args.output_dir:
        OUTPUT_DIR = args.output_dir
    
    # 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 实例化测试类并运行测试
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrueUid01752748820Json()
    test.run_tests()
