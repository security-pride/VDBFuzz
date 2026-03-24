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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-False-uid >= 0]_1752748732_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid >= 0]_1752748732.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalseUid01752748732Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid >= 0]_1752748732.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid >= 0]_1752748732.json"
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
    'RequestId': '33e2b5ee-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_40_036701BZgkzIeE',
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
    'RequestId': '33e2b5ee-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_40_036701BZgkzIeE',
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
    'RequestId': '33e2b5ee-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_40_036701BZgkzIeE',
    'data': [
    {
    'id': 17527487260722,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Jessica Haynes',
    'address': '3682 Ray Brooks\nNewmanberg, KS 58824',
    'text': 'Benefit science I create pass service put trade. Stock look apply total. Draw design represent all evidence.',
    'email': 'emily61@example.org',
    'phone_number': '394-748-2161x61080',
    'json': {
    'name': 'Stacey Morrow',
    'address': '9128 Susan Inlet\nNorth Jenna, UT 51685',
},
    'key85105': 'value62751',
},
    {
    'id': 17527487260738,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Joseph Potts',
    'address': 'Unit 6685 Box 6864\nDPO AE 21039',
    'text': 'Second senior discussion finish real sort rich camera. Less successful blue possible it sign between.\nComputer true local what list. They this note rate possible expert. Mission pattern play pay.',
    'email': 'edwardssusan@example.com',
    'phone_number': '(711)362-0334x8461',
    'json': {
    'name': 'Danielle Smith',
    'address': '0147 Barrett Glens\nSethmouth, MO 62161',
},
    'key50729': 'value25820',
    'key71317': 'value74027',
    'key93255': 'value51373',
    'key97769': 'value39131',
    'key58364': 'value20097',
    'key23689': 'value93846',
    'key73046': 'value60167',
    'key22311': 'value68216',
    'key76739': 'value29285',
    'key64822': 'value13775',
},
    {
    'id': 17527487260751,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Matthew Hawkins',
    'address': '03567 Jimenez Canyon Suite 800\nNorth Denise, PW 35800',
    'text': 'Couple by I ok assume collection rich. Open audience run inside throw. Him degree positive indicate.\nAgain ready even fear activity there. Floor Mrs eat enough campaign where free.',
    'email': 'lsanchez@example.net',
    'phone_number': '655-743-6033x2271',
    'json': {
    'name': 'Jacob Wagner',
    'address': '2687 Mary Street Apt. 003\nShirleyview, GA 73196',
},
    'key36512': 'value75971',
    'key72163': 'value52864',
    'key61513': 'value41654',
    'key56752': 'value8880',
    'key77194': 'value2096',
    'key87169': 'value88871',
    'key69859': 'value85262',
    'key30164': 'value3870',
    'key73956': 'value18673',
},
    {
    'id': 17527487260765,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'James Navarro',
    'address': '5547 Jessica Junction Apt. 967\nDakotaside, KS 42357',
    'text': 'Whole interview report alone bed window. American within above sort keep. Describe candidate defense.\nScene report field human traditional race hot. Cell pass term evening per easy water.',
    'email': 'annaortiz@example.org',
    'phone_number': '(867)546-9497x416',
    'json': {
    'name': 'Daniel Rasmussen',
    'address': '3363 Nicholas Extensions\nNew William, GA 91755',
},
    'key12105': 'value41460',
    'key27713': 'value25999',
    'key31174': 'value17128',
    'key59048': 'value14884',
},
    {
    'id': 17527487260779,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Alejandro Pugh',
    'address': '1359 Claudia Mews\nPort Joseph, ID 70579',
    'text': 'List collection soon learn recognize take.',
    'email': 'larryroman@example.com',
    'phone_number': '(454)246-7240',
    'json': {
    'name': 'Brittany Ingram',
    'address': '3010 Jones Prairie Apt. 282\nMathewberg, NY 93587',
},
    'key80014': 'value15073',
    'key46367': 'value8197',
},
    {
    'id': 17527487260792,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Helen Cooper',
    'address': '408 Foley Light Apt. 862\nNorth Candaceport, LA 75832',
    'text': 'Beyond fast role major. Usually green poor.\nLearn save why leg Congress political. Every expect staff economy. Prove heavy participant bed statement.',
    'email': 'nlang@example.net',
    'phone_number': '(408)958-4401x446',
    'json': {
    'name': 'Erin Reyes',
    'address': '4407 Peters Village Apt. 774\nLake Betty, NV 28368',
},
    'key81321': 'value33060',
},
    {
    'id': 17527487260807,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Steven Lane',
    'address': '9985 Wall Pass Suite 318\nNew Stephanie, NC 72775',
    'text': 'If PM still face own continue beyond. Guess institution summer return I anything free.\nBack after building piece raise allow. Front site live language goal strong away.',
    'email': 'andersonbenjamin@example.net',
    'phone_number': '001-913-859-1051x6500',
    'json': {
    'name': 'John Scott',
    'address': '41522 Cunningham Cliff\nHerreraville, ID 51362',
},
    'key80021': 'value49021',
    'key25275': 'value11109',
    'key2001': 'value48260',
},
    {
    'id': 17527487260821,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Matthew Maxwell',
    'address': '7259 Bird Forges Suite 650\nMeganview, NH 23239',
    'text': 'Up once suggest mean.\nThird effect economic often miss. Behavior career play lay section at rather.',
    'email': 'penny80@example.net',
    'phone_number': '7259092695',
    'json': {
    'name': 'Cynthia Sullivan',
    'address': '018 Vickie Landing Suite 816\nNicolemouth, IL 54997',
},
    'key95394': 'value78714',
    'key14954': 'value56281',
},
    {
    'id': 17527487260834,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Shelby Thomas',
    'address': '0484 French Islands Suite 181\nRickyville, AK 86766',
    'text': 'Measure hair option my possible. Evidence through nice last wish.\nLess no arm first institution rather. Assume drop it dark policy hear sometimes.',
    'email': 'bgreene@example.net',
    'phone_number': '613.629.8569x11205',
    'json': {
    'name': 'Devin Gutierrez',
    'address': '314 Valerie Terrace\nKellyhaven, VT 69336',
},
    'key75274': 'value66082',
    'key66147': 'value84510',
    'key21272': 'value59635',
    'key19196': 'value44978',
    'key72565': 'value86959',
},
    {
    'id': 17527487260847,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'April Whitehead',
    'address': '86467 Carolyn Ports Suite 548\nNew Lee, NV 28449',
    'text': 'Program fish onto machine. General father budget wait boy up though. Age kind could morning high.',
    'email': 'sheasandra@example.net',
    'phone_number': '4579176584',
    'json': {
    'name': 'Diane Graham',
    'address': 'Unit 9568 Box 7720\nDPO AE 76502',
},
    'key84912': 'value78336',
    'key41805': 'value83041',
},
    {
    'id': 17527487260859,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Mark Thomas',
    'address': '472 Richardson Isle\nJasonton, NH 53366',
    'text': 'Chair surface almost shoulder. Find capital describe front.\nMake community simple military. Forget agency firm money certain team avoid.',
    'email': 'benjaminbell@example.com',
    'phone_number': '001-280-678-9117x05435',
    'json': {
    'name': 'Debra Wood',
    'address': '0366 Samantha Creek\nCynthialand, SC 61380',
},
    'key20863': 'value50029',
    'key11177': 'value9481',
    'key93541': 'value81011',
    'key48405': 'value25470',
    'key21451': 'value70841',
    'key3971': 'value56631',
},
    {
    'id': 17527487260873,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Kurt Sparks',
    'address': '12093 Oconnor Drive Suite 221\nValenzuelaview, IA 31621',
    'text': 'Pm specific life today especially.\nThough gas director there color computer name say. Difficult artist go strategy. Media between most office him.',
    'email': 'sheryl04@example.net',
    'phone_number': '001-490-398-4142x5504',
    'json': {
    'name': 'Kimberly Green',
    'address': '884 Greer Lodge Apt. 092\nNew Jeannemouth, VT 65009',
},
    'key78811': 'value86916',
    'key53850': 'value70366',
    'key72631': 'value44295',
    'key89899': 'value54594',
    'key7796': 'value72016',
    'key36632': 'value8029',
},
    {
    'id': 17527487260887,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Kevin Moran',
    'address': '0154 Ford Stream Suite 873\nWilliamland, FL 84501',
    'text': 'Which involve physical piece. Happy allow baby manage marriage. Region place during case night matter.\nDegree near eat hundred radio only. Issue beautiful lay remember air same.',
    'email': 'richardsonalexander@example.com',
    'phone_number': '940-733-0242x558',
    'json': {
    'name': 'Teresa Gonzales',
    'address': '55044 Brady Villages\nHoustonburgh, ND 16474',
},
    'key34816': 'value39391',
    'key1381': 'value9373',
    'key25422': 'value7482',
    'key54029': 'value74557',
    'key45918': 'value46929',
},
    {
    'id': 17527487260900,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Lauren Bowman',
    'address': '4400 Eric Drives\nEast Jose, IA 38051',
    'text': 'Identify officer yes population. State year might.\nInternational right glass why special and minute. Happy friend sense employee. Wrong authority father able support short case kitchen.',
    'email': 'kimberlyjackson@example.org',
    'phone_number': '001-995-530-5074x57899',
    'json': {
    'name': 'Dominique Schultz',
    'address': '8631 Hebert Flat\nDanielchester, CT 06113',
},
    'key58912': 'value57175',
    'key71355': 'value4138',
    'key56915': 'value55994',
    'key68553': 'value10491',
    'key68296': 'value62497',
},
    {
    'id': 17527487260912,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Alisha Garcia',
    'address': '358 Laura Route\nPort Christopher, TN 54489',
    'text': 'Analysis capital may than tree air test among. People spring use among mention. Write century future man.',
    'email': 'nicolebaker@example.com',
    'phone_number': '(510)429-3290',
    'json': {
    'name': 'Gary Jackson',
    'address': '6349 Johnson Springs Suite 197\nNew Lisaland, ND 63371',
},
    'key80292': 'value15529',
    'key21711': 'value58129',
    'key16873': 'value32244',
    'key44728': 'value49981',
},
    {
    'id': 17527487260924,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Alicia Taylor',
    'address': '1841 Short Lodge\nDeckerberg, IN 53360',
    'text': 'Experience particularly stand next give. Throughout keep sometimes stand example remain. Fine product message nor.\nKnow huge skill but cultural fear try. Speak environment take left whether seek.',
    'email': 'jameswaters@example.org',
    'phone_number': '423-379-5753',
    'json': {
    'name': 'Todd Todd',
    'address': '4388 Golden Drive\nPort Rita, MS 87869',
},
    'key1177': 'value18318',
    'key11692': 'value17422',
    'key69844': 'value16912',
    'key83287': 'value5616',
    'key23229': 'value80989',
    'key21478': 'value43822',
    'key72148': 'value59390',
    'key42981': 'value59854',
    'key44035': 'value71884',
},
    {
    'id': 17527487260937,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Miss Dana Scott DVM',
    'address': '65451 Herbert Summit\nLake James, ID 02680',
    'text': 'Company minute ok character these. This reveal sing camera pick bed others. Wife college fish senior way require.\nCard maintain ten section determine east son.',
    'email': 'wwilson@example.com',
    'phone_number': '439.379.6835',
    'json': {
    'name': 'Anita Parrish',
    'address': '4576 Howard Common\nPort Michaelburgh, DC 74537',
},
    'key77702': 'value83220',
    'key68996': 'value33892',
    'key47536': 'value44933',
    'key81364': 'value15434',
    'key82680': 'value98146',
    'key55149': 'value10495',
    'key68381': 'value47167',
    'key27051': 'value42922',
    'key86188': 'value60757',
},
    {
    'id': 17527487260949,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Jessica Watson',
    'address': '1010 Chen Extension Apt. 582\nPhelpsberg, VT 24991',
    'text': 'Pm party really return. Girl audience win reality hold.\nStreet on skill. View especially eight certain.\nPolice attorney economic dog force. Able only brother address.',
    'email': 'lstone@example.net',
    'phone_number': '2874018339',
    'json': {
    'name': 'Edward Bryant',
    'address': 'Unit 7987 Box 9976\nDPO AP 54251',
},
    'key36871': 'value161',
    'key83414': 'value26723',
    'key88263': 'value29849',
},
    {
    'id': 17527487260959,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'James Smith',
    'address': '3755 Matthews Lodge\nNorth Davidfurt, WA 31204',
    'text': 'Perhaps party while decade if.\nCivil art approach. Card approach create.\nSo among generation road remain. Shake car quality pattern. Name require party.\nCan school form according national.',
    'email': 'michelle37@example.org',
    'phone_number': '369.951.9395x1999',
    'json': {
    'name': 'Robert Bates',
    'address': '91625 Colton Estates\nCarriemouth, MD 48079',
},
    'key98697': 'value7696',
    'key35884': 'value4169',
    'key50904': 'value3497',
    'key85699': 'value16636',
    'key76482': 'value12705',
    'key49587': 'value17279',
    'key62691': 'value37302',
    'key27616': 'value69563',
    'key24867': 'value59860',
},
    {
    'id': 17527487260971,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Christopher Horton',
    'address': 'PSC 6984, Box 2587\nAPO AE 77697',
    'text': 'Most candidate charge environment. Show which each evening season environmental. Section bar market son pretty.\nPainting work finally serious officer provide often. Care edge Mr religious same.',
    'email': 'samantha37@example.org',
    'phone_number': '751-648-8823',
    'json': {
    'name': 'Taylor Sanchez MD',
    'address': '28034 Arellano Stream\nNew Matthewview, VI 76476',
},
    'key54939': 'value4760',
},
    {
    'id': 17527487260981,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Kathryn Santana',
    'address': '802 Lucas Crossing\nMathisbury, SC 83505',
    'text': 'Necessary treat draw large table call true. Before smile as arrive audience national able perform. Possible day American process.',
    'email': 'tbenson@example.net',
    'phone_number': '755-840-7380',
    'json': {
    'name': 'Howard Hensley',
    'address': 'USCGC Johnson\nFPO AE 13842',
},
    'key50514': 'value16823',
},
    {
    'id': 17527487260992,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Keith Avila',
    'address': '39048 Brewer Ferry Apt. 508\nJohnstonbury, ND 98477',
    'text': 'Piece wonder alone fall ok visit involve. Walk prepare force up series at.\nWhy community what television add.\nWay there author. See certain she.',
    'email': 'dorothyjimenez@example.com',
    'phone_number': '+1-588-753-9478',
    'json': {
    'name': 'Andrew Chapman',
    'address': '912 Holloway Springs Apt. 192\nLake Melindafurt, FL 65219',
},
    'key52851': 'value80443',
},
    {
    'id': 17527487261005,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Alexander Brown',
    'address': 'Unit 1391 Box 0017\nDPO AA 02040',
    'text': 'Moment low really form late professor always. Whatever break bring senior same life general painting. Building note could save surface game black. Rock impact with subject second pressure ask.',
    'email': 'ashleyosborne@example.net',
    'phone_number': '9256036901',
    'json': {
    'name': 'Crystal Landry',
    'address': '72101 Nicole Summit Suite 239\nEast James, CA 95184',
},
    'key77087': 'value83637',
    'key45294': 'value50103',
    'key51417': 'value12364',
    'key95405': 'value84007',
},
    {
    'id': 17527487261015,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Jordan Burns',
    'address': '5408 Brady Avenue\nKinghaven, VA 64202',
    'text': 'Discover population hold center station avoid. Class fight interest crime.\nSystem expect break because. Skill speech mind international. Daughter unit much group remain than know.\nBest cell seat.',
    'email': 'danielrobinson@example.net',
    'phone_number': '001-910-386-3189x76102',
    'json': {
    'name': 'Nathan Cain',
    'address': '34049 Bernard Club\nMarychester, RI 64496',
},
    'key26395': 'value1563',
    'key51523': 'value49223',
    'key27879': 'value4090',
},
    {
    'id': 17527487261028,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'John Ball',
    'address': 'PSC 2635, Box 9737\nAPO AP 03398',
    'text': 'Military possible hour around two chair interesting play. Building interview focus special Democrat member edge.',
    'email': 'ahill@example.org',
    'phone_number': '+1-732-451-6222x59302',
    'json': {
    'name': 'Jennifer Adams',
    'address': 'Unit 2894 Box 3022\nDPO AP 91509',
},
    'key11631': 'value29023',
    'key68278': 'value37833',
    'key92612': 'value32997',
    'key26668': 'value16015',
    'key80437': 'value7467',
    'key71573': 'value23956',
    'key42075': 'value64491',
    'key39840': 'value74938',
},
    {
    'id': 17527487261035,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Derek Ramirez MD',
    'address': '00839 Joseph Extension\nPort Lauren, SC 66310',
    'text': 'Every ask Congress particular measure something culture. Else eye act pattern form activity.\nFeel authority politics. Mrs than husband between. Page it him future expert grow public.',
    'email': 'yanderson@example.org',
    'phone_number': '+1-905-393-8988x7739',
    'json': {
    'name': 'Heidi Jones',
    'address': '1395 Eric Rest\nPort Thomasstad, KY 48438',
},
    'key53821': 'value98057',
    'key98550': 'value92061',
    'key30331': 'value82233',
},
    {
    'id': 17527487261045,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Marissa White',
    'address': '70319 Davis Bridge Suite 633\nNew Melanie, TN 18857',
    'text': 'Cultural pick season energy. Rich north Democrat over. Smile south style.\nSociety mother author mother down real computer. Brother maybe modern see man.',
    'email': 'bvega@example.org',
    'phone_number': '(562)690-3051',
    'json': {
    'name': 'Brandon Maxwell',
    'address': '602 Carlos Coves Suite 404\nWest Mary, MI 73431',
},
    'key53517': 'value70562',
    'key35367': 'value55809',
    'key40230': 'value69167',
    'key67006': 'value96201',
},
    {
    'id': 17527487261056,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Nathan Johnson',
    'address': '336 Woods Ports Apt. 770\nMarkside, FL 18532',
    'text': 'Contain religious artist spring. Voice degree television.\nTurn information speak break five. Card never clearly you.',
    'email': 'moorecasey@example.com',
    'phone_number': '367-876-6796x860',
    'json': {
    'name': 'Jennifer Hodge',
    'address': '93251 Donna Square\nChavezville, MT 62514',
},
    'key74847': 'value22560',
    'key9584': 'value36283',
    'key13283': 'value55712',
    'key15630': 'value6705',
    'key26910': 'value3653',
},
    {
    'id': 17527487261067,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'John Cantu',
    'address': '9141 Young Springs Apt. 666\nNorth Jacobhaven, MP 96973',
    'text': 'All first forget future. Green however defense tell feel generation create sometimes.\nAbove image cut expect seven.\nNature analysis hour fall against good. Technology until important scene peace.',
    'email': 'kenneth13@example.net',
    'phone_number': '+1-572-723-9549x44459',
    'json': {
    'name': 'Daniel Mason',
    'address': '8468 Mcdowell Ports\nMckenzieton, MS 12622',
},
    'key1155': 'value28832',
    'key11062': 'value71956',
    'key52030': 'value67121',
    'key38572': 'value67153',
    'key44528': 'value18840',
    'key42909': 'value86886',
    'key63344': 'value78216',
    'key99941': 'value50074',
    'key35268': 'value75398',
},
    {
    'id': 17527487261079,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Craig Peterson',
    'address': '30250 Reeves Lights Apt. 538\nSouth Andrew, AS 86608',
    'text': 'Street social foot east learn. Mean close explain deep hit structure. Film result thank space enjoy quality maintain without. Still risk near message key term.',
    'email': 'bergerashley@example.net',
    'phone_number': '+1-450-315-4658x0546',
    'json': {
    'name': 'April Jones',
    'address': '636 Chan Roads Apt. 125\nNorth Andrew, ME 49331',
},
    'key95314': 'value34088',
    'key19593': 'value80424',
    'key7874': 'value14585',
    'key51741': 'value7086',
    'key97489': 'value84924',
    'key15408': 'value89688',
},
    {
    'id': 17527487261091,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Stephanie Murphy',
    'address': '82803 Henderson Trail\nNew Angela, LA 54430',
    'text': 'Face forget trip similar. Care military either my expert dog. Most boy brother hard view difference sport.\nPoor face kitchen himself under eye. Husband memory natural area.',
    'email': 'rbautista@example.org',
    'phone_number': '575-813-0887x7842',
    'json': {
    'name': 'Linda Dalton',
    'address': '228 Mathew Center Suite 760\nPerryton, IA 25076',
},
    'key91998': 'value77018',
    'key33935': 'value67698',
    'key45539': 'value31354',
    'key40332': 'value44432',
    'key87081': 'value77775',
    'key50546': 'value93610',
    'key15228': 'value89408',
    'key57637': 'value54676',
    'key24857': 'value76998',
},
    {
    'id': 17527487261103,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Patricia Hayes',
    'address': '871 Stephanie Key\nSouth Katrinaland, FL 55053',
    'text': 'No door without half later herself. Against owner toward form. Anything because walk baby hospital interest civil.',
    'email': 'bethanyjimenez@example.org',
    'phone_number': '+1-789-906-9435x0226',
    'json': {
    'name': 'Jennifer Silva',
    'address': '234 Rhodes Radial Apt. 020\nKevinshire, ND 39578',
},
    'key9034': 'value66718',
    'key96305': 'value86383',
    'key88020': 'value61904',
    'key6156': 'value1276',
    'key86916': 'value78032',
    'key96448': 'value79044',
    'key86015': 'value73781',
    'key49475': 'value99701',
    'key61230': 'value27732',
},
    {
    'id': 17527487261115,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Kristopher Dominguez',
    'address': '559 Wilson Glen\nDeanfort, MN 43016',
    'text': 'Must fly social. Bring save must store face foreign.\nOwner both side prevent risk cost so campaign. Follow Republican voice whether house open kid.',
    'email': 'courtneystrickland@example.net',
    'phone_number': '001-256-623-5582',
    'json': {
    'name': 'Leonard Williams',
    'address': '10613 Stephanie Roads\nPort Anthonymouth, CO 78160',
},
    'key75557': 'value50486',
    'key54611': 'value90681',
    'key71001': 'value64957',
    'key25014': 'value56473',
    'key4059': 'value31023',
    'key3065': 'value15825',
    'key68897': 'value90704',
    'key83412': 'value25085',
    'key31162': 'value13083',
},
    {
    'id': 17527487261128,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Christina Cox',
    'address': '58666 Daisy Gardens\nWilliamsborough, TX 09741',
    'text': 'Choose sport specific war so fast. Attorney him pull community budget three box. Season more you radio medical mouth space.\nName movie fire. Figure bad trade hair.',
    'email': 'williefritz@example.org',
    'phone_number': '492-706-6919',
    'json': {
    'name': 'Vanessa Valdez',
    'address': '467 Hailey Parkways\nCherryside, MI 71964',
},
    'key21645': 'value28295',
    'key8986': 'value79713',
    'key16087': 'value85454',
    'key13191': 'value70601',
    'key17303': 'value94733',
},
    {
    'id': 17527487261140,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Michael Butler',
    'address': '99476 Jay Vista Apt. 363\nNew Davidtown, DE 80970',
    'text': 'Back south write floor adult college respond natural. Better teach around old. It consider rate feel group look. Enough little must.',
    'email': 'rebeccajohnson@example.com',
    'phone_number': '001-908-322-3839x1918',
    'json': {
    'name': 'Joseph Wright',
    'address': '901 Jerome Knolls\nSouth Tammy, WI 62099',
},
    'key15021': 'value59349',
    'key50568': 'value94448',
    'key29274': 'value17922',
    'key35671': 'value12160',
    'key61826': 'value85399',
    'key91761': 'value93862',
},
    {
    'id': 17527487261152,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Vanessa Reyes',
    'address': '51658 Frazier Fork Suite 611\nNorth Justinhaven, AZ 15423',
    'text': 'East entire rock for. The eight low reason car.\nMan parent wide. Degree wish away suddenly message face up above. Health class since heavy represent necessary evidence.',
    'email': 'moralesjacqueline@example.net',
    'phone_number': '460-400-9153x07089',
    'json': {
    'name': 'Tracy Day',
    'address': '4861 Heather Mountain\nNorth Jamesbury, MN 74180',
},
    'key23437': 'value21222',
    'key6910': 'value35973',
    'key39906': 'value83256',
    'key36236': 'value49514',
    'key89803': 'value42515',
},
    {
    'id': 17527487261164,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Eric Wood',
    'address': '083 Jennifer Land Apt. 159\nHallhaven, ID 76252',
    'text': 'Begin subject together. Offer pressure purpose democratic example black response.',
    'email': 'aaron43@example.com',
    'phone_number': '806-923-3552x22788',
    'json': {
    'name': 'Jason Davis',
    'address': '13844 Meyer Creek\nWest David, FM 66021',
},
    'key26211': 'value69119',
    'key92289': 'value75544',
    'key53770': 'value64271',
    'key27235': 'value82944',
    'key23865': 'value17386',
},
    {
    'id': 17527487261175,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Steven Torres',
    'address': '97714 Walker Junction\nWhitakerside, MO 64976',
    'text': 'Good seat wear wide piece sound simple. Near all child themselves grow second health.\nFar close determine paper. Stand bag able friend later expect.',
    'email': 'thompsonsandra@example.net',
    'phone_number': '(493)823-2352',
    'json': {
    'name': 'Laura Mora',
    'address': '4381 Jackson Burg\nGeorgeborough, WV 07840',
},
    'key14421': 'value27920',
    'key11518': 'value23747',
    'key62365': 'value61945',
    'key84286': 'value88625',
    'key45708': 'value25342',
    'key79888': 'value23097',
    'key11670': 'value58669',
},
    {
    'id': 17527487261188,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Larry Stephens',
    'address': '3862 Lisa Valley\nEast Todd, FM 21592',
    'text': 'Back town positive speak help affect prevent hope. Public raise top fire science station. Through tell build thing Mrs mother.',
    'email': 'jameskeller@example.net',
    'phone_number': '001-338-213-5650x926',
    'json': {
    'name': 'Joan Fry',
    'address': '5900 Estrada Plaza Apt. 311\nMurrayberg, ID 35113',
},
    'key1039': 'value24006',
},
    {
    'id': 17527487261199,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Christopher Howard',
    'address': '211 Rebecca Road\nMichaelburgh, PA 21323',
    'text': 'After side gun couple tax that. Cell also only outside story.\nAgent window adult Democrat head through. Ahead standard operation brother morning.',
    'email': 'blambert@example.com',
    'phone_number': '207-348-4045x52415',
    'json': {
    'name': 'Christian Lee',
    'address': '0071 Boyd Unions Apt. 393\nSouth Justin, WA 16205',
},
    'key30610': 'value15901',
},
    {
    'id': 17527487261210,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Daniel Riggs',
    'address': '8608 Marquez Extensions Suite 162\nParkschester, WI 32039',
    'text': 'Stand their gas time age. Huge rate she marriage. Garden could according it open pattern mean.\nKnow drug happy indeed. Serve him let all investment. His couple give clearly.',
    'email': 'larsonmaria@example.org',
    'phone_number': '001-424-957-5804x54629',
    'json': {
    'name': 'Danielle Bennett',
    'address': '77266 Kelly Skyway Apt. 006\nKatelyntown, GU 57589',
},
    'key44495': 'value80033',
    'key1430': 'value40886',
    'key10722': 'value92766',
},
    {
    'id': 17527487261222,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Alexander Stanley',
    'address': '7136 Heather Creek\nMariaside, UT 09256',
    'text': 'Send learn kind strategy alone later government voice. Wear protect near down but old. Happen edge college myself light action.',
    'email': 'matthewriley@example.net',
    'phone_number': '966-491-4259',
    'json': {
    'name': 'Kathryn Baker',
    'address': '606 Bethany Bypass Suite 738\nWest Justinland, AL 41390',
},
    'key26773': 'value25849',
    'key22788': 'value55283',
    'key14893': 'value45517',
    'key583': 'value35791',
},
    {
    'id': 17527487261233,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Stacey Rivera MD',
    'address': '685 Allison Parks Suite 368\nNew Samuel, WY 32954',
    'text': 'Coach ready interesting notice morning body. Account machine check religious skin.\nKeep no artist physical prevent respond allow. Month between agree professor here take agent agency.',
    'email': 'wattsjohn@example.net',
    'phone_number': '(873)462-8560x86427',
    'json': {
    'name': 'April Martinez',
    'address': '6343 Taylor Knoll\nLake Jason, ND 04692',
},
    'key95145': 'value44113',
    'key69776': 'value47117',
    'key30367': 'value10770',
    'key49554': 'value28272',
    'key90312': 'value78386',
    'key7823': 'value56530',
    'key15222': 'value85286',
    'key43111': 'value7368',
},
    {
    'id': 17527487261245,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Michelle Wolfe',
    'address': '885 William Roads Apt. 813\nPort Stephanieland, VT 32290',
    'text': 'There bank ten central early finish. Form agreement so agreement pass hit wait happen.\nDebate care understand drive go. Since yes nice guess. Wide degree across then.',
    'email': 'laurie82@example.org',
    'phone_number': '811-581-8240',
    'json': {
    'name': 'William Lee',
    'address': '66620 Jennifer Route Apt. 298\nMichaelaberg, MD 40229',
},
    'key98749': 'value50300',
    'key60557': 'value87782',
    'key21902': 'value75710',
    'key95965': 'value8273',
    'key12378': 'value7292',
    'key90359': 'value70321',
    'key70802': 'value96763',
    'key59304': 'value53400',
    'key86359': 'value56313',
},
    {
    'id': 17527487261255,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Jennifer Warner',
    'address': '09138 Kyle Mount Suite 050\nNew Deannaland, SC 11241',
    'text': 'Thought believe need reduce major assume father drop. Star also practice general marriage become check.\nFormer and care better several.',
    'email': 'robertstimothy@example.net',
    'phone_number': '001-830-603-0211',
    'json': {
    'name': 'Dawn Williams',
    'address': '1143 Johnathan Falls Suite 278\nPatelchester, WI 38664',
},
    'key92663': 'value17278',
    'key41167': 'value57291',
    'key81333': 'value95172',
    'key10730': 'value40613',
    'key4591': 'value26868',
    'key4229': 'value41490',
    'key88436': 'value45504',
},
    {
    'id': 17527487261267,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Erica Mcgee',
    'address': 'USS Romero\nFPO AA 42097',
    'text': 'Dark upon man may from reflect. Hand floor fine.\nConcern might picture new capital receive clear. Think region let itself question try two.',
    'email': 'williamjones@example.net',
    'phone_number': '8319339681',
    'json': {
    'name': 'Denise Horn',
    'address': '81902 Lara Corners Suite 501\nPort Thomas, DE 03795',
},
    'key70736': 'value61585',
    'key21444': 'value55800',
    'key88150': 'value25225',
    'key7069': 'value25049',
    'key50253': 'value712',
    'key24564': 'value14290',
    'key41357': 'value44786',
    'key79839': 'value74483',
},
    {
    'id': 17527487261277,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Kimberly Morales',
    'address': '457 Cooper Street Apt. 691\nJefferyport, MH 29890',
    'text': 'Person already understand before prove full. Message ability personal stock two computer your. Ability very enough.\nCold nor behavior company. Prevent stock us science.',
    'email': 'hwells@example.net',
    'phone_number': '2394157609',
    'json': {
    'name': 'Mr. David Roy',
    'address': '7821 Tommy Coves\nEast Daniel, MN 44401',
},
    'key51807': 'value99647',
    'key59467': 'value63672',
    'key47147': 'value64290',
    'key29492': 'value66360',
},
    {
    'id': 17527487261287,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Amy Ryan',
    'address': '9705 Paul Pines Suite 049\nSmithbury, AS 25216',
    'text': 'Over ten while officer military night wall. Partner study kid for staff federal summer old. House else area oil there base it.\nFood main health. Campaign lawyer rate.',
    'email': 'qpeterson@example.org',
    'phone_number': '+1-861-812-4808',
    'json': {
    'name': 'Jessica Watson',
    'address': '453 Scott Landing Suite 481\nNorth Arthurton, ME 23458',
},
    'key17409': 'value79917',
    'key57020': 'value4736',
    'key91468': 'value9804',
    'key9900': 'value89204',
    'key3226': 'value3404',
    'key59687': 'value43280',
    'key52004': 'value37867',
    'key80671': 'value27066',
    'key36947': 'value92284',
},
    {
    'id': 17527487261298,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Nancy Turner',
    'address': 'USNS Brooks\nFPO AE 33194',
    'text': 'Personal way natural rest without mission participant. Public available party collection little day behind cup. Deep stuff treat chance human.',
    'email': 'ramirezmichelle@example.org',
    'phone_number': '403.215.2390',
    'json': {
    'name': 'Howard Williams',
    'address': '25453 Anderson View\nSouth Davidfort, SC 28211',
},
    'key79033': 'value18590',
    'key30059': 'value76039',
    'key12793': 'value85985',
    'key68937': 'value95606',
    'key19666': 'value41897',
    'key99089': 'value14701',
    'key61842': 'value58529',
    'key47981': 'value81894',
},
    {
    'id': 17527487261309,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Bradley Li',
    'address': '756 Jeff Inlet\nWest Jamesville, PA 48134',
    'text': 'Conference according gas popular remain will perform. Again federal Mrs rather indicate maintain brother. Medical something window risk its daughter detail.',
    'email': 'atkinshector@example.org',
    'phone_number': '604.602.0731x026',
    'json': {
    'name': 'William Stein',
    'address': '271 Kaufman Brooks Suite 401\nEast Calebtown, WI 14417',
},
    'key64686': 'value62881',
    'key72143': 'value87740',
    'key98627': 'value18608',
},
    {
    'id': 17527487261320,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Amanda Washington',
    'address': '954 Alyssa Keys\nSouth Anitamouth, AL 28452',
    'text': 'Everything receive control head thus project as catch. Approach wind pretty trouble side security hair.',
    'email': 'tdixon@example.net',
    'phone_number': '001-716-718-8325x2181',
    'json': {
    'name': 'Melissa Collins',
    'address': 'Unit 9415 Box 9648\nDPO AP 96164',
},
    'key9945': 'value48216',
},
    {
    'id': 17527487261328,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Amanda Copeland',
    'address': '5559 Rebecca Plains Suite 074\nWest Wendy, PR 33602',
    'text': 'Sell enough toward mean level brother that. Course form walk whom role season time.\nUnit capital direction expect hard talk center. Your can interesting network gas. Movie wear soon entire hot.',
    'email': 'michael50@example.net',
    'phone_number': '560-521-5582',
    'json': {
    'name': 'Lorraine Brown',
    'address': '8130 Beard Expressway\nWagnerside, VT 70570',
},
    'key68273': 'value2817',
    'key68181': 'value95996',
    'key66647': 'value83476',
    'key86911': 'value46877',
    'key54685': 'value47876',
    'key11441': 'value8635',
    'key48909': 'value9604',
    'key29066': 'value73674',
},
    {
    'id': 17527487261339,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Erica Olsen',
    'address': '14214 Herrera Track\nEast Sean, TN 67482',
    'text': 'Approach believe message toward short specific method. Report happen agreement.\nOpen executive town responsibility. Civil today participant matter. Official air family campaign.',
    'email': 'david59@example.com',
    'phone_number': '590-689-5535x081',
    'json': {
    'name': 'Anthony Reilly',
    'address': '0350 Donald Cliff\nCorychester, WA 97172',
},
    'key80558': 'value49953',
    'key12299': 'value36940',
    'key9295': 'value78159',
    'key4447': 'value67696',
    'key61828': 'value36777',
    'key30616': 'value16024',
    'key95375': 'value93851',
    'key54496': 'value52692',
},
    {
    'id': 17527487261349,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Daniel Lam',
    'address': '4811 Ricky Club Suite 716\nSmithland, NM 90103',
    'text': 'Again blue possible government skin project send.\nStock however must treatment. Travel long care source street. Morning environment marriage experience.',
    'email': 'william59@example.com',
    'phone_number': '498.387.7190',
    'json': {
    'name': 'Amanda Wilson',
    'address': '7902 White Rest\nSandersberg, NM 99528',
},
    'key51955': 'value22725',
    'key53417': 'value26477',
},
    {
    'id': 17527487261360,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Michael Reese',
    'address': 'USCGC Meyer\nFPO AE 23450',
    'text': 'Mind happen woman serve never general similar strong. Husband body market notice meet behind. Pay source probably meeting response modern.\nEasy bank story hand. Plan hair where challenge.',
    'email': 'kelliwagner@example.com',
    'phone_number': '6882651556',
    'json': {
    'name': 'Lisa Gardner',
    'address': '36612 Dalton Drive Suite 272\nChristopherbury, UT 35133',
},
    'key83238': 'value28980',
    'key91860': 'value28813',
    'key24688': 'value22634',
    'key68465': 'value8605',
    'key21417': 'value19786',
    'key77726': 'value1089',
    'key6960': 'value96804',
},
    {
    'id': 17527487261371,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Michelle Lester',
    'address': '8235 Martin Stravenue Apt. 886\nPort Natasha, PR 66397',
    'text': 'Trade list environmental employee western. Military magazine available down. Fire amount TV war western benefit painting.',
    'email': 'jacksondarren@example.net',
    'phone_number': '3576114172',
    'json': {
    'name': 'Frank James',
    'address': '5217 White Stravenue Apt. 254\nNew Pamelaport, MT 13810',
},
    'key77687': 'value61440',
    'key27743': 'value32068',
},
    {
    'id': 17527487261382,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Mrs. Susan Garner',
    'address': 'Unit 1277 Box 7941\nDPO AP 52719',
    'text': 'Buy woman report develop seat. Anyone town indicate for keep. Its economy company toward building tonight public.\nYoung point nice describe understand.',
    'email': 'francisco49@example.com',
    'phone_number': '(729)420-1279x8707',
    'json': {
    'name': 'Theresa Keller',
    'address': '16614 Huang Crossroad\nBarryfurt, PA 82372',
},
    'key12624': 'value81004',
    'key81648': 'value28156',
    'key24981': 'value24529',
    'key16305': 'value7056',
    'key90885': 'value22674',
    'key45942': 'value43199',
    'key90921': 'value1697',
    'key80621': 'value16289',
},
    {
    'id': 17527487261391,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Patricia Miller',
    'address': '58360 Christopher Mission Apt. 907\nNorth Kimberly, IL 08415',
    'text': 'Seven staff your face leader student possible language. Type face herself believe letter several usually. Guess although world left public million meeting.',
    'email': 'adrienne47@example.net',
    'phone_number': '+1-970-691-1829x0064',
    'json': {
    'name': 'Jill Morris',
    'address': '11480 Zachary Prairie\nWest Lindsayview, MS 15262',
},
    'key78411': 'value6028',
    'key29398': 'value51746',
    'key68307': 'value63869',
},
    {
    'id': 17527487261401,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Tiffany Johnson',
    'address': '15133 Laura Fort Suite 099\nCynthiamouth, ND 60485',
    'text': 'Crime responsibility American air federal read conference western. Describe far art early class only. Stuff find just few.',
    'email': 'ysummers@example.net',
    'phone_number': '(252)256-7385x32682',
    'json': {
    'name': 'Leslie Rice',
    'address': '856 Melissa Square Apt. 130\nMoraleschester, WY 88382',
},
    'key28570': 'value24200',
},
    {
    'id': 17527487261412,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Ashley Lam DDS',
    'address': '312 Garcia Branch Suite 154\nJoshuaville, NE 13492',
    'text': 'Building huge force inside check enough. South organization organization catch. More will official political former.\nStep past east these church threat shake.',
    'email': 'juan14@example.com',
    'phone_number': '(506)576-6032x59581',
    'json': {
    'name': 'Mark Nicholson',
    'address': '613 Virginia Brook Suite 383\nNorth Monica, ME 09356',
},
    'key93822': 'value88920',
    'key93283': 'value34690',
    'key25875': 'value78962',
},
    {
    'id': 17527487261423,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Mark Thomas',
    'address': '6315 Phillip Run\nRothshire, RI 95776',
    'text': 'Continue dinner husband wide. Into trade turn better fall quickly young.\nWeight experience letter camera behind fund score. Explain wife against range act bad station.',
    'email': 'kelli76@example.net',
    'phone_number': '308-460-5764x22985',
    'json': {
    'name': 'Alexis Leblanc',
    'address': '90161 Sarah Islands\nEast Thomasport, DE 77541',
},
    'key94965': 'value81980',
    'key5044': 'value36884',
},
    {
    'id': 17527487261433,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Haley Perkins',
    'address': '34116 Thompson Spurs\nLake Tracyland, MH 92867',
    'text': 'Trouble action into Republican push institution right. Side simply word necessary first. Plan up young indeed development key Congress.',
    'email': 'jonathansmith@example.org',
    'phone_number': '001-672-201-1971x65403',
    'json': {
    'name': 'Joseph Wilcox',
    'address': '957 Deleon Cove\nPort Michelle, MD 90498',
},
    'key28039': 'value76180',
    'key60142': 'value19722',
    'key32136': 'value23213',
    'key81304': 'value65046',
    'key86018': 'value26101',
    'key71808': 'value99206',
    'key558': 'value66013',
    'key24158': 'value26630',
    'key80884': 'value78830',
    'key50740': 'value51446',
},
    {
    'id': 17527487261445,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Nicholas Franco',
    'address': '7542 Sarah Extensions Suite 105\nLloydstad, VT 41802',
    'text': 'Future tell should size rich. Whether trial pressure purpose police.\nWho foot still. Have standard different. Make kid character cause.\nWonder central parent imagine trip. Hold maybe citizen.',
    'email': 'liumark@example.com',
    'phone_number': '442-902-5120x0551',
    'json': {
    'name': 'April Dunn',
    'address': '29212 Scott Fort Suite 872\nWest Justinfort, MI 52159',
},
    'key65776': 'value74809',
    'key6897': 'value3847',
},
    {
    'id': 17527487261457,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'William Curry',
    'address': 'PSC 8507, Box 0642\nAPO AE 99550',
    'text': 'Professor mouth population social former. Property send reduce note decade like you. Yard production green share shoulder chance shoulder.',
    'email': 'jmarsh@example.com',
    'phone_number': '8473683277',
    'json': {
    'name': 'Selena Baker',
    'address': '66743 Bird Springs Suite 961\nKnoxhaven, AZ 43476',
},
    'key98364': 'value72420',
},
    {
    'id': 17527487261466,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Maria Kelley',
    'address': '44346 Michelle Union\nReedland, MD 46062',
    'text': 'Some time clearly inside probably result. Upon kid or soldier. Area learn business admit.\nAmerican class thought heavy himself.\nPut standard still physical.',
    'email': 'julieacosta@example.net',
    'phone_number': '+1-801-524-9447x310',
    'json': {
    'name': 'Katherine Ramirez',
    'address': '163 Erin Canyon Suite 715\nPort Kathy, VA 08791',
},
    'key96986': 'value8907',
    'key13778': 'value57726',
    'key37434': 'value73650',
    'key73476': 'value64428',
    'key71622': 'value53553',
    'key17084': 'value57870',
    'key18883': 'value83753',
},
    {
    'id': 17527487261477,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Tammy Kim',
    'address': '0445 Victoria Union Apt. 520\nLake William, TX 33229',
    'text': 'Action and thus them box security radio simply. Society star keep record successful financial.',
    'email': 'fperez@example.net',
    'phone_number': '001-597-627-2672x537',
    'json': {
    'name': 'James Shaffer',
    'address': '485 Doris Flats\nBurnsview, OK 49430',
},
    'key79131': 'value71651',
    'key16682': 'value99620',
    'key77030': 'value12735',
    'key36986': 'value53169',
    'key81252': 'value93583',
    'key63447': 'value3404',
    'key98430': 'value41239',
    'key68232': 'value8223',
},
    {
    'id': 17527487261487,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Aaron Meza',
    'address': '8422 Michael Freeway Apt. 102\nWernerbury, NC 37618',
    'text': 'Boy stop not writer national according unit. Him note along year certainly evidence cold.\nTrouble field beautiful produce pull decade name. Then style song indicate result gas.',
    'email': 'eric77@example.com',
    'phone_number': '001-252-922-6613x02714',
    'json': {
    'name': 'Diana Clark',
    'address': '6625 Allison Greens Apt. 911\nRobertfort, RI 46481',
},
    'key40505': 'value32060',
    'key97320': 'value90160',
},
    {
    'id': 17527487261498,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Shawn Johnson',
    'address': '946 Nicole Harbor Suite 255\nLake Thomas, NC 19809',
    'text': 'Manager old teach security back. Good medical minute. Reflect discuss mission government laugh animal.',
    'email': 'ashley57@example.net',
    'phone_number': '653.333.4415',
    'json': {
    'name': 'Carlos Garcia',
    'address': '456 Wang Cove\nLake Danielmouth, VI 96153',
},
    'key78429': 'value51706',
    'key61116': 'value78794',
    'key2690': 'value44436',
    'key84685': 'value38914',
    'key14815': 'value74280',
    'key33489': 'value12943',
},
    {
    'id': 17527487261508,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Karen Phelps',
    'address': '7269 Karla Views\nPadillaborough, MS 51255',
    'text': 'Pattern decide down attention end who prove. Although girl minute Mr. Wrong camera use challenge ball none ago.\nAgo trip a last. Garden own us pressure her. Choice majority hot side daughter.',
    'email': 'jennifer65@example.net',
    'phone_number': '645-570-5099x1418',
    'json': {
    'name': 'Lisa Walton',
    'address': '16708 Cynthia Course\nBrendaburgh, NV 81711',
},
    'key22621': 'value93014',
    'key50905': 'value50510',
    'key92622': 'value3337',
    'key99322': 'value77487',
    'key23488': 'value88722',
    'key58479': 'value6900',
    'key88266': 'value81500',
    'key17547': 'value53667',
    'key61967': 'value35794',
    'key43581': 'value58768',
},
    {
    'id': 17527487261519,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Allison Nelson',
    'address': '768 Nicholas Place\nSmithton, RI 01321',
    'text': 'Institution public husband fire technology central star. Short officer view fight shoulder national. Perhaps between view claim figure certainly opportunity create.',
    'email': 'anthonypadilla@example.net',
    'phone_number': '4049083442',
    'json': {
    'name': 'Becky Brown',
    'address': '760 Scott Hills Apt. 502\nPort Samanthaton, FM 82978',
},
    'key18675': 'value34183',
},
    {
    'id': 17527487261530,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Kelsey Strong',
    'address': '11786 Kathleen Brooks Suite 154\nRogersland, CO 51385',
    'text': 'Indicate less local keep half culture. Concern lay majority TV into determine.\nRaise seek reach pass decade dark. Pressure type central. Past stage run sport fact.',
    'email': 'gjones@example.net',
    'phone_number': '001-334-798-8525',
    'json': {
    'name': 'Olivia Stewart',
    'address': '447 Dawson Lodge Apt. 388\nLewisfurt, AS 02546',
},
    'key91175': 'value42840',
},
    {
    'id': 17527487261542,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'David Williams',
    'address': 'USNV Lara\nFPO AA 99483',
    'text': 'No address administration certain none war. Run finally win order. Foreign shoulder office raise organization security financial.',
    'email': 'schmidtpaula@example.net',
    'phone_number': '2026548517',
    'json': {
    'name': 'Marcus Stephenson',
    'address': '088 Brianna Trail\nSouth Cody, SD 75955',
},
    'key47449': 'value14476',
    'key45892': 'value19198',
    'key21644': 'value84945',
    'key48085': 'value21433',
    'key84246': 'value28876',
    'key36921': 'value58178',
},
    {
    'id': 17527487261552,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Robin Neal',
    'address': '6326 Brennan Coves Apt. 321\nKaitlinville, NH 60096',
    'text': 'Expert international get decide meet wish. Event analysis west later knowledge create trouble.',
    'email': 'dannyduke@example.org',
    'phone_number': '(916)719-0930',
    'json': {
    'name': 'Tiffany Nunez',
    'address': '7612 Hall Square\nGuzmanstad, AL 99413',
},
    'key97590': 'value97524',
},
    {
    'id': 17527487261563,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Christopher Chan',
    'address': '7615 Smith Glens\nPort Latasha, PA 07732',
    'text': 'Garden else recent nothing benefit better. Region old travel special professional.\nFather present follow involve every situation teach. It degree you painting section direction.',
    'email': 'blewis@example.net',
    'phone_number': '+1-954-925-9633x56977',
    'json': {
    'name': 'Joshua Combs',
    'address': '858 Mitchell Coves\nWest Bridgetside, AK 70001',
},
    'key64541': 'value5694',
    'key16954': 'value85381',
    'key85551': 'value92250',
    'key58458': 'value29528',
    'key3271': 'value82102',
    'key32379': 'value82827',
    'key80241': 'value26004',
    'key12480': 'value50320',
},
    {
    'id': 17527487261574,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Jon Stafford',
    'address': '2889 Richard Shoals Suite 023\nEast Kristiton, IL 33232',
    'text': 'Program industry money nice power. Always great fire attack green fly. Truth voice choose rich.',
    'email': 'edavis@example.net',
    'phone_number': '(380)642-9632',
    'json': {
    'name': 'David Rowe',
    'address': '507 Cooper Corners\nSouth Joshuamouth, MD 48001',
},
    'key86789': 'value67440',
    'key62213': 'value67835',
},
    {
    'id': 17527487261585,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Mr. Rodney Maynard',
    'address': 'Unit 4230 Box 7814\nDPO AP 86851',
    'text': 'Stage race stand matter throw cell individual. Reveal better within positive bit. Her suggest wall attack drug rate. Throughout stay case certain.',
    'email': 'denisegonzalez@example.net',
    'phone_number': '295-604-9275',
    'json': {
    'name': 'James Jones',
    'address': '053 Watkins Branch Suite 199\nBaileyside, OH 77314',
},
    'key38717': 'value39816',
    'key82155': 'value71630',
    'key68628': 'value71650',
},
    {
    'id': 17527487261595,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Bradley Boyle',
    'address': '200 Ramirez Prairie Apt. 218\nMooreville, KS 24067',
    'text': 'Hair until accept nice thought. Cover morning maybe who year.\nField impact weight situation. Mission enough small though environmental total. Possible ground simply.',
    'email': 'wrichards@example.org',
    'phone_number': '001-765-507-4734x8997',
    'json': {
    'name': 'John Bean',
    'address': 'Unit 8041 Box 4245\nDPO AP 49801',
},
    'key68442': 'value15131',
    'key41200': 'value39606',
    'key74196': 'value78106',
    'key23092': 'value31649',
    'key26189': 'value72204',
    'key45782': 'value31413',
    'key55627': 'value66413',
    'key98859': 'value94208',
},
    {
    'id': 17527487261604,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Brittany Walker',
    'address': '8782 Cynthia Port Apt. 547\nPearsonfurt, MI 93804',
    'text': 'Test require join decide. Seven some price fact.\nMyself young close evidence their movement where. Rest already throughout TV.',
    'email': 'crystalduncan@example.org',
    'phone_number': '001-915-747-5571x8170',
    'json': {
    'name': 'Daniel Miller',
    'address': '0144 Albert Street Suite 514\nJoneschester, ME 49203',
},
    'key50169': 'value7875',
    'key81542': 'value56737',
    'key47925': 'value70304',
    'key14887': 'value71800',
    'key21177': 'value78347',
    'key77240': 'value40846',
    'key40849': 'value51804',
},
    {
    'id': 17527487261615,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Samantha Duarte',
    'address': '065 Regina Courts Apt. 528\nKingstad, HI 16195',
    'text': 'Six husband stop Democrat box guess wide. Cover reveal represent if increase general blood.',
    'email': 'nblake@example.com',
    'phone_number': '001-931-307-3398',
    'json': {
    'name': 'Alexander Adams',
    'address': 'Unit 8538 Box 7840\nDPO AP 69791',
},
    'key30073': 'value94565',
    'key56111': 'value92862',
},
    {
    'id': 17527487261624,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Stephen Joyce',
    'address': '36092 Doyle Underpass\nNorth Donnafort, PA 41120',
    'text': 'Skin use clearly increase thought door government produce.\nExperience these eat mention movie. Newspaper interesting specific realize.',
    'email': 'bishopashley@example.net',
    'phone_number': '300.702.5869',
    'json': {
    'name': 'Daniel Russell',
    'address': '09410 Randolph Expressway Suite 192\nChristinashire, OK 15990',
},
    'key43360': 'value79239',
    'key60338': 'value85150',
    'key23829': 'value54430',
    'key22993': 'value40083',
},
    {
    'id': 17527487261635,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Robyn Nelson',
    'address': '538 Davis Shoals Suite 804\nJenniferstad, WV 76432',
    'text': 'Water doctor your purpose scientist old professional. Rule rich positive road American field.',
    'email': 'justinmeyers@example.com',
    'phone_number': '(502)961-0360x9801',
    'json': {
    'name': 'Marcus Moore',
    'address': '33250 Donald Plains Suite 387\nNorth Jade, GA 76038',
},
    'key43987': 'value44177',
    'key81600': 'value92415',
    'key2969': 'value41476',
    'key3480': 'value92792',
    'key12300': 'value64420',
    'key36723': 'value58870',
},
    {
    'id': 17527487261647,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Deborah Mclaughlin',
    'address': '0307 Martinez Crescent Suite 300\nPort Jason, AL 57985',
    'text': 'Contain treat drive air charge. Officer campaign last management type modern everyone. Include community possible sister couple create. Business foreign cover.',
    'email': 'ayaladaniel@example.org',
    'phone_number': '(974)576-4768',
    'json': {
    'name': 'Samantha Moore',
    'address': '5814 Kimberly Circle Apt. 854\nSouth James, ME 85883',
},
    'key37925': 'value55913',
    'key26290': 'value12871',
    'key65912': 'value9384',
    'key40308': 'value12553',
    'key41214': 'value9013',
    'key11089': 'value66620',
    'key4855': 'value44770',
    'key77378': 'value37436',
    'key48752': 'value7981',
},
    {
    'id': 17527487261658,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Mary Schmidt',
    'address': '18409 David Spurs\nJarvistown, VA 53164',
    'text': 'Pay guess unit evening probably responsibility.\nBlue range ok yet name for. Religious often how investment owner. Apply buy dog would spend.',
    'email': 'allison94@example.com',
    'phone_number': '438.999.5214x0912',
    'json': {
    'name': 'Brett Shelton',
    'address': '0002 Williams Stravenue\nMichaelfurt, HI 51595',
},
    'key8724': 'value87607',
    'key52878': 'value98886',
    'key56849': 'value86783',
    'key20637': 'value88213',
    'key37186': 'value92538',
},
    {
    'id': 17527487261669,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Betty Lee',
    'address': '150 Allen Turnpike Apt. 336\nEast Williamside, MH 78020',
    'text': 'Question piece draw movement. Ask government instead her nothing model maybe sort.',
    'email': 'jcaldwell@example.org',
    'phone_number': '616-573-7209x45015',
    'json': {
    'name': 'Ronnie Campbell',
    'address': '05902 Cook Flats Apt. 536\nMelissafurt, NJ 26618',
},
    'key82247': 'value57694',
    'key97881': 'value60617',
    'key43226': 'value32300',
    'key10738': 'value67230',
    'key2094': 'value31942',
    'key47568': 'value31442',
    'key10252': 'value36484',
    'key11012': 'value93782',
},
    {
    'id': 17527487261680,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Kevin Carey DDS',
    'address': '6251 Sheila Coves\nSouth Elizabethton, AK 01479',
    'text': 'Career firm million president bad. Scene hand off attack past across here. Vote create face certain growth set provide.\nSpace laugh receive town. Drug challenge everything soldier.',
    'email': 'henry10@example.org',
    'phone_number': '970-950-8652x89200',
    'json': {
    'name': 'Kathleen Randolph',
    'address': '78238 King Summit Apt. 685\nEast Cory, PA 54397',
},
    'key99170': 'value45889',
    'key15273': 'value36640',
    'key77103': 'value10480',
    'key65019': 'value23575',
    'key31837': 'value4030',
},
    {
    'id': 17527487261691,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Martha Robertson',
    'address': 'USNS Jones\nFPO AP 60703',
    'text': 'Food garden music stage fine tough.\nItem rule or computer add. Bill part government day drug focus early.\nBreak industry fear become might author. Participant read team.',
    'email': 'leetina@example.net',
    'phone_number': '844-559-2839x92884',
    'json': {
    'name': 'John Murphy',
    'address': '509 Goodwin Ramp\nNorth Vincent, GU 57020',
},
    'key94506': 'value23108',
},
    {
    'id': 17527487261701,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Charles Kane',
    'address': '6255 Reynolds Via\nEast Noah, RI 24514',
    'text': 'Religious eye social couple tonight religious believe perhaps. Name crime white main reason walk together. Pull operation away response suddenly store nice.',
    'email': 'echavez@example.net',
    'phone_number': '786.434.8703x8272',
    'json': {
    'name': 'Sydney Holt',
    'address': 'USCGC Barnett\nFPO AE 34846',
},
    'key63476': 'value68284',
    'key61409': 'value88032',
    'key28678': 'value41459',
    'key59774': 'value44935',
    'key66408': 'value66874',
    'key61977': 'value59126',
},
    {
    'id': 17527487261711,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Christine Watson',
    'address': '187 Dale Mountains Apt. 415\nNorth Feliciaview, DC 11208',
    'text': 'Surface nice trade similar speech thing professor toward. Better fish source record senior.\nBetter else player. Face drug agree as second. Ability food any time thousand region.',
    'email': 'jarvissarah@example.net',
    'phone_number': '(484)958-8974',
    'json': {
    'name': 'Angela Lucero',
    'address': '11735 Rubio Mountain Apt. 726\nNorth Lisabury, SC 96726',
},
    'key12912': 'value74141',
    'key1948': 'value859',
    'key23985': 'value85644',
    'key88833': 'value45922',
    'key57567': 'value62638',
    'key78884': 'value65898',
    'key64947': 'value9959',
    'key44598': 'value31096',
},
    {
    'id': 17527487261722,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Johnny Larson',
    'address': 'PSC 3238, Box 3971\nAPO AE 05176',
    'text': 'Answer cup to culture. Others standard guy cost effect answer art. Capital forward evening pay.\nData gas what future name. Wonder usually step start. Election far vote.',
    'email': 'adrian69@example.com',
    'phone_number': '245.946.9231x878',
    'json': {
    'name': 'Mary Barnett',
    'address': '2640 Shannon Rapid Apt. 263\nWillieshire, NE 40053',
},
    'key66503': 'value49646',
    'key69589': 'value27458',
    'key16469': 'value46062',
    'key88863': 'value48610',
    'key16502': 'value48245',
    'key41524': 'value39806',
    'key32846': 'value93368',
},
    {
    'id': 17527487261731,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Eric Jones',
    'address': '10828 Christy Court\nNorth Crystal, NH 73473',
    'text': 'That fish movement second past. Social record building machine. Center enough continue wait hand.',
    'email': 'lodom@example.net',
    'phone_number': '001-426-989-6056x923',
    'json': {
    'name': 'Veronica Cruz',
    'address': '11271 Tristan Groves Suite 749\nTaylorshire, TX 86698',
},
    'key56390': 'value62412',
    'key14520': 'value63767',
    'key69306': 'value5695',
    'key28061': 'value85399',
    'key20624': 'value55877',
    'key63910': 'value43308',
    'key72121': 'value65430',
    'key94235': 'value9978',
    'key91547': 'value18213',
    'key1598': 'value82430',
},
    {
    'id': 17527487261741,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Emily Moreno',
    'address': '114 Chaney Lake\nNew Joeburgh, NC 32083',
    'text': 'In sing live wrong leg five. Across evidence room hear life hold. Last deal institution but movie.\nGun various send color. Because upon action worry sound. Occur career camera firm special even.',
    'email': 'michael31@example.org',
    'phone_number': '001-636-506-1561',
    'json': {
    'name': 'Michael Johnson',
    'address': '35300 Weaver Green Suite 020\nMcdanielbury, NV 94185',
},
    'key47615': 'value43005',
    'key32453': 'value73660',
    'key78991': 'value62839',
    'key51358': 'value14651',
    'key65567': 'value11798',
    'key5438': 'value46476',
    'key88757': 'value58485',
    'key81672': 'value20753',
    'key12425': 'value91514',
},
    {
    'id': 17527487261753,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Angel Anderson',
    'address': '238 Loretta Fork Suite 944\nJenniferfurt, TN 85414',
    'text': 'Strong million crime the worry show. Threat threat method single memory art under town.',
    'email': 'megantravis@example.net',
    'phone_number': '001-409-725-5593x0678',
    'json': {
    'name': 'James Ruiz',
    'address': '0861 Weber Plaza Suite 058\nGibbsport, OR 38880',
},
    'key11314': 'value57817',
    'key30423': 'value68693',
    'key95299': 'value63679',
    'key33485': 'value15496',
},
    {
    'id': 17527487261764,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Teresa Owens',
    'address': '42425 Sandra Ridge Apt. 901\nPort Jessicaberg, NH 40972',
    'text': 'Step fine risk everyone. Finally unit carry later conference teach quality.\nFew yes first. Minute assume month money hit send. Us candidate ahead.\nPeople impact theory then ever safe.',
    'email': 'nancymartinez@example.net',
    'phone_number': '588-513-7826',
    'json': {
    'name': 'Cody Brooks',
    'address': '41386 Michele Mountains\nFergusonfurt, SC 87804',
},
    'key43021': 'value36787',
    'key15512': 'value89430',
    'key57150': 'value220',
    'key93038': 'value61297',
    'key62303': 'value88787',
    'key28878': 'value14853',
},
    {
    'id': 17527487261776,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Mr. Ronald Frank',
    'address': '2979 Brandon Shoals Apt. 311\nJacquelineview, DC 51817',
    'text': 'Pick course politics despite property build then. These explain than maintain focus rich civil than.\nMaterial oil food measure.\nIdea special include join. Yet network laugh box certainly.',
    'email': 'tina12@example.org',
    'phone_number': '(609)650-9484',
    'json': {
    'name': 'Katelyn Nguyen',
    'address': '264 Hudson Garden Apt. 127\nDeanshire, NE 58808',
},
    'key6782': 'value14650',
    'key14378': 'value44793',
    'key14718': 'value39193',
    'key59725': 'value98473',
    'key20288': 'value46028',
    'key20358': 'value63840',
    'key81202': 'value10088',
},
    {
    'id': 17527487261787,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Natasha Oconnell',
    'address': '5181 Michael Street\nSmithtown, GA 54249',
    'text': 'Vote either sound even. Never less throw if.\nSport cause artist a. Teach before job commercial but clear second. Why save on put growth.\nSpecific my suddenly other stand.',
    'email': 'gdiaz@example.com',
    'phone_number': '(273)469-9473',
    'json': {
    'name': 'Rebecca Jones',
    'address': '87191 Hayden Lodge\nShanebury, PA 94239',
},
    'key13535': 'value80105',
    'key24641': 'value42112',
    'key40475': 'value88611',
    'key99832': 'value82307',
    'key42650': 'value79490',
    'key83340': 'value44895',
    'key61346': 'value62618',
    'key64984': 'value50804',
    'key4818': 'value76572',
},
    {
    'id': 17527487261798,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Isaac Cochran',
    'address': '2691 Hurst Overpass\nNorth Sean, GA 48184',
    'text': 'Car smile station news. Nor much somebody new building fire. Clear benefit throughout rock newspaper child where.',
    'email': 'lwilliams@example.net',
    'phone_number': '411-552-7839x4710',
    'json': {
    'name': 'Christina Floyd',
    'address': '695 Green Underpass Apt. 157\nRyanmouth, MD 07036',
},
    'key21101': 'value8481',
    'key60336': 'value21721',
    'key66095': 'value60556',
    'key38707': 'value78188',
    'key11947': 'value34222',
    'key31780': 'value2213',
    'key71089': 'value34227',
    'key679': 'value78989',
    'key91593': 'value71562',
    'key84069': 'value75405',
},
    {
    'id': 17527487261809,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Phyllis Velazquez',
    'address': '750 David Circles Suite 991\nDavisburgh, TX 66147',
    'text': 'Which cost nature run. Clear hope represent beautiful door bit single wonder.\nHave design place because represent base. This pull ok southern oil. Owner local yeah. Quite which image thousand sure.',
    'email': 'owatson@example.org',
    'phone_number': '8335164796',
    'json': {
    'name': 'Erica Winters',
    'address': '989 Abigail Fall\nRichardtown, ID 46730',
},
    'key99636': 'value54214',
    'key37244': 'value33885',
    'key18074': 'value84361',
    'key4058': 'value78028',
    'key12841': 'value48315',
    'key96867': 'value16385',
    'key29661': 'value8690',
    'key58499': 'value15942',
},
    {
    'id': 17527487261820,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Barbara Collins',
    'address': '850 Katrina Fall Suite 202\nLaraberg, VA 04821',
    'text': 'Top city show those the senior may. Else Congress main. Pressure hundred somebody sort investment.',
    'email': 'jennifer54@example.net',
    'phone_number': '237-242-9773x4826',
    'json': {
    'name': 'Amanda Alexander',
    'address': '034 Russo Lights Suite 619\nPort Mackenzie, PW 93186',
},
    'key62724': 'value84793',
    'key84043': 'value66540',
    'key54661': 'value84326',
    'key39449': 'value33040',
    'key78812': 'value42249',
    'key84626': 'value67094',
    'key46804': 'value63355',
    'key69545': 'value48421',
    'key29676': 'value62869',
},
    {
    'id': 17527487261830,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Eugene Robbins',
    'address': '76735 Spencer Corner Apt. 633\nMeganfort, AS 14561',
    'text': 'Source relate individual leg at admit.\nPressure including central economy system like those water. Star may base laugh wish expect pay.',
    'email': 'kimberlyramirez@example.com',
    'phone_number': '+1-331-634-3428',
    'json': {
    'name': 'Jamie Ware',
    'address': '564 Christopher Inlet Suite 178\nNorth Angela, AR 31564',
},
    'key12715': 'value24801',
    'key22897': 'value97000',
    'key88810': 'value47030',
    'key20079': 'value72512',
    'key13476': 'value77388',
},
    {
    'id': 17527487261842,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Monique Jenkins',
    'address': 'Unit 0883 Box 0326\nDPO AA 86453',
    'text': 'Enter attorney remain task community. Culture president number. Rock issue great light.\nEvidence accept cost tonight general send. Front computer vote available knowledge city central because.',
    'email': 'jeffreyclark@example.com',
    'phone_number': '+1-630-482-5387x53688',
    'json': {
    'name': 'Theresa Wood',
    'address': '743 Fisher Road\nEast Samuel, MT 29403',
},
    'key30939': 'value25850',
    'key76829': 'value75676',
    'key83502': 'value54423',
    'key57772': 'value86109',
    'key75084': 'value54901',
    'key79628': 'value79872',
    'key77779': 'value75746',
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
    'RequestId': '33e2b5ee-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_40_036701BZgkzIeE',
    'filter': 'uid >= 0',
    'limit': 100,
    'offset': 0,
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
    'RequestId': '33e2b5ee-62fa-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_38_40_036701BZgkzIeE',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-False-uid >= 0]_1752748732.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueFalseUid01752748732Json()
    test.run_tests()
