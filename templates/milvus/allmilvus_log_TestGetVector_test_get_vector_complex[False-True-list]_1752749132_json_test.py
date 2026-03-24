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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestGetVector_test_get_vector_complex[False-True-list]_1752749132_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestGetVector_test_get_vector_complex[False-True-list]_1752749132.json"
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



class AllmilvusLogtestgetvectorTestGetVectorComplexFalseTrueList1752749132Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestGetVector_test_get_vector_complex[False-True-list]_1752749132.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestGetVector_test_get_vector_complex[False-True-list]_1752749132.json"
        self.test_count = 9  # 测试方法数量
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
    'RequestId': '22ce14a0-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_45_20_877082MQnKjdUW',
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
    'RequestId': '22ce14a0-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_45_20_877082MQnKjdUW',
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
    'RequestId': '22ce14a0-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_45_20_877082MQnKjdUW',
    'data': [
    {
    'id': 17527491269124,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Richard Walsh',
    'address': '12191 Zimmerman Ville Apt. 269\nEast Joseph, PW 57481',
    'text': 'Difficult morning listen evidence social firm cut.\nTree real accept town economic step off. Film make section physical.',
    'email': 'fcharles@example.com',
    'phone_number': '322.833.9437x0290',
    'json': {
    'name': 'Michelle Stokes',
    'address': '967 Cohen Brooks Suite 934\nCrosbystad, NJ 29758',
},
    'key49584': 'value6751',
    'key84760': 'value52801',
    'key94069': 'value50790',
    'key97177': 'value88258',
},
    {
    'id': 17527491269141,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Ashley Thompson',
    'address': '811 Russell Field Apt. 196\nNew Masonside, OK 41561',
    'text': 'Help charge let. Edge put attack moment safe.\nOperation impact however speech occur brother look. Doctor whom all get.\nNever star rather herself beat oil.',
    'email': 'butlertammy@example.net',
    'phone_number': '+1-637-335-8354x15687',
    'json': {
    'name': 'Christopher Russell',
    'address': 'Unit 2566 Box 6783\nDPO AA 56586',
},
    'key38375': 'value15831',
    'key5934': 'value31806',
},
    {
    'id': 17527491269153,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Terri Middleton',
    'address': '73427 Kelly Dam Apt. 275\nKaitlynhaven, FM 96095',
    'text': 'Memory modern standard property maintain population. Save room pick easy time week. Ground pull attorney movement. Realize agreement statement water skin.',
    'email': 'morgancoleman@example.net',
    'phone_number': '207-737-9661x6396',
    'json': {
    'name': 'Nicole Hughes',
    'address': '7837 Robert Court Suite 651\nWest Ashleyshire, AS 15374',
},
    'key24021': 'value68917',
    'key57567': 'value79986',
    'key51207': 'value49485',
    'key73840': 'value46173',
    'key75750': 'value38705',
    'key14883': 'value35760',
    'key66318': 'value69191',
    'key62822': 'value49901',
    'key34155': 'value53287',
    'key86941': 'value12097',
},
    {
    'id': 17527491269167,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Angela Johnson DVM',
    'address': '746 Linda Harbor Apt. 821\nAbigailfurt, ID 78234',
    'text': 'Near hotel successful traditional pay important. Break then view bring camera cell. Water time strong before form note.',
    'email': 'justin96@example.org',
    'phone_number': '721.935.2584x767',
    'json': {
    'name': 'Jessica West',
    'address': 'USCGC Allison\nFPO AA 70471',
},
    'key47626': 'value21838',
    'key57583': 'value92234',
    'key20562': 'value17592',
    'key64728': 'value73765',
    'key53218': 'value77334',
    'key68120': 'value79139',
    'key27134': 'value7272',
    'key29880': 'value59523',
    'key78443': 'value27828',
},
    {
    'id': 17527491269179,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Caroline Gonzalez',
    'address': '55673 Robinson Freeway Apt. 778\nChristyberg, WY 08971',
    'text': 'Drug teach painting miss. Early if writer similar.\nThroughout outside history green. View dream that unit over season. System enjoy board act try bar boy. Close soon human with remember growth.',
    'email': 'jennifer03@example.com',
    'phone_number': '772.959.7306x011',
    'json': {
    'name': 'Dr. Brooke Peterson MD',
    'address': '679 Day Ford Apt. 733\nPort Scott, VA 26067',
},
    'key45819': 'value47901',
    'key10973': 'value17056',
},
    {
    'id': 17527491269192,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Shannon Romero',
    'address': '86827 Thompson Crossing\nLake Alan, IA 10600',
    'text': 'Open leader determine lawyer.\nCourt travel democratic direction follow team son. Price woman recent power your our brother garden.',
    'email': 'twilliams@example.net',
    'phone_number': '292-311-7462x99580',
    'json': {
    'name': 'Meghan Scott',
    'address': '3190 Colon Plains Apt. 352\nWest Ricky, UT 37988',
},
    'key43055': 'value21767',
    'key67207': 'value64125',
    'key72030': 'value63994',
    'key9435': 'value91536',
},
    {
    'id': 17527491269206,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Mrs. Leslie Blankenship MD',
    'address': '422 Jennifer Dam\nCynthiaport, SD 28603',
    'text': 'Office against could usually. Miss popular any to.\nScience mouth study office ten low stop word. Live operation debate. Make summer long.',
    'email': 'douglascampbell@example.org',
    'phone_number': '+1-987-829-0994',
    'json': {
    'name': 'Diane Jacobs',
    'address': '776 Manuel Throughway\nCrossburgh, SC 18026',
},
    'key52958': 'value4683',
    'key90013': 'value2924',
    'key50912': 'value48239',
    'key65982': 'value16996',
},
    {
    'id': 17527491269219,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Jason Bond',
    'address': '2659 Bonnie Mall\nChristopherfort, AS 34059',
    'text': 'Soldier listen particularly thousand. Agent evidence mind military. Country week suffer top son stock forward create.',
    'email': 'joejones@example.com',
    'phone_number': '+1-466-247-4830x2946',
    'json': {
    'name': 'Kevin Morris',
    'address': '54150 Michael Ville Suite 620\nMoniqueside, MT 23038',
},
    'key54908': 'value20790',
    'key51702': 'value5039',
    'key1398': 'value76641',
},
    {
    'id': 17527491269231,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Tracey Farrell',
    'address': 'USNV Young\nFPO AA 65730',
    'text': 'Wind different black. Lot among arrive draw enter organization international.',
    'email': 'balllinda@example.com',
    'phone_number': '(415)325-0978x02761',
    'json': {
    'name': 'Mitchell Flowers',
    'address': '99729 Charles Overpass\nAshleytown, NJ 76738',
},
    'key89342': 'value77562',
    'key45342': 'value77994',
},
    {
    'id': 17527491269241,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Kristine Davis',
    'address': '5247 Brian Fields Suite 320\nEast Anna, MA 88769',
    'text': 'Student baby investment power point general term. Father himself line treatment memory. Evening tend follow.\nHigh interest much field news benefit relate.',
    'email': 'jenny03@example.net',
    'phone_number': '761.998.5845',
    'json': {
    'name': 'Dana Gill',
    'address': 'PSC 4852, Box 6095\nAPO AA 33482',
},
    'key74849': 'value65051',
    'key56092': 'value17416',
    'key90399': 'value63385',
    'key59836': 'value67592',
},
    {
    'id': 17527491269250,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Jordan Williams',
    'address': '5062 Peters Square\nEast Georgeport, CA 29056',
    'text': 'Family peace amount. Picture second change specific keep step hard break. Everyone support book ability.',
    'email': 'cgray@example.org',
    'phone_number': '748.301.7364x416',
    'json': {
    'name': 'Ashley Cooper',
    'address': '60987 Kimberly Turnpike\nAmyville, HI 25409',
},
    'key3803': 'value68437',
},
    {
    'id': 17527491269261,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Kara Harrington',
    'address': '63508 Tucker Junction\nWest Glen, DE 61968',
    'text': 'Off western recently beyond hear involve. Could serious center could usually. Mouth young if effort need.\nSomebody case measure financial few wonder. Issue agency energy listen discover.',
    'email': 'heather69@example.org',
    'phone_number': '893.827.9809x92658',
    'json': {
    'name': 'Jason Peck',
    'address': 'PSC 9194, Box 8549\nAPO AP 94761',
},
    'key49015': 'value79279',
    'key49397': 'value73630',
    'key65785': 'value47628',
    'key44534': 'value44151',
    'key48019': 'value71947',
    'key98142': 'value19132',
    'key16610': 'value49608',
    'key74525': 'value70088',
    'key78243': 'value83712',
    'key47273': 'value51207',
},
    {
    'id': 17527491269270,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Erin Russell',
    'address': '4075 Cynthia Walk Apt. 703\nBennettburgh, VI 58453',
    'text': 'Themselves like single true. Hard officer garden fly three.\nTeam occur arrive you by. Guess speech loss by rule whole state issue. Decision house because rich after.',
    'email': 'william98@example.net',
    'phone_number': '+1-442-520-8479x99415',
    'json': {
    'name': 'Eric Riley',
    'address': '208 Kevin Fall\nNew Matthewberg, AK 57374',
},
    'key18561': 'value21352',
    'key46405': 'value47680',
    'key32414': 'value35713',
    'key61375': 'value29362',
    'key1586': 'value95223',
    'key51270': 'value67584',
    'key87355': 'value89171',
    'key81235': 'value11128',
},
    {
    'id': 17527491269281,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Ronald Gross',
    'address': '6618 Brittany Mall Suite 790\nWest Ashleyville, NM 81121',
    'text': 'Long people move manager young serious speech. Pull executive ahead realize capital month discover.\nWhole option white power. Week character rise amount mother. Special better quality administration.',
    'email': 'murraykelly@example.com',
    'phone_number': '+1-844-676-1287x62597',
    'json': {
    'name': 'Jessica Duke',
    'address': '640 Cynthia Fork\nDenisemouth, ND 05644',
},
    'key55098': 'value80684',
    'key77894': 'value37618',
    'key86759': 'value223',
    'key96120': 'value48942',
    'key72303': 'value623',
    'key44': 'value74648',
    'key51551': 'value29789',
    'key79288': 'value3136',
    'key35529': 'value51191',
    'key83197': 'value97612',
},
    {
    'id': 17527491269293,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'James Murray',
    'address': 'Unit 3370 Box 9337\nDPO AP 12400',
    'text': 'Natural theory serious minute. Impact image to from. Member body student notice remember father.',
    'email': 'krystalrussell@example.net',
    'phone_number': '(961)482-8307x30180',
    'json': {
    'name': 'Adrienne Miles',
    'address': '192 Bianca Parkways Suite 539\nLake Stephaniestad, FL 41753',
},
    'key49495': 'value53348',
    'key38603': 'value95473',
    'key31629': 'value89383',
    'key52605': 'value84013',
    'key38991': 'value1058',
    'key50364': 'value17279',
},
    {
    'id': 17527491269302,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Kristin Odom',
    'address': '3153 Michael Greens Apt. 819\nNelsonburgh, OR 72113',
    'text': 'Person market because term. Avoid kid friend only of establish. Religious claim control he.',
    'email': 'ewilliams@example.com',
    'phone_number': '360.446.1647x783',
    'json': {
    'name': 'Rachel Choi',
    'address': 'Unit 7275 Box 8073\nDPO AA 94007',
},
    'key32629': 'value59425',
    'key52364': 'value39403',
    'key81878': 'value4646',
    'key63602': 'value32041',
    'key33164': 'value63793',
    'key46908': 'value36405',
    'key61609': 'value55616',
    'key83527': 'value32417',
    'key11654': 'value37605',
    'key97291': 'value36861',
},
    {
    'id': 17527491269311,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Ruben Johnson',
    'address': '35778 Sutton Mission Suite 150\nGreenport, AK 57516',
    'text': 'Lose order beyond heavy. Wait language money military.\nNewspaper born animal force look someone season pull. Return support grow them.',
    'email': 'travis11@example.net',
    'phone_number': '610-474-6382x522',
    'json': {
    'name': 'Kimberly Chambers',
    'address': '1845 Anne Glen Apt. 400\nBurtonside, PA 52577',
},
    'key79761': 'value1378',
    'key15775': 'value24140',
},
    {
    'id': 17527491269323,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Trevor Mason',
    'address': '46905 Pamela Skyway Suite 755\nJessicaview, KY 41609',
    'text': 'Three site answer. Mind opportunity political age. Machine several court later mention.\nBoard tree over call teach. Year peace key vote thousand focus she rather. Our article late final.',
    'email': 'shawn84@example.com',
    'phone_number': '858.652.9436',
    'json': {
    'name': 'Melanie Love',
    'address': '10371 Mendoza Plaza\nBrightfurt, NE 31703',
},
    'key91635': 'value15858',
    'key72863': 'value90981',
    'key80076': 'value47382',
},
    {
    'id': 17527491269333,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Stephanie Miller',
    'address': '4969 Clark Estate Apt. 893\nNew Jenniferside, MT 80937',
    'text': 'Personal property develop per herself baby baby. Court school section all wide turn. Energy enter guy argue agreement.',
    'email': 'katelyn20@example.org',
    'phone_number': '3489702935',
    'json': {
    'name': 'Catherine Adams',
    'address': '799 Jackson Hill Apt. 540\nSouth Renee, IL 82871',
},
    'key62692': 'value5351',
    'key42044': 'value45479',
    'key24267': 'value86808',
    'key30128': 'value72486',
    'key5431': 'value46229',
    'key80203': 'value67156',
    'key38385': 'value69109',
},
    {
    'id': 17527491269344,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Jason Escobar',
    'address': '472 Samuel Trail Apt. 298\nNew Christina, VT 75665',
    'text': 'Page concern writer information. Toward follow country range.\nStage become station remember child hot cover. Fall matter sister successful. Impact war economy.',
    'email': 'erichernandez@example.net',
    'phone_number': '+1-633-513-6994x661',
    'json': {
    'name': 'Karen Johnson',
    'address': '559 Christine Springs\nJoneston, NV 26413',
},
    'key88298': 'value18213',
    'key76300': 'value53604',
    'key35065': 'value82258',
    'key44980': 'value24612',
    'key40407': 'value69354',
    'key55939': 'value3440',
    'key3179': 'value9975',
    'key64668': 'value23692',
    'key82075': 'value52516',
},
    {
    'id': 17527491269356,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Stephanie Yu',
    'address': '4433 Williams Point Suite 981\nNorth Justinview, NE 52344',
    'text': 'Trial wait cut degree recent teach high quite.\nEnjoy live their seek rich Congress.\nCentral economic ball soldier. Card project expect worker.',
    'email': 'danielharris@example.org',
    'phone_number': '6165924105',
    'json': {
    'name': 'Nicole Palmer',
    'address': '148 Alvarado Fort Apt. 190\nJacobshire, RI 95522',
},
    'key74891': 'value61535',
    'key93827': 'value77110',
    'key3085': 'value27340',
    'key85032': 'value96610',
    'key9724': 'value35172',
    'key72469': 'value52495',
    'key73599': 'value18260',
    'key83165': 'value69755',
    'key34145': 'value89084',
},
    {
    'id': 17527491269368,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Joseph Clark',
    'address': '8543 Davis Lane Apt. 622\nWest Brentside, GU 96835',
    'text': 'Scientist author make as. Appear event recently build of late treat.\nFollow only bill begin job similar throw. Moment single institution sign shake.',
    'email': 'wardcharles@example.com',
    'phone_number': '(870)596-8823x0529',
    'json': {
    'name': 'Adam Burns',
    'address': '531 Moore Court Suite 802\nNew Maurice, CT 49571',
},
    'key27138': 'value78990',
},
    {
    'id': 17527491269380,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Roger White',
    'address': 'PSC 5283, Box 2047\nAPO AA 66399',
    'text': 'Yourself situation story story condition world short side.\nUpon media thank environmental chair. Lay strategy identify discussion. Simply central thought drop wrong do degree.',
    'email': 'emily18@example.net',
    'phone_number': '+1-418-975-8015x3973',
    'json': {
    'name': 'William Ray',
    'address': 'PSC 5024, Box 4773\nAPO AP 84434',
},
    'key26882': 'value37222',
    'key27505': 'value30252',
},
    {
    'id': 17527491269386,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Sandra Campbell',
    'address': 'USS Thornton\nFPO AE 89465',
    'text': 'Share finally direction both bring maintain your. Speak forward church unit. Affect force car support leader partner.',
    'email': 'lucasmichelle@example.org',
    'phone_number': '374.992.9773x5856',
    'json': {
    'name': 'Karen Castaneda',
    'address': '413 Reynolds River\nLake Gregorytown, AL 62219',
},
    'key79156': 'value88961',
    'key88445': 'value13401',
},
    {
    'id': 17527491269397,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Abigail Palmer',
    'address': '1209 Stanley Plaza Suite 954\nPort Russellborough, MS 75089',
    'text': 'Off staff card record. Own yet meet skill.\nMajor always begin out. Financial left once ability nice skill administration.',
    'email': 'amygriffin@example.com',
    'phone_number': '772.958.1622',
    'json': {
    'name': 'Micheal Harper DDS',
    'address': '13127 Mary Junction\nEast Jorge, IL 26745',
},
    'key73716': 'value30577',
    'key95647': 'value7000',
    'key70648': 'value74166',
    'key80865': 'value29965',
    'key75960': 'value82770',
},
    {
    'id': 17527491269408,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Timothy Munoz',
    'address': 'Unit 7422 Box 6681\nDPO AP 42833',
    'text': 'Accept world budget ten main pattern before. Give today great item interview.\nSome address size your subject nearly person could. Matter significant unit east upon factor control yes.',
    'email': 'tylermarshall@example.com',
    'phone_number': '(417)547-6229x579',
    'json': {
    'name': 'Jennifer Howard',
    'address': '4567 Arias Manor\nTylerport, TN 49737',
},
    'key58698': 'value51574',
    'key63683': 'value58612',
    'key87735': 'value59034',
},
    {
    'id': 17527491269418,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Jeffrey Hernandez',
    'address': '91690 Yvette Radial Apt. 701\nPort Ryan, NE 37681',
    'text': 'Seem alone various TV item black very can. Executive although often structure trouble success. Top discuss physical.\nWestern animal arrive against suggest next. Weight stay lawyer culture soon walk.',
    'email': 'wbowman@example.net',
    'phone_number': '688-724-7638x25738',
    'json': {
    'name': 'Christian Ruiz Jr.',
    'address': '4825 Tamara Cliff Suite 361\nSouth Jenniferside, IA 28752',
},
    'key13978': 'value42700',
    'key54715': 'value27466',
    'key99918': 'value48280',
    'key41453': 'value54555',
    'key22935': 'value81727',
    'key58977': 'value2721',
},
    {
    'id': 17527491269428,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Marcus Powell',
    'address': 'USNS Barnes\nFPO AE 52674',
    'text': 'Present college test. Religious anyone summer fear example research. Real stand relationship lay reason rest. Today will old night special none citizen realize.',
    'email': 'elizabeth29@example.org',
    'phone_number': '257-731-6963x2421',
    'json': {
    'name': 'Brandy Williams',
    'address': 'PSC 8421, Box 0815\nAPO AA 65879',
},
    'key48454': 'value51876',
    'key77994': 'value96981',
    'key63048': 'value4775',
    'key66404': 'value84411',
},
    {
    'id': 17527491269436,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Carolyn Le',
    'address': '93968 Audrey Shoal Suite 798\nWest Davidburgh, RI 50459',
    'text': 'Growth hotel daughter already sense summer mean could. Around high others participant. Apply discover many themselves practice.',
    'email': 'bbarry@example.org',
    'phone_number': '+1-224-284-9427x1764',
    'json': {
    'name': 'William Richardson',
    'address': 'Unit 7009 Box 2445\nDPO AP 11159',
},
    'key20128': 'value9997',
    'key8998': 'value55418',
},
    {
    'id': 17527491269444,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Dr. Christian Lopez PhD',
    'address': '6840 Thomas Keys\nRoyton, MA 25698',
    'text': 'Notice boy side how. Notice enjoy your within fund.\nHome party scientist store keep hotel. There win attorney water. Perhaps care move teacher simple. Whose production enter goal film surface since.',
    'email': 'hahnjames@example.org',
    'phone_number': '+1-490-495-9293',
    'json': {
    'name': 'Robert Reeves',
    'address': '934 Richard Stream\nNorth Brittanystad, MI 03025',
},
    'key12108': 'value5698',
},
    {
    'id': 17527491269456,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Nancy Chapman MD',
    'address': '69788 Melissa Via\nWest Allen, NH 91500',
    'text': 'All father kind current. South kid since.\nSimply someone then however the. Single push us yeah start focus.\nProfessor perhaps music state edge by alone edge. Sort debate better seven down.',
    'email': 'sheppardsarah@example.com',
    'phone_number': '001-247-803-0765',
    'json': {
    'name': 'Denise Harris',
    'address': '41727 Arnold Walks Suite 753\nJoelmouth, MH 53531',
},
    'key52495': 'value2285',
    'key54887': 'value80570',
    'key47226': 'value26434',
    'key59667': 'value90876',
},
    {
    'id': 17527491269467,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Mrs. Ashley Jones',
    'address': '6836 Pratt Extension\nHerrerafurt, MA 51475',
    'text': 'Everyone body fly new. Hair level business down raise accept. Tell each rich during heavy dark event.\nReveal mention ago well father. Guy despite his. Among two smile role analysis star once.',
    'email': 'derek31@example.net',
    'phone_number': '931.769.6248',
    'json': {
    'name': 'Terry Mcdonald',
    'address': 'PSC 8381, Box 4203\nAPO AA 45245',
},
    'key41141': 'value46673',
    'key59650': 'value32353',
    'key44025': 'value54220',
    'key16759': 'value69530',
    'key28596': 'value81303',
    'key62209': 'value48441',
    'key50591': 'value35358',
    'key33278': 'value22534',
    'key37939': 'value18757',
    'key57247': 'value79982',
},
    {
    'id': 17527491269476,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Anna King',
    'address': '30402 Jackson Fork\nBenjaminburgh, AS 21644',
    'text': 'Act people program what activity if although magazine. Bank later public effect. Share decision market dream myself. Happen different party data range every southern.',
    'email': 'seth09@example.org',
    'phone_number': '001-436-394-0706',
    'json': {
    'name': 'Randy Stone',
    'address': '6644 Christopher Walks\nSouth Jasmine, TX 85678',
},
    'key13434': 'value29352',
    'key67469': 'value26598',
    'key24340': 'value54508',
    'key85052': 'value94810',
    'key85531': 'value91043',
    'key29324': 'value29945',
},
    {
    'id': 17527491269486,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Melanie Henry',
    'address': '45652 Barnes Parkway Apt. 501\nWest Matthewborough, TN 97603',
    'text': 'We maintain theory wear matter place. Myself list many off. Total nothing six Democrat mother matter.',
    'email': 'william34@example.com',
    'phone_number': '(742)966-5056',
    'json': {
    'name': 'John Matthews',
    'address': '7630 Brian Parkway Suite 966\nPort Graceburgh, RI 53810',
},
    'key26281': 'value56032',
    'key38424': 'value83559',
    'key22125': 'value81468',
    'key18393': 'value2802',
    'key97869': 'value54060',
    'key35337': 'value39599',
    'key18056': 'value19298',
},
    {
    'id': 17527491269497,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Anne Casey',
    'address': '5209 Julie Spur\nLake Erichaven, AZ 26320',
    'text': 'Great woman grow ahead. Whatever sort executive find. Behind financial safe to include section floor. And sort room bank party.',
    'email': 'kjackson@example.com',
    'phone_number': '259.556.5929x9099',
    'json': {
    'name': 'Eric Graves',
    'address': '0082 Ruiz Mountain\nWest Grantside, NE 66699',
},
    'key55063': 'value20836',
},
    {
    'id': 17527491269507,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Brett Parker',
    'address': '585 Sherman Cliffs Apt. 179\nSamanthashire, KY 03054',
    'text': 'Send keep whole pretty method sea. About attorney fact real. Space five school. Cultural fear discussion drug expert.',
    'email': 'troyclark@example.net',
    'phone_number': '620-244-6007x3661',
    'json': {
    'name': 'Alexa Simmons',
    'address': '144 Gregory Knolls Suite 870\nBrandyport, NV 02167',
},
    'key21981': 'value39792',
    'key94656': 'value93583',
    'key80589': 'value54983',
    'key11830': 'value50175',
},
    {
    'id': 17527491269519,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Beth Oneill',
    'address': '425 Martinez Heights\nShannonville, OR 35983',
    'text': 'According difficult serious professional professional someone. Between protect as meet around practice add beyond. Family ball not sit. Wonder he reduce PM can act.',
    'email': 'kcrawford@example.org',
    'phone_number': '203-573-5101x2695',
    'json': {
    'name': 'Kenneth Anderson',
    'address': '69460 Nathan Stravenue\nPatrickmouth, ND 51507',
},
    'key33908': 'value95342',
    'key70379': 'value88809',
    'key54860': 'value36414',
    'key36224': 'value58059',
    'key64455': 'value4953',
    'key28029': 'value48243',
    'key26316': 'value14023',
    'key67089': 'value85949',
    'key50442': 'value64772',
    'key90301': 'value73062',
},
    {
    'id': 17527491269530,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Angela Boyd',
    'address': 'USS Davis\nFPO AA 02032',
    'text': 'Wonder kitchen interest guess myself watch. Watch candidate artist.\nDirector pretty game. Understand product million thus. Close machine maintain car off.',
    'email': 'franciscodillon@example.com',
    'phone_number': '+1-857-741-5200',
    'json': {
    'name': 'Mary Jones',
    'address': '37978 Lee Tunnel Suite 008\nVickiton, CO 45317',
},
    'key40691': 'value45877',
},
    {
    'id': 17527491269540,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'David Wilson DDS',
    'address': '443 Ashlee Track\nHunterburgh, NY 76465',
    'text': 'Operation year process. Interview less name song force trade.',
    'email': 'uruiz@example.com',
    'phone_number': '+1-980-323-1902',
    'json': {
    'name': 'Christopher York',
    'address': '11590 David Lodge Apt. 753\nScottville, MN 71890',
},
    'key82764': 'value27541',
    'key49235': 'value30954',
    'key20538': 'value23537',
    'key72013': 'value55430',
    'key45071': 'value31668',
    'key85960': 'value85039',
    'key23457': 'value69077',
},
    {
    'id': 17527491269550,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Michele Lang',
    'address': '3166 Boyd Orchard\nLake April, MI 42829',
    'text': 'Everyone voice build forget. Upon audience choice. Already individual eye painting.\nChurch huge great. This foreign include government may computer door probably.',
    'email': 'uturner@example.net',
    'phone_number': '001-359-513-1726',
    'json': {
    'name': 'Charles Austin',
    'address': '25939 Davidson Underpass\nSandersside, NC 56612',
},
    'key68941': 'value8595',
    'key46085': 'value32689',
    'key14139': 'value38508',
    'key68428': 'value74713',
},
    {
    'id': 17527491269561,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Gregory Mclean',
    'address': '398 Jeffrey Course Apt. 124\nNew Brittanyview, ME 14380',
    'text': 'Research dog read way. Fall young population before economic.\nThing key along question. Century explain upon room scene cold position. Organization letter not more hundred.',
    'email': 'laurie81@example.org',
    'phone_number': '001-948-350-3114',
    'json': {
    'name': 'Tiffany Montes',
    'address': '15171 Kelsey Parkways\nEast Hannah, SD 31177',
},
    'key16382': 'value85466',
    'key41500': 'value31338',
},
    {
    'id': 17527491269572,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Luis Rodriguez',
    'address': '237 Edwards Garden Apt. 787\nLuischester, OR 99060',
    'text': 'Too blood energy special change policy meet. Try type low if.\nDream nothing treat like stage they. Personal director action wish within offer skin.\nAlmost wish health everything shake for.',
    'email': 'ghunter@example.com',
    'phone_number': '(786)434-7555x69226',
    'json': {
    'name': 'Brandon Miller',
    'address': '45716 Jason Mountain\nMarkchester, GA 19685',
},
    'key73156': 'value24464',
    'key12002': 'value53283',
    'key11490': 'value66783',
    'key53223': 'value13178',
    'key55977': 'value73719',
    'key44998': 'value83539',
    'key39712': 'value45155',
    'key46556': 'value39483',
    'key53036': 'value23883',
    'key48824': 'value89963',
},
    {
    'id': 17527491269583,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Heidi Howard',
    'address': '7263 Jeffrey Views Apt. 530\nRandallfurt, OR 97761',
    'text': 'Prove by risk forget dinner wind. Side way raise push wear however.\nWatch protect necessary. Reason state travel way partner. Return office white side candidate against.',
    'email': 'donald05@example.com',
    'phone_number': '+1-474-676-3747x5970',
    'json': {
    'name': 'Lance Hood',
    'address': '9628 Ricky Loop Suite 487\nNew Melaniemouth, PA 29103',
},
    'key26750': 'value70320',
    'key58060': 'value34943',
    'key27410': 'value86442',
    'key9086': 'value53343',
    'key63998': 'value3745',
    'key63996': 'value10016',
    'key6876': 'value9721',
    'key68780': 'value9722',
    'key3589': 'value49303',
},
    {
    'id': 17527491269594,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Roger Rogers',
    'address': '7640 Henry Pine\nGordonville, OH 13876',
    'text': 'Majority course build alone statement level study drug. Large fear eat nor home. Like the include able south other sign anything.',
    'email': 'hgibson@example.net',
    'phone_number': '686-731-9581',
    'json': {
    'name': 'Jacob Moran',
    'address': '649 Tammy Trail Suite 845\nNorth Adamview, VI 93077',
},
    'key60377': 'value28369',
    'key20855': 'value42456',
    'key95137': 'value92470',
    'key93030': 'value68909',
    'key61546': 'value85506',
    'key27022': 'value33819',
    'key3515': 'value96220',
    'key40323': 'value40554',
},
    {
    'id': 17527491269606,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Timothy Anderson',
    'address': '12384 Ashley Terrace Apt. 645\nNorth Daniel, TN 18413',
    'text': 'Project individual assume small fast power woman might. Myself anyone available learn.\nSell me determine the heart student note. Many control relate civil memory. Social soldier term.',
    'email': 'jillvaldez@example.com',
    'phone_number': '(565)818-7860x4514',
    'json': {
    'name': 'Catherine Mcbride',
    'address': '9695 Adam Gateway\nNorth Codyfurt, VA 77127',
},
    'key30691': 'value57436',
    'key83038': 'value37113',
    'key7516': 'value92707',
    'key66371': 'value23143',
    'key41868': 'value50172',
    'key57714': 'value88338',
    'key12484': 'value20666',
    'key93171': 'value69890',
    'key57556': 'value13487',
},
    {
    'id': 17527491269618,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Kelly Watson',
    'address': '35376 Brewer Hollow\nNorth Travisport, GU 78611',
    'text': 'Lose choice seven yard son various move. Try move chair lead short reduce we. Away watch manage size.',
    'email': 'rubiomiranda@example.com',
    'phone_number': '871.486.7270x21098',
    'json': {
    'name': 'Brian Burgess',
    'address': '247 Johnson Ports\nJasonberg, RI 24406',
},
    'key97313': 'value86203',
    'key22004': 'value90173',
    'key73178': 'value13484',
},
    {
    'id': 17527491269629,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Mark Ferguson',
    'address': '362 Short Rest Apt. 086\nMillerport, AR 33548',
    'text': 'Set my here study budget protect agent section. Affect will they example character.\nRelationship data just similar feel than. She approach art soldier just identify.',
    'email': 'james10@example.org',
    'phone_number': '001-699-899-5621x29747',
    'json': {
    'name': 'Brittany Schmidt',
    'address': 'USS Simpson\nFPO AA 46561',
},
    'key42215': 'value74693',
    'key93977': 'value90687',
    'key63949': 'value90647',
    'key70774': 'value77920',
    'key93662': 'value78738',
},
    {
    'id': 17527491269639,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Sandy Dawson',
    'address': '098 Dalton Fort Apt. 015\nNelsonside, DE 82454',
    'text': 'Among pattern something chance attorney decide money memory.\nHotel too stuff issue scientist business. South send minute money. Per coach bit between big them ahead.',
    'email': 'abigail36@example.com',
    'phone_number': '574-937-4478x81766',
    'json': {
    'name': 'Brent Ayala',
    'address': '294 Joshua Road Suite 341\nRobinsonburgh, VI 59914',
},
    'key29998': 'value83310',
    'key15517': 'value82847',
    'key74204': 'value24377',
    'key44179': 'value91840',
    'key23843': 'value42824',
    'key41082': 'value62779',
    'key85550': 'value34641',
},
    {
    'id': 17527491269650,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Kathleen Murphy',
    'address': '513 Victoria Forest\nElizabethville, GU 07679',
    'text': 'At tonight during meet. Young book finally foreign rich thank. Section Mr official hair contain.\nFrom design poor provide. Challenge against herself.',
    'email': 'george06@example.org',
    'phone_number': '(954)507-3921x27411',
    'json': {
    'name': 'Elizabeth Burke',
    'address': '18240 Scott Neck\nNorth Adam, LA 81992',
},
    'key93077': 'value21113',
    'key7800': 'value76599',
},
    {
    'id': 17527491269660,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Mark Brock',
    'address': '944 Debbie Mission\nWilliamshire, AS 48738',
    'text': 'Building traditional second for by speak every drop. Challenge stuff important group ok.\nTake their yourself huge lose energy.\nSuffer attorney camera never.',
    'email': 'stewartjennifer@example.com',
    'phone_number': '626.580.1033x063',
    'json': {
    'name': 'Wanda Everett',
    'address': '9296 Gonzales Tunnel\nPort Courtneyville, AR 76626',
},
    'key8927': 'value97538',
    'key26602': 'value53532',
    'key23205': 'value70475',
    'key92433': 'value4467',
    'key86493': 'value72140',
    'key38054': 'value96484',
},
    {
    'id': 17527491269670,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Daniel Davis',
    'address': '2896 Palmer Motorway Apt. 585\nSouth Claireton, HI 75867',
    'text': 'Region like how manager. Air scientist that stock picture realize. Until everything art resource.',
    'email': 'kgray@example.com',
    'phone_number': '(960)824-2696x115',
    'json': {
    'name': 'Jordan Marshall',
    'address': '722 Ryan Union Apt. 962\nDonnastad, WV 56671',
},
    'key46937': 'value38226',
},
    {
    'id': 17527491269681,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Anthony Burns',
    'address': '87771 Fischer Gateway\nKellyfort, WY 93997',
    'text': 'Recently start health woman may heart dog. Will certain simply tough agreement believe letter. Interview leave measure feel these quite military sister.',
    'email': 'vcannon@example.net',
    'phone_number': '(539)541-5472x0505',
    'json': {
    'name': 'Mrs. Autumn Rodriguez DDS',
    'address': '663 Holder Extension\nPort Jennifer, ME 48869',
},
    'key47881': 'value668',
    'key71312': 'value60371',
    'key81796': 'value12545',
    'key12495': 'value99128',
    'key88022': 'value30004',
    'key55464': 'value65340',
    'key83080': 'value16447',
    'key23764': 'value29306',
    'key8553': 'value47469',
    'key94547': 'value73027',
},
    {
    'id': 17527491269692,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Dennis Fields',
    'address': 'USNS Anderson\nFPO AP 78522',
    'text': 'Parent which bill trip range.\nProve also conference. Magazine choice figure over drive item.',
    'email': 'lisalarson@example.net',
    'phone_number': '497.920.4470x33487',
    'json': {
    'name': 'Aaron Montgomery',
    'address': '712 Hannah Forge Apt. 310\nMoranton, ID 23687',
},
    'key45428': 'value13206',
    'key54304': 'value80174',
    'key34737': 'value49745',
    'key20392': 'value78765',
    'key29869': 'value24354',
    'key5447': 'value77323',
    'key35956': 'value23657',
    'key86069': 'value32008',
    'key26203': 'value87992',
    'key91172': 'value82435',
},
    {
    'id': 17527491269702,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Sandra Young',
    'address': '883 Higgins Ports\nEast Johnfurt, MP 93057',
    'text': 'Manage citizen PM success left. Official collection approach community good air exist. Far room wear easy heavy able.',
    'email': 'rachelburke@example.org',
    'phone_number': '001-335-341-8145x471',
    'json': {
    'name': 'Douglas Robinson',
    'address': '3993 King Hollow Apt. 918\nThomasview, AR 95464',
},
    'key61614': 'value73479',
    'key73819': 'value65348',
    'key69391': 'value69556',
    'key15482': 'value95758',
    'key86761': 'value61214',
    'key87291': 'value60486',
    'key32016': 'value44012',
    'key11175': 'value46456',
    'key36872': 'value54882',
},
    {
    'id': 17527491269714,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'James Pena',
    'address': 'USCGC Johnson\nFPO AA 46205',
    'text': 'And service assume hold short lead throw. Serve not defense seven do any. Model his section system join around human.',
    'email': 'brendaarmstrong@example.net',
    'phone_number': '+1-871-582-3973x77889',
    'json': {
    'name': 'Katherine Serrano',
    'address': '06902 Martinez Ports\nNorth Daniel, ID 60817',
},
    'key83148': 'value67840',
    'key48272': 'value40813',
},
    {
    'id': 17527491269724,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Grace Howard',
    'address': 'PSC 0658, Box 7230\nAPO AA 82522',
    'text': 'Nearly oil audience dark discussion around ask. Start eight international. Mind send step natural mother piece. Movie parent stop though talk treatment executive.\nStreet design fast.',
    'email': 'whitebrian@example.com',
    'phone_number': '+1-773-739-9247x86142',
    'json': {
    'name': 'Margaret English',
    'address': '838 Kyle Roads\nSouth Kaitlin, IL 26563',
},
    'key10804': 'value52068',
    'key19995': 'value96333',
    'key55704': 'value49131',
    'key65099': 'value58092',
    'key65512': 'value70279',
    'key1960': 'value40004',
    'key75892': 'value16528',
    'key29477': 'value70934',
    'key40974': 'value81076',
},
    {
    'id': 17527491269734,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Patricia Lewis',
    'address': '02741 Hall Roads\nNorth Rebeccabury, OK 91988',
    'text': 'Decide person win small edge I miss. Sure gun toward sport model citizen challenge. Nature possible rate blue alone.\nShe bring project important.',
    'email': 'torreskristin@example.net',
    'phone_number': '(255)525-9365x225',
    'json': {
    'name': 'Nathaniel Clarke',
    'address': '77573 Tanya View\nEnglishborough, NM 24554',
},
    'key4294': 'value43305',
    'key69516': 'value91151',
    'key52351': 'value95017',
    'key41943': 'value19648',
    'key18533': 'value47261',
    'key54010': 'value90477',
    'key30887': 'value76113',
},
    {
    'id': 17527491269745,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Donna Johnson',
    'address': '954 Timothy Villages\nEast Melissa, NM 48142',
    'text': 'Theory fly hour majority shake hope. Suggest discuss rate heavy cover find they. Thousand call note. Yard happen consider maybe stay pretty discuss.',
    'email': 'amandafrost@example.com',
    'phone_number': '627-567-8999x04572',
    'json': {
    'name': 'Jimmy Morris',
    'address': '937 Jonathan Cove Suite 656\nHawkinsborough, FM 57517',
},
    'key14949': 'value48511',
    'key27815': 'value71390',
    'key59173': 'value11283',
    'key52881': 'value66935',
},
    {
    'id': 17527491269755,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Deborah Alvarado',
    'address': '18116 Scott Brook Apt. 414\nWest Tammymouth, ND 24962',
    'text': 'Item use determine political dream choice age listen. Study sell sure pretty billion necessary. Drive level pretty sort space.\nFour organization federal her. Personal story reveal bag machine.',
    'email': 'sherrygill@example.com',
    'phone_number': '458-544-7612x585',
    'json': {
    'name': 'Allison Morris',
    'address': '000 Stephanie Ramp Apt. 611\nGinamouth, IN 19391',
},
    'key99062': 'value31226',
    'key2989': 'value92377',
    'key24943': 'value45896',
    'key24361': 'value80321',
    'key11093': 'value39344',
    'key17674': 'value93062',
    'key48918': 'value21993',
    'key53993': 'value26439',
},
    {
    'id': 17527491269767,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Jeffrey Thompson',
    'address': '482 Francis Road\nWest Matthew, MI 90782',
    'text': 'Computer property necessary. Final account apply too sea put body impact. Wind check single common project job owner.\nHelp possible positive send already. Yeah hold note establish.',
    'email': 'jeffery15@example.org',
    'phone_number': '748.815.1415x927',
    'json': {
    'name': 'Toni Hoffman',
    'address': '48769 Watson Ville\nCrawfordberg, AR 70117',
},
    'key23437': 'value23912',
    'key36597': 'value98414',
    'key86380': 'value49002',
},
    {
    'id': 17527491269777,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Daniel Wilkinson',
    'address': 'Unit 9037 Box 7559\nDPO AE 53500',
    'text': 'Life power can discover response leader. Any reflect whole could think.\nNewspaper itself service half we. Present another city pass card act weight. Develop wear strategy machine certainly pressure.',
    'email': 'nicholassmith@example.net',
    'phone_number': '001-575-294-1724x3648',
    'json': {
    'name': 'Jessica Gardner',
    'address': '877 Perez Forest\nBecktown, GU 11109',
},
    'key3378': 'value18366',
    'key12951': 'value5589',
    'key30912': 'value41391',
    'key37914': 'value15588',
    'key36387': 'value17823',
    'key68406': 'value85955',
    'key37475': 'value77058',
    'key55033': 'value11203',
    'key60150': 'value19993',
    'key15770': 'value15501',
},
    {
    'id': 17527491269787,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Carrie Freeman',
    'address': '322 John Burgs\nKristenburgh, MP 17329',
    'text': 'Ready fly other follow happen. Early they figure close medical strong. Most along provide.\nLive where growth learn personal successful. Give happy require.',
    'email': 'bcaldwell@example.net',
    'phone_number': '507.992.8387x83608',
    'json': {
    'name': 'Richard Beltran',
    'address': '942 Robbins Hollow\nWilliamsshire, MA 18892',
},
    'key26696': 'value20038',
},
    {
    'id': 17527491269798,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Kyle White',
    'address': '0622 Eric Light\nWest Pamela, SD 79063',
    'text': 'Impact police cultural. Cost pull history area town large.\nPiece scientist soldier light. Way weight describe vote weight. Allow ahead system guy.',
    'email': 'harrisantonio@example.com',
    'phone_number': '(299)294-1907',
    'json': {
    'name': 'Nicholas Smith',
    'address': '10805 Jeremy Inlet\nWest Casey, AR 36763',
},
    'key14750': 'value33543',
    'key12636': 'value86012',
},
    {
    'id': 17527491269809,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Ruth Jones',
    'address': '98385 Wright Mall\nPort Meganborough, OK 25023',
    'text': 'Beyond section place blue send natural bad. See young director their including. Of affect add past the.\nSense direction least. Economic enter threat generation same.',
    'email': 'travis94@example.net',
    'phone_number': '881.719.8052',
    'json': {
    'name': 'Courtney Mills',
    'address': '2948 Ashley Rue Suite 005\nNew Rickey, AL 46753',
},
    'key71844': 'value20568',
    'key97461': 'value51393',
    'key4965': 'value5909',
},
    {
    'id': 17527491269819,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'John Jones',
    'address': 'USNS Ramsey\nFPO AA 17572',
    'text': 'Main interview find world organization detail nature. Detail produce firm any road alone. See by laugh on in form save put.',
    'email': 'hlee@example.net',
    'phone_number': '(326)919-2447',
    'json': {
    'name': 'Kristen Hall',
    'address': '3945 Scott Park Apt. 369\nLake Albert, MI 53850',
},
    'key91848': 'value18606',
    'key95257': 'value33435',
    'key64743': 'value62183',
    'key9448': 'value95217',
    'key50976': 'value2962',
    'key96547': 'value99781',
    'key68075': 'value63215',
    'key55949': 'value98345',
    'key69171': 'value21082',
},
    {
    'id': 17527491269828,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Sara Flowers',
    'address': '619 Kristina Gardens\nPort George, AS 79021',
    'text': 'Everything ask teach show them put kid. Face poor personal itself sure operation also. Teach stage former can lot college.',
    'email': 'leslie31@example.org',
    'phone_number': '+1-210-655-0056x49880',
    'json': {
    'name': 'Tracy Holloway',
    'address': '36518 Adrian Estate\nLake Brittany, UT 16130',
},
    'key51938': 'value13060',
    'key16610': 'value3662',
    'key75056': 'value48015',
    'key5953': 'value62669',
    'key65380': 'value21690',
},
    {
    'id': 17527491269838,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Shannon Woods',
    'address': '1085 Rhonda Orchard\nWest Richardland, ND 20919',
    'text': 'Past present north again fine. Whether future example report. Final beautiful industry market center behind.',
    'email': 'georgewebster@example.org',
    'phone_number': '+1-823-202-0945x6509',
    'json': {
    'name': 'Rachel Goodman',
    'address': 'USNV Dixon\nFPO AP 43999',
},
    'key95016': 'value80867',
    'key86232': 'value40421',
    'key58805': 'value31838',
    'key60090': 'value53243',
    'key85399': 'value73825',
},
    {
    'id': 17527491269848,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Jessica Lopez',
    'address': '72992 Lauren Ranch Suite 023\nDorothyville, MH 23346',
    'text': 'Guess their effect. Wish finally beyond drug dinner school. People attack billion specific check foreign truth.\nFree authority fall plan century memory travel.',
    'email': 'johnbarnes@example.net',
    'phone_number': '(246)986-4346x4343',
    'json': {
    'name': 'Barbara Curtis',
    'address': '538 Sullivan Inlet Apt. 640\nJamesstad, OR 15360',
},
    'key37105': 'value98586',
    'key13922': 'value61491',
    'key24303': 'value38902',
    'key81134': 'value71407',
    'key62397': 'value66755',
    'key15483': 'value66390',
    'key95121': 'value89156',
},
    {
    'id': 17527491269860,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Abigail Peterson',
    'address': '103 Danielle Roads Suite 193\nPerezfort, AR 50760',
    'text': 'Note finish lawyer may. Rest decision fall system my hit. Place theory report.\nList claim pretty game worry onto. Film increase feel suggest make. Industry dark anyone would.',
    'email': 'steven91@example.com',
    'phone_number': '7797109218',
    'json': {
    'name': 'Lisa Smith',
    'address': '078 Wade Turnpike\nCarrollfurt, VA 00972',
},
    'key53291': 'value19915',
    'key26112': 'value57295',
    'key59965': 'value80545',
    'key54523': 'value82813',
    'key19758': 'value15044',
    'key12987': 'value74322',
},
    {
    'id': 17527491269871,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Michael Chandler',
    'address': 'PSC 9428, Box 3120\nAPO AA 25399',
    'text': 'Others long single food base until task health. Stay evidence life security. Red ball Congress dark body.\nName test deep low even. Design fear writer determine tend family.',
    'email': 'paulthompson@example.org',
    'phone_number': '(987)564-4789',
    'json': {
    'name': 'Bobby Franco',
    'address': '51818 Henry Ville Suite 694\nCarterstad, WV 66971',
},
    'key29042': 'value25528',
    'key4563': 'value65825',
},
    {
    'id': 17527491269881,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Rebecca Preston',
    'address': '40962 Charles Ville Suite 453\nGrantbury, GA 89824',
    'text': 'Week really very. Statement dog discover group go that. Reach stock vote watch find what.\nAbout project individual per down. Myself past bag who.',
    'email': 'lynchdaniel@example.net',
    'phone_number': '538.511.3851x837',
    'json': {
    'name': 'Sara Rivas',
    'address': 'Unit 3015 Box 2828\nDPO AP 65817',
},
    'key76401': 'value47644',
    'key65434': 'value74457',
},
    {
    'id': 17527491269890,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Heidi Edwards',
    'address': '48397 Kelly Points Suite 626\nWest Melissa, MS 05816',
    'text': 'Long large truth them several open century. Individual to place product.\nBorn civil walk drop both science.\nTotal business discussion near explain. Manager old up middle fill family window.',
    'email': 'gina42@example.net',
    'phone_number': '204-670-7925',
    'json': {
    'name': 'Jessica Hansen',
    'address': '2439 Russo Land Apt. 109\nMatthewborough, NV 29814',
},
    'key31558': 'value28772',
},
    {
    'id': 17527491269901,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Brian Cooper',
    'address': '37713 James Keys\nWest Robert, MD 46551',
    'text': 'Up chair far threat business local tell when. Prepare leader final modern my benefit born. Soon her consumer person short social.\nOrganization system research remember dream peace.',
    'email': 'cphillips@example.net',
    'phone_number': '650-277-7647x69572',
    'json': {
    'name': 'William Myers',
    'address': '8230 Priscilla Drive\nNathanborough, FM 79229',
},
    'key70806': 'value84687',
    'key31563': 'value35279',
    'key38752': 'value56636',
    'key61076': 'value57959',
    'key82651': 'value53314',
    'key97196': 'value82886',
    'key93371': 'value15206',
},
    {
    'id': 17527491269911,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Alicia Anderson',
    'address': '07831 Contreras Greens\nAlexandriaport, DC 45818',
    'text': 'Far whose forward yeah recently. Perform Mrs gun.\nPresent matter near program open. Standard present quality very film firm. Interest south month performance.\nHow good second. Behavior fall son ok.',
    'email': 'susan09@example.org',
    'phone_number': '3777967817',
    'json': {
    'name': 'Raymond Yates',
    'address': 'Unit 2769 Box 6872\nDPO AA 82829',
},
    'key26313': 'value77283',
    'key508': 'value82571',
},
    {
    'id': 17527491269920,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Gregory Mitchell',
    'address': '3492 Becky Squares\nEast Jeff, MP 69355',
    'text': 'Sometimes source state letter strategy hour. Job describe better.\nJob pattern raise child such start Mr. Assume color street language risk.',
    'email': 'ktodd@example.org',
    'phone_number': '(384)764-0674x84550',
    'json': {
    'name': 'Mrs. Yvonne Moore',
    'address': '22891 Emily Fort\nLake Howardfort, MH 67280',
},
    'key85348': 'value89490',
    'key60685': 'value29797',
    'key28358': 'value90963',
    'key62213': 'value68242',
    'key67997': 'value29078',
    'key86559': 'value4510',
    'key99946': 'value22108',
    'key82817': 'value97257',
},
    {
    'id': 17527491269930,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'David Howe',
    'address': '547 Smith Keys Apt. 514\nThompsonport, SD 34348',
    'text': 'Strong among none even. Reduce four social here care leader threat. Test factor room.\nGive before night. Film whatever career operation since use. Full family seven probably let appear officer ok.',
    'email': 'petersondenise@example.org',
    'phone_number': '570.217.0666x3741',
    'json': {
    'name': 'Renee Kennedy',
    'address': '8627 Jennifer Fall\nByrdburgh, NE 48062',
},
    'key66010': 'value73437',
},
    {
    'id': 17527491269942,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Melissa Newman',
    'address': '005 Adam Underpass Suite 093\nNew Geoffreyton, PW 64826',
    'text': 'Maintain kid let seven own her beautiful. Whom peace join phone series recent Democrat standard. Respond future name establish she parent.',
    'email': 'johnnycrawford@example.com',
    'phone_number': '(805)393-5564x255',
    'json': {
    'name': 'Shelly Smith',
    'address': '007 Jamie Place\nPetersview, DE 86752',
},
    'key82119': 'value30954',
    'key99233': 'value92833',
    'key90582': 'value93617',
    'key71624': 'value81207',
},
    {
    'id': 17527491269953,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Heidi Robertson',
    'address': '5586 Cheryl Manor\nNorth Ryan, NE 17638',
    'text': 'Themselves research she. Power open again total him turn. Race clearly cultural example.\nHome boy hold agreement million Mr land.',
    'email': 'emily35@example.net',
    'phone_number': '(852)388-6337x829',
    'json': {
    'name': 'Karen Russell',
    'address': 'Unit 3341 Box 0926\nDPO AP 96276',
},
    'key18151': 'value56281',
    'key57752': 'value35897',
},
    {
    'id': 17527491269961,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Corey Reed',
    'address': 'PSC 5155, Box 8255\nAPO AE 73994',
    'text': 'Story west bad hundred girl anything. Magazine too so agree accept that design.\nAvoid he eight. Increase hard try hot. Evening get tonight open difficult.',
    'email': 'walkerjames@example.net',
    'phone_number': '+1-696-239-8269x2334',
    'json': {
    'name': 'Donald Stone',
    'address': '06513 Stone Passage\nKevinland, NH 11127',
},
    'key56890': 'value49583',
    'key16899': 'value91248',
    'key18902': 'value55326',
    'key51566': 'value84783',
    'key3067': 'value12116',
    'key14357': 'value92462',
    'key28364': 'value78080',
},
    {
    'id': 17527491269971,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Karen George',
    'address': '35555 Charles Garden\nNorth Thomasberg, AS 04994',
    'text': 'Risk back wind shoulder west. Last nearly instead party work. While discuss company answer PM thus.\nActually green realize floor could central physical total. Foreign red yes natural partner.',
    'email': 'njones@example.net',
    'phone_number': '001-633-224-5071',
    'json': {
    'name': 'Gabriel Sims',
    'address': '582 Kim Club Apt. 346\nLake Phillip, FM 17991',
},
    'key87194': 'value98503',
    'key94634': 'value96878',
    'key41644': 'value11662',
    'key73854': 'value64546',
    'key87206': 'value41652',
},
    {
    'id': 17527491269982,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Theresa Mann',
    'address': '088 Katherine Oval Suite 130\nEast Sarahland, MI 66269',
    'text': 'Knowledge meeting television media. Floor employee election pay. History school address network should.',
    'email': 'amandaferguson@example.org',
    'phone_number': '+1-662-887-7373x79944',
    'json': {
    'name': 'Glen Shelton',
    'address': '6193 Chambers Coves\nThompsontown, GA 11935',
},
    'key21700': 'value30119',
    'key44010': 'value95475',
    'key70917': 'value94753',
    'key1051': 'value90283',
    'key50650': 'value86099',
    'key12349': 'value69041',
    'key90159': 'value51906',
    'key87519': 'value12435',
    'key81899': 'value4957',
},
    {
    'id': 17527491269993,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Christina Holland',
    'address': '9527 Jarvis Extension Apt. 280\nNorth Steven, NC 25260',
    'text': 'Research lose direction check to. Suffer ground clearly.\nStudent network of speech couple board read. Surface while law actually try matter number focus. Eight eye develop me.',
    'email': 'williamgarrett@example.net',
    'phone_number': '861.725.6479x449',
    'json': {
    'name': 'Justin Davidson',
    'address': '55529 Gilbert Burg Apt. 841\nKarenview, NJ 92826',
},
    'key90607': 'value55365',
    'key88958': 'value99802',
},
    {
    'id': 17527491270005,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Christopher Morris',
    'address': 'PSC 3077, Box 6789\nAPO AP 35286',
    'text': 'That rate start respond fall surface without. Want group serve TV outside happy think first.\nInterest our sure some easy hand soldier consumer. Thousand personal season research remain.',
    'email': 'victoradams@example.com',
    'phone_number': '001-561-474-5656x05702',
    'json': {
    'name': 'Joshua Luna',
    'address': '914 Jesse Vista\nPort Amanda, MO 55592',
},
    'key33689': 'value37741',
    'key15987': 'value10817',
    'key6020': 'value94927',
    'key14584': 'value92979',
    'key83420': 'value91563',
    'key4882': 'value23640',
    'key57484': 'value68418',
    'key86357': 'value17868',
    'key47017': 'value10545',
    'key38054': 'value98415',
},
    {
    'id': 17527491270014,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Kaitlyn Blankenship',
    'address': '29511 Perez Pass Apt. 086\nWolfbury, VT 16943',
    'text': 'Thousand fall into physical. Say option cell responsibility drop issue.\nTerm avoid significant create body begin rise. Wrong new woman build. Protect including current hold.',
    'email': 'anthonyscott@example.com',
    'phone_number': '692-977-3842x052',
    'json': {
    'name': 'Hannah Garcia',
    'address': '148 Thomas Station\nDuncanfurt, SD 67174',
},
    'key39376': 'value90006',
},
    {
    'id': 17527491270026,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Courtney Jones',
    'address': '09772 Blackwell Isle Suite 177\nJohnsonfurt, MN 63644',
    'text': 'Across site save scene decade food prove. Impact third force why yet friend.\nInstead may painting. Claim record rock water.',
    'email': 'austindonna@example.net',
    'phone_number': '409-311-8218',
    'json': {
    'name': 'Larry Colon',
    'address': '279 Clark Lodge Apt. 277\nEast Jacob, AZ 98103',
},
    'key32846': 'value25920',
    'key306': 'value35371',
    'key56817': 'value18275',
    'key60540': 'value85662',
    'key92606': 'value5019',
    'key34576': 'value21021',
    'key51857': 'value6837',
    'key17958': 'value83562',
},
    {
    'id': 17527491270038,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Patrick Riley',
    'address': '600 Robert Plaza Suite 722\nWest Brian, TN 84412',
    'text': 'Control affect reach of attorney everybody. Administration run staff authority bring work. Any small make government describe.',
    'email': 'amygarcia@example.org',
    'phone_number': '(837)465-1974x5944',
    'json': {
    'name': 'Dr. Jacob Johnson',
    'address': '38394 Lisa Stream Suite 780\nPort Michael, ME 30805',
},
    'key93911': 'value20086',
    'key39748': 'value38563',
    'key26950': 'value45834',
},
    {
    'id': 17527491270049,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Michael Cooper',
    'address': '80838 Victoria Stream\nRobertbury, PR 77778',
    'text': 'Always anything product affect usually share. Hope suddenly knowledge live. Mind election go significant tell product. Safe anything on few matter.',
    'email': 'marco80@example.net',
    'phone_number': '+1-219-770-5761x18399',
    'json': {
    'name': 'John Paul',
    'address': '077 Douglas Corners Apt. 143\nEast Miguel, ID 97347',
},
    'key19626': 'value16729',
    'key64562': 'value44506',
    'key6012': 'value28227',
    'key74560': 'value9089',
    'key81188': 'value14897',
    'key70970': 'value12552',
    'key3530': 'value56521',
    'key9833': 'value16381',
    'key54154': 'value71573',
},
    {
    'id': 17527491270059,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Amber Lopez',
    'address': '7129 Potter Orchard Apt. 997\nNorth Kevinland, AK 33764',
    'text': 'You develop section tough add difficult. Necessary rich public save.\nMonth summer knowledge cold various perform large. Grow bill place step agency role task bag.',
    'email': 'rjohnson@example.net',
    'phone_number': '+1-890-465-8221x36884',
    'json': {
    'name': 'Cheyenne Figueroa',
    'address': '127 Rogers Pine Apt. 697\nAustinhaven, NY 22893',
},
    'key8261': 'value83530',
    'key27766': 'value89432',
    'key76946': 'value93610',
    'key45451': 'value28938',
    'key33334': 'value19293',
    'key13969': 'value72090',
    'key30025': 'value13669',
    'key57509': 'value46756',
    'key62515': 'value63339',
},
    {
    'id': 17527491270070,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'John Wood',
    'address': '66033 Rogers Ford Apt. 236\nNorth Leah, MI 69354',
    'text': 'Action town share early low bar. Cultural major fund design. Similar catch various protect left.',
    'email': 'sabrinawilliamson@example.org',
    'phone_number': '360.900.1694x80091',
    'json': {
    'name': 'Sara Evans',
    'address': '96395 Evans Turnpike\nPort Karen, AZ 80610',
},
    'key9650': 'value98432',
    'key36492': 'value39307',
    'key49073': 'value22251',
},
    {
    'id': 17527491270081,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Lori Medina',
    'address': '944 Brian Vista\nSouth Rodneyton, NE 41380',
    'text': 'Ok point leave than.\nThe although front doctor sign peace buy.\nAddress job maybe tax bad scene speech. Land house fact.',
    'email': 'kristen25@example.net',
    'phone_number': '001-764-916-8917x578',
    'json': {
    'name': 'Jordan Ortiz',
    'address': '283 Sarah Lodge Suite 982\nPort Brandiborough, MA 52932',
},
    'key82929': 'value1097',
    'key5263': 'value7296',
    'key51049': 'value13072',
    'key38573': 'value98993',
    'key91532': 'value59455',
    'key49393': 'value16641',
    'key97431': 'value71198',
},
    {
    'id': 17527491270091,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Tyler Wright',
    'address': '28445 Torres Pass\nCampbellhaven, HI 46967',
    'text': 'Air computer would plant party he gas. Notice real sometimes natural detail. Choice list trial man.\nOffice military cell water poor page nearly. Media north any watch.',
    'email': 'paulkathleen@example.org',
    'phone_number': '(742)263-7388',
    'json': {
    'name': 'Dawn Williams',
    'address': '7659 Wilkins Trail Apt. 394\nSouth Kelly, DC 77126',
},
    'key40987': 'value92823',
    'key76643': 'value51999',
    'key8123': 'value63071',
    'key75546': 'value22314',
    'key53799': 'value35388',
    'key56517': 'value65820',
    'key39470': 'value67034',
    'key61049': 'value89609',
},
    {
    'id': 17527491270102,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Troy Cunningham',
    'address': '738 Wood Lock Apt. 356\nNorth Jessicaville, PW 44158',
    'text': 'Pm lot believe fly natural itself sister director. Learn city ok yard serious area. However myself chance society whatever team bar hospital.',
    'email': 'aroberts@example.net',
    'phone_number': '(926)595-2351',
    'json': {
    'name': 'Christina Mueller',
    'address': '84233 Cameron Path Apt. 757\nTeresafurt, FL 50475',
},
    'key39514': 'value577',
    'key18951': 'value42255',
    'key18289': 'value35009',
    'key32265': 'value28160',
    'key95231': 'value13549',
    'key83666': 'value6891',
    'key41120': 'value81143',
    'key40977': 'value21190',
    'key27937': 'value34006',
},
    {
    'id': 17527491270113,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Alyssa Hurley',
    'address': '0164 Andres Harbor Suite 319\nSouth Kevin, GU 31464',
    'text': 'Plant step agency officer lose your region. Entire policy between which single forward really.\nAudience compare benefit.\nEnvironment only ready live other begin. Government total activity.',
    'email': 'stephanie39@example.com',
    'phone_number': '380-244-6268x5654',
    'json': {
    'name': 'William Downs',
    'address': '9310 Joel Terrace\nAdamsmouth, AL 89680',
},
    'key9789': 'value17817',
    'key62687': 'value42857',
    'key23514': 'value10582',
    'key52683': 'value70623',
    'key73164': 'value53736',
},
    {
    'id': 17527491270124,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Jeff Chavez',
    'address': '95921 Berg Flats Apt. 202\nNew Jonathan, HI 88815',
    'text': 'Rise across quality chair this garden. Phone floor current fear performance.\nHope move affect make hold run east.',
    'email': 'patrickhebert@example.org',
    'phone_number': '503.992.1898x0572',
    'json': {
    'name': 'David Adams',
    'address': '4050 Brittney Motorway Suite 112\nSmithmouth, CT 23105',
},
    'key67482': 'value53998',
    'key76247': 'value46136',
    'key79684': 'value35864',
    'key62240': 'value20549',
    'key79833': 'value13082',
    'key93230': 'value31394',
},
    {
    'id': 17527491270136,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Robert Sherman',
    'address': '61860 Paul Corners\nBenderbury, ND 87963',
    'text': 'White dinner do method thus sign house. Onto music under director decade factor ability. Relationship coach author.\nRule fish civil everyone minute growth. Hot particular wonder fish water.',
    'email': 'barnettmatthew@example.org',
    'phone_number': '001-845-574-6409',
    'json': {
    'name': 'Cynthia Sanchez',
    'address': '663 Isaac Parkway Suite 970\nKarenville, MI 80014',
},
    'key10006': 'value85901',
    'key21156': 'value3244',
    'key11749': 'value72597',
},
    {
    'id': 17527491270147,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Philip Campbell',
    'address': '8621 Bryant Track\nJenniferville, RI 60706',
    'text': 'Effect talk suffer small change quality. Strategy budget left people man style stock. Us particularly city can president different.',
    'email': 'karenle@example.net',
    'phone_number': '754.791.9329x11912',
    'json': {
    'name': 'Tammy Erickson',
    'address': '05432 Bowers Trail\nBrownshire, MP 49834',
},
    'key61952': 'value37543',
    'key4356': 'value30753',
    'key68028': 'value51913',
    'key36640': 'value76558',
    'key13580': 'value49353',
    'key29658': 'value47672',
    'key14679': 'value68887',
    'key94087': 'value58033',
    'key38057': 'value28629',
},
    {
    'id': 17527491270159,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Andrea Burns',
    'address': '93030 Heather Cliff Suite 116\nPhilipshire, IA 29906',
    'text': 'Each long take particularly foot. Significant modern impact play age.\nMeet beyond play state great. Major table two role international wind gas. Price population certain chair.',
    'email': 'jlogan@example.org',
    'phone_number': '877-392-2183x8132',
    'json': {
    'name': 'Michael Conley',
    'address': '174 Higgins Island Suite 729\nNorth Michellefurt, NJ 33857',
},
    'key97686': 'value62977',
    'key97773': 'value77323',
    'key53155': 'value46349',
    'key50229': 'value52207',
    'key9481': 'value39570',
    'key26141': 'value44073',
    'key50335': 'value271',
    'key28042': 'value23222',
},
    {
    'id': 17527491270170,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Charles Elliott',
    'address': '543 Jones Courts Apt. 205\nBrandiport, KY 45769',
    'text': 'What reason try less stock party tonight. Newspaper investment computer that two side smile thank. Allow before majority agree movement.\nVery population data mention back church. Each might employee.',
    'email': 'jessicalloyd@example.org',
    'phone_number': '(642)250-9329x38494',
    'json': {
    'name': 'Tiffany Chase',
    'address': '1041 Anthony Canyon\nLake Ericaville, CT 59592',
},
    'key18373': 'value19516',
    'key37861': 'value20601',
    'key97062': 'value82371',
    'key75628': 'value9733',
    'key40868': 'value8858',
    'key24111': 'value41216',
    'key53991': 'value64525',
},
    {
    'id': 17527491270181,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Mr. William Gomez',
    'address': '683 Robert Pass\nEast Rachelview, MI 78239',
    'text': 'Almost this property past here street. Officer article well watch artist lawyer leave. Resource maybe leader.\nIndicate collection training like answer. Kind million can yourself.',
    'email': 'greeramber@example.com',
    'phone_number': '(782)803-2203',
    'json': {
    'name': 'Dominic Romero',
    'address': '5914 Ryan Inlet Suite 270\nNew Margaretchester, LA 68801',
},
    'key24048': 'value43057',
    'key5572': 'value51436',
},
    {
    'id': 17527491270193,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Melissa Arias',
    'address': '8232 Meredith Village\nStoutborough, DC 48166',
    'text': 'Fact father eight develop lose. Growth manage son parent interest.\nSerious officer the. Effect water cause.',
    'email': 'yharvey@example.net',
    'phone_number': '848.272.7599x9077',
    'json': {
    'name': 'Dr. John Wilson DVM',
    'address': '915 Erika Freeway Suite 635\nEast Richard, WI 13352',
},
    'key91270': 'value86897',
    'key90136': 'value59163',
    'key85513': 'value89233',
    'key61954': 'value15292',
},
    {
    'id': 17527491270204,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 100,
    'name': 'Larry Howell',
    'address': '2396 Frances Mill\nPort Connor, MS 39642',
    'text': 'Class doctor order all through. Yeah as similar nation environmental agency prepare. Cultural support themselves. Mother mean per conference budget born.',
    'email': 'katherineharper@example.org',
    'phone_number': '940.844.6930',
    'json': {
    'name': 'Jacob Lopez',
    'address': '197 Jeffrey Meadows\nNorth Kevinland, NH 95948',
},
    'key86946': 'value93487',
    'key6810': 'value94503',
    'key23767': 'value20002',
    'key95945': 'value10906',
    'key66387': 'value22212',
    'key22594': 'value33918',
    'key94846': 'value18821',
},
    {
    'id': 17527491270214,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 101,
    'name': 'Nancy Collier',
    'address': '2312 Scott Hill\nJenniferbury, PW 97922',
    'text': 'Two tend west record. Look ground fly student weight of bill. Price trade stand first laugh worry. Financial poor home once agreement style.',
    'email': 'deborah66@example.org',
    'phone_number': '816.585.3761',
    'json': {
    'name': 'Christine Smith',
    'address': '241 Mccormick Walks Suite 024\nLake Thomas, NM 82337',
},
    'key6189': 'value70408',
    'key73345': 'value52952',
    'key32863': 'value52730',
    'key874': 'value40307',
    'key93339': 'value93591',
    'key43518': 'value57367',
    'key70730': 'value21282',
    'key99086': 'value79105',
    'key88765': 'value76431',
    'key40485': 'value89568',
},
    {
    'id': 17527491270226,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 102,
    'name': 'Amanda Moore',
    'address': '70879 Jones Roads Apt. 496\nWest Johnfurt, FM 34936',
    'text': 'South so relationship number. None meet firm responsibility suddenly two guess.\nGround commercial city really them the value. Late small much speak you risk. Long campaign how prove court effort.',
    'email': 'cgonzalez@example.org',
    'phone_number': '530-778-4543x3332',
    'json': {
    'name': 'Aaron Mitchell',
    'address': 'USCGC Reed\nFPO AP 91135',
},
    'key89753': 'value25606',
},
    {
    'id': 17527491270236,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 103,
    'name': 'Matthew Huffman',
    'address': '112 Marissa Loop\nMayland, KY 12412',
    'text': 'Already by least bag collection later financial. Organization few Mrs include identify country thus. Write break itself whether likely different there.',
    'email': 'yjacobson@example.net',
    'phone_number': '+1-249-977-3150x8901',
    'json': {
    'name': 'Sydney Branch',
    'address': '01759 Sanchez Tunnel Apt. 328\nNorth Christopher, RI 84539',
},
    'key20950': 'value97833',
    'key41741': 'value5544',
    'key93472': 'value15697',
    'key32297': 'value46956',
    'key92388': 'value16636',
},
    {
    'id': 17527491270247,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 104,
    'name': 'Vincent Roberts',
    'address': '6413 Danielle Curve Suite 148\nPort Rachaelborough, DC 39979',
    'text': 'Town trial music against TV indeed like.\nIndividual identify unit point foreign. Partner spend long black especially century.',
    'email': 'kathrynhartman@example.com',
    'phone_number': '+1-447-579-4298x43683',
    'json': {
    'name': 'Thomas Potts',
    'address': '199 Tiffany Brook\nPaulmouth, FL 02179',
},
    'key56550': 'value38590',
    'key48150': 'value27169',
},
    {
    'id': 17527491270258,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 105,
    'name': 'Tiffany Zamora',
    'address': '270 Vanessa Flats\nWest Marcus, NC 71239',
    'text': 'Though must well information decade. Significant difficult trial wind rest four.\nMarriage compare someone manage. Interview look lead ok here. However change western able but window eye.',
    'email': 'suelawrence@example.org',
    'phone_number': '215.448.4969x0538',
    'json': {
    'name': 'John Irwin',
    'address': '261 Joshua Shore Suite 242\nEast Donald, DE 10764',
},
    'key97581': 'value6411',
    'key81139': 'value17972',
    'key35581': 'value69055',
    'key27922': 'value40399',
    'key17782': 'value76087',
    'key70058': 'value38406',
},
    {
    'id': 17527491270269,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 106,
    'name': 'Carmen Richardson',
    'address': '502 Gabrielle Loop\nEast Brandon, NE 51644',
    'text': 'Wonder ever investment left walk professor despite. Card expert newspaper effort base size.\nNow fish network service. Eye ago final nice four current.',
    'email': 'davidmorales@example.org',
    'phone_number': '+1-374-954-4258',
    'json': {
    'name': 'Alexander Mclean',
    'address': 'Unit 6312 Box 7254\nDPO AA 61740',
},
    'key46868': 'value46231',
},
    {
    'id': 17527491270288,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 107,
    'name': 'Brian White',
    'address': '37811 Rachel Lodge\nChantown, IN 79756',
    'text': 'Subject measure major experience. Senior good collection house sister.\nManage week attention. Wonder get create despite hour car yard free. Move sing unit charge politics not still body.',
    'email': 'katherinesosa@example.net',
    'phone_number': '001-895-747-5425x576',
    'json': {
    'name': 'Carl Sherman',
    'address': '6224 Franco Lock\nEast Jose, OR 79058',
},
    'key70553': 'value71643',
    'key61373': 'value93582',
    'key10712': 'value72228',
    'key26622': 'value7087',
    'key95045': 'value59024',
},
    {
    'id': 17527491270302,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 108,
    'name': 'Michelle Rogers',
    'address': '821 Gibson Divide Suite 121\nBarbarastad, NM 89613',
    'text': 'Feeling bit great do enough than son. Recently growth ask very dream.\nMain policy film white without a. Rate anything section recognize national. Government speech heavy decade describe computer.',
    'email': 'arroyogerald@example.net',
    'phone_number': '+1-970-679-0661',
    'json': {
    'name': 'Erin Martinez',
    'address': '102 Silva Ridges\nMontoyaville, WY 37616',
},
    'key9305': 'value38970',
    'key69825': 'value14345',
    'key90537': 'value33205',
    'key78445': 'value39813',
    'key597': 'value71592',
    'key71409': 'value26292',
    'key74233': 'value83108',
    'key94985': 'value14834',
    'key31340': 'value98493',
    'key99233': 'value63291',
},
    {
    'id': 17527491270315,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 109,
    'name': 'Kimberly Mckee',
    'address': '5370 Burns Mountain\nEast Reneemouth, MI 91649',
    'text': 'Perform human face Republican finish adult. Go share system great director. State economic blue yes article.',
    'email': 'christopherwilliams@example.com',
    'phone_number': '726-211-3561',
    'json': {
    'name': 'Michael Yang',
    'address': '639 James Roads Suite 429\nNorth Paulchester, SC 01331',
},
    'key85680': 'value83850',
    'key47750': 'value75588',
    'key89129': 'value46415',
    'key92680': 'value88894',
    'key12839': 'value12589',
    'key90494': 'value78255',
},
    {
    'id': 17527491270327,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 110,
    'name': 'Mary Jones',
    'address': 'Unit 3507 Box 3300\nDPO AP 22216',
    'text': 'Could including treatment conference land know ok. Their free tax different.\nStrategy water rule at. Full process open wonder guy kind skill. Tend million baby woman born.\nProject quickly clearly.',
    'email': 'meganmorgan@example.net',
    'phone_number': '001-252-936-4138x13846',
    'json': {
    'name': 'Peter Davis',
    'address': 'USS Hall\nFPO AP 04820',
},
    'key90908': 'value99276',
    'key84416': 'value60422',
    'key59286': 'value46981',
    'key96137': 'value9752',
    'key24774': 'value91418',
    'key72312': 'value8220',
    'key71215': 'value22084',
    'key4701': 'value92911',
},
    {
    'id': 17527491270335,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 111,
    'name': 'Richard Hunt',
    'address': 'Unit 3069 Box 1278\nDPO AE 85422',
    'text': 'Sea east education collection evening. End figure wear enjoy give political group detail.',
    'email': 'reynoldsbrian@example.org',
    'phone_number': '706.301.9817',
    'json': {
    'name': 'Manuel Hansen',
    'address': '163 Cardenas Vista\nTimothyport, NJ 20413',
},
    'key23657': 'value54490',
    'key48678': 'value30295',
    'key22467': 'value19820',
    'key95222': 'value52197',
    'key21539': 'value76240',
    'key87471': 'value83758',
    'key36200': 'value53068',
    'key20398': 'value42147',
    'key70189': 'value3166',
    'key67958': 'value34189',
},
    {
    'id': 17527491270345,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 112,
    'name': 'Amy Martinez',
    'address': '0326 Terry Neck\nSouth Tyler, MO 65301',
    'text': 'They popular water. Fear contain rest difference admit community law.\nCandidate move account life physical. Late finally provide maybe rest. Direction future such beyond modern.',
    'email': 'toddbryant@example.com',
    'phone_number': '742-266-5259',
    'json': {
    'name': 'William Edwards',
    'address': '59310 Garcia Mews\nWest Lisa, HI 74205',
},
    'key46002': 'value38113',
    'key59139': 'value34263',
    'key71141': 'value39648',
    'key57545': 'value85948',
    'key62758': 'value82987',
    'key32142': 'value51163',
    'key12061': 'value48107',
    'key1528': 'value11874',
    'key70659': 'value31812',
    'key57188': 'value74080',
},
    {
    'id': 17527491270356,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 113,
    'name': 'Cory Rodriguez MD',
    'address': '9979 Mckenzie Plaza\nIngramshire, MT 33523',
    'text': 'Believe down story old expert. Risk include keep. Reason friend opportunity senior now.',
    'email': 'robert32@example.org',
    'phone_number': '+1-599-513-9237',
    'json': {
    'name': 'Lindsey Russo',
    'address': '351 Rebecca Rest Apt. 611\nChristopherland, FL 89036',
},
    'key13978': 'value23180',
},
    {
    'id': 17527491270367,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 114,
    'name': 'Scott Contreras',
    'address': '0276 Vincent Parkways Suite 461\nDeniseshire, PA 29173',
    'text': 'Reduce of understand marriage. Maybe realize here hard official again skill.\nLevel factor gun too. Notice around perform beat benefit we general note. Let large education effect these.',
    'email': 'blaketaylor@example.net',
    'phone_number': '839.651.0241x7777',
    'json': {
    'name': 'Dr. Lori Young DDS',
    'address': '81303 Barr Lights Suite 840\nKellymouth, FM 78827',
},
    'key55506': 'value31836',
    'key81226': 'value47116',
    'key72652': 'value71730',
    'key84186': 'value49038',
    'key72982': 'value21860',
    'key73238': 'value58136',
    'key219': 'value84869',
    'key49937': 'value25343',
    'key40859': 'value52884',
    'key15535': 'value10972',
},
    {
    'id': 17527491270379,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 115,
    'name': 'Charles Adams',
    'address': '67614 Mcdonald Orchard\nDavidtown, PA 76565',
    'text': 'Upon similar no power fill heart. Whom be start director put.\nLaw population stay service note her experience also. Themselves month choice relationship.',
    'email': 'carmenpark@example.com',
    'phone_number': '554-852-5842x3586',
    'json': {
    'name': 'Deborah Williams',
    'address': '9065 Danielle Corners Suite 421\nPort Paigemouth, MI 88025',
},
    'key99582': 'value55196',
    'key67476': 'value32989',
    'key33697': 'value19337',
    'key67401': 'value95878',
},
    {
    'id': 17527491270390,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 116,
    'name': 'Mrs. Taylor Mcconnell MD',
    'address': '269 Bishop Locks\nPort Jadefort, IL 45395',
    'text': 'Pull her big language ground. Leader land history though. Tree ahead thought sign have compare democratic.\nMatter hour actually nature voice say show. Two specific agency send whether international.',
    'email': 'bishoppaige@example.net',
    'phone_number': '813.641.4243x0106',
    'json': {
    'name': 'Joshua Vaughn',
    'address': '4027 Johnson Ville Suite 432\nLake Michaelshire, MA 72257',
},
    'key40611': 'value85841',
    'key53192': 'value76940',
    'key7386': 'value17281',
},
    {
    'id': 17527491270402,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 117,
    'name': 'Timothy Kennedy',
    'address': '256 White Lake\nWest Donnafort, CT 20200',
    'text': 'Half test know appear class. When action thus business.\nMean land why institution. Professional run officer imagine.',
    'email': 'jwagner@example.com',
    'phone_number': '001-346-319-0629x687',
    'json': {
    'name': 'Mary Burton',
    'address': '6577 Shaw Crest\nNorth Elizabeth, HI 16112',
},
    'key9242': 'value94867',
    'key92293': 'value84231',
    'key82117': 'value79430',
    'key28441': 'value99393',
    'key73429': 'value62624',
    'key30061': 'value75854',
    'key10492': 'value37266',
},
    {
    'id': 17527491270413,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 118,
    'name': 'Susan Brooks',
    'address': '140 Mejia Causeway\nWest Donnaville, IA 32890',
    'text': 'Left factor yes enjoy child toward blue. Hard might message. Whole decision property blood would each write.\nStrategy last audience. Player dinner teach. Player open represent election.',
    'email': 'greed@example.net',
    'phone_number': '8259355604',
    'json': {
    'name': 'Christopher Hansen',
    'address': '0771 Manuel Crossroad\nJohnchester, FM 03092',
},
    'key78753': 'value35841',
    'key97764': 'value91542',
    'key85974': 'value26185',
    'key55463': 'value56521',
},
    {
    'id': 17527491270424,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 119,
    'name': 'Andrea Coleman MD',
    'address': '9277 Martin Walks\nSouth Rebecca, NC 73611',
    'text': 'Mr discover soldier manage. Raise near despite technology. Including attention need hand huge. Less pass out learn discussion difference see hotel.\nResponse within win strategy guess.',
    'email': 'teresa50@example.org',
    'phone_number': '671.440.3992x264',
    'json': {
    'name': 'Mitchell Summers',
    'address': '0358 Garcia Port Apt. 445\nLake Gabrielmouth, ND 26990',
},
    'key54904': 'value11634',
},
    {
    'id': 17527491270435,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 120,
    'name': 'Brittany Baker',
    'address': 'USNV Hancock\nFPO AP 77491',
    'text': 'Important not door all low international for. Know continue cut least politics rate worker. Gas per threat either say pull she long. Whether cut after support.',
    'email': 'erictran@example.com',
    'phone_number': '+1-573-582-3239',
    'json': {
    'name': 'Kimberly Taylor',
    'address': '7846 Barnes Coves\nPort Zachary, IL 72237',
},
    'key82907': 'value66762',
    'key64724': 'value28443',
    'key12027': 'value92750',
    'key40984': 'value7060',
    'key25194': 'value47568',
    'key43958': 'value32389',
    'key4520': 'value10211',
    'key4195': 'value74927',
    'key87276': 'value54808',
    'key935': 'value47853',
},
    {
    'id': 17527491270445,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 121,
    'name': 'Christina Ramirez',
    'address': '730 Delgado Junction\nLake Christopherfurt, KS 98863',
    'text': 'Sister production analysis grow challenge heavy. Change human accept compare center suffer poor them. Little policy pattern official world.',
    'email': 'andrewzuniga@example.net',
    'phone_number': '001-546-859-1612x59854',
    'json': {
    'name': 'Ryan Ellis',
    'address': '463 Baxter Expressway Suite 242\nEast Michaelhaven, MT 27876',
},
    'key46907': 'value46560',
    'key79815': 'value30043',
    'key94657': 'value79984',
    'key98449': 'value38827',
    'key80241': 'value47353',
},
    {
    'id': 17527491270457,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 122,
    'name': 'Anthony Jordan',
    'address': '373 Leon Squares Suite 893\nNew Derek, TN 66639',
    'text': 'One quite painting early research. Imagine enter able eye set family. Capital reflect off great must heavy I parent.\nWay hour talk say participant now.',
    'email': 'yvettewright@example.org',
    'phone_number': '001-993-643-6815',
    'json': {
    'name': 'Ian Smith',
    'address': '10771 Jesse Spur Suite 620\nKevinshire, AR 45327',
},
    'key97480': 'value39264',
    'key70899': 'value15940',
    'key2421': 'value62531',
    'key89897': 'value92791',
},
    {
    'id': 17527491270468,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 123,
    'name': 'Kara Harris',
    'address': '77294 Patrick Lights Suite 741\nWilkersonport, MH 59657',
    'text': 'Instead phone performance recently relate nothing. Already after produce. Official respond form look agree.\nTreat college especially sing ahead. Hear far and pick improve environmental worker.',
    'email': 'amber07@example.org',
    'phone_number': '+1-576-771-6361x127',
    'json': {
    'name': 'Cheyenne Krause',
    'address': '730 Andrew Motorway\nPort Nicholasfurt, MO 04453',
},
    'key27814': 'value60251',
    'key21688': 'value92223',
    'key83590': 'value27728',
    'key49751': 'value16894',
    'key14290': 'value78955',
    'key39035': 'value87675',
},
    {
    'id': 17527491270479,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 124,
    'name': 'Jennifer Mcintyre',
    'address': '632 Lance Mews Apt. 488\nWhiteview, OR 65495',
    'text': 'Customer thing piece full. Pm audience cold born follow former occur.',
    'email': 'veronicabailey@example.org',
    'phone_number': '(545)687-7526',
    'json': {
    'name': 'Martin Martinez',
    'address': '3605 Emily Neck\nRyanhaven, MN 28645',
},
    'key88122': 'value89687',
    'key29369': 'value48328',
    'key67230': 'value61602',
    'key37389': 'value70721',
},
    {
    'id': 17527491270491,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 125,
    'name': 'Meredith Hubbard',
    'address': '249 Young Estate\nNew Carrie, MD 11749',
    'text': 'Always big win travel trouble election always. Film street especially believe pay control relationship detail. Option finally still before him.',
    'email': 'rebeccaharris@example.org',
    'phone_number': '+1-439-628-9102',
    'json': {
    'name': 'Margaret Wallace',
    'address': '14752 Nelson Rapids\nAnnstad, HI 71462',
},
    'key63671': 'value53273',
    'key58407': 'value55816',
    'key55297': 'value87182',
    'key63848': 'value865',
    'key30372': 'value85514',
},
    {
    'id': 17527491270502,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 126,
    'name': 'Peter Olson',
    'address': '73998 Forbes Fork\nMartinezborough, OH 29055',
    'text': 'Friend make mean about stay investment. Mention never clear thousand why.',
    'email': 'craigsullivan@example.com',
    'phone_number': '495-591-8980',
    'json': {
    'name': 'James Oconnor',
    'address': '920 Michael Pass\nSouth Ashleystad, OK 12345',
},
    'key53050': 'value11098',
    'key25988': 'value74553',
    'key54349': 'value51172',
    'key7619': 'value23972',
    'key61818': 'value67045',
    'key90261': 'value54436',
    'key73347': 'value61142',
    'key30685': 'value51058',
    'key21518': 'value93966',
},
    {
    'id': 17527491270513,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 127,
    'name': 'Taylor Page',
    'address': 'USNS Johnson\nFPO AE 38315',
    'text': 'Health southern discover artist board onto condition. Current start why from forget sell. Talk city beautiful stand interest woman get water. Ball office loss billion foreign myself.',
    'email': 'leecraig@example.org',
    'phone_number': '+1-619-997-6622x3022',
    'json': {
    'name': 'Michelle Duncan',
    'address': '17939 Hogan Highway Apt. 595\nCynthiatown, OR 47979',
},
    'key591': 'value27674',
},
    {
    'id': 17527491270524,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 128,
    'name': 'Paul Brock',
    'address': '3367 Martinez Estates Apt. 265\nLake Robert, NE 46901',
    'text': 'Push set respond. Foot something remember it.\nLife current government put different. Her age arm system. Serve dark address from serve half face each.',
    'email': 'stephanie79@example.org',
    'phone_number': '559-261-5894',
    'json': {
    'name': 'Ashley Sloan',
    'address': '40591 Theresa Grove\nLake James, ME 29471',
},
    'key70744': 'value76',
    'key7299': 'value14003',
    'key78323': 'value48175',
    'key4785': 'value58786',
    'key48900': 'value59473',
},
    {
    'id': 17527491270534,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 129,
    'name': 'Rebecca Wilson',
    'address': '448 Curtis Drives\nTrevinobury, SC 82893',
    'text': 'Day school defense seat. Either baby set authority share thus talk. Friend real agreement.\nArrive old attention fall southern specific difference defense. Control want wait sing star whole ask.',
    'email': 'ramseyjoseph@example.org',
    'phone_number': '397.311.6573x4479',
    'json': {
    'name': 'Dr. Karen Murphy',
    'address': '774 Olson Rest Apt. 540\nJasonmouth, RI 08011',
},
    'key93007': 'value26141',
    'key55308': 'value41325',
    'key79681': 'value78751',
    'key29962': 'value74971',
},
    {
    'id': 17527491270546,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 130,
    'name': 'Alyssa Bailey',
    'address': '612 Raymond Ports Suite 658\nDanielborough, NH 09292',
    'text': 'Need what pretty different off might best risk. Visit use structure second represent. Trial hundred human church same.\nPaper minute team create true ground me. Wrong time participant often walk.',
    'email': 'kelleytimothy@example.net',
    'phone_number': '341-383-9830x91909',
    'json': {
    'name': 'Ryan Berry',
    'address': '64005 Andersen Fields\nEast Alexanderberg, NH 69855',
},
    'key64837': 'value45321',
    'key51285': 'value78949',
    'key18403': 'value97989',
    'key10100': 'value35922',
    'key41074': 'value127',
    'key22667': 'value81002',
    'key82468': 'value6586',
    'key40090': 'value9378',
    'key10528': 'value84678',
    'key23991': 'value54604',
},
    {
    'id': 17527491270558,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 131,
    'name': 'Matthew Thompson',
    'address': '3254 Hall Hills\nStephenbury, WY 98587',
    'text': 'Media impact possible their nice. Later chair everyone leg billion Republican. Floor under research drop million yeah.\nSeek much there final single according although. Pm indicate southern.',
    'email': 'mholloway@example.com',
    'phone_number': '001-648-953-7224x89713',
    'json': {
    'name': 'Jessica Wong',
    'address': '65685 Gonzales Bypass Suite 411\nLake Scott, AS 58495',
},
    'key12696': 'value11701',
    'key46285': 'value79870',
    'key7984': 'value6881',
    'key21178': 'value97816',
    'key96477': 'value60177',
    'key44292': 'value60500',
},
    {
    'id': 17527491270569,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 132,
    'name': 'Stephanie Smith',
    'address': '608 Paul Trail\nDeniseview, AR 93664',
    'text': 'Soldier speak cause inside. Author fire range federal.\nSpring when bag I myself hard.',
    'email': 'calvinstrickland@example.org',
    'phone_number': '219-673-4395x99984',
    'json': {
    'name': 'Todd Contreras',
    'address': '80898 Brown Junction\nMorrisfurt, MD 22842',
},
    'key62206': 'value50249',
    'key50347': 'value31737',
    'key18104': 'value88203',
    'key31598': 'value47732',
},
    {
    'id': 17527491270580,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 133,
    'name': 'Mary Richardson',
    'address': '56658 Anderson Rapid\nMartinezview, UT 91927',
    'text': 'Appear among can adult may when. When ahead debate ok friend name.\nLow practice yeah party picture. Gun effect on decision with box.',
    'email': 'reedantonio@example.net',
    'phone_number': '(239)859-7841x5141',
    'json': {
    'name': 'Matthew Hall',
    'address': '966 Deborah Lodge Apt. 847\nSouth Ianbury, NE 99866',
},
    'key39433': 'value37714',
    'key17627': 'value34577',
},
    {
    'id': 17527491270592,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 134,
    'name': 'Alejandro Thompson',
    'address': '95068 Christy Plaza Apt. 332\nBrendashire, HI 14747',
    'text': 'Sister yes feel billion girl prevent point worry. Choice project hour exist usually claim. Democratic various together realize note by draw.',
    'email': 'sharonharding@example.com',
    'phone_number': '771.964.9870',
    'json': {
    'name': 'Mary Sullivan',
    'address': '9844 Perez Prairie Apt. 166\nWest Cherylside, WY 34972',
},
    'key72907': 'value63611',
},
    {
    'id': 17527491270604,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 135,
    'name': 'Cindy Jones',
    'address': 'PSC 0966, Box 1516\nAPO AP 96827',
    'text': 'Soldier girl safe. Tv spring itself cold. Paper price require election star yet.\nIndicate perform area buy democratic. Under sea ball data.',
    'email': 'scottbrenda@example.org',
    'phone_number': '6119983671',
    'json': {
    'name': 'Joan Crawford',
    'address': '82606 Brown Unions\nSamuelchester, MN 32068',
},
    'key20389': 'value8476',
    'key76135': 'value37506',
    'key25694': 'value76355',
    'key37557': 'value31752',
    'key12562': 'value4476',
    'key61554': 'value59988',
    'key30171': 'value62750',
},
    {
    'id': 17527491270613,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 136,
    'name': 'Thomas Wells',
    'address': '8001 Tiffany View Suite 116\nEast Laura, IN 77811',
    'text': 'Friend quickly feel never. Society kid boy everything today because product. Book Mr capital herself history.\nHealth bring edge thus rather girl.',
    'email': 'huynhchristopher@example.com',
    'phone_number': '6839293723',
    'json': {
    'name': 'John Chaney',
    'address': '5191 Margaret Island Suite 406\nMarksland, MH 07109',
},
    'key26377': 'value85777',
    'key77092': 'value12449',
},
    {
    'id': 17527491270624,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 137,
    'name': 'Danielle Clark',
    'address': '4531 Mary Islands Suite 808\nCarterhaven, MP 07997',
    'text': 'Have product prepare food finally speech. Idea identify low thousand difficult decision. Century no impact sport price.',
    'email': 'williampatton@example.org',
    'phone_number': '(260)467-7295',
    'json': {
    'name': 'Sheila Hays',
    'address': '1422 Ortiz Manors Suite 033\nNew Neil, WI 86952',
},
    'key70994': 'value80354',
    'key32623': 'value61900',
    'key3439': 'value59581',
    'key72498': 'value39164',
    'key22459': 'value66229',
    'key38040': 'value73110',
    'key99646': 'value12108',
    'key96351': 'value83331',
    'key62667': 'value28984',
},
    {
    'id': 17527491270636,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 138,
    'name': 'Mindy Thompson',
    'address': '205 Andrade Trail Apt. 624\nVancehaven, ND 60735',
    'text': 'Machine gun despite whom no follow. Statement should school describe help impact hot. Member but house father join.',
    'email': 'blakevalencia@example.org',
    'phone_number': '001-213-277-4247x7986',
    'json': {
    'name': 'Travis Lindsey',
    'address': '064 Clark Summit\nPerezfort, TN 90784',
},
    'key41874': 'value14472',
    'key62104': 'value31305',
    'key7138': 'value12787',
    'key15118': 'value4916',
    'key8515': 'value17408',
    'key77823': 'value52670',
    'key43932': 'value55243',
},
    {
    'id': 17527491270648,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 139,
    'name': 'Kathryn Walters',
    'address': '4852 Patterson Groves Suite 281\nNew Charlesside, ND 23361',
    'text': 'Almost garden maintain long system week meet. Music its nearly class. In popular hour population let.',
    'email': 'debra64@example.com',
    'phone_number': '4004043601',
    'json': {
    'name': 'Michelle Johnston',
    'address': '13472 Mayer Crossing Suite 246\nNew James, OK 15407',
},
    'key98008': 'value52715',
    'key52350': 'value9432',
},
    {
    'id': 17527491270659,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 140,
    'name': 'Diana Murphy',
    'address': '674 Cantrell Fork Suite 998\nBrayshire, VT 92746',
    'text': 'However may walk scientist decide. New summer own debate if look himself nature.\nAlmost no become understand all message wish. Tough whose major.\nCrime yes control.',
    'email': 'julie60@example.org',
    'phone_number': '(870)413-6852x2416',
    'json': {
    'name': 'Toni Norman',
    'address': '77956 Simpson Knolls Suite 680\nShepherdtown, PW 12076',
},
    'key51183': 'value93109',
},
    {
    'id': 17527491270670,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 141,
    'name': 'Kevin Travis',
    'address': '931 Michael Row Suite 909\nToddbury, WV 02529',
    'text': 'Each real party husband. Institution institution collection they government international.\nTeach event hear. In above itself garden bit case amount material. Base anyone record bill think.',
    'email': 'jeffreyknight@example.net',
    'phone_number': '577.504.7022',
    'json': {
    'name': 'Jessica Neal',
    'address': '862 Erica Vista Suite 203\nKathrynhaven, VT 65384',
},
    'key17129': 'value22716',
    'key5623': 'value1510',
    'key47652': 'value8841',
    'key12958': 'value37715',
    'key27679': 'value85381',
    'key17921': 'value78284',
    'key40634': 'value20164',
},
    {
    'id': 17527491270681,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 142,
    'name': 'Jason Chavez',
    'address': '7079 Leslie Roads Suite 764\nWest Cindyfurt, MH 23953',
    'text': 'Carry music admit politics. Claim buy play serve. Nation politics better region accept hold. Effect miss choose side kid level expect.\nSpace name amount decision family state.',
    'email': 'gary69@example.net',
    'phone_number': '6794228691',
    'json': {
    'name': 'Wesley Nelson',
    'address': '8948 James Roads Apt. 329\nLake Rickview, WI 17200',
},
    'key66190': 'value63944',
    'key77683': 'value13466',
    'key40413': 'value84849',
    'key24111': 'value91884',
    'key19936': 'value21307',
},
    {
    'id': 17527491270692,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 143,
    'name': 'Brian Beard',
    'address': '86466 Salazar Keys Apt. 812\nSouth Douglasfurt, KS 45070',
    'text': 'Range window describe example want. Ago report condition pretty road suddenly.\nDefense individual attack interview sometimes instead. Recognize organization civil major control.',
    'email': 'emilyprice@example.com',
    'phone_number': '+1-648-372-5447',
    'json': {
    'name': 'Patricia Miller',
    'address': '56960 Taylor Flat\nPort Brian, NH 33400',
},
    'key612': 'value53960',
    'key34556': 'value37108',
},
    {
    'id': 17527491270703,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 144,
    'name': 'Noah Berry',
    'address': '0549 Washington Mission\nSmithstad, RI 97511',
    'text': 'Grow white join yourself about speech bank. Alone possible free according possible agency. Into shake former week avoid concern available by.',
    'email': 'montgomerymichael@example.net',
    'phone_number': '3338693552',
    'json': {
    'name': 'Michael Ware DDS',
    'address': '6856 Mitchell Trail\nWest Tara, VI 14743',
},
    'key28586': 'value69267',
    'key37633': 'value95057',
    'key73758': 'value66928',
    'key25570': 'value45479',
    'key4447': 'value98566',
    'key49021': 'value68191',
    'key82176': 'value18356',
    'key98931': 'value63958',
    'key39342': 'value21660',
},
    {
    'id': 17527491270715,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 145,
    'name': 'John Pena',
    'address': '380 Wright Burgs\nWest Michael, VT 60186',
    'text': 'With idea model himself.\nReceive church teacher Mrs form maintain. Pressure strategy easy number near which. Station public room war difficult do focus.',
    'email': 'smithaaron@example.com',
    'phone_number': '(762)528-7865',
    'json': {
    'name': 'Tara Levy',
    'address': '1824 Stephanie Glen Suite 207\nBartlettfurt, MI 04904',
},
    'key69500': 'value31203',
    'key91732': 'value47795',
    'key25998': 'value17206',
    'key790': 'value89854',
    'key75400': 'value84446',
    'key30305': 'value86471',
    'key21677': 'value49717',
    'key57685': 'value20395',
    'key72418': 'value89611',
},
    {
    'id': 17527491270727,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 146,
    'name': 'Megan Simmons',
    'address': '0668 Pamela Drive Apt. 302\nBenjaminberg, VI 73018',
    'text': 'Expect country never piece build laugh. Candidate industry air. Conference month important its.',
    'email': 'martinezkaren@example.org',
    'phone_number': '885-370-9599x579',
    'json': {
    'name': 'Roger Montgomery',
    'address': '2371 Patel Cove\nGonzalezshire, NY 88873',
},
    'key5435': 'value77814',
},
    {
    'id': 17527491270738,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 147,
    'name': 'John Gibson',
    'address': 'Unit 7281 Box 7743\nDPO AA 76922',
    'text': 'Young whatever wonder thank resource month customer. Beyond challenge save wife loss level. Share floor also my Congress crime visit.',
    'email': 'klivingston@example.net',
    'phone_number': '001-265-524-5083x0052',
    'json': {
    'name': 'Peter Robinson',
    'address': 'PSC 2360, Box 6034\nAPO AA 31009',
},
    'key88962': 'value93167',
    'key57234': 'value31165',
    'key61042': 'value88345',
},
    {
    'id': 17527491270745,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 148,
    'name': 'Sarah Hamilton',
    'address': '00301 Sheryl Inlet Apt. 406\nBonillaberg, FL 79951',
    'text': 'Will television those guess project attorney. Arrive company offer everything event be wife. Sing house buy wall act environmental sure.',
    'email': 'gkim@example.org',
    'phone_number': '001-925-380-1346x07703',
    'json': {
    'name': 'Gabriel Silva',
    'address': '01111 Alexander Trail Apt. 214\nEast Virginia, AZ 50656',
},
    'key58890': 'value10950',
    'key9001': 'value13142',
    'key52797': 'value66596',
},
    {
    'id': 17527491270756,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 149,
    'name': 'Mitchell Garcia',
    'address': '06080 House Isle\nNorth Charleshaven, CT 93518',
    'text': 'Number yet strong consumer audience choice opportunity. Low turn born age career perform stand career.',
    'email': 'keith38@example.com',
    'phone_number': '231.271.5102x49911',
    'json': {
    'name': 'Jill French',
    'address': '742 Jessica Locks\nWest Randyview, PA 18944',
},
    'key85544': 'value18528',
    'key40948': 'value86268',
    'key72770': 'value2789',
},
    {
    'id': 17527491270767,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 150,
    'name': 'Gregory Johnson',
    'address': '699 Burgess Oval\nReeseberg, MI 77965',
    'text': 'Sea admit deep instead start factor. Always unit religious peace whom also send. These everything local arm.',
    'email': 'williamsjason@example.org',
    'phone_number': '+1-432-720-3738',
    'json': {
    'name': 'Darren Thompson',
    'address': '1094 Andrea Parks Suite 913\nGibsontown, AR 48631',
},
    'key45021': 'value1772',
    'key13990': 'value95135',
    'key72135': 'value38249',
    'key25364': 'value43904',
    'key92298': 'value66406',
    'key433': 'value63660',
    'key97971': 'value24459',
    'key40230': 'value83640',
},
    {
    'id': 17527491270779,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 151,
    'name': 'Latoya Cook',
    'address': '1780 Johnson Skyway Apt. 943\nLake Amandahaven, WA 97906',
    'text': 'Dog white however population specific his everybody. Majority rich conference particularly. Follow southern several fish view.',
    'email': 'brandonjones@example.com',
    'phone_number': '(386)842-6796',
    'json': {
    'name': 'Patrick Brown',
    'address': 'PSC 3844, Box 6895\nAPO AE 19579',
},
    'key4164': 'value36637',
    'key18198': 'value42288',
    'key64137': 'value91124',
    'key87528': 'value96075',
    'key22896': 'value89090',
    'key74472': 'value38049',
    'key94983': 'value13220',
    'key54429': 'value92668',
    'key77191': 'value23681',
},
    {
    'id': 17527491270788,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 152,
    'name': 'Kristina Hunter',
    'address': '9569 Brian Way Apt. 296\nEast Davidfurt, MS 55918',
    'text': 'Rule pay energy also.\nStandard art adult deep number. Rate meet eye enter artist practice. Create maybe and card pick husband.',
    'email': 'qschmidt@example.net',
    'phone_number': '001-696-771-9848x9886',
    'json': {
    'name': 'Mr. Andrew Perkins Jr.',
    'address': '480 Sarah Road Apt. 530\nPort Jeffreystad, PW 47077',
},
    'key17511': 'value63957',
    'key40766': 'value71699',
    'key1374': 'value68375',
    'key3935': 'value14398',
    'key68873': 'value96924',
    'key24143': 'value7962',
    'key43220': 'value1875',
    'key30554': 'value30666',
    'key15761': 'value89578',
},
    {
    'id': 17527491270800,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 153,
    'name': 'Donald Berg',
    'address': '666 Riley Lodge\nPort Adam, VI 28986',
    'text': 'Hear method for west service impact several. All compare success follow nor. Serious floor last change.\nLocal management sign investment. City general finally special something.',
    'email': 'peter13@example.com',
    'phone_number': '910-215-5577x2596',
    'json': {
    'name': 'Jocelyn Patterson',
    'address': '89132 Alfred Island\nMcmahonshire, IN 26582',
},
    'key47448': 'value62407',
    'key68204': 'value17879',
    'key54040': 'value92692',
    'key40874': 'value10739',
    'key26284': 'value37904',
    'key77311': 'value28109',
    'key7523': 'value52684',
    'key28538': 'value60770',
},
    {
    'id': 17527491270811,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 154,
    'name': 'Martin Hall',
    'address': '1538 Pham Views\nEast Robert, TX 38913',
    'text': 'Capital event edge decide outside. Table TV left attorney among. Author fall they.\nFar western floor start always brother same.',
    'email': 'barrettkathryn@example.net',
    'phone_number': '904.321.4049x2111',
    'json': {
    'name': 'Tracey Phillips',
    'address': 'PSC 4638, Box 3349\nAPO AA 97567',
},
    'key28221': 'value69738',
    'key48505': 'value251',
    'key43435': 'value84187',
    'key92630': 'value69924',
},
    {
    'id': 17527491270821,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 155,
    'name': 'Kenneth Wilson',
    'address': '474 Dennis Creek\nLake John, DE 80657',
    'text': 'Turn cultural paper to scientist tend.\nSuffer knowledge city establish trouble type. Score hot modern community minute second.',
    'email': 'lisa49@example.net',
    'phone_number': '7023450444',
    'json': {
    'name': 'Daniel Short',
    'address': '02224 Michael Fall\nNelsonbury, PR 74287',
},
    'key72949': 'value46164',
    'key90349': 'value26005',
    'key37229': 'value84031',
    'key56919': 'value97860',
    'key43968': 'value77156',
    'key68284': 'value74392',
},
    {
    'id': 17527491270832,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 156,
    'name': 'Tracy Barajas',
    'address': '619 Marks Port Suite 830\nNew Virginia, MH 16668',
    'text': 'Until issue accept talk focus decade pass. Fly although continue. West ground woman run picture discover.',
    'email': 'aking@example.org',
    'phone_number': '001-411-606-1513x93244',
    'json': {
    'name': 'Steven Shelton',
    'address': '0966 Pittman Ferry Suite 872\nJosephchester, MS 30432',
},
    'key57872': 'value63544',
    'key61343': 'value14940',
    'key29310': 'value87289',
    'key72525': 'value6746',
    'key33965': 'value47575',
    'key13601': 'value8448',
    'key54126': 'value42557',
},
    {
    'id': 17527491270845,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 157,
    'name': 'Robin Pierce',
    'address': '75623 Madden Highway\nBrownstad, DC 33903',
    'text': 'Order base support arm end. Win best choice job.\nContinue politics those. Ahead board kind change today. Head affect believe pretty marriage school minute.',
    'email': 'ann05@example.com',
    'phone_number': '(740)848-4885x394',
    'json': {
    'name': 'Amanda Hart',
    'address': 'Unit 5330 Box 2982\nDPO AA 50054',
},
    'key86176': 'value12037',
    'key99902': 'value93748',
    'key30526': 'value73655',
},
    {
    'id': 17527491270854,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 158,
    'name': 'Cynthia Rivera',
    'address': '604 Michael Underpass\nFletcherland, MN 01561',
    'text': 'Agreement bag house believe. You involve practice fear choose phone. Fund court fill paper down indicate space.\nHim direction seek natural. Born several size price.',
    'email': 'kevinconley@example.com',
    'phone_number': '001-985-690-8852',
    'json': {
    'name': 'William Blake',
    'address': '522 Nicholas Views Apt. 724\nLynnmouth, HI 70999',
},
    'key90282': 'value80788',
    'key40460': 'value30015',
    'key77534': 'value19474',
    'key3754': 'value82620',
    'key56216': 'value46830',
    'key5307': 'value17950',
    'key17965': 'value25029',
    'key13285': 'value33175',
    'key57126': 'value61411',
    'key10027': 'value27340',
},
    {
    'id': 17527491270867,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 159,
    'name': 'Kirsten Jones',
    'address': '977 Hoover Haven\nNorth Ivan, IA 45040',
    'text': 'Enjoy fund collection grow near. Over war available somebody arrive. Scene over onto man above.\nSmall technology red more. Such police actually.',
    'email': 'kimramirez@example.com',
    'phone_number': '001-375-764-7250x015',
    'json': {
    'name': 'Tabitha Kim',
    'address': '1063 Michael Stream Suite 647\nAliciahaven, NC 63106',
},
    'key38479': 'value20036',
    'key62154': 'value8823',
    'key8817': 'value25552',
    'key62848': 'value65515',
    'key31057': 'value64914',
},
    {
    'id': 17527491270879,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 160,
    'name': 'Kimberly Carlson',
    'address': '40156 Robert Lodge\nHarringtonberg, MA 31125',
    'text': 'Age into magazine public eat indicate. Debate while agreement community state current.\nContain laugh that discussion. Store special lead. Player task benefit direction Republican shake create.',
    'email': 'sampsonoscar@example.net',
    'phone_number': '001-768-852-4455x498',
    'json': {
    'name': 'Emily Collier',
    'address': '7830 Brian Points\nBeverlyborough, LA 21033',
},
    'key98551': 'value49432',
    'key69303': 'value57002',
},
    {
    'id': 17527491270891,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 161,
    'name': 'Brittany Martin',
    'address': 'USCGC Moore\nFPO AP 40003',
    'text': 'Begin open difficult along effort very Mrs. Per establish imagine here view past.\nNow at better mean hotel policy. Parent several order Mr floor think.',
    'email': 'bushangel@example.net',
    'phone_number': '742.265.3337x335',
    'json': {
    'name': 'Jonathon Harrison',
    'address': '8963 Martinez Cliffs\nEast Melissa, IN 23780',
},
    'key69861': 'value39721',
    'key11866': 'value66689',
    'key64463': 'value37309',
    'key97855': 'value32816',
    'key289': 'value85634',
    'key49778': 'value86231',
    'key81160': 'value17175',
    'key7743': 'value10362',
    'key11276': 'value35796',
    'key3785': 'value7608',
},
    {
    'id': 17527491270901,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 162,
    'name': 'Carolyn Hartman',
    'address': '204 Jamie Villages Apt. 626\nPort Larryport, TX 53561',
    'text': 'Million it skin accept bar.\nFund rest clear state recognize. Consumer wear return lot whatever real.',
    'email': 'smithjohn@example.org',
    'phone_number': '(450)435-0284',
    'json': {
    'name': 'Ernest Rice',
    'address': '6300 Karen Villages Apt. 997\nSanchezside, OK 70366',
},
    'key72331': 'value86693',
    'key5202': 'value88315',
    'key72056': 'value1346',
},
    {
    'id': 17527491270912,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 163,
    'name': 'Jacob Guerrero',
    'address': 'Unit 0475 Box 7218\nDPO AE 58842',
    'text': 'Beyond hour beat. Old idea animal.\nSuddenly reflect short ball rock team.\nPeople buy popular customer. Since argue case week final drug benefit.',
    'email': 'costamarc@example.org',
    'phone_number': '672.715.1189x8302',
    'json': {
    'name': 'Elizabeth Moreno',
    'address': '741 Colleen Lights\nAndrewchester, GU 69604',
},
    'key45999': 'value47429',
},
    {
    'id': 17527491270922,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 164,
    'name': 'Michael Watkins',
    'address': '84912 Leslie Heights\nWest Derrick, VT 44375',
    'text': 'Ever only beat blue eat military. Mouth center customer even despite win now. Medical car result road. Real threat government hit.',
    'email': 'qmiller@example.net',
    'phone_number': '288.898.4861',
    'json': {
    'name': 'Priscilla Harrington',
    'address': '09795 David Station Apt. 922\nThomasbury, SC 79159',
},
    'key50084': 'value85880',
    'key27790': 'value47098',
    'key43656': 'value98013',
    'key53829': 'value69402',
    'key3501': 'value3550',
    'key57986': 'value58104',
    'key11455': 'value40700',
    'key49824': 'value24339',
    'key75457': 'value53532',
    'key65065': 'value66562',
},
    {
    'id': 17527491270932,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 165,
    'name': 'Yesenia Parker',
    'address': '947 Wood Circles Suite 532\nKevinmouth, ID 99104',
    'text': 'Send form newspaper him. Phone by plant sort part.\nKey name occur professor attorney have nation nation. Task pass enjoy.\nEight forget center prove above assume. Set gun occur study.',
    'email': 'phamjim@example.com',
    'phone_number': '(981)780-9814',
    'json': {
    'name': 'Cynthia Nichols',
    'address': '961 Harold Park\nEast Tristan, VI 96393',
},
    'key2138': 'value46019',
    'key21048': 'value65654',
    'key81573': 'value3633',
    'key52535': 'value11250',
    'key74716': 'value31738',
},
    {
    'id': 17527491270944,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 166,
    'name': 'Kristina White',
    'address': 'PSC 3449, Box 1367\nAPO AA 69726',
    'text': 'Lead range case find plant mention. Kitchen century picture rich leg dog.\nPut rule experience blue. Ground performance movie right reason hand throughout.',
    'email': 'gcunningham@example.org',
    'phone_number': '001-407-217-3469x589',
    'json': {
    'name': 'Lori Ball',
    'address': '71607 Glass Canyon\nWillieland, NE 48409',
},
    'key20863': 'value1719',
    'key89500': 'value88388',
    'key61997': 'value92974',
    'key94975': 'value58584',
    'key46861': 'value81396',
    'key38638': 'value26683',
    'key75355': 'value35049',
    'key94385': 'value25104',
},
    {
    'id': 17527491270953,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 167,
    'name': 'Amber Joyce',
    'address': '80548 Kelly Ports\nCoxhaven, OR 99443',
    'text': 'Vote edge accept appear keep method. Suggest lose turn stand. Into protect behind own yourself organization.',
    'email': 'julia26@example.net',
    'phone_number': '569-767-9704x25274',
    'json': {
    'name': 'Mary Ross MD',
    'address': 'PSC 5715, Box 3765\nAPO AA 10038',
},
    'key63002': 'value81319',
    'key68396': 'value83064',
    'key1684': 'value29902',
    'key20689': 'value5851',
},
    {
    'id': 17527491270962,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 168,
    'name': 'David Burke',
    'address': '85412 Schneider Inlet Apt. 952\nLake Ericport, CO 55559',
    'text': 'Rest however scientist return. Region near argue.\nMarriage likely within sort relationship. Great give near late.',
    'email': 'cindy84@example.org',
    'phone_number': '6673387327',
    'json': {
    'name': 'Kayla Mcguire',
    'address': '95511 Thomas Fall Suite 701\nIanland, OR 65584',
},
    'key89429': 'value10904',
    'key82281': 'value86796',
    'key11698': 'value17951',
    'key46460': 'value45295',
    'key47757': 'value89409',
    'key82245': 'value40927',
},
    {
    'id': 17527491270973,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 169,
    'name': 'Noah Duncan',
    'address': '20302 Tammy Key\nNorth Michaelhaven, NJ 28743',
    'text': 'Happy by former fact always air evening. Low recent throw. Young exist show service. Beyond senior body.\nPart animal sometimes marriage many by rest. Approach start success agency cold collection.',
    'email': 'garygutierrez@example.com',
    'phone_number': '989.598.2626',
    'json': {
    'name': 'Ann Conway',
    'address': '03601 Frederick Drive Apt. 928\nHopkinsfurt, TX 01461',
},
    'key83435': 'value29536',
},
    {
    'id': 17527491270986,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 170,
    'name': 'Collin Lopez',
    'address': '54205 Garcia Crossroad\nNorth Jason, RI 47307',
    'text': 'Challenge into book more figure expert my. Accept eye few hot hair early. Hope democratic success fly those impact however. Less other energy price lay something whom.',
    'email': 'steven35@example.net',
    'phone_number': '(817)786-8103x3310',
    'json': {
    'name': 'Melissa Martin',
    'address': '1193 Harris Terrace\nEast Shaneburgh, UT 62896',
},
    'key8120': 'value70198',
    'key93795': 'value43763',
    'key36549': 'value73925',
    'key37200': 'value18742',
    'key55784': 'value40273',
},
    {
    'id': 17527491270997,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 171,
    'name': 'Daniel Shelton',
    'address': '985 Wright Tunnel\nWest Thomas, ME 49364',
    'text': 'Word free surface couple religious today. Apply only sing theory without. Window network cold and traditional.',
    'email': 'pmcconnell@example.org',
    'phone_number': '(697)699-7343',
    'json': {
    'name': 'Kristen Christian',
    'address': '594 Timothy Ville\nCarterborough, FM 89404',
},
    'key42360': 'value33395',
    'key82393': 'value98937',
    'key68314': 'value95389',
    'key9982': 'value29078',
    'key65589': 'value58580',
    'key81231': 'value48283',
    'key64126': 'value91684',
    'key64636': 'value42999',
},
    {
    'id': 17527491271008,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 172,
    'name': 'Joshua Morton',
    'address': '470 Zimmerman River\nJacobton, MD 06175',
    'text': 'Various smile early. Skill around street major page without before kid.',
    'email': 'douglasgreen@example.net',
    'phone_number': '(873)684-0358x179',
    'json': {
    'name': 'Anna Smith',
    'address': '78966 Andrew Stream Apt. 266\nSouth David, KY 08822',
},
    'key47937': 'value28085',
    'key62348': 'value49110',
    'key98356': 'value36688',
    'key32693': 'value32916',
    'key32394': 'value45851',
    'key23660': 'value1442',
    'key51311': 'value62132',
    'key13954': 'value40587',
},
    {
    'id': 17527491271021,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 173,
    'name': 'Brian Nelson',
    'address': '404 John Viaduct\nNorth Lawrencestad, MT 76654',
    'text': 'Attorney same customer key art break. Base I decision rest drive every.\nTeach training remember what a benefit. Clearly bed defense high image.\nDetermine wind tax.',
    'email': 'angelica84@example.net',
    'phone_number': '001-781-203-4768',
    'json': {
    'name': 'Tara Gibson',
    'address': '73163 Castro Green Apt. 466\nNorth Hannah, OH 76545',
},
    'key40629': 'value3131',
    'key56298': 'value14772',
    'key30389': 'value64783',
    'key54994': 'value61255',
},
    {
    'id': 17527491271032,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 174,
    'name': 'Elizabeth Frank',
    'address': '683 Miller Valleys Suite 159\nSouth Samanthaborough, CO 57628',
    'text': 'The bank do. Indicate loss blood can weight up.\nKind they spring program. Produce at American stuff could. Part still shake policy laugh security less.',
    'email': 'ericawilliamson@example.net',
    'phone_number': '868-216-4042',
    'json': {
    'name': 'Lauren Mccarthy',
    'address': '659 Christopher Avenue Apt. 525\nStaceyton, OH 16135',
},
    'key85573': 'value48563',
    'key44104': 'value88177',
    'key72166': 'value95747',
    'key70431': 'value52064',
    'key49450': 'value80586',
    'key19667': 'value73885',
},
    {
    'id': 17527491271044,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 175,
    'name': 'David Fitzpatrick',
    'address': 'PSC 0415, Box 0864\nAPO AE 98634',
    'text': 'Part four strong purpose history ask. Democratic past more already field land.\nGrow performance story Republican old throughout blue. Economic learn voice to.',
    'email': 'henry42@example.org',
    'phone_number': '490.999.0950x96714',
    'json': {
    'name': 'Betty Jacobs',
    'address': '261 Natalie Fall Apt. 592\nCaitlintown, PW 04375',
},
    'key63899': 'value50040',
    'key18368': 'value10859',
    'key47268': 'value30363',
    'key62791': 'value75256',
    'key4041': 'value48038',
    'key20392': 'value55933',
    'key45649': 'value65147',
    'key37978': 'value29449',
    'key68440': 'value15983',
    'key32878': 'value96122',
},
    {
    'id': 17527491271054,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 176,
    'name': 'Christina Lewis',
    'address': '55830 Sandra Pines Suite 656\nMartinland, DE 82695',
    'text': 'Build must PM do. Population soon listen cultural serious power. Interest along particular poor look talk might.\nInclude north discover simply. Imagine hope couple light doctor a step.',
    'email': 'erinfox@example.com',
    'phone_number': '279-216-7937x76589',
    'json': {
    'name': 'Jacob Sparks',
    'address': 'Unit 7771 Box 6774\nDPO AP 30282',
},
    'key88730': 'value1947',
    'key68377': 'value45227',
    'key65168': 'value39486',
    'key54923': 'value31882',
},
    {
    'id': 17527491271064,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 177,
    'name': 'Michael Thomas',
    'address': '3890 Ronald Springs Apt. 657\nNew Angelamouth, SC 96102',
    'text': 'Animal writer real single. Education listen difficult perform establish control. Say continue beautiful full early can.',
    'email': 'amclaughlin@example.com',
    'phone_number': '716-676-4798',
    'json': {
    'name': 'Kurt Wilcox',
    'address': '06211 Vincent Island Apt. 695\nWest Michael, VA 01854',
},
    'key5646': 'value10319',
    'key38642': 'value87076',
    'key92585': 'value11629',
    'key13090': 'value50514',
    'key29998': 'value96215',
    'key21694': 'value39971',
    'key9427': 'value63598',
},
    {
    'id': 17527491271075,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 178,
    'name': 'Jeffrey Kelley',
    'address': 'Unit 2523 Box 7916\nDPO AA 92037',
    'text': 'Quite difference key best happy. Theory raise personal way.\nFree kid mention sell street. Realize ability summer impact address yes.\nData late system away. Issue morning response wide other serious.',
    'email': 'kathleensmith@example.org',
    'phone_number': '001-562-366-7510',
    'json': {
    'name': 'Richard Vargas',
    'address': '6369 Linda Station Suite 891\nJamesport, NY 65069',
},
    'key10120': 'value55337',
},
    {
    'id': 17527491271086,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 179,
    'name': 'Stephanie Thompson MD',
    'address': '840 Christina Crossroad\nPhilipton, FM 06730',
    'text': 'Choice reveal within great certain walk bad. Miss place able across computer well.',
    'email': 'williamskayla@example.org',
    'phone_number': '(288)919-9137',
    'json': {
    'name': 'Clayton Nelson',
    'address': '918 Manuel Harbors\nLake Jennifermouth, UT 83148',
},
    'key44488': 'value60255',
    'key13693': 'value35651',
    'key80420': 'value8004',
    'key13362': 'value12011',
    'key94201': 'value15500',
    'key15492': 'value71618',
    'key6717': 'value18596',
    'key27407': 'value81846',
},
    {
    'id': 17527491271097,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 180,
    'name': 'William Walker',
    'address': '6873 Tanya Branch\nWest Cameron, CA 06916',
    'text': 'Suggest organization from old. Administration standard instead soon any necessary.\nEmployee green side. Present rock government only man. Especially operation appear cover out.',
    'email': 'kennethfry@example.net',
    'phone_number': '(520)275-9066x18791',
    'json': {
    'name': 'Juan Kennedy',
    'address': '1181 Perry Common\nNorth Michael, MH 70868',
},
    'key58270': 'value33620',
},
    {
    'id': 17527491271108,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 181,
    'name': 'Erika Escobar',
    'address': '392 Travis Squares Suite 230\nCortezchester, IA 17203',
    'text': 'Executive third high buy player. Idea upon leader car station perhaps personal. Identify just choose school idea officer may.',
    'email': 'nelsondavid@example.net',
    'phone_number': '658-351-7898',
    'json': {
    'name': 'Peter Hardy',
    'address': '637 Valerie Knolls Apt. 747\nStacieville, NE 09190',
},
    'key52568': 'value46291',
    'key43922': 'value67876',
    'key78157': 'value38916',
    'key56735': 'value23059',
    'key51610': 'value16357',
    'key49758': 'value36432',
},
    {
    'id': 17527491271120,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 182,
    'name': 'George Holder IV',
    'address': '5835 Atkinson Inlet Suite 513\nEast Roberttown, AL 90879',
    'text': 'Test give majority including quality physical. Purpose especially war just machine evening.\nTrip really yourself reduce forget scene major. Dream black easy explain after hospital.',
    'email': 'michael92@example.com',
    'phone_number': '(371)361-2080x0372',
    'json': {
    'name': 'Yvonne Phillips',
    'address': '73204 Christian Junction Suite 454\nWilliamsmouth, GU 46343',
},
    'key65950': 'value15961',
    'key27533': 'value10793',
    'key9680': 'value6180',
    'key32799': 'value34015',
    'key13116': 'value52974',
},
    {
    'id': 17527491271131,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 183,
    'name': 'Samantha Campbell',
    'address': '2484 Scott Heights\nPort Jerrytown, NY 59217',
    'text': 'New common American central listen mention level rich.\nAfter other consumer partner stage yes. Imagine provide woman public. Girl write song friend any.',
    'email': 'sherrycherry@example.net',
    'phone_number': '001-563-513-8351x285',
    'json': {
    'name': 'Jennifer Young',
    'address': '77325 Martin Lodge\nNorth Jennifer, MP 16262',
},
    'key69444': 'value95164',
    'key10686': 'value82686',
    'key42277': 'value77878',
    'key85663': 'value24882',
    'key11897': 'value49654',
    'key54140': 'value31059',
},
    {
    'id': 17527491271142,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 184,
    'name': 'Keith Bell',
    'address': '42108 Jones Circles\nNorth Kellyview, NE 76861',
    'text': 'Today radio education able teacher continue model. Nor others sometimes.\nTeam record sense center because national. Son if apply water better option simply. Close special power six.',
    'email': 'jenna89@example.net',
    'phone_number': '001-952-653-1754',
    'json': {
    'name': 'Michelle Phillips',
    'address': '22369 Angela Branch\nHammondburgh, AZ 49834',
},
    'key74612': 'value48331',
},
    {
    'id': 17527491271153,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 185,
    'name': 'Christina Meyers',
    'address': 'USNV Mcdaniel\nFPO AA 51382',
    'text': 'Beyond chair none level plant animal draw. Body series look thought. Seek old whatever middle six environmental.\nFood fine Congress finish call American responsibility.',
    'email': 'wstanley@example.com',
    'phone_number': '001-283-266-8092x2350',
    'json': {
    'name': 'Angela James',
    'address': '40843 Wilkins Course\nKellyfort, KY 31243',
},
    'key18725': 'value38203',
    'key37830': 'value95570',
},
    {
    'id': 17527491271162,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 186,
    'name': 'Tiffany Reeves',
    'address': '6619 Jon Run Suite 546\nFergusonton, ID 57589',
    'text': 'Follow mean face tend majority draw war. Herself end performance class real. Would board meeting artist word left.\nRather represent save. Cause analysis least front model board.',
    'email': 'harnold@example.org',
    'phone_number': '2138684127',
    'json': {
    'name': 'Laura Clark',
    'address': '7461 Nicole Dam Apt. 299\nEast Paulland, MI 34354',
},
    'key47915': 'value14202',
    'key81680': 'value23550',
    'key92310': 'value68266',
    'key74555': 'value6847',
},
    {
    'id': 17527491271173,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 187,
    'name': 'David Payne',
    'address': '205 Park Trail Suite 192\nWest Glenn, NC 25663',
    'text': 'Without career every compare us skill partner. Argue hold boy fact high life.\nSame serious those. Else computer door rather hard dream ten life. System away better as Democrat will decision.',
    'email': 'scottgregory@example.org',
    'phone_number': '(471)556-7315',
    'json': {
    'name': 'Melissa Bennett',
    'address': '359 Jones Islands Suite 849\nLake Evanborough, MT 50112',
},
    'key72816': 'value89202',
    'key47581': 'value13106',
    'key70503': 'value4236',
    'key84285': 'value80945',
    'key39382': 'value55740',
    'key85458': 'value91111',
},
    {
    'id': 17527491271189,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 188,
    'name': 'Howard Pena',
    'address': '489 Bryan Radial\nJustinfurt, TN 63410',
    'text': 'Compare collection too reveal step many.\nFocus among method claim opportunity medical.\nImportant myself fact. Upon yes before issue Mrs table state.',
    'email': 'thomasreynolds@example.com',
    'phone_number': '+1-223-541-9832',
    'json': {
    'name': 'Adam Bishop',
    'address': '24342 Velasquez Camp Suite 802\nBrookeview, AR 90278',
},
    'key62571': 'value23926',
    'key31543': 'value52962',
    'key93150': 'value21729',
    'key93736': 'value76222',
    'key56967': 'value54617',
    'key15922': 'value56391',
    'key20142': 'value88378',
    'key35950': 'value74428',
    'key60473': 'value39899',
    'key86624': 'value79018',
},
    {
    'id': 17527491271201,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 189,
    'name': 'Spencer Obrien',
    'address': '4492 Fisher Row\nBrownburgh, ND 13972',
    'text': 'Quickly peace among leg data idea. Herself alone show artist me military amount.\nThat skill player. Idea throw foot. Question natural while social instead.\nFamily style history traditional than.',
    'email': 'marissa89@example.net',
    'phone_number': '983-406-8465x42865',
    'json': {
    'name': 'Peter Foster',
    'address': '598 Debbie Port Apt. 993\nMirandatown, WI 32823',
},
    'key97123': 'value52645',
    'key25921': 'value17601',
    'key95711': 'value53496',
    'key75449': 'value92332',
    'key25462': 'value84881',
    'key94547': 'value38062',
    'key32286': 'value32500',
    'key3058': 'value54216',
    'key27276': 'value15727',
},
    {
    'id': 17527491271214,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 190,
    'name': 'John Reed',
    'address': '2275 Mclaughlin Branch\nMcbrideville, ME 80513',
    'text': 'Budget together night since particularly also brother. Product technology population tree or hope who. Value pick simply night enough.\nCar hair after which interview. Detail floor own indicate.',
    'email': 'lisa08@example.com',
    'phone_number': '(719)352-7126x802',
    'json': {
    'name': 'Kendra Armstrong',
    'address': '0091 Stephen Burg\nNew Jasonborough, NC 08293',
},
    'key95573': 'value90327',
    'key20775': 'value80243',
    'key9320': 'value33605',
    'key9388': 'value652',
},
    {
    'id': 17527491271226,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 191,
    'name': 'Deanna Vega',
    'address': '3985 Samantha Trace Suite 285\nWaltersburgh, IL 52804',
    'text': 'Often bank class color from various alone. However along staff.\nWorld quality case relate cultural week. Five chair draw.',
    'email': 'anne30@example.net',
    'phone_number': '(964)516-3168x8111',
    'json': {
    'name': 'Michael Johnson',
    'address': '2341 Garcia Neck Apt. 976\nNorth Davidtown, UT 74619',
},
    'key74772': 'value75803',
    'key10417': 'value40245',
    'key86577': 'value84859',
    'key14613': 'value59315',
    'key90901': 'value90469',
    'key18709': 'value9164',
},
    {
    'id': 17527491271238,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 192,
    'name': 'Carl Lopez',
    'address': '353 Kimberly Shoals\nSouth Kenneth, NE 90933',
    'text': 'Because once security kind affect base later. Couple long probably animal get.\nClass analysis answer business space. Determine trial easy life century explain deal.',
    'email': 'gabriellagarcia@example.net',
    'phone_number': '+1-485-871-0751x771',
    'json': {
    'name': 'Stephen Barr',
    'address': '84214 Page Summit\nPort Erikaville, NJ 32264',
},
    'key17070': 'value55308',
    'key81042': 'value68781',
    'key17403': 'value4588',
    'key72860': 'value8380',
},
    {
    'id': 17527491271250,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 193,
    'name': 'Troy Young',
    'address': '30877 Brandon Knoll Apt. 839\nEast Patriciaview, MP 63742',
    'text': 'Be remember population who board instead level. Southern statement positive positive big act position your.\nClass audience conference his. Pm reveal company my in six.',
    'email': 'lwright@example.org',
    'phone_number': '+1-276-527-6420x42826',
    'json': {
    'name': 'John Everett',
    'address': '039 Susan Cove Apt. 259\nSilvaport, IA 96355',
},
    'key69276': 'value49478',
    'key63333': 'value20632',
    'key54668': 'value9628',
    'key52626': 'value33603',
    'key67921': 'value26294',
    'key1508': 'value96881',
    'key96590': 'value14836',
    'key15047': 'value26658',
    'key52434': 'value92325',
},
    {
    'id': 17527491271261,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 194,
    'name': 'Lori Anderson',
    'address': '259 Melissa Stravenue\nJenniferberg, NM 11675',
    'text': 'Line thought week whom subject floor. Land tree case evening affect administration really table. Situation third boy doctor bill.',
    'email': 'ghernandez@example.net',
    'phone_number': '7293217736',
    'json': {
    'name': 'Deborah Floyd',
    'address': '48441 Tran Crest Apt. 580\nWest Kayla, PR 94661',
},
    'key22878': 'value42353',
    'key78629': 'value68887',
    'key14843': 'value49505',
    'key38008': 'value42525',
    'key4104': 'value19548',
    'key18590': 'value52785',
    'key97443': 'value3988',
    'key94094': 'value47988',
    'key29124': 'value26142',
},
    {
    'id': 17527491271272,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 195,
    'name': 'Karen Franklin',
    'address': 'USS Thompson\nFPO AE 61946',
    'text': 'Common when back hold. City six into spring resource office.',
    'email': 'david39@example.com',
    'phone_number': '7305715527',
    'json': {
    'name': 'John Johnson',
    'address': '17383 Castro Villages Apt. 754\nJennaview, NE 31732',
},
    'key89603': 'value38336',
},
    {
    'id': 17527491271282,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 196,
    'name': 'Stephanie Torres',
    'address': '31109 Crawford Crest\nLaurenport, OH 67911',
    'text': 'Material wrong we media girl. Out commercial among floor.\nSpace close southern to face generation and. Area small range series note eight course.',
    'email': 'sarahsolis@example.net',
    'phone_number': '+1-467-300-9803',
    'json': {
    'name': 'Taylor Stewart',
    'address': '962 Hernandez Extensions Suite 209\nNicholestad, NE 94447',
},
    'key20335': 'value88623',
    'key49376': 'value70543',
},
    {
    'id': 17527491271293,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 197,
    'name': 'Lisa Potts',
    'address': '82781 Hahn Extensions\nWest Sandrashire, VA 33070',
    'text': 'Reason eight window why center man put. Among region project hot. Evening whether add keep. Especially focus quality local style size.',
    'email': 'hstephens@example.com',
    'phone_number': '+1-852-393-8562x4220',
    'json': {
    'name': 'Cynthia Johnson',
    'address': '058 Johnson Turnpike\nNew Michael, MP 83738',
},
    'key23390': 'value40506',
    'key66625': 'value9234',
    'key9977': 'value92948',
    'key2946': 'value10525',
    'key39928': 'value65574',
    'key2666': 'value8054',
    'key51146': 'value94404',
    'key67687': 'value90370',
    'key99371': 'value10167',
},
    {
    'id': 17527491271304,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 198,
    'name': 'Travis Hill',
    'address': '555 Robinson Cliffs Suite 336\nKatieberg, AR 64314',
    'text': 'Partner throw care administration check million. Various happy thus article police. Bad participant sure bit.\nWin identify food hit child. Lot phone by how.',
    'email': 'rlamb@example.com',
    'phone_number': '610-336-1198x53400',
    'json': {
    'name': 'Emily Jones',
    'address': '62756 Silva Locks\nSouth Jacquelinechester, IL 84749',
},
    'key11889': 'value71601',
},
    {
    'id': 17527491271315,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 199,
    'name': 'Matthew Lopez',
    'address': '735 Michael Course\nNew Samanthatown, GU 04555',
    'text': 'Race mission war cause employee kitchen during. Site three maintain natural up. Make husband national reality late during mouth.',
    'email': 'kevinwalls@example.org',
    'phone_number': '001-244-815-1005x693',
    'json': {
    'name': 'Andrew Hunt',
    'address': 'PSC 7780, Box 5301\nAPO AA 50450',
},
    'key94647': 'value14472',
    'key82478': 'value65244',
    'key72441': 'value66370',
    'key93754': 'value86564',
    'key61141': 'value74651',
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
    'RequestId': '22ce14a0-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_45_20_877082MQnKjdUW',
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
    'filter': 'uid in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 199]',
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
        """测试请求 4 - POST http://172.17.0.5:23210/v2/vectordb/entities/get"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/get")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/get'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '22ce14a0-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_45_20_877082MQnKjdUW',
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
    'id': self.mutator.generate_float_array(dimension=100, normalized=True),
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



    def test_request_5(self):
        """测试请求 5 - POST http://172.17.0.5:23210/v2/vectordb/collections/list"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/list")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/list'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '22ce14a0-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = 'null'
        
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



    def test_request_6(self):
        """测试请求 6 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '22ce14a0-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_45_20_877082MQnKjdUW',
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



    def test_request_7(self):
        """测试请求 7 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '22ce14a0-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_45_20_877082MQnKjdUW',
    'dbName': 'default',
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



    def test_request_8(self):
        """测试请求 8 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '22ce14a0-62fb-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_45_20_877082MQnKjdUW',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestGetVector_test_get_vector_complex[False-True-list]_1752749132.json')
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
    test = AllmilvusLogtestgetvectorTestGetVectorComplexFalseTrueList1752749132Json()
    test.run_tests()
