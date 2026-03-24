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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestQueryVector_test_query_vector_with_int64_filter[True-True-uid in [1,2,3,4]]_1752748617_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid in [1,2,3,4]]_1752748617.json"
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



class AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUidIn12341752748617Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid in [1,2,3,4]]_1752748617.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid in [1,2,3,4]]_1752748617.json"
        self.test_count = 8  # 测试方法数量
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
    'RequestId': 'ee25a49e-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_43_035324EYujWVoC',
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
    'RequestId': 'ee25a49e-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_43_035324EYujWVoC',
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
    'RequestId': 'ee25a49e-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_43_035324EYujWVoC',
    'data': [
    {
    'id': 17527486090712,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Donna Carter',
    'address': '37690 Chapman Common\nDavenportshire, CT 02020',
    'text': 'Although avoid employee six. Season laugh media consider.\nTv writer however way. There beat eight last be if among. Guy spring heart lot important level.',
    'email': 'hannah80@example.com',
    'phone_number': '+1-999-900-7551x8436',
    'json': {
    'name': 'Pamela Cline',
    'address': 'PSC 1068, Box 9814\nAPO AP 89342',
},
    'key75776': 'value27621',
    'key27991': 'value86936',
    'key36977': 'value20075',
    'key80154': 'value33592',
    'key16275': 'value16639',
    'key6870': 'value65200',
},
    {
    'id': 17527486090731,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Amber Leonard',
    'address': 'USS Lewis\nFPO AP 22562',
    'text': 'Class our hot need thought nation own. Less strategy general record call. Able likely activity notice body compare. Its civil indeed.\nRegion tax sound. Personal region almost boy cause family.',
    'email': 'elizabethwood@example.net',
    'phone_number': '4968503001',
    'json': {
    'name': 'Dawn Jones',
    'address': '969 Reed Prairie Apt. 518\nEast Lisastad, MT 05035',
},
    'key88222': 'value91131',
    'key28102': 'value78594',
    'key28317': 'value71891',
},
    {
    'id': 17527486090746,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Matthew Mcintosh',
    'address': '1887 Justin Port\nHernandezbury, PR 48653',
    'text': 'Contain its step unit above room. Military explain his. Word staff kitchen type newspaper.',
    'email': 'millersarah@example.org',
    'phone_number': '+1-415-870-7367x90380',
    'json': {
    'name': 'Joe Taylor',
    'address': '357 Jonathan Summit\nNorth Justin, AL 70772',
},
    'key18370': 'value77701',
    'key65374': 'value84411',
    'key40678': 'value69619',
},
    {
    'id': 17527486090760,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Sharon Hill',
    'address': '56633 Roach Tunnel Apt. 886\nPhillipsmouth, IN 65426',
    'text': 'Book side structure likely civil pass right. Than body crime enter.\nEnvironment kitchen agent health do affect about.\nGreat season listen voice whatever last. Decade fund bag up anyone hundred.',
    'email': 'clarkstacy@example.net',
    'phone_number': '+1-453-709-8677',
    'json': {
    'name': 'Joseph Smith',
    'address': 'USCGC Mcdonald\nFPO AE 20161',
},
    'key32306': 'value42527',
    'key43373': 'value54408',
    'key89113': 'value37441',
    'key7499': 'value99248',
    'key91711': 'value61292',
    'key3596': 'value10816',
    'key90917': 'value10989',
    'key61964': 'value77011',
    'key80668': 'value85441',
},
    {
    'id': 17527486090775,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Joseph Norman',
    'address': '0771 Angela Common\nCarterview, NV 06389',
    'text': 'Left like work hundred. Network begin operation. Drug in treatment quality deep ability.\nClose minute remember poor war next institution fall. Everything democratic thank much.',
    'email': 'haledebra@example.org',
    'phone_number': '707.221.4340',
    'json': {
    'name': 'Mark Thompson DDS',
    'address': '119 Santiago Springs Apt. 082\nSouth Jonathan, NY 23822',
},
    'key2222': 'value50637',
    'key97837': 'value94256',
    'key16813': 'value31315',
    'key53676': 'value79614',
    'key57589': 'value53250',
},
    {
    'id': 17527486090789,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Christina Montoya',
    'address': '97005 Kathleen Divide Apt. 496\nAndreaberg, IA 20891',
    'text': 'People wife they level operation. Owner then experience under above. Result view every trip lose.',
    'email': 'christineevans@example.org',
    'phone_number': '698.662.6995x95811',
    'json': {
    'name': 'Kevin Rogers',
    'address': '94128 Yolanda Ramp Apt. 081\nPort Kaitlinmouth, MP 07005',
},
    'key19276': 'value14237',
    'key22778': 'value82770',
},
    {
    'id': 17527486090805,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Linda Jones',
    'address': '61966 Kelly Rue Apt. 552\nAndreahaven, KS 77911',
    'text': 'May with yet certainly when left.\nFear open use prevent next particularly toward front. Mean tonight under amount computer. Technology rate determine defense.',
    'email': 'jeffreywilson@example.com',
    'phone_number': '696-997-7610',
    'json': {
    'name': 'Ashley Gonzalez',
    'address': '71238 Barnes Drive Suite 874\nLatoyaborough, WY 95119',
},
    'key21523': 'value24653',
},
    {
    'id': 17527486090820,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Adam Potts',
    'address': '4211 Kristen Parks\nNorth Lorraine, IL 22590',
    'text': 'Artist rather major play personal. Tell their allow support staff crime window Congress.\nThank wrong only. Much direction job study party reason. Oil truth son whatever mission.',
    'email': 'bward@example.com',
    'phone_number': '(515)902-7223x144',
    'json': {
    'name': 'Rachel Shaffer',
    'address': '42120 Cox Ramp\nConradview, CA 10518',
},
    'key56918': 'value18376',
    'key90322': 'value15772',
    'key71201': 'value70628',
    'key45314': 'value92625',
    'key85584': 'value21788',
    'key84642': 'value86587',
    'key42388': 'value6787',
    'key68560': 'value62069',
    'key83349': 'value40232',
},
    {
    'id': 17527486090834,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Whitney Smith',
    'address': '2857 Timothy Station Apt. 144\nLake Maryview, IA 44068',
    'text': 'Buy partner water since should heart. Possible help life their local write.\nPolice turn full wish but music or. Hospital attention list action discover eat lead.',
    'email': 'sara22@example.com',
    'phone_number': '(684)304-6256x10247',
    'json': {
    'name': 'Donna Santiago',
    'address': '9450 Tammy Island Suite 585\nDavisfort, NV 64806',
},
    'key56623': 'value60370',
    'key48542': 'value22429',
    'key87818': 'value32408',
    'key59216': 'value756',
    'key71641': 'value57872',
    'key97503': 'value47357',
    'key39115': 'value57497',
    'key12625': 'value83688',
    'key78719': 'value90242',
    'key55440': 'value18678',
},
    {
    'id': 17527486090848,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Megan Scott',
    'address': '37147 Watson Circle\nPort Warren, NY 85795',
    'text': 'Owner myself local face local choose level those. Toward direction until part. Account drop ground offer firm guess behind.\nService both remain outside carry.',
    'email': 'scottelizabeth@example.org',
    'phone_number': '+1-689-857-1138',
    'json': {
    'name': 'Susan Duran',
    'address': '601 Patrick Garden\nBurtonshire, PA 70578',
},
    'key96857': 'value81945',
    'key97282': 'value81613',
},
    {
    'id': 17527486090862,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Michelle Dunn',
    'address': '0041 Kim Alley\nNicolebury, AL 66139',
    'text': 'Onto address personal radio him current.\nPossible age debate would according. Else animal involve month opportunity she. Civil around modern area property student though.',
    'email': 'zgarcia@example.net',
    'phone_number': '342.757.4150x6177',
    'json': {
    'name': 'Joshua Robinson',
    'address': '61845 Jessica Coves Suite 672\nPort Garyburgh, IL 68966',
},
    'key42018': 'value7191',
    'key40945': 'value86513',
    'key8325': 'value93517',
},
    {
    'id': 17527486090876,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'David Nelson',
    'address': '293 Blevins Mews Apt. 575\nNorth Earltown, IA 22612',
    'text': 'Only today determine sell space fast. History floor citizen its. Could thought chair.\nOwn skill key eat local. Citizen buy remain character who.',
    'email': 'barronrobert@example.net',
    'phone_number': '3392800312',
    'json': {
    'name': 'Edward Scott',
    'address': '973 Courtney Forges Apt. 111\nPaulborough, NH 83443',
},
    'key40783': 'value93250',
    'key4858': 'value99919',
    'key12053': 'value93647',
},
    {
    'id': 17527486090891,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Mary Johnson',
    'address': '42338 Cole Grove Apt. 736\nBrookeborough, AS 67640',
    'text': 'Wind especially standard director subject. Key specific before. Manager grow assume language probably message two.',
    'email': 'victoria19@example.com',
    'phone_number': '901.546.1489',
    'json': {
    'name': 'Autumn Keller',
    'address': '963 Michael Union\nNew Marc, WI 14287',
},
    'key71992': 'value3378',
    'key68824': 'value39381',
    'key48555': 'value88578',
    'key51380': 'value30294',
},
    {
    'id': 17527486090903,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Kimberly Miller',
    'address': 'Unit 7555 Box 4272\nDPO AE 61027',
    'text': 'Price goal four reveal. Region might day space raise article.\nPlace pay view. Chair media science south exist.\nNo matter this high board smile concern. Production discover guess free eight impact.',
    'email': 'drichard@example.net',
    'phone_number': '780-206-9560x2070',
    'json': {
    'name': 'Samantha Brown',
    'address': '9926 Johnson Villages\nBakerhaven, GA 41637',
},
    'key28436': 'value78430',
},
    {
    'id': 17527486090914,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Sharon Thomas',
    'address': '341 Ricardo Lane\nDixonfort, MT 95193',
    'text': 'State health yourself hand do. Until similar bar true suffer some consumer money.',
    'email': 'sschmidt@example.org',
    'phone_number': '001-524-917-4720',
    'json': {
    'name': 'Jeanne Barr',
    'address': '5939 Jared Locks Apt. 301\nNew Kimberlyberg, AL 51662',
},
    'key84620': 'value84588',
    'key73596': 'value43983',
    'key94979': 'value16558',
},
    {
    'id': 17527486090926,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Casey Morales',
    'address': '54151 Sean Common\nWeaverborough, HI 67498',
    'text': 'Goal much cost red old protect whatever these. Director forget where six enter despite.\nCandidate gun still analysis myself close popular. Lot how around believe side find.',
    'email': 'tstone@example.net',
    'phone_number': '+1-326-870-5409x2657',
    'json': {
    'name': 'Sean Schmidt',
    'address': '4668 Burns Ports Apt. 353\nGregoryside, MI 02277',
},
    'key98921': 'value54798',
    'key92139': 'value3097',
    'key29316': 'value59093',
},
    {
    'id': 17527486090939,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Alicia Foster',
    'address': 'PSC 0447, Box 5053\nAPO AE 22801',
    'text': 'Take middle keep pay build newspaper fund. Population through somebody kid recognize. Full machine star defense right.',
    'email': 'michaelalandry@example.org',
    'phone_number': '001-767-285-5953x8271',
    'json': {
    'name': 'Victoria Norris',
    'address': '762 Robinson Lock Suite 233\nDaltonstad, GU 86761',
},
    'key55654': 'value60916',
    'key33579': 'value7072',
    'key53213': 'value98454',
    'key90319': 'value74721',
    'key87440': 'value82378',
    'key83982': 'value94183',
    'key82643': 'value16213',
},
    {
    'id': 17527486090951,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'Virginia Sanchez',
    'address': '75160 Miller Pike Apt. 221\nTarafort, MH 70068',
    'text': 'Toward decision growth. Work wish difficult member parent him cost recent. Sort while beyond technology site not. Think actually forward back threat money.',
    'email': 'briannaelliott@example.com',
    'phone_number': '2535381490',
    'json': {
    'name': 'Nathaniel Stewart',
    'address': '425 Keith Viaduct\nEast Christophershire, CT 71132',
},
    'key68589': 'value96941',
    'key73460': 'value49972',
    'key38288': 'value26381',
    'key94281': 'value2640',
},
    {
    'id': 17527486090965,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Beverly Murphy',
    'address': '8361 Perry Throughway\nJuliemouth, TX 73155',
    'text': 'Authority agency car news back concern. Order for win federal. Least provide low suggest.\nWhether skin ever try safe. Do knowledge seat suffer left mind. Raise respond article sign receive machine.',
    'email': 'amandagay@example.com',
    'phone_number': '(997)587-4032',
    'json': {
    'name': 'Daniel Jackson',
    'address': '894 Lewis Terrace Suite 550\nAveryborough, HI 60727',
},
    'key9191': 'value50815',
    'key60226': 'value23968',
    'key88169': 'value60491',
},
    {
    'id': 17527486090980,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Steven Garner',
    'address': '4218 Jeffrey Court\nWest Bradymouth, PA 79270',
    'text': 'Career particularly economic detail total. Democrat table opportunity television. Million important enough choose shoulder edge.',
    'email': 'bradleymadison@example.com',
    'phone_number': '588.815.0580',
    'json': {
    'name': 'Adrian Maxwell',
    'address': '204 Francisco Prairie Suite 380\nJosephview, WA 38042',
},
    'key51549': 'value78559',
    'key21209': 'value78231',
    'key56050': 'value94637',
    'key74216': 'value11283',
    'key85153': 'value9471',
    'key87905': 'value72789',
    'key13805': 'value84340',
    'key53768': 'value96920',
},
    {
    'id': 17527486090993,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Aaron Flynn',
    'address': '195 Vaughan Pass Suite 370\nSouth Colleenbury, TN 42068',
    'text': 'Charge treatment concern thank company mention investment. Analysis firm here smile return country.',
    'email': 'jeffrey26@example.org',
    'phone_number': '001-568-416-8064x799',
    'json': {
    'name': 'Jessica Boone',
    'address': '7518 Patricia Cliffs Suite 639\nSouth Jeremy, MD 04161',
},
    'key76075': 'value75050',
    'key19122': 'value3386',
    'key41721': 'value2955',
},
    {
    'id': 17527486091005,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Phyllis Carpenter',
    'address': '56469 Anderson Overpass Apt. 402\nWest Benjamin, IA 48994',
    'text': 'Writer argue investment. Weight chance vote music offer organization trade dream. Series above free meet lot bank her. May serve woman office contain law.',
    'email': 'matthew24@example.com',
    'phone_number': '958.986.4064x51313',
    'json': {
    'name': 'Tim Gray',
    'address': '377 Stephanie Landing Apt. 569\nAmandamouth, NC 12918',
},
    'key9158': 'value25038',
    'key10823': 'value15250',
    'key57369': 'value93564',
    'key68823': 'value13049',
    'key6149': 'value91731',
    'key94907': 'value95068',
    'key34670': 'value33445',
},
    {
    'id': 17527486091017,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Katelyn Green',
    'address': '75729 Alvarez Stravenue Suite 964\nWest Dianeberg, HI 48618',
    'text': 'Action concern bad mean individual say him. Others morning room value according window rest.',
    'email': 'anthony27@example.net',
    'phone_number': '001-342-379-2004x427',
    'json': {
    'name': 'Mary Roberts',
    'address': '8153 Mack Course Apt. 243\nOrtizville, WY 34936',
},
    'key28422': 'value98840',
    'key268': 'value40862',
    'key61695': 'value71079',
    'key39046': 'value98466',
},
    {
    'id': 17527486091030,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Meagan Williams',
    'address': '21544 Morgan Summit\nJamesstad, SD 09795',
    'text': 'Chair power assume entire goal hot issue risk. Add among third image science necessary. Team event but compare center bar.',
    'email': 'jenniferjordan@example.org',
    'phone_number': '+1-987-446-5166x695',
    'json': {
    'name': 'Deborah Melendez',
    'address': 'Unit 3239 Box 8290\nDPO AE 33287',
},
    'key72648': 'value50405',
    'key82229': 'value2277',
},
    {
    'id': 17527486091040,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Wendy Luna',
    'address': '9603 Christopher Squares Suite 043\nLake Michelefurt, DC 36306',
    'text': 'Plant trouble live chance base sea goal back. Rather bit attack add determine control.',
    'email': 'linhannah@example.org',
    'phone_number': '(697)613-0516x8824',
    'json': {
    'name': 'Sarah Williams',
    'address': 'Unit 6586 Box 8414\nDPO AE 81337',
},
    'key41744': 'value10191',
    'key66172': 'value56137',
    'key77269': 'value64853',
    'key5820': 'value75342',
    'key98724': 'value17868',
    'key70495': 'value81292',
    'key64110': 'value96070',
    'key60714': 'value78967',
},
    {
    'id': 17527486091050,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Robert Jarvis',
    'address': '549 Bartlett Drive\nWest Danny, DE 35923',
    'text': 'Accept fine drug something speak. Speak society single single require drug scene.\nFinish owner parent month nor according believe.',
    'email': 'hortonjonathan@example.org',
    'phone_number': '+1-237-858-8388',
    'json': {
    'name': 'Ryan Franklin',
    'address': '62718 Hernandez Wall\nJoyberg, RI 90687',
},
    'key83073': 'value92204',
    'key99979': 'value44044',
    'key27995': 'value23254',
    'key14726': 'value87283',
    'key71826': 'value1388',
},
    {
    'id': 17527486091062,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Gary Walters',
    'address': '503 Sarah Field\nHillmouth, GA 50649',
    'text': 'Find short everybody development happen. Middle continue news suggest second perhaps first. Store network writer perform response trade.',
    'email': 'rcook@example.net',
    'phone_number': '001-479-458-5787x080',
    'json': {
    'name': 'Michelle Chapman',
    'address': '72976 Janet Club Suite 813\nJoshuaville, ME 99339',
},
    'key66915': 'value5221',
    'key9212': 'value51561',
},
    {
    'id': 17527486091074,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Matthew Stevens',
    'address': '7180 Mcdaniel Oval Apt. 598\nRhondaville, MI 64006',
    'text': 'Popular next require administration. Grow shake pretty. Step leg join provide task let.\nEarly design day degree situation position concern. Trip eight can interview agent office campaign.',
    'email': 'jamesthomas@example.net',
    'phone_number': '7874234908',
    'json': {
    'name': 'Alan Ramirez',
    'address': '653 Potts Locks\nClarenceland, NM 60885',
},
    'key28967': 'value172',
    'key89831': 'value10639',
    'key76842': 'value75930',
    'key90825': 'value24143',
    'key7460': 'value50793',
    'key46184': 'value34593',
    'key69983': 'value63383',
    'key45643': 'value72027',
    'key78740': 'value49197',
    'key55577': 'value54662',
},
    {
    'id': 17527486091087,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Stephanie Olson',
    'address': '6358 Edwin Road\nShawnfort, CA 25052',
    'text': 'Begin forget per hit road. Although hospital rise group range rise.\nOthers rest believe two strategy. Recent southern build his mean situation.',
    'email': 'xhill@example.com',
    'phone_number': '(699)670-1098x976',
    'json': {
    'name': 'Lindsay Cooke',
    'address': '2238 Dana Corner Suite 468\nSouth Jorge, IA 79365',
},
    'key35406': 'value88314',
    'key89138': 'value44838',
    'key83324': 'value28540',
    'key95442': 'value76344',
    'key26722': 'value61710',
    'key24320': 'value27600',
    'key80238': 'value65744',
},
    {
    'id': 17527486091098,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'James Williams',
    'address': '204 Marie Course\nWest Chadfurt, WV 50129',
    'text': 'Short difference wear example put worker. Check among claim white. Detail color very guy reveal. Goal tell how soon ask born threat participant.',
    'email': 'daniellechaney@example.org',
    'phone_number': '333.552.4565',
    'json': {
    'name': 'Linda Ramos',
    'address': '453 Nicole Pine\nFoxport, TN 83606',
},
    'key43856': 'value54804',
    'key48244': 'value78058',
    'key3709': 'value5687',
    'key27824': 'value70965',
    'key85098': 'value60584',
    'key10846': 'value7138',
    'key95745': 'value50359',
},
    {
    'id': 17527486091110,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Stephen Montoya',
    'address': '6941 David Mission Suite 430\nLake Taylor, UT 84515',
    'text': 'Situation whose western either lose whether effort. Rise American commercial feeling.\nRespond away boy method article ahead him. Three put citizen interest capital evidence from.',
    'email': 'timothy63@example.org',
    'phone_number': '(612)523-4633x9410',
    'json': {
    'name': 'Vincent Romero',
    'address': '5754 Blankenship Via\nMarkville, AZ 54150',
},
    'key25467': 'value48028',
    'key35151': 'value6375',
    'key15583': 'value13816',
    'key30680': 'value80161',
    'key43762': 'value30112',
    'key53202': 'value76495',
    'key72629': 'value4056',
    'key76031': 'value9897',
},
    {
    'id': 17527486091121,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'Emily Stanley',
    'address': '7541 Strickland Shoal\nJorgeshire, NY 53598',
    'text': 'Street should impact career health toward. Oil society key generation others. Live visit their stand author forget election hotel. Bar city money note until charge go.',
    'email': 'barnesvirginia@example.net',
    'phone_number': '(227)288-8210x6691',
    'json': {
    'name': 'Shane Valdez',
    'address': '173 Andrew Causeway Apt. 779\nJonesland, CT 19283',
},
    'key94184': 'value94604',
    'key26563': 'value51352',
    'key62251': 'value41253',
    'key96352': 'value57812',
    'key12666': 'value34382',
},
    {
    'id': 17527486091133,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Sarah Wright',
    'address': '204 Simpson Isle\nSouth Gabrielleborough, MH 45338',
    'text': 'Car offer industry everything. It stuff other hot second. Believe cell government their very.\nAnswer hour a Congress cup class. Line much have name cell a.',
    'email': 'omar72@example.net',
    'phone_number': '8372727116',
    'json': {
    'name': 'Elizabeth Taylor',
    'address': '387 Clark Club Apt. 702\nPort Michaelmouth, NC 45911',
},
    'key8317': 'value39690',
    'key24659': 'value53854',
    'key9598': 'value24787',
    'key55262': 'value65958',
    'key4928': 'value35512',
    'key96862': 'value33353',
    'key56756': 'value47520',
    'key89163': 'value89748',
    'key13334': 'value76656',
},
    {
    'id': 17527486091144,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'John Marsh',
    'address': '7815 James Flat\nEast Brianhaven, MN 07026',
    'text': 'Wonder morning natural. Gas prevent watch family body nature. Suddenly house central.',
    'email': 'sawyerjasmine@example.net',
    'phone_number': '437.689.0646x653',
    'json': {
    'name': 'Kayla Gonzalez',
    'address': '10192 Adams Ports Suite 957\nKristinmouth, LA 83409',
},
    'key53633': 'value56199',
    'key84689': 'value69394',
    'key76782': 'value84772',
    'key15638': 'value304',
    'key71633': 'value31683',
},
    {
    'id': 17527486091155,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Melissa Allen',
    'address': '090 Thomas Summit Apt. 436\nNormanton, NH 20467',
    'text': 'Strong development past condition some. Machine window activity rise may listen serve. Perform Mr economic seven indicate become heart.',
    'email': 'toddscott@example.com',
    'phone_number': '8474271089',
    'json': {
    'name': 'Billy Hernandez',
    'address': 'PSC 5179, Box 2522\nAPO AP 61695',
},
    'key1168': 'value21942',
    'key64840': 'value36028',
    'key71777': 'value11224',
},
    {
    'id': 17527486091164,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Mark Lopez',
    'address': '9174 Summers Ridge\nDyerberg, SC 25569',
    'text': 'Event agency serve movie size somebody. Federal democratic avoid past hotel behavior.\nDevelopment we the. Half guy four special discover heavy.',
    'email': 'johnnichols@example.com',
    'phone_number': '5718720372',
    'json': {
    'name': 'Devin Beck',
    'address': 'PSC 0638, Box 6333\nAPO AP 62454',
},
    'key67596': 'value44461',
    'key76567': 'value74777',
    'key88627': 'value44938',
    'key33533': 'value91572',
    'key93588': 'value38260',
    'key5139': 'value4300',
    'key92039': 'value45693',
    'key11464': 'value32924',
    'key38493': 'value14554',
},
    {
    'id': 17527486091174,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Stephanie Barry',
    'address': 'Unit 6826 Box 2580\nDPO AA 05040',
    'text': 'West sign own question. Office find bit occur.\nInstitution move should or remain tax economic race. Evidence often somebody PM course hundred certain.',
    'email': 'michael52@example.org',
    'phone_number': '707.211.4944',
    'json': {
    'name': 'David Reeves',
    'address': '659 Wolfe Rest Suite 010\nSouth Nicole, MD 13156',
},
    'key31440': 'value26683',
},
    {
    'id': 17527486091182,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Dana Atkins',
    'address': '881 Tyler Harbors Suite 209\nCoreytown, DC 62833',
    'text': 'Size why behavior street dog number quickly particularly. Rather sign threat find. Base energy after.',
    'email': 'nelsonrobert@example.com',
    'phone_number': '001-901-305-1230x791',
    'json': {
    'name': 'Lisa Long',
    'address': '1754 Ibarra Creek\nNorth Jerry, MH 48514',
},
    'key81130': 'value98468',
    'key62341': 'value40902',
    'key98048': 'value97',
    'key97121': 'value34036',
    'key49426': 'value64517',
    'key18489': 'value56259',
    'key64902': 'value43691',
},
    {
    'id': 17527486091193,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'Isaac Hawkins',
    'address': '898 Robert Lights\nHenryview, WI 98039',
    'text': 'Quite again quality the. Television air push information visit customer their heavy. Church spring rather control security both food. Site past direction option product environmental top.',
    'email': 'smithjames@example.net',
    'phone_number': '354-553-9429x83534',
    'json': {
    'name': 'Carrie Zavala',
    'address': '984 Mays Mountains\nBarkerport, UT 46247',
},
    'key36719': 'value24282',
},
    {
    'id': 17527486091205,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'Jennifer Ross',
    'address': '19932 Sarah Plain Apt. 021\nAndreafurt, MT 82637',
    'text': 'Over but to contain. Fact direction measure audience. Law provide between game reality.\nApply across put next beyond paper ahead. Manager staff free sometimes. Leader range trial Democrat go.',
    'email': 'amy37@example.net',
    'phone_number': '527-592-5167',
    'json': {
    'name': 'Phillip Stafford',
    'address': '803 King Center Apt. 097\nMendozastad, IA 52007',
},
    'key23230': 'value22444',
    'key96267': 'value13864',
    'key56629': 'value91106',
    'key41512': 'value24093',
    'key85594': 'value93380',
},
    {
    'id': 17527486091217,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'James Wood',
    'address': '02268 Dominique Falls Apt. 943\nNorth Andrew, MN 48727',
    'text': 'Performance government strategy front. Hour stay include organization. Likely air admit response event.\nPast staff just knowledge central magazine.',
    'email': 'amy04@example.com',
    'phone_number': '001-897-574-3096x621',
    'json': {
    'name': 'Olivia Reyes',
    'address': '3055 Caleb Pine\nNorth Adrian, PR 04685',
},
    'key49865': 'value66144',
    'key81573': 'value34071',
    'key91215': 'value87566',
    'key25147': 'value62191',
    'key12300': 'value42644',
    'key9705': 'value17419',
},
    {
    'id': 17527486091228,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Tiffany Young',
    'address': '5677 Mitchell Rapid Suite 620\nDunnfurt, DE 33406',
    'text': 'Low matter school store. Six growth interview idea. Summer go data with.\nWhere perform head hot move improve region. Tonight adult hundred six shake actually cold.',
    'email': 'daniel29@example.org',
    'phone_number': '(662)603-9752',
    'json': {
    'name': 'James Peterson',
    'address': '67721 Cassandra Causeway\nMarkstad, ME 04842',
},
    'key55449': 'value10999',
    'key9863': 'value14050',
    'key90391': 'value18561',
    'key75174': 'value71',
},
    {
    'id': 17527486091240,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Dr. James Jenkins DDS',
    'address': '42606 Sandra Point Apt. 408\nEast Deborahburgh, HI 30738',
    'text': 'Property base entire room be quite hospital word. Or child director suddenly represent.\nIndustry detail those space. May others grow simply among drug.',
    'email': 'bradyronald@example.org',
    'phone_number': '+1-654-834-6933x6255',
    'json': {
    'name': 'Laura Campbell',
    'address': '54922 Michele Squares Apt. 595\nPort Timothy, AZ 75090',
},
    'key23730': 'value78984',
    'key60812': 'value93753',
    'key71005': 'value54580',
    'key29284': 'value95747',
    'key38430': 'value45685',
    'key60948': 'value36954',
    'key38211': 'value98877',
},
    {
    'id': 17527486091252,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'Mr. Kyle Gonzalez',
    'address': '5750 Christopher Cape\nSouth Rebeccaport, OH 38622',
    'text': 'Reflect lead there six somebody. Traditional reduce study part.\nEvent worker we whose. Cost pattern enjoy specific season two population turn.',
    'email': 'sarahstevens@example.org',
    'phone_number': '890.939.0008',
    'json': {
    'name': 'Derek Kelly',
    'address': '2342 Hayes Field Suite 479\nNorth Colleenmouth, IN 24832',
},
    'key3750': 'value5638',
    'key70508': 'value18905',
    'key90619': 'value85265',
    'key87426': 'value16160',
},
    {
    'id': 17527486091265,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Timothy Miller',
    'address': '6632 Kyle Groves Suite 971\nWest Jessica, KS 96863',
    'text': 'Rock wrong alone order. Without benefit future fine your anyone. Nice left reach reduce interest generation full.\nNew animal body special. Conference election goal table.',
    'email': 'briandiaz@example.net',
    'phone_number': '9282322257',
    'json': {
    'name': 'Vanessa Cook',
    'address': '940 Powell Rapid\nPort Bradley, VA 44963',
},
    'key46717': 'value70191',
    'key6550': 'value37580',
    'key88682': 'value92337',
    'key65572': 'value18909',
},
    {
    'id': 17527486091277,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Victoria Carlson',
    'address': '776 Deborah Greens Apt. 768\nScotttown, DC 87164',
    'text': 'Pressure road human among experience. Deep page seem. Tend glass instead although.',
    'email': 'yateselizabeth@example.org',
    'phone_number': '+1-591-880-1610x75700',
    'json': {
    'name': 'Aaron Hanson',
    'address': '2889 Sarah Summit\nWest Leonard, KY 52629',
},
    'key26186': 'value19004',
    'key99135': 'value11657',
    'key24343': 'value82513',
    'key48929': 'value81114',
    'key64703': 'value75790',
    'key66885': 'value24994',
    'key55861': 'value46314',
    'key54315': 'value2565',
    'key24770': 'value99005',
},
    {
    'id': 17527486091289,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'Donna Hensley',
    'address': '85809 Katie Parkways Suite 141\nBakerstad, MI 17489',
    'text': 'Health simple where reflect important mention how look. Wear word watch man.\nKey value property so network receive movie quality. Remember expect turn main scene would raise.',
    'email': 'amy16@example.org',
    'phone_number': '913-790-9513x4353',
    'json': {
    'name': 'Jennifer Burns',
    'address': '411 Morrow Mill Suite 600\nCoreyland, NC 21638',
},
    'key3369': 'value70406',
    'key33317': 'value19630',
    'key43140': 'value3982',
    'key1474': 'value3933',
    'key59007': 'value47788',
    'key15540': 'value26592',
},
    {
    'id': 17527486091301,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Edward Roth',
    'address': 'Unit 3389 Box 8771\nDPO AE 18049',
    'text': 'Once mouth bad safe cut.\nCamera skin firm peace. Either piece himself there method hospital child guess.',
    'email': 'nwilkinson@example.net',
    'phone_number': '+1-735-346-0804',
    'json': {
    'name': 'Cassidy Silva',
    'address': '3604 Roberson Wells\nRodgersborough, AS 55816',
},
    'key69037': 'value54901',
},
    {
    'id': 17527486091310,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Nathan Warner',
    'address': '79527 Parker Way Apt. 580\nRachelberg, DC 23759',
    'text': 'Mention low quickly dark outside point. Candidate court get heart sign such. Section then card free.\nCustomer common key six. Which serve national prevent. All day hour entire TV speak.',
    'email': 'gcopeland@example.org',
    'phone_number': '448-359-2538x602',
    'json': {
    'name': 'Jonathan Sanchez',
    'address': '38585 Rose Mill Suite 010\nNew Katherine, RI 39280',
},
    'key97432': 'value65339',
    'key54137': 'value31940',
    'key34948': 'value54725',
    'key19601': 'value11958',
    'key53054': 'value55780',
    'key33723': 'value7539',
    'key7687': 'value53644',
},
    {
    'id': 17527486091320,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Renee Perez',
    'address': '2931 Kelly Burg\nRobertsport, CO 41568',
    'text': 'Pay parent carry vote. Commercial seven east although.\nAudience behind race watch trouble.\nShoulder strong summer voice student. Might how animal.',
    'email': 'ujohnson@example.org',
    'phone_number': '254.302.1531x562',
    'json': {
    'name': 'Kimberly Jensen',
    'address': '759 Mercedes Ramp\nWallsburgh, AK 56308',
},
    'key78778': 'value44485',
    'key34810': 'value98694',
    'key84752': 'value83474',
    'key95457': 'value10426',
    'key30931': 'value3063',
    'key43463': 'value93001',
    'key73216': 'value79844',
    'key13277': 'value35519',
    'key42324': 'value5305',
},
    {
    'id': 17527486091331,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Kyle Johnson',
    'address': '6917 Dawson Garden Suite 205\nKatrinaport, VI 88603',
    'text': 'Eat attention produce generation campaign wall of. Assume necessary stock next total employee. Matter allow wind would myself south over.',
    'email': 'molly44@example.net',
    'phone_number': '(323)712-5558x4445',
    'json': {
    'name': 'Wayne Tran',
    'address': 'USNV Miller\nFPO AE 47263',
},
    'key482': 'value80059',
    'key44090': 'value91500',
    'key21179': 'value21602',
    'key86048': 'value23715',
    'key38882': 'value98110',
    'key98077': 'value49230',
    'key29160': 'value11223',
    'key76560': 'value96253',
    'key62260': 'value81327',
},
    {
    'id': 17527486091341,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Brian Smith',
    'address': '93061 Ramirez Way Apt. 669\nPort Colleenview, NE 18153',
    'text': 'Like particularly any none best medical pass a. Knowledge seem she.\nWorld ten hold. Rise teacher blue think say whole serve treat. Head shake leave despite behavior.\nAccording third you end.',
    'email': 'hhill@example.net',
    'phone_number': '4047221155',
    'json': {
    'name': 'Marissa Webb',
    'address': '06305 Cook Ways Suite 035\nBentleyville, NJ 94513',
},
    'key67041': 'value17041',
    'key39658': 'value15535',
},
    {
    'id': 17527486091352,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'Shelby Williams',
    'address': '3852 Ann Plains Suite 519\nRachelview, MI 84318',
    'text': 'Congress follow office process finish like. Past sister let by wall ball big. Enter paper hit already would news.\nHard wait life tend the responsibility. Serve ten before throw.\nIt hard prepare whom.',
    'email': 'jessicahunter@example.net',
    'phone_number': '494.790.3351x8582',
    'json': {
    'name': 'Joshua Escobar',
    'address': 'USCGC Hernandez\nFPO AA 02127',
},
    'key41021': 'value18682',
    'key2448': 'value84905',
},
    {
    'id': 17527486091362,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Christine Price',
    'address': '41621 Cole Valleys\nAmandaville, FL 66492',
    'text': 'American nature provide. Range add itself stand enter finally.\nWife detail scene degree ask. Although season light but throw defense carry city. Teach walk local.',
    'email': 'bairdamy@example.com',
    'phone_number': '001-836-309-4678x06064',
    'json': {
    'name': 'Ann Craig',
    'address': 'Unit 1148 Box 9816\nDPO AE 61455',
},
    'key5003': 'value33939',
    'key84594': 'value93150',
    'key45303': 'value48104',
    'key65399': 'value60829',
    'key59343': 'value82690',
    'key40082': 'value23457',
    'key17300': 'value12476',
    'key31043': 'value72205',
    'key96725': 'value84331',
},
    {
    'id': 17527486091372,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Michelle Velasquez',
    'address': '653 Quinn Fields\nWest Karenmouth, MD 98844',
    'text': 'Either early of discuss serve base wide. Provide art finally region front manager down.\nRemember manager onto wear quite air. Cultural task pretty.',
    'email': 'robertsronald@example.com',
    'phone_number': '613.704.4481',
    'json': {
    'name': 'Kathleen Smith',
    'address': '096 Jones Orchard\nHudsonberg, NC 53921',
},
    'key73703': 'value34227',
    'key54465': 'value36758',
    'key39125': 'value21606',
    'key93339': 'value34956',
},
    {
    'id': 17527486091383,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Natalie Henson',
    'address': '45556 Sarah Prairie\nWest Tammystad, IN 33383',
    'text': 'No cold stop bank heart green though. Former actually protect foreign actually either blue.\nThrough none general cut talk respond. Himself avoid account trial feel four. Begin site pay west hot.',
    'email': 'heatherturner@example.org',
    'phone_number': '(756)635-9412x40395',
    'json': {
    'name': 'Jeremy Rogers',
    'address': '9475 Calvin Mission\nWest Gregoryland, MT 73562',
},
    'key24187': 'value74008',
    'key30346': 'value2284',
    'key70814': 'value18241',
    'key58196': 'value67382',
},
    {
    'id': 17527486091394,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'John White',
    'address': '318 Ashley Walks Suite 880\nLake Joshua, OR 22136',
    'text': 'Bed customer ask. Artist environment or lay use.\nFather yard not. Field enough perform new.\nWorker range bag piece voice night record both. Environmental coach our time hope.',
    'email': 'donaldlong@example.org',
    'phone_number': '(296)271-1893x95951',
    'json': {
    'name': 'Michael Wright',
    'address': 'USCGC Tanner\nFPO AA 67791',
},
    'key65621': 'value48462',
    'key12874': 'value44325',
    'key89396': 'value85999',
    'key62524': 'value96557',
    'key44691': 'value85049',
    'key91840': 'value48562',
    'key36674': 'value2726',
    'key23321': 'value55419',
    'key80859': 'value10206',
},
    {
    'id': 17527486091404,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'Ryan Williams',
    'address': '023 Curry Forks Apt. 955\nCrystalshire, MI 97927',
    'text': 'At follow form hair left. Drop number would whole ask general. Pick rather develop right or still end.',
    'email': 'sweeneymichael@example.net',
    'phone_number': '+1-511-414-3996x72672',
    'json': {
    'name': 'Brandon Nelson',
    'address': '384 Natalie Path Apt. 081\nTimothyshire, NM 65490',
},
    'key2452': 'value94905',
    'key60814': 'value10085',
    'key67793': 'value18880',
    'key11901': 'value24651',
    'key96940': 'value45165',
},
    {
    'id': 17527486091416,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'James Wong',
    'address': '24702 Gates Lodge Suite 512\nSherryfurt, DE 44037',
    'text': 'Crime first tax serious half best mother energy.\nMaybe collection skill my continue throughout. Economic sport capital effect. Important in require reflect offer.',
    'email': 'heathermoreno@example.com',
    'phone_number': '(304)474-7114x6921',
    'json': {
    'name': 'Gina Wyatt',
    'address': '0065 Dennis Trail Apt. 769\nAnitaville, MT 52882',
},
    'key58305': 'value46426',
    'key53557': 'value5992',
    'key33777': 'value47338',
    'key28818': 'value36323',
    'key57105': 'value45874',
    'key23914': 'value44265',
    'key31725': 'value99768',
    'key71002': 'value25688',
    'key71411': 'value47571',
    'key90429': 'value66367',
},
    {
    'id': 17527486091428,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Eric Kirk',
    'address': '8477 Andrew Center Suite 231\nWest John, VT 43862',
    'text': 'Major politics ten result purpose economic spend media. It my word food. Quality western food child put.',
    'email': 'orhodes@example.com',
    'phone_number': '443.988.2919x04994',
    'json': {
    'name': 'Michael Guzman',
    'address': '473 Tyler Squares Suite 040\nNew Deanbury, KY 11187',
},
    'key45060': 'value21101',
    'key70879': 'value76646',
    'key33422': 'value78388',
    'key68802': 'value30814',
    'key70234': 'value67896',
    'key50234': 'value72869',
    'key29072': 'value36674',
    'key40777': 'value97559',
    'key98030': 'value56751',
},
    {
    'id': 17527486091438,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Alexis Schwartz',
    'address': '47971 Katherine Meadow Apt. 258\nEast Lauren, VI 13301',
    'text': 'Rock food candidate model travel. Part physical daughter with almost sister place kind. Former none break attention speech.',
    'email': 'evansjohn@example.net',
    'phone_number': '001-483-810-6621x559',
    'json': {
    'name': 'Jennifer Harvey',
    'address': '14803 Robert Ford\nBenjaminburgh, ME 67030',
},
    'key38744': 'value83108',
    'key25896': 'value53269',
    'key27451': 'value51088',
    'key59921': 'value78540',
    'key1973': 'value71747',
    'key84197': 'value70086',
    'key11852': 'value24656',
    'key72621': 'value20983',
    'key91260': 'value29193',
},
    {
    'id': 17527486091449,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Jessica Martin',
    'address': '35554 Walters Fork\nNew Stephen, FM 16229',
    'text': 'Goal none over say total draw detail talk. Room recently side career. Key entire response beyond. Cost increase focus people compare.',
    'email': 'cordovarebecca@example.net',
    'phone_number': '597.664.0265',
    'json': {
    'name': 'Margaret Dougherty',
    'address': 'PSC 6304, Box 8253\nAPO AE 93562',
},
    'key7077': 'value41583',
    'key88234': 'value35287',
    'key17986': 'value48193',
    'key63508': 'value57503',
    'key69149': 'value47269',
    'key6755': 'value5297',
    'key22237': 'value42129',
    'key12425': 'value48368',
    'key18012': 'value39052',
},
    {
    'id': 17527486091458,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Michael Brady',
    'address': '3711 Blake Street Suite 583\nNorth Dawnton, ME 67337',
    'text': 'Conference of individual and usually. Husband throughout include enjoy beyond level. Fast my almost general watch above management.\nModern take receive no card far story. Along up camera.',
    'email': 'meyerskimberly@example.com',
    'phone_number': '615-781-1083x0448',
    'json': {
    'name': 'Justin Walker',
    'address': 'PSC 6090, Box 9415\nAPO AE 10138',
},
    'key89': 'value5938',
    'key7068': 'value33044',
    'key35834': 'value14558',
    'key62199': 'value98522',
    'key16405': 'value64995',
    'key92064': 'value6765',
},
    {
    'id': 17527486091468,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Beth Garcia',
    'address': '51736 Rogers Flat\nNew Jennifer, MP 09473',
    'text': 'Might region data though take mission three. Produce clear move especially north. Only nature first job. Always course explain size start.',
    'email': 'martinezchristopher@example.net',
    'phone_number': '907.866.6725',
    'json': {
    'name': 'Karen Lambert',
    'address': '136 Nicole Vista\nPort Heatherstad, MO 91404',
},
    'key13028': 'value93743',
    'key27279': 'value15067',
    'key20047': 'value70636',
    'key95749': 'value86633',
    'key9020': 'value64364',
    'key34208': 'value39151',
    'key10043': 'value66836',
},
    {
    'id': 17527486091479,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Crystal Reyes',
    'address': '765 Jessica Roads\nEvanstown, NE 73898',
    'text': 'Approach no have sure yet consider hour. Part moment there more last step. Dinner visit message five product sometimes thank top.',
    'email': 'jenniferwolfe@example.net',
    'phone_number': '799-542-2445',
    'json': {
    'name': 'Catherine Smith',
    'address': '7837 Powell Highway\nStonebury, FM 50266',
},
    'key8782': 'value85008',
    'key28358': 'value46357',
},
    {
    'id': 17527486091491,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Michael Peters',
    'address': '288 House Viaduct\nPort Micheal, VT 55753',
    'text': 'Civil center image father behind card. Federal small drive ability wide maintain possible.\nUnit watch stuff fight all. Affect east though research. Walk system summer bag.',
    'email': 'rswanson@example.org',
    'phone_number': '958.280.9265x94380',
    'json': {
    'name': 'Travis Vincent',
    'address': '56088 Castro Burg\nJeremyberg, GA 74229',
},
    'key79891': 'value37288',
},
    {
    'id': 17527486091502,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Teresa Smith',
    'address': '506 Debra Freeway\nTranview, MI 40003',
    'text': 'Me result policy good scene pull.\nResponsibility base network open. Image relationship relationship song form view bar.',
    'email': 'coxkathryn@example.org',
    'phone_number': '001-293-875-9043x187',
    'json': {
    'name': 'Christopher Curtis',
    'address': '40002 Anna Camp\nPort Charlesport, ID 43109',
},
    'key22366': 'value7894',
    'key40653': 'value4796',
    'key5213': 'value97864',
    'key39319': 'value1321',
    'key43163': 'value65493',
},
    {
    'id': 17527486091513,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Joshua Valdez',
    'address': '61941 Calhoun Trace Apt. 068\nSandrachester, MN 02548',
    'text': 'Seat argue heavy age material. Music space always thousand form skill process. Describe computer perform energy generation south administration. Garden different source small.',
    'email': 'loganfelicia@example.net',
    'phone_number': '001-280-450-3802x449',
    'json': {
    'name': 'Jennifer Wright',
    'address': 'USNS Figueroa\nFPO AE 58560',
},
    'key95690': 'value44484',
    'key99216': 'value26663',
    'key80671': 'value35693',
    'key82017': 'value10400',
    'key90186': 'value48676',
    'key59623': 'value71580',
    'key32924': 'value9298',
},
    {
    'id': 17527486091524,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Teresa Ellison DVM',
    'address': '514 Goodman Forges Apt. 733\nWhitakerbury, WI 38234',
    'text': 'West fire weight poor.',
    'email': 'morganbutler@example.com',
    'phone_number': '+1-785-737-4287x8167',
    'json': {
    'name': 'Sean Watson',
    'address': '708 Kramer Parks\nCarpenterton, AS 36138',
},
    'key82497': 'value33325',
    'key77702': 'value80668',
    'key44361': 'value3352',
    'key56510': 'value64340',
    'key16094': 'value85099',
    'key27261': 'value98295',
},
    {
    'id': 17527486091536,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'George Morales',
    'address': '49085 Leslie Branch\nWest Austin, TN 19226',
    'text': 'Glass how positive week.\nFront against animal here city shoulder. Discover direction bring shake. Hundred save over development information. Thought shake staff these continue.',
    'email': 'matthewcantu@example.net',
    'phone_number': '001-245-323-0518x598',
    'json': {
    'name': 'Joseph Blackburn',
    'address': '638 Sandra Walks Apt. 759\nGomezberg, KY 67643',
},
    'key14256': 'value94398',
    'key22459': 'value34930',
},
    {
    'id': 17527486091547,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Jean Gomez',
    'address': '7881 Megan Flats\nLopezbury, MS 85984',
    'text': 'Information talk party former leader.\nCompare religious painting break positive. Nearly cup positive expert. Green cut news candidate book.',
    'email': 'cindyjackson@example.org',
    'phone_number': '(468)736-4834',
    'json': {
    'name': 'Jessica Smith',
    'address': '13446 Suzanne Garden\nWest Matthew, NH 90406',
},
    'key21734': 'value31244',
},
    {
    'id': 17527486091558,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Kevin Ford',
    'address': '994 Kimberly Rest Suite 522\nLauraborough, PW 31137',
    'text': 'Reflect science radio suffer control. Down tend that score on among. Sing all participant ahead travel reach happy piece.',
    'email': 'allengonzales@example.org',
    'phone_number': '804-356-5493',
    'json': {
    'name': 'Angela Mcdonald',
    'address': '166 Tabitha Streets Apt. 748\nChaseville, CT 52691',
},
    'key21545': 'value78336',
    'key43474': 'value77423',
    'key31619': 'value4341',
},
    {
    'id': 17527486091569,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Stephanie Buck',
    'address': '98599 Ray Vista\nGravesfurt, SC 38928',
    'text': 'Sign human maintain management he would. Indicate money to everything message new economic. Give reach truth heavy name boy far three.',
    'email': 'deckernatalie@example.org',
    'phone_number': '214.549.7088x770',
    'json': {
    'name': 'Grace Hughes',
    'address': '432 Thomas Road\nKathrynberg, RI 82890',
},
    'key95251': 'value74723',
    'key70594': 'value48312',
    'key90682': 'value40529',
    'key96257': 'value50460',
    'key39794': 'value32687',
    'key56288': 'value33930',
    'key66780': 'value3807',
    'key42327': 'value97710',
    'key49027': 'value25948',
    'key33946': 'value19582',
},
    {
    'id': 17527486091580,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'Eric Weeks',
    'address': 'PSC 6315, Box 3508\nAPO AA 29031',
    'text': 'Near official movement try economic important actually executive. Me Mrs within. Weight give candidate performance sure just sort. Weight heart follow.',
    'email': 'christophercisneros@example.net',
    'phone_number': '7886424289',
    'json': {
    'name': 'Charles Potter',
    'address': '186 Hodges Springs Apt. 029\nEast Joseph, CO 54059',
},
    'key39416': 'value47041',
    'key61895': 'value49272',
    'key66052': 'value33524',
    'key21182': 'value75572',
    'key11534': 'value68072',
    'key11497': 'value17412',
    'key62951': 'value80442',
    'key43421': 'value46398',
    'key73260': 'value18912',
    'key81863': 'value24365',
},
    {
    'id': 17527486091590,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Jasmine Ortiz',
    'address': '75920 Tiffany Keys Apt. 735\nAmandaton, VT 29243',
    'text': 'Land one should discover speech democratic. Politics only question teach. Right policy director spring.\nOpen difference lawyer TV new foreign. Wear end computer dog.',
    'email': 'fhurst@example.net',
    'phone_number': '(991)555-2571x089',
    'json': {
    'name': 'Michael Rivers',
    'address': '1220 White Points Suite 806\nWest Joshua, PA 25446',
},
    'key45882': 'value57869',
    'key51650': 'value88696',
    'key53199': 'value5179',
    'key8505': 'value89581',
    'key96029': 'value86247',
    'key42116': 'value39478',
    'key6591': 'value3067',
    'key63146': 'value53932',
    'key19033': 'value89591',
},
    {
    'id': 17527486091601,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Sarah Gross',
    'address': '72016 Hart Spring\nNorth Heather, MA 13147',
    'text': 'Least seek final while continue her study value. Miss fact fish sure learn might. Writer responsibility hot contain list force million lay.',
    'email': 'cindygarza@example.net',
    'phone_number': '603.836.8060x2761',
    'json': {
    'name': 'Anthony Stevens',
    'address': '506 Melissa Isle\nAlyssamouth, MD 95042',
},
    'key48229': 'value8652',
    'key29749': 'value32977',
    'key54233': 'value6069',
},
    {
    'id': 17527486091612,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Cynthia Mitchell',
    'address': '7485 Todd Island Apt. 184\nSouth Jamestown, MN 42639',
    'text': 'Plant himself push see worker say. Draw try itself. Impact its change mouth.\nCouple million mouth always find top group task. Officer good mouth theory some explain believe.',
    'email': 'kathleenbaker@example.net',
    'phone_number': '399.220.1437x713',
    'json': {
    'name': 'Tiffany Carter',
    'address': '453 Brown Fords\nJosephside, OR 19609',
},
    'key85295': 'value78937',
    'key81648': 'value66675',
},
    {
    'id': 17527486091624,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Michael Morales',
    'address': '482 Sean Land\nLindsaymouth, MH 96254',
    'text': 'Training attack purpose buy. Concern camera stay foreign. Show score cut nor respond skill once. Lose team different plant couple white.',
    'email': 'ustewart@example.net',
    'phone_number': '(550)982-3677',
    'json': {
    'name': 'Isaiah Chandler',
    'address': '93988 Amanda Plain\nNew Carlos, VT 91802',
},
    'key90964': 'value17270',
    'key47146': 'value73707',
    'key94557': 'value24442',
    'key60578': 'value48782',
    'key81370': 'value11564',
    'key48561': 'value10330',
    'key13133': 'value49515',
    'key27176': 'value12282',
    'key18468': 'value494',
},
    {
    'id': 17527486091633,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'Kelly Torres',
    'address': '740 Chapman Isle Apt. 387\nSimpsonland, KY 80312',
    'text': 'Look military second partner.\nCivil evidence care political figure chance. Force shoulder professor life. Most not stock another father.',
    'email': 'matthew91@example.org',
    'phone_number': '+1-904-397-4875x17642',
    'json': {
    'name': 'Jasmine Jones',
    'address': '92252 Tina Islands Suite 619\nSouth Mindy, KY 91390',
},
    'key65175': 'value95710',
    'key21433': 'value84663',
    'key32204': 'value87958',
    'key48239': 'value38407',
    'key40309': 'value94899',
    'key50483': 'value5024',
    'key16540': 'value51899',
    'key81191': 'value68381',
},
    {
    'id': 17527486091644,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Ryan Bass',
    'address': '4211 Trevor Garden\nDerrickmouth, DE 72058',
    'text': 'Teach save open major. Close fly remain own we.\nAgainst still notice mission market. Position hour first do turn say space behavior.',
    'email': 'fjimenez@example.net',
    'phone_number': '+1-662-572-7250x87360',
    'json': {
    'name': 'Ryan Wolf',
    'address': '59821 Tony Cape Suite 264\nNorth Monicaton, WA 95930',
},
    'key66325': 'value35225',
    'key61544': 'value98669',
    'key22361': 'value16783',
    'key94456': 'value22572',
    'key81660': 'value14522',
    'key86374': 'value97241',
    'key68146': 'value20617',
},
    {
    'id': 17527486091655,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Marcus Rivers',
    'address': '3244 Wright Island\nLake Andrestad, NM 88533',
    'text': 'Final investment moment amount she. Well while line policy itself east someone.\nSubject no one camera others. Live close carry why view. Health hold memory more worry.',
    'email': 'tina43@example.com',
    'phone_number': '001-285-672-7746x57471',
    'json': {
    'name': 'Anne Guerrero',
    'address': 'PSC 8854, Box 6137\nAPO AE 96297',
},
    'key12174': 'value67560',
    'key23966': 'value6379',
    'key24013': 'value78948',
    'key41502': 'value26391',
    'key72072': 'value175',
    'key95984': 'value95873',
    'key93468': 'value30134',
    'key27823': 'value26196',
},
    {
    'id': 17527486091664,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Catherine Reed',
    'address': '4147 Cook Lane Apt. 124\nWest Sergio, DC 86959',
    'text': 'Second society technology edge threat story discover. Top appear himself yeah land professional.\nHair account gas three argue. Traditional move number gas. Build old hear child.',
    'email': 'rharris@example.org',
    'phone_number': '001-776-497-1534x9155',
    'json': {
    'name': 'Elizabeth Peterson',
    'address': '23355 George Brooks Suite 470\nVanessaberg, RI 63853',
},
    'key17217': 'value25064',
    'key27462': 'value13152',
    'key70436': 'value68402',
    'key87085': 'value53247',
    'key81892': 'value26063',
    'key57176': 'value89020',
    'key14863': 'value79323',
    'key11371': 'value3249',
    'key51487': 'value96262',
},
    {
    'id': 17527486091675,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'Michael Mcneil',
    'address': '5250 Weiss Crest Apt. 723\nLake Brandon, ND 17976',
    'text': 'Among difference Mr. Case health high impact outside someone discuss type.\nShare into per left truth price answer activity. Police business possible fast.',
    'email': 'robertreed@example.org',
    'phone_number': '001-526-274-3992',
    'json': {
    'name': 'Roy Stevens',
    'address': '660 Stephanie Hill Suite 058\nLisashire, KY 70860',
},
    'key55651': 'value57004',
    'key39920': 'value70738',
    'key35488': 'value7197',
    'key50315': 'value44415',
    'key15755': 'value61196',
    'key85387': 'value56564',
    'key70401': 'value90215',
    'key21377': 'value93622',
    'key61419': 'value87184',
    'key69242': 'value74503',
},
    {
    'id': 17527486091686,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Mark Barton',
    'address': '539 Tammy Village Suite 675\nLake Hannahburgh, NC 38904',
    'text': 'Piece material huge range number. Focus sure travel air hit throughout ask color. Magazine group recently seat region far shake.',
    'email': 'audreyallen@example.com',
    'phone_number': '(476)207-0716',
    'json': {
    'name': 'Kevin Harris',
    'address': '7074 Dominguez Shore Suite 328\nWilliamsstad, UT 58632',
},
    'key99688': 'value21046',
    'key20980': 'value93342',
    'key32864': 'value81305',
    'key35128': 'value38826',
    'key10104': 'value97629',
    'key63719': 'value98552',
    'key93681': 'value29879',
    'key17940': 'value30379',
},
    {
    'id': 17527486091698,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Jared Woods',
    'address': '186 Gina Pines Apt. 601\nNew Kellyburgh, NE 83590',
    'text': 'Attorney his indeed water officer true table. Break recently even air him.\nCommon vote begin artist. Owner imagine any war. Certain hair marriage set change while.',
    'email': 'breyes@example.net',
    'phone_number': '373.856.0874',
    'json': {
    'name': 'Tracy Lawrence',
    'address': '622 Donald Brooks\nWatsontown, MH 49094',
},
    'key69714': 'value92029',
    'key47384': 'value69158',
    'key77358': 'value4969',
    'key28707': 'value83535',
    'key4635': 'value1145',
    'key69831': 'value85823',
},
    {
    'id': 17527486091709,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Bailey Harris',
    'address': '247 Thomas Road\nCoxville, RI 69193',
    'text': 'Huge above help will some management give. Strategy certain focus should.',
    'email': 'smithleah@example.com',
    'phone_number': '7929183681',
    'json': {
    'name': 'Veronica Washington',
    'address': 'Unit 1582 Box 2470\nDPO AP 23477',
},
    'key74479': 'value59701',
    'key89399': 'value71339',
    'key6146': 'value45403',
    'key73049': 'value91226',
    'key64384': 'value19352',
    'key45396': 'value88080',
    'key39581': 'value2801',
},
    {
    'id': 17527486091719,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Kenneth Barry',
    'address': '264 Moore Court\nSouth Danielville, CA 74362',
    'text': 'Statement meet face hair easy cause game. Much recently line nothing best.\nCut officer power yourself seat image key. Full bit star little.',
    'email': 'vvaughn@example.org',
    'phone_number': '795-951-9110x883',
    'json': {
    'name': 'Terry Rivera',
    'address': '86305 William Light\nLake Davidland, SD 46716',
},
    'key68230': 'value73830',
    'key78225': 'value81561',
    'key89775': 'value25838',
    'key74455': 'value96184',
    'key25731': 'value29829',
    'key28903': 'value32772',
    'key76643': 'value98032',
    'key76550': 'value87633',
    'key58800': 'value96296',
},
    {
    'id': 17527486091729,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Richard Lambert',
    'address': '652 Carroll Square Apt. 484\nKathleenburgh, NE 98623',
    'text': 'Study own arrive summer him capital member. Run baby likely whether off. Result yeah as.\nIncrease a issue. Federal strong also something. Role prepare white follow kitchen leg station.',
    'email': 'catherine55@example.com',
    'phone_number': '(212)952-2755',
    'json': {
    'name': 'Stephen Bass',
    'address': '4423 Murray Manors Suite 610\nEast Steven, MS 43059',
},
    'key17129': 'value32561',
    'key74459': 'value58185',
    'key60424': 'value33739',
    'key10960': 'value32816',
    'key52086': 'value21878',
    'key72117': 'value67846',
    'key29153': 'value62568',
    'key71443': 'value47018',
    'key70948': 'value568',
},
    {
    'id': 17527486091740,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Aaron Stark',
    'address': '80567 Wu Route\nHensleyborough, KS 22214',
    'text': 'Enter late rise hope. Republican research mouth and. Soldier skin sort check free.\nTask push statement address. Hour production voice idea reason into friend.',
    'email': 'kaylabrown@example.org',
    'phone_number': '(655)391-7696',
    'json': {
    'name': 'Roger Bates',
    'address': '047 Rodriguez Brook\nKimberlyberg, MT 87256',
},
    'key87070': 'value58186',
    'key30478': 'value12633',
},
    {
    'id': 17527486091751,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Stephanie Anderson',
    'address': '61085 Michael Mountains Suite 502\nNorth Kelseymouth, NY 73501',
    'text': 'Out recently by into. Land my free avoid few event dinner.\nEnjoy include policy particular natural beautiful. Education marriage stock standard.\nLay probably senior price position see.',
    'email': 'lfuller@example.org',
    'phone_number': '(583)456-3599',
    'json': {
    'name': 'Dale Brown',
    'address': 'USNS Thompson\nFPO AE 85073',
},
    'key73293': 'value48074',
    'key97075': 'value259',
    'key72580': 'value83600',
    'key43361': 'value49692',
    'key81446': 'value46639',
    'key79064': 'value5676',
    'key76693': 'value24455',
    'key53780': 'value67947',
    'key84669': 'value81858',
},
    {
    'id': 17527486091761,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Crystal Valentine',
    'address': '194 Richard Ford Suite 949\nAnthonyland, FL 35527',
    'text': 'Trip off whatever democratic have put. This view more force hard. Staff able blue part defense hotel teacher.\nSpace father teach. Figure matter reduce Mrs do. Writer own someone none.',
    'email': 'bradley23@example.com',
    'phone_number': '001-374-730-1992x079',
    'json': {
    'name': 'David Merritt MD',
    'address': '92038 Nunez Crest Suite 671\nEast Phillip, AZ 46628',
},
    'key54272': 'value80632',
    'key19697': 'value73249',
    'key56465': 'value5350',
    'key77066': 'value42935',
    'key23259': 'value63735',
    'key21821': 'value19670',
    'key42853': 'value69293',
},
    {
    'id': 17527486091771,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Jennifer Obrien',
    'address': '01298 Martha Keys\nSouth Jennifer, KS 21420',
    'text': 'Than dog meeting about now guess blood there. Sport cover house author. Than behind cell see actually.\nAttorney choice top pass rather lay. Side wide animal down similar experience.',
    'email': 'joshua52@example.com',
    'phone_number': '(323)261-8361',
    'json': {
    'name': 'Dawn Castro',
    'address': '4209 Katie Island Apt. 484\nPort John, WI 98894',
},
    'key88941': 'value79371',
    'key22737': 'value95491',
    'key79183': 'value70558',
},
    {
    'id': 17527486091781,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Ryan Lee',
    'address': '111 Mccoy Prairie\nSouth Teresaside, MI 41149',
    'text': 'Any paper talk establish. Hear stage move realize store production particularly. Those major stuff we middle response.',
    'email': 'jonesclifford@example.com',
    'phone_number': '742-575-3512',
    'json': {
    'name': 'Elizabeth Ford',
    'address': '53368 Griffith Prairie\nEast Jenniferfurt, VI 07206',
},
    'key14981': 'value9919',
    'key73739': 'value23247',
    'key64128': 'value84276',
},
    {
    'id': 17527486091793,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Catherine Phillips',
    'address': '365 Crosby Motorway Suite 946\nGardnerstad, DE 24499',
    'text': 'Senior while light thing decide few change. Product sport green dream. Through role none finish best learn benefit.',
    'email': 'achavez@example.org',
    'phone_number': '7838947394',
    'json': {
    'name': 'Amber Duran',
    'address': '43712 Mata Path\nWest Michael, NJ 11434',
},
    'key83871': 'value6907',
    'key4582': 'value2484',
    'key98847': 'value57403',
    'key77882': 'value32814',
},
    {
    'id': 17527486091804,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Robert Harmon',
    'address': '20242 Melissa Key\nNorth John, MH 77367',
    'text': 'Cost me for hold girl store. Capital and shake. Thank once threat out reveal.\nParticipant movie word me politics. Beautiful sort boy summer not throw discussion.',
    'email': 'hodgesbrooke@example.net',
    'phone_number': '6735710130',
    'json': {
    'name': 'Stephanie Howard',
    'address': '0829 Michael Flat\nCatherinemouth, MN 24384',
},
    'key90790': 'value22509',
    'key65657': 'value77292',
    'key7302': 'value90545',
    'key2696': 'value98042',
    'key58505': 'value34027',
},
    {
    'id': 17527486091814,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Tyler Johnson',
    'address': '6544 Tyler Place\nNew Melissa, WY 15793',
    'text': 'Store day trial role middle pull you. Hair book production career race bring. Position improve interest music.',
    'email': 'castillojordan@example.net',
    'phone_number': '780.643.1315',
    'json': {
    'name': 'Lauren White',
    'address': '50972 Davis Divide Apt. 891\nWest Tabitha, OR 60158',
},
    'key93034': 'value41639',
},
    {
    'id': 17527486091825,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Charlene Duke MD',
    'address': '6330 Hall Rapid\nEmilystad, KS 74576',
    'text': 'Day outside may try. Discover well site else computer. It from than maybe employee trip.\nMonth career student itself position sing. Heavy throughout trouble surface perform husband trial significant.',
    'email': 'thomas47@example.org',
    'phone_number': '001-806-550-9947',
    'json': {
    'name': 'Debra Bernard',
    'address': '01698 Brown Branch Suite 830\nGomezview, IN 99448',
},
    'key39590': 'value45289',
    'key5375': 'value63137',
    'key95797': 'value7658',
    'key84528': 'value39763',
    'key23822': 'value7810',
    'key62147': 'value82715',
    'key15957': 'value42906',
    'key11562': 'value87828',
    'key11588': 'value55359',
},
    {
    'id': 17527486091837,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Lucas Brooks',
    'address': '349 Sierra Radial\nMathisfurt, NY 02462',
    'text': 'Against hope new similar news participant. Teacher police vote address that indicate. Success guess court ability simply who.\nMind across much form. Environment him scene north.',
    'email': 'gwilliams@example.org',
    'phone_number': '(758)716-6752x8602',
    'json': {
    'name': 'Alicia Morales',
    'address': '2738 Steven Course Suite 645\nNew Michaelfort, TN 12237',
},
    'key72759': 'value82301',
    'key44176': 'value54943',
    'key78241': 'value77960',
    'key5621': 'value3561',
    'key77163': 'value35791',
    'key99943': 'value20485',
    'key87933': 'value85400',
},
    {
    'id': 17527486091847,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Robert Martin',
    'address': '39233 Pierce Key\nPort Karen, MD 17568',
    'text': 'People industry by style. Describe democratic start language gun on challenge.',
    'email': 'lopezlauren@example.com',
    'phone_number': '901-626-9711x341',
    'json': {
    'name': 'Scott Gordon',
    'address': '5856 Valdez Creek\nLake Andrewton, KY 75546',
},
    'key26903': 'value6114',
    'key1565': 'value14794',
    'key79958': 'value63505',
    'key61606': 'value9343',
    'key22660': 'value42898',
},
    {
    'id': 17527486091859,
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Jill Smith',
    'address': '215 Teresa Way Apt. 816\nKimport, PR 36498',
    'text': 'Speech all why answer back. Reduce natural national. Picture if today from material machine color.',
    'email': 'yusean@example.net',
    'phone_number': '3334400577',
    'json': {
    'name': 'Paul Parks',
    'address': '51130 Katherine Causeway Suite 886\nBrownhaven, PR 57915',
},
    'key20324': 'value97650',
    'key26887': 'value52751',
    'key93158': 'value95086',
    'key59016': 'value48425',
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
    'RequestId': 'ee25a49e-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_43_035324EYujWVoC',
    'filter': 'uid in [1,2,3,4]',
    'limit': 100,
    'offset': 0,
    'outputFields': [
    'name',
    'text',
    'id',
    'phone_number',
    'uid',
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
        """测试请求 4 - POST http://172.17.0.5:23210/v2/vectordb/collections/list"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/list")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/list'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': 'ee25a49e-62f9-11f0-85c3-0242ac11000b',
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



    def test_request_5(self):
        """测试请求 5 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': 'ee25a49e-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_43_035324EYujWVoC',
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



    def test_request_6(self):
        """测试请求 6 - POST http://172.17.0.5:23210/v2/vectordb/collections/drop"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/drop")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/drop'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': 'ee25a49e-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_43_035324EYujWVoC',
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



    def test_request_7(self):
        """测试请求 7 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': 'ee25a49e-62f9-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_36_43_035324EYujWVoC',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestQueryVector_test_query_vector_with_int64_filter[True-True-uid in [1,2,3,4]]_1752748617.json')
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
    test = AllmilvusLogtestqueryvectorTestQueryVectorWithInt64FilterTrueTrueUidIn12341752748617Json()
    test.run_tests()
