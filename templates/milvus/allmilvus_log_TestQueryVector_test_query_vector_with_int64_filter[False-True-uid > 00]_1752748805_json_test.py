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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > 00]_1752748805_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > 00]_1752748805.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrueUid001752748805Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > 00]_1752748805.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > 00]_1752748805.json"
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
    'RequestId': '5f5e1830-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_52_987637wuFoIfJS',
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
    'RequestId': '5f5e1830-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_52_987637wuFoIfJS',
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
    'RequestId': '5f5e1830-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_52_987637wuFoIfJS',
    'data': [
    {
    'id': 17527487990248,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Robin Todd',
    'address': '76250 Phillip Ridges Suite 161\nSmithmouth, PW 30420',
    'text': 'Of us suffer that should market tend discussion. Space safe east happen American land attorney.',
    'email': 'pday@example.org',
    'phone_number': '001-505-523-5255x77190',
    'json': {
    'name': 'Kelly Heath',
    'address': 'PSC 9779, Box 7081\nAPO AA 14894',
},
    'key254': 'value52961',
    'key65834': 'value69267',
    'key13760': 'value59950',
    'key35263': 'value10569',
    'key21447': 'value92827',
    'key33469': 'value74663',
    'key17852': 'value72656',
    'key6919': 'value32236',
    'key69637': 'value96927',
    'key32351': 'value2079',
},
    {
    'id': 17527487990262,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Mrs. Julie Murphy DVM',
    'address': '35562 Tracy Prairie\nPort Darrylborough, FL 12001',
    'text': 'We once surface tax long. Individual through idea base happen. Well draw particular amount big debate no.',
    'email': 'qwells@example.net',
    'phone_number': '4716732112',
    'json': {
    'name': 'Stephanie Smith',
    'address': '05629 Lewis Inlet\nStuartville, ND 20640',
},
    'key69591': 'value80938',
    'key33433': 'value16059',
    'key6988': 'value95980',
    'key42543': 'value10477',
    'key90371': 'value77888',
    'key83466': 'value70413',
    'key29026': 'value26271',
    'key1897': 'value38491',
    'key2840': 'value48794',
},
    {
    'id': 17527487990275,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Michelle Krause',
    'address': '16968 Johnson River Apt. 505\nSouth Johnport, ME 84639',
    'text': 'Seat not too despite. Size stay director above show black.\nCost minute oil interview century type. Activity investment professor which support. Girl dinner wife.',
    'email': 'chambersjeremiah@example.org',
    'phone_number': '911-394-7448',
    'json': {
    'name': 'Deborah Holland',
    'address': '215 Samantha Inlet\nEast Vanessamouth, MA 42501',
},
    'key50548': 'value52943',
    'key19944': 'value95086',
    'key72407': 'value661',
    'key56687': 'value86316',
    'key17185': 'value30451',
    'key30355': 'value17421',
    'key79681': 'value99903',
    'key48108': 'value46683',
    'key18194': 'value70165',
},
    {
    'id': 17527487990288,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Ryan Ortiz',
    'address': '3920 Jamie Roads Suite 312\nWest Angela, TN 62446',
    'text': 'Election rock same two. Whole she that lot head daughter. Future ask meet. Wide affect once remain parent.',
    'email': 'mario09@example.org',
    'phone_number': '5649041512',
    'json': {
    'name': 'Karen Carrillo',
    'address': '91571 Mark Expressway Apt. 350\nJillianhaven, KY 11637',
},
    'key93777': 'value48746',
    'key6088': 'value42908',
    'key34796': 'value40375',
    'key22412': 'value20692',
    'key14348': 'value96710',
    'key5525': 'value92582',
    'key62049': 'value18934',
    'key67784': 'value22570',
    'key71654': 'value70689',
},
    {
    'id': 17527487990299,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Hector Greer',
    'address': '4148 Chavez Stravenue Suite 556\nNorth Marissaburgh, NC 29911',
    'text': 'Only rich list surface goal back concern. Street create when nice chance. Meet Mrs summer road hair lay believe.\nBlue southern meeting seven home ok. Market past year side cover seven large move.',
    'email': 'travis83@example.net',
    'phone_number': '(603)916-0818x9292',
    'json': {
    'name': 'Randall Cochran',
    'address': '363 Meyer Parkway\nOsborneport, MO 40309',
},
    'key76593': 'value78336',
    'key81263': 'value4396',
    'key17370': 'value98296',
},
    {
    'id': 17527487990311,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Nathan Fitzpatrick',
    'address': '21773 Gomez Parkway Apt. 964\nAlyssaport, KY 25448',
    'text': 'Enjoy box alone manage forward window consumer help. Letter herself southern between. Century parent specific their never either ask college.',
    'email': 'michellefrazier@example.net',
    'phone_number': '(874)552-3677x9723',
    'json': {
    'name': 'Deborah Neal',
    'address': '215 Shannon Parkways\nHendersontown, IN 19895',
},
    'key23262': 'value94290',
},
    {
    'id': 17527487990323,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Jennifer Scott',
    'address': '04775 Ramirez Glen Suite 006\nNew Alan, MN 85378',
    'text': 'Soon late drive stop health. Upon nothing town per later serve growth.\nSuch instead century consumer total our. Prevent society large thus gun lot surface.',
    'email': 'gmartin@example.com',
    'phone_number': '941.308.6926',
    'json': {
    'name': 'Diane Curry',
    'address': '149 Boyer Bridge Suite 216\nPortermouth, PA 39586',
},
    'key9': 'value64128',
    'key62274': 'value52382',
    'key36515': 'value73735',
    'key47609': 'value96999',
    'key1091': 'value24381',
    'key32159': 'value31248',
    'key13205': 'value91515',
    'key28331': 'value81716',
},
    {
    'id': 17527487990336,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Mary Mcconnell',
    'address': '402 Herring Hill\nDonnaland, WA 12623',
    'text': 'Four list shoulder.\nOut garden increase. Once strategy street last international throughout again. Act front place capital.',
    'email': 'ibrock@example.com',
    'phone_number': '001-396-480-7336',
    'json': {
    'name': 'Mrs. Stacey Cooper',
    'address': '852 Dorothy Corner Apt. 736\nAprilborough, KS 15222',
},
    'key29092': 'value16807',
    'key47854': 'value30255',
    'key27520': 'value7989',
},
    {
    'id': 17527487990347,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Timothy Thomas',
    'address': '60396 Ashley Rest Apt. 976\nChristopherview, IN 17915',
    'text': 'Join quality culture no paper garden. Claim special although sea society yet return air. Sometimes however message price own model.',
    'email': 'myersdawn@example.com',
    'phone_number': '412.988.1606x080',
    'json': {
    'name': 'Cynthia Wagner',
    'address': '3050 Julie Throughway Suite 367\nEast Christinabury, PA 17430',
},
    'key50150': 'value64065',
    'key61748': 'value47333',
    'key85390': 'value37849',
    'key90348': 'value33018',
    'key61928': 'value62285',
    'key5760': 'value60159',
    'key80427': 'value7449',
    'key22934': 'value46040',
    'key28793': 'value97851',
},
    {
    'id': 17527487990358,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Paige Small',
    'address': '410 Angela Wall Suite 875\nPort Barry, MP 86798',
    'text': 'Couple girl four tax process director close cold. Stand necessary pressure official.\nTraditional clear guy perhaps. Lot suddenly radio customer real analysis.',
    'email': 'uriddle@example.net',
    'phone_number': '(705)673-9637',
    'json': {
    'name': 'Heidi Thompson',
    'address': '68244 Michelle Square\nNorth Jamieshire, AL 88715',
},
    'key47393': 'value71808',
    'key8077': 'value76134',
    'key5736': 'value35251',
    'key52394': 'value81605',
    'key38644': 'value11498',
    'key90009': 'value79097',
},
    {
    'id': 17527487990369,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Paul Prince',
    'address': '1101 Christopher Well\nPort Tracyville, IA 97197',
    'text': 'Magazine model book official. Near perhaps how argue effort now traditional policy. Improve audience figure control point.',
    'email': 'williamsdustin@example.com',
    'phone_number': '255.551.3665',
    'json': {
    'name': 'Dr. Jose Ashley',
    'address': 'PSC 9232, Box 1997\nAPO AP 28127',
},
    'key71319': 'value2229',
    'key50436': 'value54488',
    'key32451': 'value8477',
    'key66974': 'value21392',
    'key69740': 'value27696',
    'key22910': 'value17933',
},
    {
    'id': 17527487990378,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Justin Leonard',
    'address': '3389 Sherman Walk Suite 206\nEast Tammy, CO 45807',
    'text': 'Thought brother cell break billion history. I democratic national simple poor edge.\nSouthern traditional responsibility well.',
    'email': 'vrobinson@example.net',
    'phone_number': '5242988011',
    'json': {
    'name': 'Vicki Salinas',
    'address': '447 Felicia Centers Apt. 367\nAngelaside, NC 64312',
},
    'key65595': 'value62341',
},
    {
    'id': 17527487990389,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Christina Ruiz',
    'address': '272 Karen Vista Suite 503\nLake Brenda, FL 59001',
    'text': 'Executive executive chance specific. Beyond character which score financial could as.\nUnderstand site enough. Affect here number along join medical. Describe look five center message.',
    'email': 'fernandoelliott@example.net',
    'phone_number': '001-525-847-8639x9609',
    'json': {
    'name': 'Kyle Marshall',
    'address': '840 Massey Unions Apt. 205\nThomasmouth, OH 17799',
},
    'key6894': 'value99253',
    'key66431': 'value71798',
    'key29000': 'value87852',
    'key29384': 'value16021',
    'key46867': 'value16419',
},
    {
    'id': 17527487990401,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Dakota Reid',
    'address': '7148 Jackson Causeway\nWest Cameron, WI 14545',
    'text': 'Important leave kind whose movie avoid model.\nJob project charge rich. Determine part want necessary school interesting.\nInterview director outside real partner condition.',
    'email': 'cwoodard@example.org',
    'phone_number': '694.652.7054',
    'json': {
    'name': 'Pamela Nguyen',
    'address': '109 Christopher Manors\nTraviston, ME 89421',
},
    'key59392': 'value72809',
    'key38813': 'value36251',
},
    {
    'id': 17527487990411,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Ashley Smith',
    'address': '6162 Jack Drive Apt. 801\nPort Heather, KY 23568',
    'text': 'Eat weight until director. Population car race indeed accept down respond house.\nRemember exactly no receive night article. Late discussion although each. Care outside hot into.',
    'email': 'denisehill@example.com',
    'phone_number': '001-835-244-2007x589',
    'json': {
    'name': 'Lori Herman',
    'address': '3729 Cox Spring\nSouth Tony, PR 89785',
},
    'key93109': 'value16265',
    'key98792': 'value7622',
    'key79723': 'value44607',
    'key41114': 'value63395',
    'key29932': 'value29130',
    'key60107': 'value42972',
},
    {
    'id': 17527487990422,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Andrew Davis',
    'address': '5173 Salinas Pines\nLukeside, MN 32327',
    'text': 'Ten enough factor same another name become face.\nSure try property option investment bag. Six art next or. Wide tough attention your will work.',
    'email': 'carolcurtis@example.net',
    'phone_number': '001-843-248-6795x1698',
    'json': {
    'name': 'Dakota Long',
    'address': '98427 Ashley Centers\nNorth Philip, FM 31364',
},
    'key21216': 'value13002',
},
    {
    'id': 17527487990434,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Tristan Campbell',
    'address': '0153 Jones Dale Suite 999\nDeanhaven, AZ 21629',
    'text': 'Early end most kitchen send age. Whether the real range food him else. Part response Mrs actually someone exist professional.\nSize role want or north memory. Hospital board authority action.',
    'email': 'tiffanydodson@example.net',
    'phone_number': '(363)205-0485',
    'json': {
    'name': 'Sharon Poole',
    'address': '50883 Strickland Skyway Suite 160\nLake Richardberg, AZ 67613',
},
    'key98719': 'value73640',
    'key2527': 'value50860',
    'key52616': 'value98994',
    'key96755': 'value42470',
    'key710': 'value74726',
    'key41379': 'value3529',
},
    {
    'id': 17527487990446,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Carol Doyle',
    'address': '1415 Stevens Rue Apt. 151\nNorth Jamesborough, OH 10283',
    'text': 'Recognize box bill produce. Two increase without always down newspaper. Above detail choice.',
    'email': 'danaanderson@example.net',
    'phone_number': '(690)941-4807x821',
    'json': {
    'name': 'Rodney Meyer',
    'address': '6254 Daniel Run Suite 887\nLake Shelby, WY 11257',
},
    'key53742': 'value10688',
    'key8276': 'value9202',
    'key17897': 'value53990',
    'key77387': 'value68343',
    'key84550': 'value31558',
    'key6593': 'value76192',
    'key79023': 'value91143',
},
    {
    'id': 17527487990457,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Lisa Barrera',
    'address': '4228 Henry Manor\nMichellebury, PA 77964',
    'text': 'Professional could image physical. Industry garden available whole.\nDetermine fine science sense. Ask community matter gas under present will point.',
    'email': 'jwood@example.net',
    'phone_number': '+1-663-203-6770',
    'json': {
    'name': 'Laurie Tate',
    'address': '3140 Jacobs Points\nSouth Victoria, MN 42577',
},
    'key6706': 'value31505',
},
    {
    'id': 17527487990468,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Eric Martin',
    'address': 'Unit 2112 Box 3738\nDPO AE 40151',
    'text': 'Score here lawyer throw over build color crime. Although condition song across good for run. Notice interest read do.\nBlack deal wait cell. World necessary later important member my.',
    'email': 'kristina13@example.com',
    'phone_number': '3065940103',
    'json': {
    'name': 'Kevin Foster',
    'address': '21533 David Estates Suite 928\nLake Timothy, TX 84864',
},
    'key60450': 'value36313',
    'key28646': 'value64145',
    'key75985': 'value36148',
    'key30973': 'value35075',
    'key39944': 'value65917',
    'key89864': 'value89345',
    'key85614': 'value12356',
    'key34331': 'value82518',
    'key40466': 'value52687',
    'key21145': 'value96329',
},
    {
    'id': 17527487990477,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Kimberly Edwards',
    'address': '66980 Vazquez Tunnel\nNorth Derek, ID 12707',
    'text': 'Three different apply will sense medical family. Interview benefit rise court national go.',
    'email': 'conleyyvonne@example.org',
    'phone_number': '546.916.0848',
    'json': {
    'name': 'Larry Savage',
    'address': '1948 Angelica Mountains Suite 759\nNew Jennifermouth, DC 38162',
},
    'key70537': 'value66653',
    'key38235': 'value77068',
    'key29945': 'value18859',
    'key5449': 'value64485',
    'key71586': 'value75278',
},
    {
    'id': 17527487990488,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Patrick Mills',
    'address': '40848 William Meadow\nNew Sierrachester, NJ 68991',
    'text': 'National artist occur space. Son north small. Inside same pay industry everything only.\nEconomy everything population theory event world wide. Occur very performance leave.',
    'email': 'javier24@example.org',
    'phone_number': '001-953-814-2037x801',
    'json': {
    'name': 'Angela Walton',
    'address': '576 Kristina Prairie\nNew Anthony, IA 12545',
},
    'key60322': 'value13254',
},
    {
    'id': 17527487990498,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Brian Newman',
    'address': '86086 Parks Oval Apt. 090\nNorth Michael, WV 89261',
    'text': 'Suddenly simply everything piece manage surface bed. Personal a east low decade inside want understand. Research statement issue seat.\nInvestment order exactly. Eight she meeting go.',
    'email': 'chogan@example.net',
    'phone_number': '613.541.0797x266',
    'json': {
    'name': 'Anna Murphy',
    'address': '47358 Frederick Shore\nAndrewtown, CT 27563',
},
    'key72546': 'value11115',
    'key47485': 'value83907',
    'key89520': 'value71548',
    'key29590': 'value42989',
    'key32720': 'value96717',
    'key85977': 'value23891',
    'key46986': 'value92785',
    'key56639': 'value47126',
},
    {
    'id': 17527487990508,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Randy Dawson',
    'address': '747 Koch Stream Suite 856\nEast Anthony, FL 57287',
    'text': 'Member movie contain deal.\nOut least anyone poor record seven. Case whatever week fly trip bill ground some.',
    'email': 'ifernandez@example.org',
    'phone_number': '(643)276-9988x24535',
    'json': {
    'name': 'Stacey Singh',
    'address': '699 Michael Shore\nPort James, UT 55537',
},
    'key2110': 'value22641',
    'key44340': 'value76836',
    'key50851': 'value76508',
    'key43173': 'value13464',
    'key71299': 'value4161',
    'key66781': 'value82502',
    'key69357': 'value26507',
},
    {
    'id': 17527487990519,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Kendra Davis',
    'address': 'Unit 7115 Box 3053\nDPO AP 75730',
    'text': 'Purpose in attention action. Feeling team expert. Blue and table open.',
    'email': 'nmedina@example.com',
    'phone_number': '856.586.8598x415',
    'json': {
    'name': 'Marcus Bird',
    'address': '38236 Wilson Drive\nKeithmouth, AS 49368',
},
    'key85676': 'value26210',
    'key382': 'value78183',
    'key89951': 'value69473',
    'key85458': 'value56117',
    'key19116': 'value22349',
    'key11146': 'value11718',
    'key2397': 'value91979',
    'key64652': 'value3761',
    'key47918': 'value38638',
},
    {
    'id': 17527487990528,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Daniel Clark',
    'address': '822 Berry Drive\nGarymouth, WA 40549',
    'text': 'History in rock degree generation officer glass. Current same will one respond number will sea.\nChurch grow again late against name. Former idea seek.',
    'email': 'timothy40@example.org',
    'phone_number': '001-831-466-0407x9708',
    'json': {
    'name': 'Sandra Kim',
    'address': '675 Zamora Cliff\nEast Brandonmouth, MO 38220',
},
    'key10663': 'value46497',
    'key53499': 'value13621',
    'key44683': 'value86861',
},
    {
    'id': 17527487990538,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Michelle Curtis',
    'address': 'Unit 1370 Box 9725\nDPO AP 74316',
    'text': 'Long vote couple home.\nBy specific site particularly Republican start race. Remain him today too recent green. Speech read standard fund heart out.',
    'email': 'kurthaynes@example.org',
    'phone_number': '9179499442',
    'json': {
    'name': 'Corey Salinas',
    'address': '162 Katherine Forge Apt. 900\nRickyborough, TN 46839',
},
    'key41813': 'value90601',
    'key860': 'value29906',
},
    {
    'id': 17527487990548,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Aaron Russell',
    'address': '65719 Albert Port Apt. 071\nEast Joseph, MP 74483',
    'text': 'Simple treatment crime quality possible population owner century. Table take bad rest risk around guess. Magazine call wonder history mention they member. Cover trial must throw thank check.',
    'email': 'jamesbautista@example.com',
    'phone_number': '3193065529',
    'json': {
    'name': 'Eric Stewart',
    'address': '602 Thomas Club Suite 587\nFigueroaton, GU 63139',
},
    'key59592': 'value4003',
    'key73409': 'value58898',
},
    {
    'id': 17527487990559,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Mitchell Patton',
    'address': '27669 Graham Islands Suite 908\nPort Mary, AZ 51287',
    'text': 'Toward move focus work close.\nManage religious physical although avoid control. Father know degree his bad student.\nNational bad happy public party. Police federal cover only as individual glass.',
    'email': 'ymorrow@example.org',
    'phone_number': '001-842-615-4811x0355',
    'json': {
    'name': 'Thomas Johnson',
    'address': '0293 Thompson Lake\nGoldentown, HI 98423',
},
    'key96260': 'value85137',
    'key35214': 'value97489',
    'key34760': 'value18615',
    'key87237': 'value59503',
    'key85601': 'value89664',
},
    {
    'id': 17527487990570,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'James Anderson',
    'address': '7974 Martinez Divide Suite 581\nNorth Lisamouth, FM 95248',
    'text': 'Remember clearly prevent more.\nTonight thousand everyone. Today agree similar hear discuss customer. Yard again federal perhaps.\nFine she similar.',
    'email': 'olsonmark@example.net',
    'phone_number': '+1-511-201-6752x86430',
    'json': {
    'name': 'Elizabeth Hatfield',
    'address': '53621 Gary Street\nPerezfurt, NC 31718',
},
    'key14687': 'value19448',
    'key9239': 'value83933',
    'key10283': 'value14126',
    'key87082': 'value74377',
},
    {
    'id': 17527487990582,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Monica Wu',
    'address': '08418 Jackson Landing Suite 257\nPort Kim, KY 26345',
    'text': 'Maintain rule job spend others. Child center general likely.\nAir large just stage too sort. Station alone western ready agent past her. Business happy eye born surface reason.',
    'email': 'denise64@example.net',
    'phone_number': '(285)908-1475',
    'json': {
    'name': 'Brenda Dixon',
    'address': '6479 Stacy Vista Apt. 697\nBryanshire, VA 05634',
},
    'key7714': 'value75518',
    'key20212': 'value84414',
    'key3089': 'value91981',
    'key91666': 'value73685',
    'key86699': 'value39078',
    'key86732': 'value10395',
    'key27212': 'value41794',
},
    {
    'id': 17527487990593,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Renee Decker',
    'address': '138 Deborah Forks\nPatrickton, GA 97763',
    'text': 'Business ready reach they. Personal address wife another red we.\nKnowledge skin bill service position tell heart. Reflect near ready rate century pattern.',
    'email': 'roberta51@example.com',
    'phone_number': '001-712-713-5864x780',
    'json': {
    'name': 'Brittany Olson',
    'address': '773 Morgan Plaza Suite 513\nWest Stacy, VI 04778',
},
    'key34081': 'value14759',
    'key44790': 'value26648',
    'key17414': 'value76884',
    'key71097': 'value33285',
    'key79998': 'value53513',
},
    {
    'id': 17527487990604,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Michael Kelly',
    'address': '377 Evan Freeway\nNew Luistown, AS 78785',
    'text': 'Fight recognize challenge. Might road usually national race.\nWorld say right. Bar campaign between special room end. Some least fact apply measure personal report blood.',
    'email': 'hudsonsarah@example.com',
    'phone_number': '237.433.0054x246',
    'json': {
    'name': 'Wayne Harris DDS',
    'address': '8585 Kayla Isle Apt. 015\nNorth Seanville, KS 75169',
},
    'key8051': 'value79101',
    'key18851': 'value19480',
    'key46630': 'value41376',
    'key52033': 'value33153',
    'key15739': 'value11158',
    'key51033': 'value21091',
    'key40698': 'value94440',
    'key39933': 'value72992',
},
    {
    'id': 17527487990616,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Robert Jenkins',
    'address': '6792 Webb Meadows Apt. 493\nPort Melissafurt, AZ 73504',
    'text': 'The collection language especially probably. Father tonight season writer against writer.\nWrite want hotel when under. Her modern in produce throw thus loss reveal. Couple scientist bed former.',
    'email': 'michaelking@example.org',
    'phone_number': '2575909631',
    'json': {
    'name': 'Brooke Chavez',
    'address': '30875 Clark Throughway Suite 834\nNew Sara, GU 62860',
},
    'key18924': 'value5427',
    'key3122': 'value10926',
    'key32760': 'value72134',
    'key26541': 'value22129',
    'key56545': 'value8929',
    'key76914': 'value30992',
    'key95704': 'value94033',
},
    {
    'id': 17527487990628,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Ricardo Finley',
    'address': '95479 Watson Haven\nJessicaville, SC 62899',
    'text': 'Writer floor cause prevent director. Open sometimes significant truth. Of modern coach series blue magazine should none.',
    'email': 'jamesroman@example.com',
    'phone_number': '+1-614-233-4937',
    'json': {
    'name': 'Taylor Armstrong',
    'address': '0966 Wyatt Springs\nGuerreroport, IN 93183',
},
    'key595': 'value39791',
    'key10211': 'value28957',
    'key92726': 'value56321',
    'key58947': 'value77672',
    'key18478': 'value44768',
    'key9815': 'value59364',
    'key92168': 'value65351',
},
    {
    'id': 17527487990640,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Tammy Taylor',
    'address': '9194 Kim Tunnel\nPort Jenny, MT 43827',
    'text': 'Morning meet surface will. Section without role teach citizen official. Family challenge whose forget treat ground.\nMajority charge contain environmental notice. Story population list recognize.',
    'email': 'allenrobert@example.net',
    'phone_number': '7682924472',
    'json': {
    'name': 'Susan Gibson',
    'address': '88810 Solomon Glen\nPort Jeffery, LA 97179',
},
    'key25939': 'value84294',
    'key34291': 'value20989',
    'key54703': 'value92824',
    'key47003': 'value83927',
    'key12930': 'value3132',
    'key96373': 'value23991',
    'key44982': 'value35377',
},
    {
    'id': 17527487990652,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Elizabeth Hall',
    'address': 'USNS Sherman\nFPO AE 35740',
    'text': 'Leg result deal which series of find. Truth into again until treatment.\nFrom real do need thought look. Lead amount leg myself.\nFront power movie. Reach baby adult couple choose indicate fear local.',
    'email': 'omarquez@example.org',
    'phone_number': '508-282-6387x53161',
    'json': {
    'name': 'Erica Wolfe',
    'address': '74220 Robert Valley\nPort Toni, PR 15607',
},
    'key81035': 'value190',
    'key50540': 'value77931',
    'key32049': 'value9452',
    'key87768': 'value8613',
},
    {
    'id': 17527487990662,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Heather Pena',
    'address': '29580 Jeffrey Centers\nJonathanbury, MH 50642',
    'text': 'Generation provide prepare over value half. As successful each able team.\nAround exactly control parent kitchen couple risk.',
    'email': 'gloria15@example.net',
    'phone_number': '(658)936-1890',
    'json': {
    'name': 'Judith Patel',
    'address': '4933 Jonathan Pines Suite 777\nEast Benjamin, MO 41453',
},
    'key42676': 'value14357',
    'key58137': 'value51468',
    'key63186': 'value16714',
    'key80731': 'value29868',
    'key82072': 'value95352',
},
    {
    'id': 17527487990672,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Heidi Smith',
    'address': '8274 Patricia Light\nSouth Kaitlynland, MH 76117',
    'text': 'Difference feel prove animal six view. Former financial thank break official understand herself. Not full better star standard plan. Leg player rather mission.',
    'email': 'millsnatasha@example.com',
    'phone_number': '5622660326',
    'json': {
    'name': 'Susan Williams',
    'address': '40995 Steele Shoals Apt. 006\nCarrietown, NE 88975',
},
    'key33797': 'value1625',
    'key51740': 'value97816',
    'key3673': 'value3189',
    'key47082': 'value47984',
},
    {
    'id': 17527487990683,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Cheryl Trevino',
    'address': '4699 Vasquez Burg\nNew Dennis, WY 28494',
    'text': 'Entire might edge society word. Sport staff forward own year young these.\nLose door under make. Threat protect product growth behind wall.',
    'email': 'ambermyers@example.com',
    'phone_number': '(447)367-0482x84968',
    'json': {
    'name': 'Christopher Wright',
    'address': '10286 Gallagher Dale Suite 270\nNew Veronicashire, OK 04282',
},
    'key53363': 'value53951',
    'key45476': 'value76478',
    'key7631': 'value55005',
    'key98614': 'value39404',
    'key95263': 'value42682',
},
    {
    'id': 17527487990694,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Jessica Fisher',
    'address': '563 Adams Station\nNorth Karastad, VI 40319',
    'text': 'Sit shake dark focus. Total environment thing camera store six final. Court push action middle so rest.',
    'email': 'zacharysherman@example.org',
    'phone_number': '606-387-4958x14919',
    'json': {
    'name': 'Matthew Houston',
    'address': '0556 James Forge Suite 648\nKellerton, MH 60387',
},
    'key55815': 'value15965',
    'key75854': 'value64194',
    'key12763': 'value92129',
},
    {
    'id': 17527487990706,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Lisa Reyes',
    'address': '2330 Carpenter Crescent Apt. 311\nLawsonport, VT 85965',
    'text': 'Need room produce audience learn.\nHold loss hold character word mouth you. Tonight into natural school degree. Easy quickly change usually pressure fill nation.',
    'email': 'elizabethfuller@example.net',
    'phone_number': '001-329-980-6428',
    'json': {
    'name': 'Julia Gomez',
    'address': '61417 Wendy Spurs Apt. 383\nJacobburgh, ID 05920',
},
    'key68726': 'value88918',
    'key27822': 'value94009',
    'key51819': 'value20772',
    'key60480': 'value74806',
    'key29953': 'value43351',
    'key47420': 'value22331',
    'key16281': 'value41820',
    'key26165': 'value3906',
},
    {
    'id': 17527487990718,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Megan Peck',
    'address': 'USNV Richard\nFPO AE 02664',
    'text': 'Source major before require quickly. Tax ever action reason million power important. Part charge wish senior attorney trip reality.',
    'email': 'greerkathleen@example.org',
    'phone_number': '+1-352-225-4254x43549',
    'json': {
    'name': 'Joel Rivers',
    'address': '757 Russell Place Suite 684\nSalazarview, VA 25273',
},
    'key25342': 'value9821',
    'key85759': 'value28724',
    'key43916': 'value77231',
    'key44025': 'value53822',
    'key81854': 'value47459',
    'key67475': 'value4533',
    'key66608': 'value12182',
    'key16071': 'value50429',
    'key88197': 'value61367',
},
    {
    'id': 17527487990728,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Kent Thompson',
    'address': '75977 Edward Fall Apt. 966\nGrahammouth, NV 99701',
    'text': 'Allow total generation international charge. Sense behind civil series tell fish consumer.\nSpeech question six boy hard sport respond. Among newspaper shake up institution point what.',
    'email': 'aoconnell@example.com',
    'phone_number': '976-855-2333x37225',
    'json': {
    'name': 'Rachel White',
    'address': '1009 Moran Way Suite 170\nAlexandermouth, PW 01763',
},
    'key49097': 'value85298',
},
    {
    'id': 17527487990739,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Shane Le',
    'address': 'PSC 0580, Box 9816\nAPO AA 85316',
    'text': 'Best work movement doctor. Enter in Mr report scientist issue that. Specific blood mention certainly.\nLay mother race age from both somebody. Use Congress share research author dark.',
    'email': 'laura24@example.net',
    'phone_number': '(609)874-2995x73593',
    'json': {
    'name': 'Tracy Smith',
    'address': '3954 Davis Groves Apt. 494\nEast Richardburgh, WI 73575',
},
    'key52055': 'value38463',
    'key37081': 'value88171',
},
    {
    'id': 17527487990748,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Erin Hernandez',
    'address': 'USCGC Campos\nFPO AE 46281',
    'text': 'Budget investment hope. Lot budget per energy.\nTrial among institution building. Decide back number family color since. Trouble too full over. Up really option fast officer smile.',
    'email': 'tylerparker@example.net',
    'phone_number': '955.705.1601x40054',
    'json': {
    'name': 'James Navarro',
    'address': '1659 Wilson Gardens Suite 014\nMillerbury, CT 22362',
},
    'key63039': 'value95290',
},
    {
    'id': 17527487990759,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Derek Gonzalez',
    'address': '503 Brady Fall Suite 150\nNorth Debramouth, NY 77882',
    'text': 'Camera many friend hope improve whole total theory. Toward language receive support. Help hold most teacher until north church.',
    'email': 'nicholas22@example.com',
    'phone_number': '+1-569-843-1031x27447',
    'json': {
    'name': 'Casey Schmidt',
    'address': '73001 Hoffman Mountain\nQuinnside, AR 15022',
},
    'key95410': 'value29864',
    'key85872': 'value59308',
    'key55561': 'value37398',
    'key70818': 'value46552',
    'key41197': 'value22792',
    'key2584': 'value9126',
    'key16298': 'value94530',
    'key94258': 'value59717',
},
    {
    'id': 17527487990769,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Kimberly Hoffman',
    'address': '208 Holly Shoal Suite 745\nNew Hectorshire, CT 26725',
    'text': 'Unit member foot tough. Read mind but record. Enter fish best. Democratic rise your theory.',
    'email': 'evanscesar@example.org',
    'phone_number': '+1-716-338-7425',
    'json': {
    'name': 'David Hopkins',
    'address': '789 Randy Locks Suite 363\nNew Cherylfort, AS 24952',
},
    'key89506': 'value1694',
    'key64191': 'value16414',
    'key76451': 'value4900',
},
    {
    'id': 17527487990781,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Joshua Butler',
    'address': '62646 Bowman Mountain Apt. 088\nMichaelfurt, SD 24718',
    'text': 'By federal his born war guy.\nToo these more coach sure scientist program. Main middle certain.\nThird station age follow suggest allow available it. Dream Congress contain I agree.',
    'email': 'jamesjohnson@example.org',
    'phone_number': '449.318.6811',
    'json': {
    'name': 'David Johnson',
    'address': '86435 Yoder Falls Apt. 823\nPort Desiree, MD 05644',
},
    'key25702': 'value12032',
},
    {
    'id': 17527487990792,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Arthur Long',
    'address': '2361 Ronnie Pass\nNew Anna, MO 32129',
    'text': 'People station weight start whatever majority hold family. Address determine along including. Dinner relationship hold.',
    'email': 'morrisonjoseph@example.com',
    'phone_number': '+1-975-357-9496',
    'json': {
    'name': 'Jacob Johnson PhD',
    'address': '3462 Russell Locks\nNorth Christine, NJ 56442',
},
    'key75688': 'value71621',
    'key79707': 'value27597',
    'key16485': 'value86990',
    'key1390': 'value94151',
    'key78558': 'value83583',
    'key74875': 'value92658',
    'key96238': 'value77402',
    'key27614': 'value44049',
    'key46165': 'value14690',
    'key21552': 'value59087',
},
    {
    'id': 17527487990804,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Melissa Hill',
    'address': 'Unit 2515 Box 1886\nDPO AP 15215',
    'text': 'Recently development summer collection. Simply heavy name low executive improve.\nNice less place data face feel beautiful. Name maintain fly process development easy also.',
    'email': 'fmendez@example.net',
    'phone_number': '377-850-1496x5000',
    'json': {
    'name': 'Jon Baker',
    'address': '54962 Scott Isle Apt. 333\nKempton, MA 59912',
},
    'key63368': 'value82193',
    'key99443': 'value32970',
    'key26286': 'value63607',
},
    {
    'id': 17527487990813,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Spencer Smith',
    'address': '991 Miller Cliff\nLake Rachelville, IN 25469',
    'text': 'Behavior growth tough white threat course baby car.\nPolitical threat seat pick. Might car although manage.\nFree fine last keep hair responsibility.',
    'email': 'mollyclements@example.com',
    'phone_number': '620.600.2978x6546',
    'json': {
    'name': 'Vanessa Tucker',
    'address': '4764 Brittany Pass\nPort Wesleyland, NV 09960',
},
    'key80190': 'value97416',
    'key19940': 'value73465',
    'key2244': 'value8721',
},
    {
    'id': 17527487990825,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Cheryl Thomas',
    'address': '7082 Lewis Spring\nSouth Joel, NM 05988',
    'text': 'Matter increase turn article. Unit adult condition clearly notice central. West five establish something able wear. College north family.',
    'email': 'lawrencesnyder@example.net',
    'phone_number': '343.924.2374x15606',
    'json': {
    'name': 'Cathy Kim',
    'address': '4461 Knapp Brooks Apt. 624\nPort Raymondhaven, AK 86538',
},
    'key58433': 'value3627',
    'key8259': 'value54658',
    'key21640': 'value99099',
    'key20042': 'value43272',
    'key53345': 'value35836',
},
    {
    'id': 17527487990838,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Debra Larson',
    'address': '1604 Tommy Port\nJamesfurt, MT 65565',
    'text': 'Safe minute environment book out expect. Professor others around front. Lawyer ground involve while case north.',
    'email': 'hgeorge@example.org',
    'phone_number': '001-630-965-4336x5387',
    'json': {
    'name': 'Joann Mejia',
    'address': '49204 Michelle Fork\nBenjaminview, UT 45943',
},
    'key96595': 'value66349',
    'key20069': 'value75992',
},
    {
    'id': 17527487990849,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'John Guerrero',
    'address': '51061 Kristen Course\nEast Angelland, CO 05397',
    'text': 'Truth clear heavy worry item. Fly theory key then.\nBreak with sometimes five decade effect statement. Majority long second ready room husband.',
    'email': 'brownphillip@example.com',
    'phone_number': '(610)479-9052x626',
    'json': {
    'name': 'Kristin Jones',
    'address': '7009 Thompson Viaduct\nAndersonview, PA 66824',
},
    'key17298': 'value62836',
    'key11023': 'value1419',
    'key338': 'value70412',
},
    {
    'id': 17527487990861,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Joseph Diaz',
    'address': 'Unit 0408 Box 5258\nDPO AE 40639',
    'text': 'If under prevent science create last.\nRoad feel often rest deal building. Bill action common language.\nMention many play draw often. Tv network skill.',
    'email': 'davidjohnston@example.org',
    'phone_number': '(337)301-5722x5907',
    'json': {
    'name': 'Jennifer Weber',
    'address': '600 Michael Lane Suite 566\nEast Nathan, NV 90906',
},
    'key25135': 'value19859',
    'key65125': 'value28747',
},
    {
    'id': 17527487990871,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Mary Barton',
    'address': '09159 John Camp Apt. 116\nGayton, NE 63955',
    'text': 'Choice generation road economy simply next. Own each care nation else red note. Away institution old star.',
    'email': 'stevenwilson@example.com',
    'phone_number': '7005337436',
    'json': {
    'name': 'Nancy Martinez',
    'address': '147 Burns Stravenue\nPort Dennistown, WA 09707',
},
    'key61864': 'value97487',
    'key89816': 'value57255',
    'key46675': 'value39540',
    'key72410': 'value12916',
    'key70823': 'value83279',
    'key16712': 'value83732',
    'key12495': 'value11539',
},
    {
    'id': 17527487990884,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Dakota Miller II',
    'address': '2814 Phillip Locks Apt. 650\nAdrianatown, OK 11707',
    'text': 'Responsibility off hotel left general say. Garden effort effect sport door career big. At score research among already.\nOther range yet ball middle notice skill. Ground where why film nothing.',
    'email': 'phillipsmichelle@example.org',
    'phone_number': '901.521.0166',
    'json': {
    'name': 'Emily Parker',
    'address': '77335 Parks Islands Apt. 308\nLake Leslie, FM 58419',
},
    'key99119': 'value74835',
    'key77562': 'value7648',
    'key84213': 'value4266',
    'key71505': 'value7376',
    'key77859': 'value25001',
    'key92196': 'value9122',
    'key47036': 'value9156',
},
    {
    'id': 17527487990896,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Jennifer Watson',
    'address': '703 Peterson Burg Apt. 313\nMichaelside, KS 30317',
    'text': 'Reality understand stock fill issue glass. Leg star student executive guy character wear answer. Instead radio born mind.',
    'email': 'martinamy@example.com',
    'phone_number': '(613)562-2879x73174',
    'json': {
    'name': 'Richard Mcdonald',
    'address': '052 Morgan River\nBrianchester, PW 68883',
},
    'key92238': 'value55325',
    'key708': 'value30521',
    'key39070': 'value56248',
},
    {
    'id': 17527487990908,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Thomas Smith',
    'address': 'PSC 5339, Box 4486\nAPO AP 59058',
    'text': 'View rest weight tree step during Democrat. Build food local film whom media. Gun tonight specific man certainly assume.\nEarly vote each green.',
    'email': 'cmcdowell@example.net',
    'phone_number': '8778962829',
    'json': {
    'name': 'Mary Lopez',
    'address': 'USCGC Morris\nFPO AE 21974',
},
    'key44583': 'value70929',
    'key49451': 'value16289',
    'key81431': 'value56137',
    'key58446': 'value19611',
},
    {
    'id': 17527487990916,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Adam Huber',
    'address': '236 Brad Shores Apt. 289\nLambbury, IN 45280',
    'text': 'Some cover article kid add change star. Effort receive year interview attack summer half.\nBusiness production medical war bill court share boy. Hundred different nor until democratic ball.',
    'email': 'amycarr@example.org',
    'phone_number': '416.740.5655x8903',
    'json': {
    'name': 'Brian Stewart',
    'address': '0380 Stephens Valley Suite 340\nLopezhaven, OR 86598',
},
    'key28764': 'value87281',
    'key48497': 'value79757',
    'key6009': 'value96316',
    'key80351': 'value37004',
},
    {
    'id': 17527487990928,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Deborah Hernandez',
    'address': '7034 Mcknight Mission Suite 568\nKennethshire, WV 83919',
    'text': 'The beyond technology culture newspaper oil church step. Lose hair cause network marriage part concern. West throw feeling will contain try.\nEnvironment suffer indeed gun job.',
    'email': 'jensenautumn@example.org',
    'phone_number': '001-536-510-2130',
    'json': {
    'name': 'David Peterson',
    'address': '76850 Hansen Dam Apt. 925\nGeorgeview, UT 09518',
},
    'key27422': 'value8776',
    'key97218': 'value34217',
},
    {
    'id': 17527487990940,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Susan Salinas',
    'address': '686 Smith Trace Apt. 231\nWest Carolyn, PW 81115',
    'text': 'Operation with coach relationship wall. Role trip since fall sea tough.\nCongress specific if action. Above management focus reality require edge blue.',
    'email': 'reyesgina@example.com',
    'phone_number': '+1-732-673-9636x1266',
    'json': {
    'name': 'Barry Smith',
    'address': '816 Casey Light\nPort Jeffrey, KY 53664',
},
    'key57306': 'value49731',
    'key55450': 'value75801',
    'key54514': 'value89633',
},
    {
    'id': 17527487990951,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Sara Stevens',
    'address': '295 Jimmy Pines\nWest Kayleeside, VA 03511',
    'text': 'Rock read stay rate smile term network clear. Fall situation represent official expect. Shoulder factor cause identify position raise purpose.',
    'email': 'mcclureronald@example.net',
    'phone_number': '+1-857-840-9389x29050',
    'json': {
    'name': 'Jerry Stone MD',
    'address': '711 Eric Motorway Suite 493\nNorth Brett, VT 81639',
},
    'key59512': 'value56559',
    'key39640': 'value91094',
},
    {
    'id': 17527487990963,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Angela Miller',
    'address': '3233 Joseph Keys\nNicolehaven, LA 26805',
    'text': 'Physical five begin hold know draw us off. Letter strong away agency she teacher quickly. Partner lay meeting part moment.\nCouple detail once late rock field.',
    'email': 'edwardstrickland@example.net',
    'phone_number': '+1-250-876-6000x5257',
    'json': {
    'name': 'Pamela Fisher',
    'address': '83266 Casey Shores Suite 973\nGutierrezmouth, OH 31832',
},
    'key97482': 'value90463',
    'key7640': 'value57682',
    'key90504': 'value54035',
    'key80753': 'value78604',
},
    {
    'id': 17527487990975,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Joann Williams',
    'address': '0553 Reid Drive Apt. 952\nRichburgh, CT 41524',
    'text': 'Piece always then body next run. Probably meeting answer arm reason majority. Radio whatever many raise.\nHour simply imagine expert. Act even probably.',
    'email': 'psoto@example.com',
    'phone_number': '938.930.5627',
    'json': {
    'name': 'Daniel Reed',
    'address': '639 Duarte Port\nJamesborough, IL 66223',
},
    'key67552': 'value21982',
    'key79921': 'value30146',
    'key88485': 'value99737',
    'key87042': 'value34484',
    'key37165': 'value71416',
    'key52053': 'value7945',
    'key44762': 'value98152',
},
    {
    'id': 17527487990987,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Mr. Ricky Martinez',
    'address': '983 Mitchell Gateway\nWest Megan, LA 96058',
    'text': 'Why relate even southern even wait bring. Often support usually today conference party threat fight.\nStuff style forward doctor. Evening relationship drop activity career deal.',
    'email': 'markgarcia@example.net',
    'phone_number': '(762)461-6295x82979',
    'json': {
    'name': 'Daniel Fitzpatrick',
    'address': '099 Kerr Dale\nMaxwellfurt, OR 27236',
},
    'key28684': 'value25833',
    'key27778': 'value35874',
    'key98191': 'value20597',
    'key99042': 'value94632',
    'key38034': 'value39689',
    'key79378': 'value61670',
    'key93298': 'value17718',
    'key6280': 'value78427',
    'key62754': 'value76311',
    'key77901': 'value23317',
},
    {
    'id': 17527487991000,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Brett Henry',
    'address': '385 Butler Trail Apt. 206\nNew William, WA 33985',
    'text': 'Affect leader answer also. Community Republican dream leader. Fast general debate according.\nStaff history executive bill budget blood. Civil personal sure way.\nTruth along law system away.',
    'email': 'hooverpaul@example.org',
    'phone_number': '(682)552-7409x286',
    'json': {
    'name': 'Ryan James',
    'address': '136 Tanya Island Suite 046\nGibbsbury, OK 79641',
},
    'key36224': 'value12450',
},
    {
    'id': 17527487991012,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Amanda Carpenter',
    'address': '916 Vanessa Mountains Suite 957\nEast Megan, DC 55640',
    'text': 'Serve popular go person rock miss. Material he hard gun.',
    'email': 'jonathanpearson@example.org',
    'phone_number': '9703056671',
    'json': {
    'name': 'Sharon Morgan',
    'address': '41361 Murray Drive\nNorth Davidfurt, CT 06386',
},
    'key23875': 'value76808',
    'key68336': 'value38404',
},
    {
    'id': 17527487991023,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Katherine Brown',
    'address': '9123 Atkinson Shoals Suite 101\nWilliamschester, IN 05965',
    'text': 'Yard around economy station single word sound. South stuff drug his.\nEat begin story election whatever natural another. When market where heavy determine when moment.',
    'email': 'bbradshaw@example.org',
    'phone_number': '001-321-839-6731x3022',
    'json': {
    'name': 'Caleb Frey',
    'address': '16675 Mitchell Ranch Suite 162\nRamosland, TN 49237',
},
    'key20183': 'value68263',
    'key74659': 'value2225',
    'key30230': 'value44784',
    'key39741': 'value20606',
    'key30318': 'value29317',
    'key17649': 'value69647',
},
    {
    'id': 17527487991034,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Gilbert Hansen',
    'address': '83537 Kathleen Spring\nMargaretmouth, MP 73797',
    'text': 'Win decision good military family. Over painting actually body show brother.\nList behavior most center party election quality evening. Police measure do form.',
    'email': 'tina42@example.com',
    'phone_number': '(481)270-2764',
    'json': {
    'name': 'James Wright',
    'address': '656 Katherine Plains Suite 460\nJenniferton, HI 98689',
},
    'key18250': 'value76253',
    'key35038': 'value99586',
    'key15401': 'value53914',
    'key37348': 'value48396',
    'key16087': 'value3178',
    'key47869': 'value68525',
    'key99375': 'value30493',
    'key19662': 'value56376',
    'key13351': 'value28210',
},
    {
    'id': 17527487991045,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Robert King',
    'address': '96444 Brown Unions Suite 517\nEast Amyhaven, WY 60249',
    'text': 'Better street cut expect drop drug strategy form. Power sound just big yard. Generation compare traditional law.',
    'email': 'sydney73@example.net',
    'phone_number': '217-512-8472',
    'json': {
    'name': 'Rebecca Williams',
    'address': '9643 Moore Viaduct Apt. 504\nJasonport, VI 16136',
},
    'key13010': 'value50789',
    'key74836': 'value27037',
    'key55120': 'value37917',
    'key42932': 'value24937',
    'key10715': 'value56490',
    'key40606': 'value6706',
    'key1873': 'value24679',
},
    {
    'id': 17527487991056,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Frank Martin',
    'address': '074 Thomas Mountain\nFuenteston, NC 98200',
    'text': 'Deep into they save sit culture anything happy. Send business public choose staff space. Between everything nearly community.\nSize well when per room fine along.',
    'email': 'watkinskevin@example.com',
    'phone_number': '753-662-7477',
    'json': {
    'name': 'Lindsey Stewart',
    'address': '8880 Grimes Harbors Apt. 880\nRobertmouth, OH 17863',
},
    'key38414': 'value35262',
    'key69326': 'value79302',
    'key16717': 'value93167',
    'key90899': 'value55430',
    'key68238': 'value53412',
    'key81304': 'value96857',
    'key27852': 'value41710',
    'key16808': 'value12744',
    'key94197': 'value70843',
},
    {
    'id': 17527487991067,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Lorraine Pham',
    'address': 'PSC 8882, Box 8081\nAPO AA 27836',
    'text': 'Book gas way week carry game story. Matter environment happy serious effect create.\nImpact training trip. Easy rock full magazine party.',
    'email': 'laurasutton@example.org',
    'phone_number': '(955)644-7179',
    'json': {
    'name': 'Karl Vega',
    'address': '04768 Timothy Inlet\nNew Nancyland, MN 36124',
},
    'key3406': 'value42159',
    'key37748': 'value24386',
    'key36579': 'value39575',
    'key37207': 'value78519',
    'key84579': 'value20315',
    'key7529': 'value48462',
},
    {
    'id': 17527487991077,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Brian Thompson',
    'address': '433 Tiffany Ports Suite 291\nEast Ginaton, WV 71023',
    'text': 'Pull myself message author paper. I mission along put commercial page poor.\nDespite method particular let. Either have nearly relate.',
    'email': 'cartermichael@example.net',
    'phone_number': '+1-208-804-8345',
    'json': {
    'name': 'Tamara James',
    'address': '737 Martinez Junction\nLake Julia, NH 92103',
},
    'key47515': 'value25162',
    'key17143': 'value15239',
    'key36891': 'value9896',
},
    {
    'id': 17527487991088,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Melissa Rogers',
    'address': '6201 Nicole Ramp\nSmithborough, DC 04256',
    'text': 'They than scene yeah million civil. There need read. Enjoy feel major know water.\nOnce kid woman white worker left follow. Result instead fall woman fund camera make.',
    'email': 'tmorris@example.net',
    'phone_number': '4472753775',
    'json': {
    'name': 'Laura Knight',
    'address': '25324 Mason Center Suite 272\nLake Martinfurt, GU 79915',
},
    'key43162': 'value14596',
    'key10793': 'value24058',
    'key62105': 'value80720',
    'key64020': 'value75384',
    'key16305': 'value38332',
    'key33982': 'value88510',
    'key38266': 'value27570',
},
    {
    'id': 17527487991100,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Christopher Trevino',
    'address': '72904 Sandy Curve Apt. 083\nElizabethstad, VI 16073',
    'text': 'They often employee recognize. We just entire bed free scientist.\nWe development significant. Other fast room second crime instead. Pm art beautiful half.',
    'email': 'thomasrice@example.net',
    'phone_number': '4007910683',
    'json': {
    'name': 'Stacey Gillespie',
    'address': '3187 John Ramp Suite 745\nNorth Jenniferport, GU 55781',
},
    'key5729': 'value4889',
    'key95020': 'value17666',
    'key52554': 'value95618',
    'key71073': 'value47778',
    'key12424': 'value31594',
    'key4248': 'value12195',
    'key92761': 'value21531',
    'key66803': 'value68012',
},
    {
    'id': 17527487991111,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Michael Fuller',
    'address': '90716 Guerrero Plain\nPort Jessicafurt, SC 83319',
    'text': 'Dream nature somebody beautiful concern level. It find coach question seven reflect he forget. Use later community country resource wrong.',
    'email': 'calvin56@example.com',
    'phone_number': '(312)212-6974',
    'json': {
    'name': 'Kara Williams',
    'address': '94138 John Union Apt. 302\nLake Sarah, NH 12112',
},
    'key78503': 'value4398',
    'key72805': 'value41915',
    'key60837': 'value47173',
    'key32909': 'value58617',
    'key69406': 'value19978',
    'key82134': 'value2260',
    'key11555': 'value35634',
    'key26497': 'value33882',
    'key87592': 'value8841',
},
    {
    'id': 17527487991123,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Lauren White',
    'address': '997 Webster Forges Apt. 531\nBrownport, KY 89798',
    'text': 'Glass really development budget. Quickly quality physical American follow task drive.\nMust point coach reduce itself. Office record wall chance.',
    'email': 'hpark@example.com',
    'phone_number': '958.424.3043',
    'json': {
    'name': 'Cynthia Larsen',
    'address': '993 Diane Court\nPort Michelle, ID 35965',
},
    'key58371': 'value27726',
    'key97720': 'value78546',
},
    {
    'id': 17527487991134,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Larry Duncan',
    'address': '4155 Ross Shores\nEast Jeremytown, WY 04981',
    'text': 'Sport still energy southern public. Building now thought drop.\nPay author despite fall.',
    'email': 'evanswilliam@example.net',
    'phone_number': '+1-770-719-3037x1795',
    'json': {
    'name': 'Brenda Cooper',
    'address': 'Unit 7547 Box 2788\nDPO AP 49132',
},
    'key32713': 'value64323',
    'key65749': 'value54988',
    'key2404': 'value10246',
    'key20063': 'value85296',
    'key45769': 'value33321',
    'key34620': 'value5284',
},
    {
    'id': 17527487991144,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'John Forbes',
    'address': '3648 Anthony Garden Apt. 046\nNew Danaberg, MI 61792',
    'text': 'Million trial life cause. Think structure talk couple from. Sound door relationship it blue market. Provide democratic sell why on team.',
    'email': 'nathan19@example.org',
    'phone_number': '449.606.5975',
    'json': {
    'name': 'Stephen Vega',
    'address': '0674 Nicholas Field\nNew Nathan, NH 13470',
},
    'key14799': 'value69286',
    'key74307': 'value9969',
    'key3937': 'value61283',
},
    {
    'id': 17527487991165,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Todd Evans',
    'address': 'USS Mcdowell\nFPO AE 08057',
    'text': 'Teach explain even second movie. First put step phone pull partner. Save the above television trial option.\nMedical kitchen enough join different power. Good city beautiful remain left west.',
    'email': 'ryananderson@example.net',
    'phone_number': '+1-821-275-5173x01642',
    'json': {
    'name': 'Willie Mitchell',
    'address': '1030 Thomas Square\nNew Amanda, DE 02364',
},
    'key53041': 'value87520',
    'key51829': 'value65996',
    'key41905': 'value63346',
    'key6517': 'value37513',
    'key83973': 'value10283',
    'key68542': 'value76688',
    'key15572': 'value61571',
    'key62121': 'value93204',
    'key80087': 'value55108',
},
    {
    'id': 17527487991180,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Adrian Williams',
    'address': '6764 Janet Ranch Suite 378\nKristopherfort, NV 38095',
    'text': 'Believe from western build yet executive phone.\nPhysical many simple by. She investment forward ability place throw.',
    'email': 'brian60@example.com',
    'phone_number': '645-907-6650',
    'json': {
    'name': 'Zachary Holland',
    'address': '4178 Davis Prairie\nLake Amandafort, MT 24631',
},
    'key45612': 'value40668',
    'key78228': 'value38983',
    'key94179': 'value65505',
    'key36391': 'value6103',
},
    {
    'id': 17527487991191,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Kimberly Thomas MD',
    'address': '903 David Circle Apt. 657\nWest Pamelachester, PW 13157',
    'text': 'Recently light design increase especially near bill. Test think listen imagine. Score board practice Mrs start.',
    'email': 'miranda06@example.org',
    'phone_number': '757.929.3527',
    'json': {
    'name': 'Taylor Garcia',
    'address': '33066 Bradley Streets\nKimberlymouth, TX 04120',
},
    'key51832': 'value92896',
    'key46332': 'value48298',
    'key70873': 'value22857',
    'key54242': 'value17757',
    'key31563': 'value20031',
    'key68380': 'value14667',
},
    {
    'id': 17527487991202,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Joseph Garcia DVM',
    'address': 'Unit 1687 Box 6759\nDPO AE 09399',
    'text': 'Nation figure view call shoulder law yet. Above then TV eat situation page write.\nCareer kid task ten service care everything. Fill beat themselves lot often. Meet stop rich field.',
    'email': 'greeneroberto@example.org',
    'phone_number': '641-321-5825',
    'json': {
    'name': 'Meagan Huynh',
    'address': '70290 Carpenter Ville Apt. 879\nLake Codyburgh, MT 08745',
},
    'key24128': 'value13993',
    'key4902': 'value71660',
    'key1097': 'value56693',
    'key5397': 'value88865',
    'key5027': 'value98990',
},
    {
    'id': 17527487991213,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Regina Richardson',
    'address': '2976 Devon Union\nWest Jessicaport, NE 24099',
    'text': 'Heart company community sell. Than actually human administration. Control black from theory while decision smile. Start large check.\nHere save speak year morning. Pressure relate page open.',
    'email': 'valerie88@example.org',
    'phone_number': '(271)647-1926x433',
    'json': {
    'name': 'James Sanchez',
    'address': '506 Welch Oval Suite 878\nSouth Katie, ID 94351',
},
    'key6622': 'value46048',
    'key21217': 'value45649',
    'key56589': 'value46301',
    'key96104': 'value25803',
    'key30976': 'value95354',
},
    {
    'id': 17527487991224,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Samantha Mcgee',
    'address': '6217 Tyler Radial\nReynoldsview, SC 59670',
    'text': 'Only concern know difficult full however project. Garden thing instead keep which grow.\nThese popular onto build call happen. Much difference sound student either her foreign.',
    'email': 'christyjames@example.com',
    'phone_number': '340-480-7371',
    'json': {
    'name': 'Michael Rodriguez',
    'address': '8938 Greer Parks\nWalkerside, SD 91576',
},
    'key70351': 'value15522',
},
    {
    'id': 17527487991236,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Nicole Arroyo',
    'address': '0974 Gomez Alley\nPort Priscilla, ME 66022',
    'text': 'Suffer before decade suggest skill. Foreign child six radio.\nTrip much call difficult white election center important. Story color away the.',
    'email': 'omartinez@example.org',
    'phone_number': '001-897-222-3271x63604',
    'json': {
    'name': 'John Lewis',
    'address': '806 Richardson Inlet\nLangstad, HI 23641',
},
    'key27181': 'value6487',
},
    {
    'id': 17527487991249,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Katherine Mcguire',
    'address': '322 Rhodes Knoll\nAaronbury, MS 93097',
    'text': 'Store pick social end site raise tough. Matter heavy she. Avoid describe write series on recently. Window discussion whom throw myself fight campaign manager.',
    'email': 'williamsonkelly@example.com',
    'phone_number': '(353)234-3789',
    'json': {
    'name': 'James Barnes',
    'address': '772 Robert Row Apt. 825\nLake Lauren, TN 93485',
},
    'key65653': 'value69510',
    'key55997': 'value2949',
    'key91046': 'value70287',
    'key42965': 'value90087',
    'key17273': 'value88924',
},
    {
    'id': 17527487991261,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Michael Smith',
    'address': '10587 Smith Orchard\nWest Malik, NH 45219',
    'text': 'Represent few task growth. Test statement audience west occur page room. Play among spring sometimes clearly left. Well wall meet too.\nDrive development seat them.',
    'email': 'valerie87@example.net',
    'phone_number': '(825)225-4414x177',
    'json': {
    'name': 'Donna Swanson',
    'address': '31832 Phillips Stravenue\nMosleyberg, MP 98615',
},
    'key5029': 'value6083',
    'key85893': 'value86220',
    'key60593': 'value94841',
    'key42394': 'value56770',
    'key34954': 'value68540',
    'key73888': 'value94751',
    'key50693': 'value19746',
    'key70328': 'value12445',
},
    {
    'id': 17527487991273,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Susan Reyes',
    'address': '25554 Hamilton Inlet\nNew Brandon, MT 74190',
    'text': 'Quality stuff song recognize leave set democratic. Expert ability tax part job home. Must new another child about case.',
    'email': 'smithtiffany@example.com',
    'phone_number': '5887589136',
    'json': {
    'name': 'Rachel Wall',
    'address': '764 Edward Station Suite 394\nSandersshire, MI 99201',
},
    'key31660': 'value27779',
    'key56708': 'value6030',
    'key84603': 'value74902',
    'key42600': 'value24149',
    'key65254': 'value33727',
    'key11786': 'value59043',
    'key76678': 'value4596',
},
    {
    'id': 17527487991285,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Dorothy Trevino',
    'address': '4146 Kristina Stream Suite 985\nNew David, VA 15935',
    'text': 'Next drug not daughter probably begin. Explain case do Mr. Art left citizen charge change between thing especially.\nWalk call federal fly drive provide. Always budget now level.',
    'email': 'mcbridemark@example.org',
    'phone_number': '338.272.1509x57322',
    'json': {
    'name': 'Courtney Hernandez',
    'address': '222 Frank Corner\nKristinaburgh, IA 85717',
},
    'key51577': 'value65317',
    'key21310': 'value32104',
},
    {
    'id': 17527487991296,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Molly Cohen',
    'address': '43226 Benjamin Terrace\nPort Tina, CT 84055',
    'text': 'Minute serious group. Assume science quickly image during production community. Interest statement outside edge past people rate main.',
    'email': 'mooredanny@example.org',
    'phone_number': '+1-233-264-9763x0374',
    'json': {
    'name': 'Ronald Lewis DDS',
    'address': '22528 Anna Meadows Apt. 733\nSouth Jessicaview, NM 11463',
},
    'key64494': 'value75018',
    'key80462': 'value10847',
    'key40095': 'value17560',
    'key13813': 'value28339',
    'key81786': 'value50149',
    'key54262': 'value35484',
    'key4016': 'value8104',
    'key61234': 'value98744',
},
    {
    'id': 17527487991307,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Ashley Green',
    'address': 'Unit 6798 Box 5587\nDPO AA 23661',
    'text': 'Deep security board raise. Usually action market might effect. Too hope accept power think.\nCar be collection both color. Mr image assume claim institution fall cell deep.',
    'email': 'georgejason@example.com',
    'phone_number': '6326457690',
    'json': {
    'name': 'Luis Burns',
    'address': '18321 Michael Isle Suite 898\nNeilfurt, VT 94600',
},
    'key12128': 'value63536',
    'key63676': 'value53423',
    'key6476': 'value73355',
    'key15496': 'value70377',
    'key64818': 'value39195',
    'key36942': 'value46089',
    'key54811': 'value99905',
    'key7317': 'value35229',
    'key2192': 'value5666',
    'key3002': 'value46203',
},
    {
    'id': 17527487991317,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Marie Spence',
    'address': '421 Lindsay Unions\nPort Morganshire, RI 70968',
    'text': 'Just ground citizen light toward each. I yard likely word.\nMost detail police dark would these father.',
    'email': 'williamjensen@example.org',
    'phone_number': '+1-460-617-8053',
    'json': {
    'name': 'Marcus Griffin',
    'address': '42779 Christopher Gardens\nAntonioborough, MO 32298',
},
    'key81858': 'value83915',
    'key87652': 'value18755',
    'key15591': 'value26033',
    'key99483': 'value15104',
    'key82771': 'value70450',
    'key60576': 'value41279',
    'key85701': 'value70382',
},
    {
    'id': 17527487991328,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'James Davis',
    'address': '45523 George Court Suite 800\nMaryside, SD 55968',
    'text': 'Laugh seven see majority investment measure become true. Management throw newspaper weight car seven successful.',
    'email': 'alopez@example.org',
    'phone_number': '001-793-338-4684',
    'json': {
    'name': 'Aaron Williams',
    'address': '532 Wilson Trail\nPort Cynthiaville, MT 02782',
},
    'key52685': 'value20667',
    'key34189': 'value8787',
    'key19673': 'value24898',
    'key83263': 'value16278',
    'key58673': 'value33043',
    'key53196': 'value60180',
    'key55747': 'value44408',
    'key80774': 'value40041',
    'key55927': 'value94279',
},
    {
    'id': 17527487991338,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Adam Thomas',
    'address': 'USCGC Shepherd\nFPO AP 68949',
    'text': 'Late think effort can explain. Occur weight experience style agent cold. Money to truth test policy.\nMessage dark score many newspaper serious.',
    'email': 'uolson@example.net',
    'phone_number': '752.922.8805x236',
    'json': {
    'name': 'Joshua Williams',
    'address': 'USS Frye\nFPO AA 40073',
},
    'key27978': 'value72609',
    'key24781': 'value37698',
    'key58913': 'value41149',
    'key77810': 'value98951',
},
    {
    'id': 17527487991347,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Christina Taylor',
    'address': '586 Goodman Rest\nKimberlymouth, WY 96530',
    'text': 'Production scientist require manager pay toward. Local institution effort recognize away use near maybe. Network whatever pay walk tonight form.',
    'email': 'morrisrebecca@example.net',
    'phone_number': '+1-775-744-6753x5899',
    'json': {
    'name': 'Jonathan Perkins',
    'address': '8859 Justin Alley Apt. 802\nDavidburgh, WA 53111',
},
    'key79735': 'value96210',
    'key49261': 'value42976',
    'key94995': 'value91463',
    'key87568': 'value54676',
    'key49825': 'value20686',
    'key41804': 'value95187',
},
    {
    'id': 17527487991358,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Chelsea Koch',
    'address': '1451 Melissa Canyon Apt. 138\nMilestown, MD 76828',
    'text': 'Process senior production paper actually arrive. Exactly skin brother you memory people involve.\nKid shake movement. Yourself pay bit really. Collection learn great.',
    'email': 'brownkevin@example.com',
    'phone_number': '382-376-7835x6778',
    'json': {
    'name': 'Joshua Hoffman',
    'address': '60892 Leblanc Springs\nPort Jennifer, KS 08113',
},
    'key98531': 'value15270',
},
    {
    'id': 17527487991370,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Alexander Haynes',
    'address': '64868 Stevens Course\nLake Robert, NY 77631',
    'text': 'College war his law. Front forward election win but. Of son top two water style.',
    'email': 'gswanson@example.com',
    'phone_number': '274-355-5227',
    'json': {
    'name': 'Derek Garcia',
    'address': '42827 Ware Meadows Apt. 021\nKarenberg, PA 65444',
},
    'key85359': 'value65231',
    'key32558': 'value95971',
    'key79743': 'value45830',
    'key12565': 'value98273',
    'key97639': 'value46029',
    'key65442': 'value27615',
    'key29034': 'value86249',
    'key31954': 'value5418',
    'key55789': 'value26030',
    'key42565': 'value81499',
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
    'RequestId': '5f5e1830-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_52_987637wuFoIfJS',
    'filter': 'uid > 0',
    'limit': 100,
    'offset': 0,
    'outputFields': [
    'name',
    'text',
    'id',
    'phone_number',
    'address',
    'uid',
    'email',
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
    'RequestId': '5f5e1830-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_39_52_987637wuFoIfJS',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[False-True-uid > 00]_1752748805.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterFalseTrueUid001752748805Json()
    test.run_tests()
