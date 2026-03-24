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
from urllib.parse import urlsplit, urlunsplit

# 导入变异模块
try:
    from vdbfuzz.mutator import Mutator
except ImportError:
    try:
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if repo_root not in sys.path:
            sys.path.append(repo_root)
        try:
            from vdbfuzz.mutator import Mutator
        except ImportError:
            try:
                from vdb_fuzzer.src.mutator import Mutator
            except ImportError:
                sys.path.append(repo_root)
                try:
                    from src.mutator import Mutator
                except ImportError:
                    vdb_fuzzer_path = os.path.join(repo_root, 'vdb_fuzzer')
                    if os.path.exists(vdb_fuzzer_path):
                        sys.path.append(os.path.dirname(vdb_fuzzer_path))
                        from vdb_fuzzer.src.mutator import Mutator
                    else:
                        raise ImportError
    except ImportError:
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
logger = logging.getLogger('vdb_fuzzer.test.test_discovery_test_query_with_nan')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_discovery.test_query_with_nan"
VDB_TYPE = "qdrant"


def build_target_url(url_path):
    base = urlsplit(TARGET_URL.rstrip('/'))
    if not base.scheme or not base.netloc:
        raise ValueError(f"目标URL格式无效: {TARGET_URL}")

    candidate = url_path or "/"
    if not candidate.startswith(('http://', 'https://')):
        candidate = "/" + candidate.lstrip('/')

    parsed = urlsplit(candidate)
    path = parsed.path or "/"
    return urlunsplit((base.scheme, base.netloc, path, parsed.query, parsed.fragment))


def send_request(content, request_type="PUT", url_path="http://localhost:6333/collections/congruence_test_collection?timeout=60", custom_headers=None):
    """
    发送请求到目标服务器

    Args:
        content: 请求内容
        request_type: 请求方法，默认为"PUT"
        url_path: URL路径，默认为"http://localhost:6333/collections/congruence_test_collection?timeout=60"
        custom_headers: 自定义请求头，如果提供则会合并到默认headers
        
    Returns:
        requests.Response: 响应对象
    """
    if not TARGET_URL:
        raise ValueError("目标URL未设置，请使用 -t 参数指定目标服务器URL")
    
    url = build_target_url(url_path)
    
    # 基础请求头
    headers = {
        'Content-Type': 'application/json',
    }

    # 合并自定义请求头
    if custom_headers:
        headers.update(custom_headers)

    headers.pop('Host', None)
    headers.pop('host', None)
    headers.pop('Content-Length', None)
    headers.pop('content-length', None)

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
        return response.status_code == 200
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



class TestDiscoverytestQueryWithNan:
    """自动生成的VDB模糊测试类 - test_discovery.test_query_with_nan"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_discovery.test_query_with_nan"
        self.test_count = 7  # 测试方法数量
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
        """测试请求 0 - PUT http://localhost:6333/collections/congruence_test_collection?timeout=60"""
        logger.info(f"跳过非写请求或无内容请求: PUT http://localhost:6333/collections/congruence_test_collection?timeout=60")
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/congruence_test_collection?timeout=60'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '129',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'text': {
    'size': 50,
    'distance': 'Cosine',
},
    'image': {
    'size': 100,
    'distance': 'Dot',
},
    'code': {
    'size': 80,
    'distance': 'Euclid',
},
},
}


        send_request(original_content, method, url_path, headers)
        return True



    def test_request_1(self):
        """测试请求 1 - PUT http://localhost:6333/collections/congruence_test_collection/points?wait=true"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/congruence_test_collection/points?wait=true")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points?wait=true'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '139293',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 100,
    'id_str': [
    '06',
    '07',
],
    'text_data': 'f970d532e29e4ac78a9f7d7855540ce6',
    'rand_digit': 5,
    'rand_number': 0.64287,
    'rand_signed_int': 1,
    'rand_datetime': '2000-03-22T18:14:43',
    'text_array': [
    '68da66d7a1de46fd944d5b557f066d49',
    '1f4af0763c7b4987903188ce0f2e5a5e',
],
    'words': 'monkey bee',
    'nested': {
    'id': 100,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lobster',
    'tiger',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'lion',
},
},
    {
    'id': 1,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 101,
    'id_str': [
    '29',
    '15',
    '25',
],
    'text_data': '5bca81144f154efab08d677a6e7cb69e',
    'rand_digit': 2,
    'rand_number': 0.36114,
    'rand_signed_int': -9,
    'rand_datetime': '2000-11-06 16:53:24.514792+1200',
    'text_array': [
    'e2b5d2d112b04f9ba81a2922bf934641',
    '645d31a7186e4e52b40e49277300b3a3',
],
    'words': 'giraffe chicken',
    'nested': {
    'id': 101,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ant',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mouse',
    'turtle',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'rabbit',
    'maybe_null': 'ape',
},
},
    {
    'id': 2,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 102,
    'id_str': [
    '04',
],
    'text_data': '22b6ce8dcb5949d0b8f3e32392639c5d',
    'rand_digit': 8,
    'rand_number': 0.34141,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-26 02:38:20+0400',
    'text_array': [
    'e282bc54bb6c4349874651dd5cecd0d2',
    '61b93a7e991f41adbc4aa8db1a65feb2',
],
    'words': 'duck whale',
    'nested': {
    'id': 102,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bear',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'camel',
    'butterfly',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.52716,
    'maybe': 'duck',
    'maybe_null': 'lobster',
},
},
    {
    'id': 3,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 103,
    'id_str': [
    '20',
    '15',
    '06',
    '20',
],
    'text_data': 'd70d9f01bba846d096a63ba227648c55',
    'rand_digit': 2,
    'rand_number': 0.31251,
    'rand_signed_int': -9,
    'rand_datetime': '2001-01-20T12:25:30.130173',
    'text_array': [
    '1d687b5016a64f87a3f6b8f2555520db',
    '6c2bbd59f6f34d558e6a8365b976d536',
],
    'words': 'chicken shark',
    'nested': {
    'id': 103,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'bee',
    'gorilla',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': [
    16,
],
    'rand_bool': True,
    'mixed_type': 0.04618,
    'maybe': 'deer',
    'maybe_null': None,
},
},
    {
    'id': 4,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 104,
    'id_str': [
    '24',
    '03',
    '05',
],
    'text_data': '37260748a09d4bc1a5854aa188ee1036',
    'rand_digit': 9,
    'rand_number': 0.8931,
    'rand_signed_int': -5,
    'rand_datetime': '2000-01-26 18:42:55+0300',
    'text_array': [
    '816a93e9e04a4e3a8bfba79d787a5f5a',
    '80b8667d81114006a5051c7f353e3b73',
],
    'words': 'spider grasshopper',
    'nested': {
    'id': 104,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'mouse',
    'octopus',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 'koala',
    'maybe': 'elephant',
},
},
    {
    'id': 5,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 105,
    'id_str': [
    '28',
    '10',
    '21',
    '03',
    '29',
],
    'text_data': 'f335f9bbddd64095afd144bb58caf556',
    'rand_digit': 1,
    'rand_number': 0.5987,
    'rand_signed_int': 2,
    'rand_datetime': '2000-10-20T11:53:09',
    'text_array': [
    '95844f1c83d24206a06e3ebff4534cd4',
    'cb1874fb8be749fba1c52b89d07ed756',
],
    'words': 'fox dragonfly',
    'nested': {
    'id': 105,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'fish',
    'shark',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'jaguar',
},
},
    {
    'id': 6,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 106,
    'id_str': [
    '12',
    '11',
],
    'text_data': '4a6a548eb6a24ddf8227ba4cc2f0f77b',
    'rand_digit': 3,
    'rand_number': 0.02457,
    'rand_signed_int': 3,
    'rand_datetime': '2000-07-31T07:14:17.699770',
    'text_array': [
    '38bce90b4eec415da170e648c7f5d655',
    '843fbba0781840b69bb7406b87aefe3e',
],
    'words': 'bee camel',
    'nested': {
    'id': 106,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
    -1,
],
    [
    10,
],
],
    'two_words': [
    'bee',
    'snail',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.74165,
    'maybe': 'pig',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 7,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 107,
    'id_str': [
    '17',
    '30',
    '01',
],
    'text_data': '984e93c5e4c640d58ff874a450c7127b',
    'rand_digit': 0,
    'rand_number': 0.86006,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-26T05:28:06.865596',
    'text_array': [
    '5b4e076ad5d84d9f9002aa8e8e780c53',
    '18d2d6d3dcaf4e27b1c9653c646e1ab7',
],
    'words': 'sloth cow',
    'nested': {
    'id': 107,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'mouse',
    'squid',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': [
    90,
],
    'rand_bool': False,
    'mixed_type': 'grasshopper',
    'maybe': 'wolf',
    'maybe_null': 'cheetah',
},
},
    {
    'id': 8,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 108,
    'id_str': [
    '29',
],
    'text_data': '5ff905421ebb49678f9307abbc44ded3',
    'rand_digit': 6,
    'rand_number': 0.6422,
    'rand_signed_int': 10,
    'rand_datetime': '2000-03-05 01:09:39-0500',
    'text_array': [
    '2df144cf944740ab987dc53ed568653d',
    '48b206c347114094bd06fa6f8b99d041',
],
    'words': 'elephant kangaroo',
    'nested': {
    'id': 108,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'monkey',
    'turtle',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'snake',
},
},
    {
    'id': 9,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 109,
    'id_str': [
    '13',
    '25',
    '22',
    '13',
    '25',
],
    'text_data': 'cc8305c86d60493fbb7882924100ce1f',
    'rand_digit': 9,
    'rand_number': 0.3767,
    'rand_signed_int': -9,
    'rand_datetime': '2000-12-02T19:16:28-0400',
    'text_array': [
    'd8513189eb194269bd93f3a2f3dc0b4d',
    '2999e5acb3b3484682887c2e94b3f9d9',
],
    'words': 'sheep snake',
    'nested': {
    'id': 109,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'crab',
    'ape',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'hyena',
},
},
    {
    'id': 10,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 110,
    'id_str': [
    '26',
    '28',
    '26',
    '21',
    '25',
],
    'text_data': 'b650915f15284448a79f4be4bbc6b1f3',
    'rand_digit': 6,
    'rand_number': 0.96956,
    'rand_signed_int': 4,
    'rand_datetime': '2000-07-08T06:44:06-0800',
    'text_array': [
    '753e29eed54341c29d68ac495faabb6b',
    'f24c980626e84d328fec9bbb26d89129',
],
    'words': 'chicken hyena',
    'nested': {
    'id': 110,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fish',
    'octopus',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 5,
    'maybe': 'frog',
    'maybe_null': 'goat',
},
},
    {
    'id': 11,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 111,
    'id_str': [
    '25',
],
    'text_data': '420506d3729549d7b6d38281391858a6',
    'rand_digit': 5,
    'rand_number': 0.74002,
    'rand_signed_int': 2,
    'rand_datetime': '2000-03-22T01:20:25-1000',
    'text_array': [
    '144540defffc41c18f9d539aad6a409e',
    '766956b1bae34aa1bd31d75deb4dd9df',
],
    'words': 'zebra grasshopper',
    'nested': {
    'id': 111,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 8,
},
],
},
    'nested_array': [
    [
    -7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'grasshopper',
    'hyena',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'rhino',
    'maybe': 'leopard',
    'maybe_null': None,
},
},
    {
    'id': 12,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 112,
    'id_str': [
    '08',
    '27',
    '16',
    '18',
    '24',
],
    'text_data': '1456fcad721b40d0b05ea304ff67dbec',
    'rand_digit': 7,
    'rand_number': 0.41856,
    'rand_signed_int': 1,
    'rand_datetime': '2000-05-02T00:44:32-0400',
    'text_array': [
    'aca483b1467c47d28f8ac374b38da859',
    '7c1006b5b5d84ad2a3c8dbca2824582b',
],
    'words': 'frog bear',
    'nested': {
    'id': 112,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fly',
    'giraffe',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': [
    73,
],
    'rand_bool': True,
    'mixed_type': False,
    'maybe_null': 'mosquito',
},
},
    {
    'id': 13,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 113,
    'id_str': [
    '26',
    '23',
    '18',
    '22',
    '29',
],
    'text_data': '3fb4be8cd93144119bf854a17d65378e',
    'rand_digit': 8,
    'rand_number': 0.31747,
    'rand_signed_int': -8,
    'rand_datetime': '2000-07-04 15:52:12.524012',
    'text_array': [
    '283492dc605a48d3bfdd807b1635f3c1',
    '9e99b1263a084d7280f86498c080e581',
],
    'words': 'elephant leopard',
    'nested': {
    'id': 113,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bee',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'rhino',
    'elephant',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'frog',
},
},
    {
    'id': 14,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 114,
    'id_str': [
    '25',
    '16',
    '26',
    '27',
    '11',
],
    'text_data': '54145e008c1c4a27b6106ebf5348ff52',
    'rand_digit': 7,
    'rand_number': 0.44937,
    'rand_signed_int': 7,
    'rand_datetime': '2000-11-16 02:09:41+0700',
    'text_array': [
    '71ef9f4ff07644ab9046b65985a2e473',
    '92d1af1457364752a6775ff030138e48',
],
    'words': 'rhino elephant',
    'nested': {
    'id': 114,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cat',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dog',
    'turtle',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 6,
    'maybe_null': 'rhino',
},
},
    {
    'id': 15,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 115,
    'id_str': [
    '02',
],
    'text_data': 'e6548c4f22834b72ac4727de80720064',
    'rand_digit': 8,
    'rand_number': 0.32398,
    'rand_signed_int': 3,
    'rand_datetime': '2001-01-26 13:17',
    'text_array': [
    'c4535fee1a8b432c8d8078e9a23ca17f',
    '0157cf4dca494a52a8fa48da1c15a350',
],
    'words': 'squid dragonfly',
    'nested': {
    'id': 115,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'bee',
    'rabbit',
],
    'city': {
    'name': 'Copenhagen',
    'geo': {
    'lat': 55.676097,
    'lon': 12.568337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': 'dolphin',
},
},
    {
    'id': 16,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 116,
    'id_str': [
    '04',
    '19',
    '03',
    '05',
    '15',
],
    'text_data': '55e0e0b881b74aebaeb90083ed3cd1c8',
    'rand_digit': 9,
    'rand_number': 0.23208,
    'rand_signed_int': -4,
    'rand_datetime': '2000-05-07T22:53:00.495310',
    'text_array': [
    'ae58f46d589049298b48f56ad44744bf',
    '4f8e595025b84018b3def1fe08083261',
],
    'words': 'camel bird',
    'nested': {
    'id': 116,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
    6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'cow',
    'zebra',
],
    'city': {
    'name': 'Seoul',
    'geo': {
    'lat': 37.566535,
    'lon': 126.977969,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 5,
    'maybe': 'ladybug',
},
},
    {
    'id': 17,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 117,
    'id_str': [
    '07',
    '06',
    '23',
    '29',
    '23',
],
    'text_data': '51178e4019d7431e899d5de42c0084e7',
    'rand_digit': 4,
    'rand_number': 0.25501,
    'rand_signed_int': 10,
    'rand_datetime': '2000-03-09 09:28',
    'text_array': [
    '2cbd95f8d857465889104d4613f7062b',
    '32c4649f249b4a9287126899a9a50301',
],
    'words': 'jaguar bear',
    'nested': {
    'id': 117,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 7,
},
],
},
    'nested_array': [
    [
    4,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    2,
],
],
    'two_words': [
    'dog',
    'squid',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': 18,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 118,
    'id_str': [
    '01',
],
    'text_data': '19b97f54fb524c3b9c55257c265f1992',
    'rand_digit': 4,
    'rand_number': 0.24696,
    'rand_signed_int': -10,
    'rand_datetime': '2000-02-14 15:15',
    'text_array': [
    '3be0728acfcd46cf800e726fcdafd02e',
    'ecb32b2a0e6d417f823f31d476a35e22',
],
    'words': 'wolf rabbit',
    'nested': {
    'id': 118,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 6,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,3__',
    'two_words': [
    'hyena',
    'rhino',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
    'maybe_null': 'scorpion',
},
},
    {
    'id': 19,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 119,
    'id_str': [
    '20',
    '01',
    '03',
    '01',
    '14',
],
    'text_data': 'b25947dd3c7b44c8b1de6116f94bc2b4',
    'rand_digit': 0,
    'rand_number': 0.55488,
    'rand_signed_int': 7,
    'rand_datetime': '2000-03-12T02:15:17',
    'text_array': [
    '4e275ae6ecb34343a1456852324ea69f',
    '00dfdfb34ec1470a965b5335f50a788d',
],
    'words': 'snail fox',
    'nested': {
    'id': 119,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'spider',
    'chicken',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': [
    85,
],
    'rand_bool': False,
    'mixed_type': 1,
    'maybe_null': 'pig',
},
},
    {
    'id': 20,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 120,
    'id_str': [
    '07',
],
    'text_data': 'e2a74b14b3784fe88a500d050b9442f6',
    'rand_digit': 5,
    'rand_number': 0.75061,
    'rand_signed_int': -2,
    'rand_datetime': '2000-09-17T13:50:16.775339+0400',
    'text_array': [
    '2d862dcc79e24c11aa78df014c5f0cb1',
    'ba1c64fa7937405f9be317369adb3ff4',
],
    'words': 'ape crab',
    'nested': {
    'id': 120,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snake',
    'lobster',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'panda',
},
},
    {
    'id': 21,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 121,
    'id_str': [
    '09',
    '15',
    '04',
],
    'text_data': '21c5c5f9b5cf40899bf4be089e469182',
    'rand_digit': 5,
    'rand_number': 0.5967,
    'rand_signed_int': 6,
    'rand_datetime': '2000-08-06 20:24:08',
    'text_array': [
    '51da930d2cb448ff8c317553a9f73196',
    '68716a14d1c0435e9339ff6ddb433565',
],
    'words': 'crab shark',
    'nested': {
    'id': 121,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'hyena',
    'elephant',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 'kangaroo',
    'maybe_null': None,
},
},
    {
    'id': 22,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 122,
    'id_str': [
    '23',
    '24',
    '12',
],
    'text_data': 'b0269b906d714cc0b8e0f328e5834ade',
    'rand_digit': 0,
    'rand_number': 0.31121,
    'rand_signed_int': 1,
    'rand_datetime': '2001-01-06T06:02:55',
    'text_array': [
    'e21717f5cf2f4c9da153ed809a1140c7',
    '9443e7162e694c63ad8acad056485e64',
],
    'words': 'whale kangaroo',
    'nested': {
    'id': 122,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'gorilla',
    'hippo',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': [
    10,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'kangaroo',
},
},
    {
    'id': 23,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 123,
    'id_str': [
    '05',
    '27',
    '09',
    '06',
    '20',
],
    'text_data': '11b1d4a724a84638b51eca428b2fd1b2',
    'rand_digit': 5,
    'rand_number': 0.13609,
    'rand_signed_int': 4,
    'rand_datetime': '2000-08-06 20:06',
    'text_array': [
    '9c9840885f4f40f29685a54167d0fbc2',
    '9da28e388d204c2aa4a52c3b68d0d91b',
],
    'words': 'monkey squid',
    'nested': {
    'id': 123,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'cat',
    'jaguar',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': [
    54,
],
    'rand_bool': True,
    'mixed_type': 0.36176,
    'maybe_null': 'bird',
},
},
    {
    'id': 24,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 124,
    'id_str': [
],
    'text_data': '625cbe5474bd4bbb92a0322f5961ec4b',
    'rand_digit': 6,
    'rand_number': 0.07589,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-05T16:07:33.102013+0000',
    'text_array': [
    '0d0d90ad5eb945ae9fc713e84fdd1dfe',
    '0aa1124d931a4f52867f1544d3e319b3',
],
    'words': 'turtle cow',
    'nested': {
    'id': 124,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'panda',
    'chicken',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'whale',
},
},
    {
    'id': 25,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 125,
    'id_str': [
    '25',
    '26',
    '27',
    '20',
    '28',
],
    'text_data': 'ad50858ec3374961b6670da375bc7a90',
    'rand_digit': 0,
    'rand_number': 0.2346,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-13T10:33:39+1000',
    'text_array': [
    'aa7a0ee83b8f472491a791a5dacad787',
    '43d107f542c549b7af7a49b16aa174a1',
],
    'words': 'sloth lizard',
    'nested': {
    'id': 125,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'shark',
    'frog',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.57436,
},
},
    {
    'id': 26,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 126,
    'id_str': [
    '09',
    '26',
    '09',
    '06',
],
    'text_data': '6fa49fa2900a4b6bab50e95f4b76214c',
    'rand_digit': 8,
    'rand_number': 0.72873,
    'rand_signed_int': -10,
    'rand_datetime': '2000-01-30 19:46:02-1100',
    'text_array': [
    '5bdef29c935e45db8c74b524386682ff',
    '749659cd701346fc90740dcaea8786b0',
],
    'words': 'cat snake',
    'nested': {
    'id': 126,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'wolf',
    'tiger',
],
    'city': {
    'name': 'Frankfurt',
    'geo': {
    'lat': 50.110922,
    'lon': 8.682127,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'shark',
    'maybe_null': 'frog',
},
},
    {
    'id': 27,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 127,
    'id_str': [
],
    'text_data': '1e2dd8783c38461b859f7e6cd84ae956',
    'rand_digit': 4,
    'rand_number': 0.58938,
    'rand_signed_int': -5,
    'rand_datetime': '2000-01-25 23:05:22',
    'text_array': [
    'd178a1fde6c94940b649c7ddc1cb9748',
    '28d1d9635d4e4de9a58ca06412d89f6a',
],
    'words': 'cheetah panda',
    'nested': {
    'id': 127,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'sloth',
    'wolf',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 'monkey',
    'maybe_null': 'squid',
},
},
    {
    'id': 28,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 128,
    'id_str': [
    '04',
    '24',
    '27',
    '20',
],
    'text_data': 'b2aa4cec78974807a1341a67ec599fd8',
    'rand_digit': 3,
    'rand_number': 0.49822,
    'rand_signed_int': -10,
    'rand_datetime': '2000-03-29T23:59:11.457153',
    'text_array': [
    '04915dec51af4f2888d5541e96ca39bb',
    'bd0839082667432694e023c9afb85667',
],
    'words': 'dolphin bear',
    'nested': {
    'id': 128,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'spider',
    'cat',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 'fish',
},
},
    {
    'id': 29,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 129,
    'id_str': [
    '29',
    '03',
    '15',
    '13',
],
    'text_data': '6eb2d5729e3b4bd5bccc1ac541661aed',
    'rand_digit': 6,
    'rand_number': 0.6978,
    'rand_signed_int': -2,
    'rand_datetime': '2000-12-18 10:12:40.895357+0900',
    'text_array': [
    '37dcfb7d11de42a1a4473b81c490c04c',
    '6a5bb4d8fa8e4dc8b92d00ffcfaf0afb',
],
    'words': 'panda sloth',
    'nested': {
    'id': 129,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ladybug',
    'snake',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.052,
    'maybe': 'kangaroo',
    'maybe_null': None,
},
},
    {
    'id': 30,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 130,
    'id_str': [
],
    'text_data': 'ff54f03697a64c4d864fd35d89604196',
    'rand_digit': 1,
    'rand_number': 0.17649,
    'rand_signed_int': 7,
    'rand_datetime': '2000-10-30 19:03:09.839304-0400',
    'text_array': [
    '27b20a4a2ef44e0da2c7634fac324250',
    '1002d2ca0567437fa4b72d45eb819edc',
],
    'words': 'chicken mouse',
    'nested': {
    'id': 130,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'cow',
    'gorilla',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'sloth',
    'maybe_null': 'spider',
},
},
    {
    'id': 31,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 131,
    'id_str': [
    '17',
    '22',
    '05',
    '28',
    '24',
],
    'text_data': '56cccec4d5a84eeb9389da4e1fa5bc35',
    'rand_digit': 0,
    'rand_number': 0.37898,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-22 22:27:36.729573',
    'text_array': [
    '56744e64534c46b9a58e98a7710f3f1e',
    'fcf83e4cc0a241f4a22f21c7ed9d284e',
],
    'words': 'snail gorilla',
    'nested': {
    'id': 131,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dog',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'shark',
    'rabbit',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'snake',
    'maybe_null': 'shark',
},
},
    {
    'id': 32,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 132,
    'id_str': [
    '18',
],
    'text_data': '3032870e4bad4ca7a0c89f74100372f6',
    'rand_digit': 0,
    'rand_number': 0.85458,
    'rand_signed_int': 10,
    'rand_datetime': '2000-12-23 11:52:22.860992-0600',
    'text_array': [
    '075ad3440d7e4bccbd1e721daace196a',
    'daa016b1b0af4e8e9c8260657b81ec2a',
],
    'words': 'panda scorpion',
    'nested': {
    'id': 132,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    [
    -1,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fish',
    'shark',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 4,
    'maybe': 'rhino',
},
},
    {
    'id': 33,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 133,
    'id_str': [
    '20',
    '06',
    '04',
],
    'text_data': '36b3f8a2cd3c46cf87704a55db1ee344',
    'rand_digit': 4,
    'rand_number': 0.41962,
    'rand_signed_int': 9,
    'rand_datetime': '2000-10-03T01:26:55-0300',
    'text_array': [
    'd989b8800b604b69a310551d2c3d1d43',
    '99a6c306ce8b4e57995bb0b562d09d66',
],
    'words': 'lizard dog',
    'nested': {
    'id': 133,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 6,
},
],
},
    'nested_array': [
    [
    5,
],
],
    'two_words': [
    'horse',
    'frog',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'hyena',
},
},
    {
    'id': 34,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 134,
    'id_str': [
    '22',
    '17',
    '26',
],
    'text_data': 'ea64920242ec4ca396328a5c1291d96f',
    'rand_digit': 2,
    'rand_number': 0.42548,
    'rand_signed_int': -10,
    'rand_datetime': '2000-07-15 05:50:55.933873',
    'text_array': [
    'c9ac7031ec69437d8b71085cf213ad3d',
    'aaf68d63d4604d05ad604df391c06954',
],
    'words': 'panda frog',
    'nested': {
    'id': 134,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'frog',
    'panda',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'bird',
    'maybe_null': None,
},
},
    {
    'id': 35,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 135,
    'id_str': [
],
    'text_data': 'f5db085f98bd4faea53d5955efd15ec3',
    'rand_digit': 9,
    'rand_number': 0.97733,
    'rand_signed_int': -9,
    'rand_datetime': '2000-03-23 21:43:59',
    'text_array': [
    '1318efa41f7f4552987133c374668711',
    '560449038d67426ea710e0c2f97b4eb6',
],
    'words': 'cow rhino',
    'nested': {
    'id': 135,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'zebra',
    'mosquito',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': [
    23,
],
    'rand_bool': False,
    'mixed_type': 'rhino',
    'maybe_null': 'fish',
},
},
    {
    'id': 36,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 136,
    'id_str': [
],
    'text_data': '04b6070dd34e4c129e8c7b22040d3183',
    'rand_digit': 9,
    'rand_number': 0.96967,
    'rand_signed_int': 6,
    'rand_datetime': '2000-08-20T10:24:47',
    'text_array': [
    '6617512c99f54488ae2d14cecc591ef9',
    'e9f10e1724394a29a40772dbf16d464a',
],
    'words': 'fish rhino',
    'nested': {
    'id': 136,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'turtle',
    'pig',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': [
    65,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'hippo',
},
},
    {
    'id': 37,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 137,
    'id_str': [
    '03',
    '01',
    '16',
    '15',
    '10',
],
    'text_data': 'f5c1e375f05a43df9dde195606f15cdf',
    'rand_digit': 7,
    'rand_number': 0.48197,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-02 00:29:34',
    'text_array': [
    '84ce443a1ad945caa6ff2346d8e5c27f',
    'bc605f3e1d084aa0956bde430998f7bb',
],
    'words': 'bear chicken',
    'nested': {
    'id': 137,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'leopard',
    'cheetah',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 4,
    'maybe': 'cheetah',
    'maybe_null': 'grasshopper',
},
},
    {
    'id': 38,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 138,
    'id_str': [
    '17',
    '14',
    '01',
],
    'text_data': 'adec3982065940d983a89a8a92d90c95',
    'rand_digit': 5,
    'rand_number': 0.21472,
    'rand_signed_int': -1,
    'rand_datetime': '2000-02-26',
    'text_array': [
    '4a06675406e14ad79ecc68c761683437',
    '3f70b4e849d04b9aa0516a8808974c02',
],
    'words': 'scorpion ladybug',
    'nested': {
    'id': 138,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'cat',
    'fish',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'lizard',
    'maybe_null': 'hippo',
},
},
    {
    'id': 39,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 139,
    'id_str': [
],
    'text_data': '9b1e7ca46e6a450cbb06b768e878632b',
    'rand_digit': 2,
    'rand_number': 0.23802,
    'rand_signed_int': 9,
    'rand_datetime': '2000-12-26 12:17:50.979088+0600',
    'text_array': [
    'fa68bf3d752447cdb5e553f5fe6163e8',
    '246f1bd85f7e4231a1f62ac71a67f793',
],
    'words': 'ape octopus',
    'nested': {
    'id': 139,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'kangaroo',
    'octopus',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': [
    98,
],
    'rand_bool': True,
    'mixed_type': 'crab',
    'maybe_null': None,
},
},
    {
    'id': 40,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 140,
    'id_str': [
],
    'text_data': 'fba61b6432744b5593b6a857b9f68a7b',
    'rand_digit': 9,
    'rand_number': 0.17776,
    'rand_signed_int': 1,
    'rand_datetime': '2000-02-06T23:56:45.219720-10:00',
    'text_array': [
    '820ba5bc32a1482fafa8dbd5507bc04e',
    '499c9107640f4dda9115a4996dfd1284',
],
    'words': 'dragonfly tiger',
    'nested': {
    'id': 140,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'panda',
    'dog',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.65858,
    'maybe': 'squid',
},
},
    {
    'id': 41,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 141,
    'id_str': [
    '11',
    '08',
],
    'text_data': '746d81b421d2494da9ec79481428201c',
    'rand_digit': 0,
    'rand_number': 0.28363,
    'rand_signed_int': -3,
    'rand_datetime': '2000-07-21T22:38:40.953845',
    'text_array': [
    'ee92154217f8408b847c22616e09b079',
    '2f9646bfb97c40f484e6a343c1a6eef7',
],
    'words': 'spider crab',
    'nested': {
    'id': 141,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'dragonfly',
    'dolphin',
],
    'city': {
    'name': 'Zurich',
    'geo': {
    'lat': 47.376887,
    'lon': 8.541694,
},
},
    'rand_tuple': [
    85,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'dog',
    'maybe_null': 'leopard',
},
},
    {
    'id': 42,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 142,
    'id_str': [
    '16',
    '16',
    '23',
    '01',
    '18',
],
    'text_data': '725aec9ab215485d92d4d8aeb86fe133',
    'rand_digit': 0,
    'rand_number': 0.73321,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-29 01:54:31+0500',
    'text_array': [
    '7350597c0c98444299f4e6542bd6df77',
    '2050d707c3ed45cc84b3e6d8ed6ac02a',
],
    'words': 'zebra giraffe',
    'nested': {
    'id': 142,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'leopard',
    'butterfly',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': [
    38,
],
    'rand_bool': False,
    'mixed_type': 'lobster',
    'maybe_null': 'rabbit',
},
},
    {
    'id': 43,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 143,
    'id_str': [
],
    'text_data': '6d61c0d9abce4a47ba7fa1e3317bbef5',
    'rand_digit': 0,
    'rand_number': 0.71385,
    'rand_signed_int': 0,
    'rand_datetime': '2001-01-06T18:44:09.424726Z',
    'text_array': [
    '4083ffd93b1346f89cd608f1d6736b93',
    '496614d5723e434bab9917ae5bfa091f',
],
    'words': 'monkey hyena',
    'nested': {
    'id': 143,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'squid',
    'mosquito',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'hippo',
    'maybe_null': None,
},
},
    {
    'id': 44,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 144,
    'id_str': [
    '30',
    '23',
],
    'text_data': '6a3099f5458a419d959beb01da590961',
    'rand_digit': 0,
    'rand_number': 0.17533,
    'rand_signed_int': 7,
    'rand_datetime': '2000-06-29 10:24:23.144163',
    'text_array': [
    '6eae02d7ada44442bc73290da3120654',
    '7e5c3f2c19ce445ea7d1e7edf1b48cd1',
],
    'words': 'grasshopper mouse',
    'nested': {
    'id': 144,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    10,
],
    [
    10,
],
],
    'two_words': [
    'frog',
    'dog',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'giraffe',
},
},
    {
    'id': 45,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 145,
    'id_str': [
],
    'text_data': '519e096f670b431b9f6697e787b51255',
    'rand_digit': 8,
    'rand_number': 0.1759,
    'rand_signed_int': 2,
    'rand_datetime': '2000-04-27T09:32:44.790987',
    'text_array': [
    'a4a0d7fa164342c9a43a9167a9ce69d9',
    'e8aec16f883c4cbdb6ce588e7de9c6e6',
],
    'words': 'giraffe spider',
    'nested': {
    'id': 145,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'shark',
    'chicken',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'sloth',
},
},
    {
    'id': 46,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 146,
    'id_str': [
    '08',
],
    'text_data': '6756713b23564d5284395dba7395b5a3',
    'rand_digit': 2,
    'rand_number': 0.96049,
    'rand_signed_int': 1,
    'rand_datetime': '2000-04-17T13:30:25',
    'text_array': [
    '82fe99c7f88c4fbba6c99136a6f41236',
    '0c81356619414a66a1ed67053831c2be',
],
    'words': 'ape crab',
    'nested': {
    'id': 146,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'sheep',
    'crab',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 47,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 147,
    'id_str': [
],
    'text_data': 'a49fb1a27c1a4aabbde0f8b9ed38e3a1',
    'rand_digit': 7,
    'rand_number': 0.00778,
    'rand_signed_int': 7,
    'rand_datetime': '2001-01-30T06:05:42',
    'text_array': [
    'f2ffb6dcda0e4400b2587b7e677428a7',
    '87871f06dc7e4e5ab74bce6126060b44',
],
    'words': 'pig spider',
    'nested': {
    'id': 147,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'tiger',
    'snake',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 48,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 148,
    'id_str': [
    '14',
    '10',
],
    'text_data': '40d97c6d72374260a112512155ca1fe9',
    'rand_digit': 0,
    'rand_number': 0.21343,
    'rand_signed_int': 0,
    'rand_datetime': '2000-04-19T15:30:26-0400',
    'text_array': [
    'cc9e9fe89f344a709330125b9bcf5cd7',
    '8b148536c46a451d8bd05a86e9b9b6f3',
],
    'words': 'kangaroo bird',
    'nested': {
    'id': 148,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -6,
],
],
    'two_words': [
    'hippo',
    'giraffe',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': 'bear',
},
},
    {
    'id': 49,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 149,
    'id_str': [
    '12',
    '21',
    '06',
    '12',
],
    'text_data': '9e964dc8d0ee48fc9206e18991d3add2',
    'rand_digit': 8,
    'rand_number': 0.49058,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-09T17:36:19.268742',
    'text_array': [
    'e343851cbf4e488a9c849180b76149b2',
    '8f9056b57cf74576ac5ae70477a66bab',
],
    'words': 'hippo lizard',
    'nested': {
    'id': 149,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'squid',
    'cat',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'squid',
},
},
    {
    'id': 50,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 150,
    'id_str': [
    '07',
    '24',
    '19',
],
    'text_data': '72be6f1db998464895f184b4e6346933',
    'rand_digit': 9,
    'rand_number': 0.67164,
    'rand_signed_int': 0,
    'rand_datetime': '2001-01-03T03:12:49.335376+10:00',
    'text_array': [
    'f24029b3305148a599e83dea7d42bdcf',
    '77268f98512741baacc92b4c3f79a7c5',
],
    'words': 'snake panda',
    'nested': {
    'id': 150,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'jaguar',
    'sheep',
],
    'city': {
    'name': 'Seoul',
    'geo': {
    'lat': 37.566535,
    'lon': 126.977969,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 51,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 151,
    'id_str': [
    '26',
],
    'text_data': '0ae683c6b92344c280e644a02c0f555b',
    'rand_digit': 5,
    'rand_number': 0.0635,
    'rand_signed_int': 2,
    'rand_datetime': '2000-02-08T14:21:01',
    'text_array': [
    '5387ecf8cb8d4e32896788ebcbe7f8e9',
    '7ecf0c98cabf48149b89fa706770e786',
],
    'words': 'lobster gorilla',
    'nested': {
    'id': 151,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dragonfly',
    'koala',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fish',
    'maybe_null': 'chicken',
},
},
    {
    'id': 52,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 152,
    'id_str': [
],
    'text_data': '7088b4fbea064a3a89b9562486a932a4',
    'rand_digit': 3,
    'rand_number': 0.34025,
    'rand_signed_int': -2,
    'rand_datetime': '2000-11-06T06:02:37.873623+02:00',
    'text_array': [
    '613e9617c5ca49f9ad1a713ea0b821ee',
    '3a4da73bdd7a4125a99daa104bea61a5',
],
    'words': 'deer pig',
    'nested': {
    'id': 152,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'crab',
    'bird',
],
    'city': {
    'name': 'Seoul',
    'geo': {
    'lat': 37.566535,
    'lon': 126.977969,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'leopard',
},
},
    {
    'id': 53,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 153,
    'id_str': [
    '24',
    '29',
],
    'text_data': '2b5df4ba025a4a7f9cd92f6d05c27e5f',
    'rand_digit': 0,
    'rand_number': 0.49104,
    'rand_signed_int': 3,
    'rand_datetime': '2000-03-16 06:29:52.783834-1100',
    'text_array': [
    '782deae3255e43cbae2bb59570867bc0',
    'd83e1e3133fe43e981c63c206489bcf6',
],
    'words': 'grasshopper camel',
    'nested': {
    'id': 153,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'scorpion',
    'sloth',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'octopus',
    'maybe': 'fox',
    'maybe_null': 'monkey',
},
},
    {
    'id': 54,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 154,
    'id_str': [
    '27',
    '29',
],
    'text_data': '8585eb4a1e2b4ada998941501cfa7a22',
    'rand_digit': 8,
    'rand_number': 0.17134,
    'rand_signed_int': -1,
    'rand_datetime': '2000-07-26T19:06:20.614757',
    'text_array': [
    '329470f7bc28403c91f4257c503d81c8',
    '3ee6a1450c9f4f518c5bc0657bf41fc3',
],
    'words': 'zebra fish',
    'nested': {
    'id': 154,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snail',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fly',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lion',
    'grasshopper',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'hippo',
    'maybe_null': 'dolphin',
},
},
    {
    'id': 55,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 155,
    'id_str': [
    '25',
    '03',
],
    'text_data': '22046594442647178381092f7596914d',
    'rand_digit': 3,
    'rand_number': 0.31837,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-27 06:33:37.616783+0200',
    'text_array': [
    '972b558143cf4f7c910b88ed857369fd',
    '153802a8da2b493b8534e66e3c8466de',
],
    'words': 'fly koala',
    'nested': {
    'id': 155,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -4,
],
],
    'two_words': [
    'leopard',
    'dragonfly',
],
    'city': {
    'name': 'Kharkiv',
    'geo': {
    'lat': 49.980812,
    'lon': 36.25272,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 56,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 156,
    'id_str': [
],
    'text_data': '7531c2cd7b11429084bbbabe6d87ff25',
    'rand_digit': 1,
    'rand_number': 0.72778,
    'rand_signed_int': 4,
    'rand_datetime': '2000-06-30T16:18:15',
    'text_array': [
    '6b24ef2bbabd439aa6485013ce0b5c72',
    'cc7a80ece276421fa03d392d54d4b49a',
],
    'words': 'tiger gorilla',
    'nested': {
    'id': 156,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'horse',
    'chicken',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': [
    87,
],
    'rand_bool': False,
    'mixed_type': 'frog',
    'maybe': 'monkey',
    'maybe_null': 'ape',
},
},
    {
    'id': 57,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 157,
    'id_str': [
    '28',
    '02',
    '28',
],
    'text_data': '4f450c7e8686412e97a9184c87a5d3a5',
    'rand_digit': 8,
    'rand_number': 0.37706,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-16T13:18:53-0900',
    'text_array': [
    '25a98034cdf94a498889dc5efc758479',
    '9015ded7edb84c7092b78bbed0a19427',
],
    'words': 'bee ant',
    'nested': {
    'id': 157,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lion',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'bee',
    'ape',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'gorilla',
    'maybe_null': None,
},
},
    {
    'id': 58,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 158,
    'id_str': [
    '12',
    '11',
    '06',
],
    'text_data': 'b3513f6925c44bffa5671fbdb97b3169',
    'rand_digit': 3,
    'rand_number': 0.52852,
    'rand_signed_int': 9,
    'rand_datetime': '2000-02-18T01:53:32.398921+1200',
    'text_array': [
    '9dd6b9b581504a38aafa4f1381d7279d',
    '2ba916c1a7b541e5adebcf6835a08f61',
],
    'words': 'fish hippo',
    'nested': {
    'id': 158,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lion',
    'chicken',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': [
    85,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'elephant',
    'maybe_null': 'kangaroo',
},
},
    {
    'id': 59,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 159,
    'id_str': [
    '17',
    '17',
],
    'text_data': '6600c8ad2dde4efbb31f4078213f1c4f',
    'rand_digit': 5,
    'rand_number': 0.84703,
    'rand_signed_int': -9,
    'rand_datetime': '2001-01-29T20:12:19.201090-0300',
    'text_array': [
    '6a199f2fc52c4b16a50e59cd92eb1f06',
    '19a99af9a48f4d7b9ebfa4d4f580a10f',
],
    'words': 'scorpion lobster',
    'nested': {
    'id': 159,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -4,
],
    [
],
],
    'two_words': [
    'monkey',
    'bee',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 7,
    'maybe_null': 'horse',
},
},
    {
    'id': 60,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 160,
    'id_str': [
    '21',
    '15',
    '11',
    '16',
    '10',
],
    'text_data': 'f35a6029e95c4ecd82b6979ef5c6e82a',
    'rand_digit': 7,
    'rand_number': 0.6056,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-19 07:46:40+0600',
    'text_array': [
    'd2379fdf8bb1494b92b973a6e852c2f0',
    '9a8ffe458d674922a5c567c317e6da72',
],
    'words': 'grasshopper whale',
    'nested': {
    'id': 160,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'scorpion',
    'lobster',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 7,
    'maybe_null': 'bee',
},
},
    {
    'id': 61,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 161,
    'id_str': [
],
    'text_data': '29bcbe6115404582964d9d8d4a25fc66',
    'rand_digit': 2,
    'rand_number': 0.90557,
    'rand_signed_int': -10,
    'rand_datetime': '2000-12-21',
    'text_array': [
    'ffca4a5ec0394af49b1838d99853381c',
    '17594c5f8523424bbe8f47730a6bc190',
],
    'words': 'elephant koala',
    'nested': {
    'id': 161,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    [
],
],
    'two_words': [
    'cat',
    'tiger',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': [
    62,
],
    'rand_bool': True,
    'mixed_type': 5,
    'maybe': 'lizard',
    'maybe_null': None,
},
},
    {
    'id': 62,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 162,
    'id_str': [
    '19',
    '10',
    '25',
    '21',
],
    'text_data': '5a4261079ab64c7aa5c3b3e6907235e3',
    'rand_digit': 3,
    'rand_number': 0.27117,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-27T00:55:41.975781',
    'text_array': [
    '4d49d5f914f84ef7b84b7e7efa1c7025',
    '4e566d4c531f4173b3e49d7d49c23806',
],
    'words': 'tiger lion',
    'nested': {
    'id': 162,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'whale',
    'fish',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe_null': 'gorilla',
},
},
    {
    'id': 63,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 163,
    'id_str': [
    '01',
    '13',
    '12',
    '26',
],
    'text_data': '7270165937294e6080ff22a84f760d74',
    'rand_digit': 9,
    'rand_number': 0.89457,
    'rand_signed_int': 2,
    'rand_datetime': '2001-01-08T22:27:15.674298-0700',
    'text_array': [
    '4da51f34df00472089fe675137f349b5',
    '2cd4693ed6aa425b9a4398b2f35a5d57',
],
    'words': 'fly shark',
    'nested': {
    'id': 163,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'wolf',
    'duck',
],
    'city': {
    'name': 'Copenhagen',
    'geo': {
    'lat': 55.676097,
    'lon': 12.568337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
},
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



    def test_request_2(self):
        """测试请求 2 - PUT http://localhost:6333/collections/congruence_secondary_collection?timeout=60"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/congruence_secondary_collection?timeout=60")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/congruence_secondary_collection?timeout=60'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '129',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'text': {
    'size': 50,
    'distance': 'Cosine',
},
    'image': {
    'size': 100,
    'distance': 'Dot',
},
    'code': {
    'size': 80,
    'distance': 'Euclid',
},
},
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
        """测试请求 3 - PUT http://localhost:6333/collections/congruence_secondary_collection/points?wait=true"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/congruence_secondary_collection/points?wait=true")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/congruence_secondary_collection/points?wait=true'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '137895',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 100,
    'id_str': [
    '15',
],
    'text_data': '23fb717263ba4dbc921f9ad4217781c4',
    'rand_digit': 1,
    'rand_number': 0.69999,
    'rand_signed_int': 10,
    'rand_datetime': '2000-10-06T04:00:49.601062',
    'text_array': [
    '7077d44772d144c8a380a1eaab86c4e9',
    '7686a873b72b4615a774bf697ceabc34',
],
    'words': 'wolf squid',
    'nested': {
    'id': 100,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'deer',
    'mouse',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': [
    40,
],
    'rand_bool': False,
    'mixed_type': 0.46229,
    'maybe': 'rhino',
    'maybe_null': 'deer',
},
},
    {
    'id': 1,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 101,
    'id_str': [
    '14',
    '09',
],
    'text_data': 'fc8d2a813ef54cfb89c393237e23a2cc',
    'rand_digit': 0,
    'rand_number': 0.7133,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-26 21:36:25',
    'text_array': [
    '015c53637bf544cd93a2113f8ad9cf0e',
    '834fec0288b340e08aa9c03c5ae40987',
],
    'words': 'grasshopper monkey',
    'nested': {
    'id': 101,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    [
    -4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'fox',
    'panda',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.26801,
},
},
    {
    'id': 2,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 102,
    'id_str': [
    '01',
    '17',
    '05',
],
    'text_data': '46938c3c2f1e42e6aa3721bd51361bff',
    'rand_digit': 9,
    'rand_number': 0.46764,
    'rand_signed_int': 3,
    'rand_datetime': '2000-07-29T18:41:47.290864',
    'text_array': [
    'd5f49bdbf9ef46e1b8a134552a320cab',
    '524a8e0439fe4875bbd009a6632bc2cf',
],
    'words': 'butterfly goat',
    'nested': {
    'id': 102,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'deer',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fox',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'cat',
    'rabbit',
],
    'city': {
    'name': 'Kharkiv',
    'geo': {
    'lat': 49.980812,
    'lon': 36.25272,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'frog',
    'maybe_null': None,
},
},
    {
    'id': 3,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 103,
    'id_str': [
    '04',
],
    'text_data': '3ce9e1e123c145eabff912137fd7b212',
    'rand_digit': 3,
    'rand_number': 0.62003,
    'rand_signed_int': -2,
    'rand_datetime': '2000-09-14 03:20:57',
    'text_array': [
    'de29a1e301e242d49b24ffd674e6d6bc',
    'c884a155d444494396a4d955fae423b5',
],
    'words': 'camel bee',
    'nested': {
    'id': 103,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ant',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ladybug',
    'cat',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
},
},
    {
    'id': 4,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 104,
    'id_str': [
    '18',
    '30',
    '08',
],
    'text_data': 'b9443bdc8ac848d6bd3018ecf9a95a91',
    'rand_digit': 6,
    'rand_number': 0.0238,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-03T10:49:16-0200',
    'text_array': [
    '22fddf51fe38473ca391075ae7f9859e',
    '51ccc24f163e4f7984122f77acfdd863',
],
    'words': 'fly cat',
    'nested': {
    'id': 104,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'ladybug',
    'octopus',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'panda',
},
},
    {
    'id': 5,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 105,
    'id_str': [
    '08',
    '13',
    '18',
],
    'text_data': 'cd5ce454d6574befb13440ca0b25f988',
    'rand_digit': 9,
    'rand_number': 0.62048,
    'rand_signed_int': -7,
    'rand_datetime': '2000-06-14T22:13:02.278953',
    'text_array': [
    'ca00444a794642ac8f1d435eb97237d2',
    'd07e3e510e20445eaedd3a38389337c8',
],
    'words': 'lion wolf',
    'nested': {
    'id': 105,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'whale',
    'dragonfly',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
    'maybe_null': None,
},
},
    {
    'id': 6,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 106,
    'id_str': [
    '03',
    '29',
    '27',
    '29',
    '27',
],
    'text_data': '3f9f9bfd5a8a420790b37219a20a64ed',
    'rand_digit': 9,
    'rand_number': 0.03459,
    'rand_signed_int': 3,
    'rand_datetime': '2000-12-12T06:46:45.602000+05:00',
    'text_array': [
    '14d6dc82ddc0469480b2e3398ce3c8a8',
    '4b64ec1953b54da2baa93d4cbd5c4f1a',
],
    'words': 'turtle ape',
    'nested': {
    'id': 106,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 8,
},
],
},
    'nested_array': [
    [
    -7,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    4,
],
],
    'two_words': [
    'bee',
    'duck',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': [
    84,
],
    'rand_bool': False,
    'mixed_type': 5,
    'maybe_null': None,
},
},
    {
    'id': 7,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 107,
    'id_str': [
    '08',
    '14',
    '23',
],
    'text_data': '9e22f4a0870f4bfcb37cf8ea03c407ea',
    'rand_digit': 6,
    'rand_number': 0.59867,
    'rand_signed_int': -5,
    'rand_datetime': '2000-11-07 12:58:56.045121',
    'text_array': [
    '3a7fc9424d134df0993eba5d767767c2',
    '50b5fdfb9db34206a244de01acaf2c16',
],
    'words': 'grasshopper duck',
    'nested': {
    'id': 107,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'kangaroo',
    'deer',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 0,
    'maybe': 'rhino',
    'maybe_null': None,
},
},
    {
    'id': 8,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 108,
    'id_str': [
    '12',
    '16',
    '02',
    '15',
],
    'text_data': 'fa2ef03ad726442fa5ec4449cf4aac29',
    'rand_digit': 5,
    'rand_number': 0.00088,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-31T18:33:50.316529-0800',
    'text_array': [
    '100be903485f44d790d9d45bccc51ab9',
    'f758e7be65844a4fa0fa788f6591f520',
],
    'words': 'frog fish',
    'nested': {
    'id': 108,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'cow',
    'gorilla',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'scorpion',
},
},
    {
    'id': 9,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 109,
    'id_str': [
    '17',
    '11',
    '03',
    '16',
],
    'text_data': 'dae31a20f05c486ca70f9e3c778a0e24',
    'rand_digit': 3,
    'rand_number': 0.01305,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-22 08:12',
    'text_array': [
    '838e0ff490f94292aa5ff6e2afd79423',
    'be16994bb03f4412a744b934d353b2c7',
],
    'words': 'bird deer',
    'nested': {
    'id': 109,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snake',
    'cow',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': [
    54,
],
    'rand_bool': False,
    'mixed_type': 5,
},
},
    {
    'id': 10,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 110,
    'id_str': [
    '16',
],
    'text_data': '7c9de9fdcf0c42a690542a5b4bebd187',
    'rand_digit': 4,
    'rand_number': 0.51453,
    'rand_signed_int': 8,
    'rand_datetime': '2000-09-26 03:06',
    'text_array': [
    '8a487b6131fb4a4085566055a4adc439',
    '027137c97aaf499d906dfd0a6e3e76d8',
],
    'words': 'cheetah bird',
    'nested': {
    'id': 110,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bird',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fox',
    'cow',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'crab',
},
},
    {
    'id': 11,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 111,
    'id_str': [
    '01',
    '17',
    '06',
    '20',
    '07',
],
    'text_data': 'c6f4a70039e24d8aa517888e67b8c2e5',
    'rand_digit': 0,
    'rand_number': 0.59741,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-26 01:23',
    'text_array': [
    'd21e75b8e53843a7a67bfd8e8a9eacca',
    'b61a053a366a4e588ce98a243719c5e5',
],
    'words': 'cheetah spider',
    'nested': {
    'id': 111,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'lizard',
    'cow',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'bear',
    'maybe_null': 'squid',
},
},
    {
    'id': 12,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 112,
    'id_str': [
    '07',
    '12',
    '15',
    '16',
    '01',
],
    'text_data': 'd76de6da85ee45069eefa05962a7a903',
    'rand_digit': 8,
    'rand_number': 0.04639,
    'rand_signed_int': -6,
    'rand_datetime': '2000-05-10T16:08:19.583086-12:00',
    'text_array': [
    'da87d5088d374c0b8444f1404c06a311',
    '697ab783f0594feca8fe4e7709e5fa8f',
],
    'words': 'dog ape',
    'nested': {
    'id': 112,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 3,
},
],
},
    'nested_array': [
    [
    6,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'ant',
    'bee',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 3,
    'maybe_null': None,
},
},
    {
    'id': 13,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 113,
    'id_str': [
    '08',
    '16',
    '21',
    '25',
],
    'text_data': '64ab5f41af4f4de19ea9230d2894dba5',
    'rand_digit': 8,
    'rand_number': 0.09389,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-14T16:11:02.718987',
    'text_array': [
    'f82c9a328bcb44e8991bb958cbce2a8d',
    '01bfe758c81343e2969b272c7f9e2f6d',
],
    'words': 'panda dog',
    'nested': {
    'id': 113,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'wolf',
    'snake',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': [
    83,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'turtle',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 14,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 114,
    'id_str': [
    '09',
],
    'text_data': '38de5715ade04717a5326de48d4f24b6',
    'rand_digit': 3,
    'rand_number': 0.98537,
    'rand_signed_int': -7,
    'rand_datetime': '2000-04-29 09:54',
    'text_array': [
    '43eb3b29b72b42ab977e1a76b6aa3908',
    'ed9c11e41de04d28856f1dbefb654a6f',
],
    'words': 'sloth wolf',
    'nested': {
    'id': 114,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'squid',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bear',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'dragonfly',
    'hyena',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
},
},
    {
    'id': 15,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 115,
    'id_str': [
    '16',
    '09',
    '24',
],
    'text_data': '71b8e8893d2440b6ab9442e5294f6ef9',
    'rand_digit': 0,
    'rand_number': 0.96851,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-15T06:37:15-0500',
    'text_array': [
    '259ed32c52c84eb88c49df28bb57a25c',
    '8fa08bdf9f774cbaaa98db3c9348dc67',
],
    'words': 'panda gorilla',
    'nested': {
    'id': 115,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    7,
],
    [
    5,
],
],
    'two_words': [
    'bee',
    'spider',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'sheep',
},
},
    {
    'id': 16,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 116,
    'id_str': [
],
    'text_data': 'f2203cc4f33a46d5a212042cf4844017',
    'rand_digit': 9,
    'rand_number': 0.23698,
    'rand_signed_int': 10,
    'rand_datetime': '2000-11-01',
    'text_array': [
    'de4e29e223d846698f0d7ca1ab656fa8',
    '2819893667d242a6a5c4c06802f4a7c3',
],
    'words': 'giraffe pig',
    'nested': {
    'id': 116,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'turtle',
    'hyena',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'camel',
},
},
    {
    'id': 17,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 117,
    'id_str': [
],
    'text_data': '1d4afeaf4b7e428f9947bc16af3a021e',
    'rand_digit': 3,
    'rand_number': 0.17602,
    'rand_signed_int': 10,
    'rand_datetime': '2000-11-04T22:19:56',
    'text_array': [
    '4087e2849a40492f89a86f00b543494c',
    '86bff1e30fd44bd6952f4c32d08a1222',
],
    'words': 'shark sheep',
    'nested': {
    'id': 117,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snail',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'giraffe',
    'rabbit',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'ant',
    'maybe_null': 'mosquito',
},
},
    {
    'id': 18,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 118,
    'id_str': [
    '08',
    '21',
    '17',
],
    'text_data': 'ed7ee3eabdaf4386b78f4d8b23c7748d',
    'rand_digit': 2,
    'rand_number': 0.90725,
    'rand_signed_int': -3,
    'rand_datetime': '2000-01-21',
    'text_array': [
    '96b0caabcca54fdbaf0cceff038606b0',
    '18aa30f7b3f14c02a0b442f7e4564242',
],
    'words': 'cheetah giraffe',
    'nested': {
    'id': 118,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fox',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'koala',
    'camel',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'koala',
    'maybe_null': None,
},
},
    {
    'id': 19,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 119,
    'id_str': [
    '13',
    '08',
    '27',
],
    'text_data': '8a5069e7533143e996ec4f1d4c0c95d2',
    'rand_digit': 4,
    'rand_number': 0.11822,
    'rand_signed_int': 8,
    'rand_datetime': '2000-06-09T12:35:33',
    'text_array': [
    '484c96f27d064844bfd59ef35911ccd2',
    '6eb3e1498b064d458c7ef52b3709d301',
],
    'words': 'shark mouse',
    'nested': {
    'id': 119,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'goat',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cheetah',
    'goat',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': [
    3,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'bee',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 20,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 120,
    'id_str': [
    '23',
],
    'text_data': '7da3f3bd267d4943ac706d1cec0dd912',
    'rand_digit': 6,
    'rand_number': 0.56854,
    'rand_signed_int': 7,
    'rand_datetime': '2000-07-02',
    'text_array': [
    '89dd7d0771a2427bb3971d31822f6700',
    '22246ac85b784b4a867fe640e1dd4c70',
],
    'words': 'fox lobster',
    'nested': {
    'id': 120,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'lion',
    'elephant',
],
    'city': {
    'name': 'Johannesburg',
    'geo': {
    'lat': -26.204103,
    'lon': 28.047305,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'frog',
},
},
    {
    'id': 21,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 121,
    'id_str': [
    '13',
    '26',
    '03',
],
    'text_data': '15876a9b6523473db18f8f3ca8d4de80',
    'rand_digit': 3,
    'rand_number': 0.16058,
    'rand_signed_int': 4,
    'rand_datetime': '2000-07-26T19:45:26-0300',
    'text_array': [
    'f69256591aae47669ad7f80bb1189ed7',
    '0b01b09de1544179ae927affcd5047f9',
],
    'words': 'bee dog',
    'nested': {
    'id': 121,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'chicken',
    'rabbit',
],
    'city': {
    'name': 'Riga',
    'geo': {
    'lat': 56.949649,
    'lon': 24.105186,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 3,
    'maybe': 'scorpion',
},
},
    {
    'id': 22,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 122,
    'id_str': [
    '20',
    '21',
    '04',
],
    'text_data': '47f54b6b19f74351981c41cc7680154c',
    'rand_digit': 5,
    'rand_number': 0.56157,
    'rand_signed_int': -8,
    'rand_datetime': '2000-05-09 08:17:38.899570+0400',
    'text_array': [
    '1cc19d3dad1547f58dd500f0904a0216',
    'b57561e2426b40e784c6952e21fa07fe',
],
    'words': 'dolphin rabbit',
    'nested': {
    'id': 122,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'crab',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'hippo',
    'fox',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'cat',
    'maybe_null': 'grasshopper',
},
},
    {
    'id': 23,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 123,
    'id_str': [
],
    'text_data': 'eb854b3391ec4b8b89898c54851337b4',
    'rand_digit': 4,
    'rand_number': 0.93356,
    'rand_signed_int': 9,
    'rand_datetime': '2000-07-10 21:42:54.122710',
    'text_array': [
    '69517bfee82c428e814f3e1d6c44bf58',
    'da855b0375274fcebc57f370b6733e21',
],
    'words': 'goat fish',
    'nested': {
    'id': 123,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'goat',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'jaguar',
    'fish',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.90941,
    'maybe': 'mouse',
    'maybe_null': 'wolf',
},
},
    {
    'id': 24,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 124,
    'id_str': [
    '01',
],
    'text_data': '338049ef53c7431fb47bc24ecae33fdc',
    'rand_digit': 2,
    'rand_number': 0.98775,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-05 18:29:45.449264',
    'text_array': [
    '2e0174c441bf4cceb1dabc0335d41de8',
    '9f2536f1a54b49018312ec4bc3532d9f',
],
    'words': 'mouse scorpion',
    'nested': {
    'id': 124,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'deer',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'zebra',
},
},
    {
    'id': 25,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 125,
    'id_str': [
    '21',
],
    'text_data': 'dddbee0e1b8d4dbf84761e4ffd566e89',
    'rand_digit': 2,
    'rand_number': 0.67172,
    'rand_signed_int': 5,
    'rand_datetime': '2000-03-02',
    'text_array': [
    '9f4d12434e9c48d9bb6d488b88d70080',
    '2370d907334b4688a076697b07113095',
],
    'words': 'deer panda',
    'nested': {
    'id': 125,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'horse',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 8,
},
],
},
    'nested_array': [
    [
    4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'horse',
    'fly',
],
    'city': {
    'name': 'Kharkiv',
    'geo': {
    'lat': 49.980812,
    'lon': 36.25272,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'dragonfly',
},
},
    {
    'id': 26,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 126,
    'id_str': [
],
    'text_data': 'ec28cbfbd1654361989376a0ceeb0d57',
    'rand_digit': 2,
    'rand_number': 0.37157,
    'rand_signed_int': 10,
    'rand_datetime': '2000-03-07 13:15:41.566609',
    'text_array': [
    'a9daabace052447a82bc7932ab66fa0d',
    '3c0f165515e749148a7cf9ac56c72c76',
],
    'words': 'whale dog',
    'nested': {
    'id': 126,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'sloth',
    'hippo',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'deer',
    'maybe_null': 'fly',
},
},
    {
    'id': 27,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 127,
    'id_str': [
    '11',
],
    'text_data': '5d27c76aa116445ab19cab450b6df14a',
    'rand_digit': 5,
    'rand_number': 0.00801,
    'rand_signed_int': 1,
    'rand_datetime': '2000-05-17T01:03:06.135607',
    'text_array': [
    'b334da0ec05e4882ae9f5e095f7fa5b2',
    'd992c2e2a60e474b8aba98e8b2bae555',
],
    'words': 'leopard bear',
    'nested': {
    'id': 127,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -10,
],
],
    'two_words': [
    'jaguar',
    'lion',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': [
    11,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 28,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 128,
    'id_str': [
    '20',
],
    'text_data': 'c28eece3b464474ca52537113dfcbe16',
    'rand_digit': 9,
    'rand_number': 0.86406,
    'rand_signed_int': -10,
    'rand_datetime': '2000-04-17 08:29:31+0300',
    'text_array': [
    '5f7b505634754975bb203e4109400875',
    'b847816c460e424fb51ae22514c4c093',
],
    'words': 'tiger butterfly',
    'nested': {
    'id': 128,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    0,
],
],
    'two_words': [
    'sheep',
    'duck',
],
    'city': {
    'name': 'Frankfurt',
    'geo': {
    'lat': 50.110922,
    'lon': 8.682127,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'ladybug',
},
},
    {
    'id': 29,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 129,
    'id_str': [
],
    'text_data': '216461cbd0174972b64e14f106e427fb',
    'rand_digit': 4,
    'rand_number': 0.94521,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-21T14:11:19+0200',
    'text_array': [
    '6203ce655cd54e049f26d60c7065559c',
    'dc887bfd33984f30bfa397ea9d7d51e7',
],
    'words': 'butterfly bear',
    'nested': {
    'id': 129,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fly',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'horse',
    'bee',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.97877,
    'maybe_null': None,
},
},
    {
    'id': 30,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 130,
    'id_str': [
],
    'text_data': '1e0e180f11104b7297a2f7d72345e148',
    'rand_digit': 2,
    'rand_number': 0.11233,
    'rand_signed_int': 9,
    'rand_datetime': '2000-05-15 15:20:06+0700',
    'text_array': [
    'e94a7b761c1046e9bdd6538ffdd9491e',
    'c84dcd77b67442b48d1ee909d92168b7',
],
    'words': 'ant sloth',
    'nested': {
    'id': 130,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fish',
    'cheetah',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'sloth',
    'maybe': 'pig',
    'maybe_null': 'bee',
},
},
    {
    'id': 31,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 131,
    'id_str': [
],
    'text_data': '8dcf6dba0e8d451ea20ceb5769d0c15d',
    'rand_digit': 4,
    'rand_number': 0.80651,
    'rand_signed_int': 2,
    'rand_datetime': '2000-06-25 12:08:01.858535-0400',
    'text_array': [
    '279a7b72091b43b1af43c0dc40ce8f37',
    '31442376eecb4ea6bbbde9b0dcf76e54',
],
    'words': 'lizard elephant',
    'nested': {
    'id': 131,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ape',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'dolphin',
    'tiger',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 1,
    'maybe_null': None,
},
},
    {
    'id': 32,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 132,
    'id_str': [
],
    'text_data': 'b4e258839afc4b139faecc3e8aa769e2',
    'rand_digit': 4,
    'rand_number': 0.11852,
    'rand_signed_int': -4,
    'rand_datetime': '2000-02-28 16:27:24',
    'text_array': [
    '28023c5a8af44470ac34044b1ec7700d',
    'b49893229dc34c2ab352d3d9ae5a3e1a',
],
    'words': 'squid grasshopper',
    'nested': {
    'id': 132,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'frog',
    'octopus',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': [
    9,
],
    'rand_bool': False,
    'mixed_type': 'sheep',
    'maybe': 'dolphin',
},
},
    {
    'id': 33,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 133,
    'id_str': [
    '20',
    '17',
],
    'text_data': '945e109c3d974cdaa67c6ed0d55baa4a',
    'rand_digit': 4,
    'rand_number': 0.51922,
    'rand_signed_int': 7,
    'rand_datetime': '2000-09-20T22:35:18-0800',
    'text_array': [
    'd28486935197488cbbc5bea9539a5ed9',
    'bb7a49cd171e42a5a409f7ecf3504df8',
],
    'words': 'leopard butterfly',
    'nested': {
    'id': 133,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'bear',
    'spider',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'hippo',
    'maybe_null': None,
},
},
    {
    'id': 34,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 134,
    'id_str': [
    '27',
    '17',
    '02',
],
    'text_data': '4eb654edede4475caec77596297ebe95',
    'rand_digit': 8,
    'rand_number': 0.76886,
    'rand_signed_int': 3,
    'rand_datetime': '2000-05-23T13:49:29.447848',
    'text_array': [
    'ee70486fe5764093bfe07c82e722d40a',
    '4b94a4b7769c47f09628bb5ca8600ef9',
],
    'words': 'ant scorpion',
    'nested': {
    'id': 134,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'fox',
    'fox',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 3,
    'maybe': 'butterfly',
    'maybe_null': 'tiger',
},
},
    {
    'id': 35,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 135,
    'id_str': [
],
    'text_data': 'ab572108c19b4fd38999d7f86ed0143a',
    'rand_digit': 4,
    'rand_number': 0.22759,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-08T11:07:55',
    'text_array': [
    '5b005a1bfb984125adad5d19e763e594',
    '426ad1b5aa7447e4a0b29d140fc4e87d',
],
    'words': 'lion spider',
    'nested': {
    'id': 135,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ant',
    'tiger',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 36,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 136,
    'id_str': [
    '18',
],
    'text_data': 'daefaeea387645b199c606e3df72b3c9',
    'rand_digit': 4,
    'rand_number': 0.51723,
    'rand_signed_int': -10,
    'rand_datetime': '2000-11-30 07:56:56-1000',
    'text_array': [
    '19b1a2c4b987492b8e38f385aeb07d7e',
    'a2fb5a25f9464bae943eb5d853ddadea',
],
    'words': 'mosquito goat',
    'nested': {
    'id': 136,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    2,
],
    [
],
],
    'two_words': [
    'cat',
    'bird',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 2,
    'maybe_null': 'panda',
},
},
    {
    'id': 37,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 137,
    'id_str': [
    '07',
    '18',
],
    'text_data': 'bf7b5cd5942e49a8904daed8684d5e9e',
    'rand_digit': 8,
    'rand_number': 0.70473,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-21 04:56:27.698282+0300',
    'text_array': [
    '1dc5963b97fe4b348d1c5cb9a1ee5c08',
    '4304d7fc3bf84a6299e83d3c2c64765f',
],
    'words': 'lizard turtle',
    'nested': {
    'id': 137,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'camel',
    'koala',
],
    'city': {
    'name': 'Cardiff',
    'geo': {
    'lat': 51.481581,
    'lon': -3.17909,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
},
},
    {
    'id': 38,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 138,
    'id_str': [
    '05',
],
    'text_data': 'fc742e2d3f1842d9bd9fe69ad20c385b',
    'rand_digit': 8,
    'rand_number': 0.81532,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-03T03:12:08.976865+05:00',
    'text_array': [
    'df1d7dfe2fb24b209e35e5c8546f1d5d',
    '6278c5aa07c04747919efe2e35ae56fc',
],
    'words': 'camel hippo',
    'nested': {
    'id': 138,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -3,
],
],
    'two_words': [
    'frog',
    'snail',
],
    'city': {
    'name': 'Athens',
    'geo': {
    'lat': 37.98381,
    'lon': 23.727539,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 39,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 139,
    'id_str': [
    '27',
    '03',
    '06',
    '10',
    '06',
],
    'text_data': '95f8ad71dea34de8910557a0c938bde4',
    'rand_digit': 0,
    'rand_number': 0.62736,
    'rand_signed_int': 9,
    'rand_datetime': '2000-10-30T07:51:29.454346-09:00',
    'text_array': [
    '7a02c0a058c9472ca1769919c655ba27',
    '689e7860faad43c49b331fb27ad69480',
],
    'words': 'leopard panda',
    'nested': {
    'id': 139,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'lion',
    'lobster',
],
    'city': {
    'name': 'Johannesburg',
    'geo': {
    'lat': -26.204103,
    'lon': 28.047305,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'giraffe',
},
},
    {
    'id': 40,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 140,
    'id_str': [
    '10',
    '29',
    '05',
],
    'text_data': '7fbf131db0574f669036d75af73de222',
    'rand_digit': 1,
    'rand_number': 0.71883,
    'rand_signed_int': -6,
    'rand_datetime': '2000-02-27 22:55:59+0200',
    'text_array': [
    '33958609f1164e4a9cfe6498c314ce02',
    'b392a2d99faf49a6ad84668cc76202f1',
],
    'words': 'lobster ladybug',
    'nested': {
    'id': 140,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'pig',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    [
    -3,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'butterfly',
    'mouse',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'duck',
    'maybe_null': 'ant',
},
},
    {
    'id': 41,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 141,
    'id_str': [
    '22',
],
    'text_data': '33a2054985c746329891add061bd5f50',
    'rand_digit': 2,
    'rand_number': 0.80828,
    'rand_signed_int': 7,
    'rand_datetime': '2000-11-29 14:23:01-0600',
    'text_array': [
    '9e61f59064184feba5f19407990009ea',
    '3153130a4b574d5d831306995a00a318',
],
    'words': 'frog chicken',
    'nested': {
    'id': 141,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    [
    -5,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    7,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'snake',
    'deer',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 42,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 142,
    'id_str': [
    '28',
    '17',
    '29',
    '07',
],
    'text_data': 'caa8da48f656443ab2e71c8a8034025f',
    'rand_digit': 8,
    'rand_number': 0.7249,
    'rand_signed_int': 0,
    'rand_datetime': '2000-09-19T16:09:40.663486+0100',
    'text_array': [
    'f5ca9ce24707457a8a2331ae134b7198',
    'ca14c532548c40d998a2dcc890f333ec',
],
    'words': 'ape gorilla',
    'nested': {
    'id': 142,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'butterfly',
    'koala',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.53871,
    'maybe': 'panda',
    'maybe_null': 'elephant',
},
},
    {
    'id': 43,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 143,
    'id_str': [
    '22',
],
    'text_data': '0de224a984d04e18ba0130012a8c067a',
    'rand_digit': 6,
    'rand_number': 0.11747,
    'rand_signed_int': -4,
    'rand_datetime': '2000-09-10T06:26:44.989166+0800',
    'text_array': [
    'e615a1fb6f8c44c9927a959b9e71c3e5',
    'b80994772ffe4c05a7435783ec1e4dac',
],
    'words': 'zebra rabbit',
    'nested': {
    'id': 143,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fox',
    'dragonfly',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'turtle',
},
},
    {
    'id': 44,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 144,
    'id_str': [
    '11',
    '27',
],
    'text_data': '8bfc631a51b24beaa444e2e595971951',
    'rand_digit': 3,
    'rand_number': 0.72914,
    'rand_signed_int': 7,
    'rand_datetime': '2000-05-03T10:43:31.110617-12:00',
    'text_array': [
    '9a87a38a6560400d95365c3890c577e7',
    '4b5ac368a4fe4e818d4b44b27feedf0a',
],
    'words': 'zebra fox',
    'nested': {
    'id': 144,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    1,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'mosquito',
    'sloth',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 45,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 145,
    'id_str': [
],
    'text_data': '5bf09f0fe9b2434398874a4cda39859d',
    'rand_digit': 2,
    'rand_number': 0.07296,
    'rand_signed_int': -2,
    'rand_datetime': '2000-03-07T16:58:37+0600',
    'text_array': [
    '92ba91d4992d4341b17c9cab63e4efa4',
    'c52c21dab9ee4843b16741ba256c2808',
],
    'words': 'elephant crab',
    'nested': {
    'id': 145,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'bird',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': [
    45,
],
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'dolphin',
},
},
    {
    'id': 46,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 146,
    'id_str': [
    '19',
],
    'text_data': '1c844983b66e4829b633c43fe583dc46',
    'rand_digit': 6,
    'rand_number': 0.66187,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-15T08:25:17-0200',
    'text_array': [
    '2791cde3720f4b3094730d4cd6e0b121',
    '017f01e485c74644ad335425498afcad',
],
    'words': 'snail lizard',
    'nested': {
    'id': 146,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'horse',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ant',
    'elephant',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.05611,
    'maybe': 'horse',
    'maybe_null': 'octopus',
},
},
    {
    'id': 47,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 147,
    'id_str': [
    '17',
],
    'text_data': '4515adbb94fe4c02aea5711c84989283',
    'rand_digit': 6,
    'rand_number': 0.29274,
    'rand_signed_int': -10,
    'rand_datetime': '2000-11-25',
    'text_array': [
    '0b7f03a4e29b4d70a27457e05bf9e30e',
    'acf98e09f53f480d8c9233e5745d0a4d',
],
    'words': 'lion cat',
    'nested': {
    'id': 147,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'pig',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'cat',
    'squid',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 48,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 148,
    'id_str': [
    '25',
    '07',
    '02',
],
    'text_data': 'f2bb876bd75c4e9792203b54eaccb032',
    'rand_digit': 5,
    'rand_number': 0.57446,
    'rand_signed_int': -3,
    'rand_datetime': '2000-08-23T22:26:02+1000',
    'text_array': [
    '3a0ad89e724647128bcb30a34615258b',
    '59dadbf485ea4a04aed7b36da7fbbc4a',
],
    'words': 'crab giraffe',
    'nested': {
    'id': 148,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cow',
    'crab',
],
    'city': {
    'name': 'Cardiff',
    'geo': {
    'lat': 51.481581,
    'lon': -3.17909,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'fox',
    'maybe_null': 'dolphin',
},
},
    {
    'id': 49,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 149,
    'id_str': [
    '05',
    '08',
    '25',
    '17',
    '19',
],
    'text_data': '065661170dc7402e92583d49708a2ffb',
    'rand_digit': 6,
    'rand_number': 0.58146,
    'rand_signed_int': -1,
    'rand_datetime': '2000-04-20',
    'text_array': [
    '2c4695062c984b8fb84aedcd9838637b',
    'a75be2c159114e03baa8ed948be29279',
],
    'words': 'sloth octopus',
    'nested': {
    'id': 149,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'cheetah',
    'lion',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': [
    18,
],
    'rand_bool': True,
    'mixed_type': 'scorpion',
    'maybe_null': 'pig',
},
},
    {
    'id': 50,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 150,
    'id_str': [
    '26',
],
    'text_data': 'c50532594b64457aa57976af2a2226c7',
    'rand_digit': 6,
    'rand_number': 0.81193,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-06 10:36',
    'text_array': [
    '13945ede683d4418baf781219f4e11c1',
    '6381a3b1ece6493b8b52b3f879e7bbe6',
],
    'words': 'cheetah sheep',
    'nested': {
    'id': 150,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'spider',
    'bee',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'pig',
    'maybe_null': 'crab',
},
},
    {
    'id': 51,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 151,
    'id_str': [
    '29',
    '08',
    '26',
],
    'text_data': '58635a1a9be947a4b0dbd51ca0cab959',
    'rand_digit': 8,
    'rand_number': 0.28818,
    'rand_signed_int': 4,
    'rand_datetime': '2000-06-15 13:51:10',
    'text_array': [
    'b95ebb013e7a414094296d207d5bd424',
    '691f4383fe184e44b555c502f55fb60e',
],
    'words': 'cheetah ladybug',
    'nested': {
    'id': 151,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'mouse',
    'cheetah',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 'turtle',
    'maybe_null': 'deer',
},
},
    {
    'id': 52,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 152,
    'id_str': [
    '02',
    '09',
    '27',
],
    'text_data': '8a03fcd612ac4a0aac5ffb2fa2e73326',
    'rand_digit': 7,
    'rand_number': 0.21009,
    'rand_signed_int': -5,
    'rand_datetime': '2000-02-20T17:24:37.363980',
    'text_array': [
    '5226f1310d284ea697001eb01246fe5d',
    '7f3a4b2ee6854d05ab3ff5de482987cc',
],
    'words': 'octopus wolf',
    'nested': {
    'id': 152,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bee',
    'rabbit',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'rhino',
},
},
    {
    'id': 53,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 153,
    'id_str': [
    '09',
    '08',
    '27',
    '27',
    '23',
],
    'text_data': '4fdc5e37eb9e46069889a7643043d61c',
    'rand_digit': 0,
    'rand_number': 0.07998,
    'rand_signed_int': 8,
    'rand_datetime': '2000-11-22 18:08:49.789286',
    'text_array': [
    '4deaf61e7d04403e9f785e8f2e38f1ed',
    '09f25444cb7946148df4a6f0af8db4e2',
],
    'words': 'squid rabbit',
    'nested': {
    'id': 153,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'dolphin',
    'whale',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'fox',
},
},
    {
    'id': 54,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 154,
    'id_str': [
    '03',
    '26',
],
    'text_data': 'e08f31b8b453413cacd3fa0c045d0b0d',
    'rand_digit': 4,
    'rand_number': 0.43848,
    'rand_signed_int': 6,
    'rand_datetime': '2000-05-10 03:30:58.684671-0200',
    'text_array': [
    'fea4ad8715cf4531a4ff1faf75bbfb37',
    '98c9289df171489fa70eb46267950016',
],
    'words': 'sloth fox',
    'nested': {
    'id': 154,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'mosquito',
    'butterfly',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'rabbit',
    'maybe_null': None,
},
},
    {
    'id': 55,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 155,
    'id_str': [
    '04',
],
    'text_data': 'd04cbe4f52504ba7858572ccdea79376',
    'rand_digit': 1,
    'rand_number': 0.75783,
    'rand_signed_int': -7,
    'rand_datetime': '2000-04-27 11:25:13',
    'text_array': [
    '92a91d10324d49559dc6c3f541c5ac34',
    '20c4ab9ce81c4f898bc9ae83be98fc6c',
],
    'words': 'turtle crab',
    'nested': {
    'id': 155,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 8,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,2__',
    'two_words': [
    'hyena',
    'duck',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'snake',
    'maybe': 'fox',
    'maybe_null': 'fox',
},
},
    {
    'id': 56,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 156,
    'id_str': [
    '23',
],
    'text_data': '9a12ce5055374b11bc81edb606d41e21',
    'rand_digit': 7,
    'rand_number': 0.81023,
    'rand_signed_int': 0,
    'rand_datetime': '2000-11-07 01:48:00',
    'text_array': [
    '1fcc737bfb1040dd98e4492bef0d4fc7',
    '6f51bd06d0614561bf8043bf516883ee',
],
    'words': 'lobster sloth',
    'nested': {
    'id': 156,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 4,
},
],
},
    'nested_array': [
    [
    7,
],
],
    'two_words': [
    'crab',
    'dragonfly',
],
    'city': {
    'name': 'Seoul',
    'geo': {
    'lat': 37.566535,
    'lon': 126.977969,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 'rhino',
    'maybe_null': 'bear',
},
},
    {
    'id': 57,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 157,
    'id_str': [
],
    'text_data': 'edf4119c1fa0442ab23f5b0e2dd9f275',
    'rand_digit': 2,
    'rand_number': 0.89303,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-23T17:59:00.153893',
    'text_array': [
    'cbe7d7a2080a4e9187f807261f1fb6f2',
    '503b2eb07bac479caa49abf5becd984b',
],
    'words': 'horse jaguar',
    'nested': {
    'id': 157,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    10,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'cat',
    'dragonfly',
],
    'city': {
    'name': 'Moscow',
    'geo': {
    'lat': 55.755826,
    'lon': 37.6173,
},
},
    'rand_tuple': [
    99,
],
    'rand_bool': False,
    'mixed_type': False,
},
},
    {
    'id': 58,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 158,
    'id_str': [
    '03',
    '25',
    '07',
    '14',
    '18',
],
    'text_data': '2e24a7beaa0c4dd6a4bfaa2f15970be6',
    'rand_digit': 6,
    'rand_number': 0.38864,
    'rand_signed_int': -7,
    'rand_datetime': '2000-03-15 09:51:11+0300',
    'text_array': [
    '022a16ac9b394137993cf1cd23054a90',
    'be640cc8334c4cfaa71dc2c7b560041e',
],
    'words': 'fly ape',
    'nested': {
    'id': 158,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'turtle',
    'goat',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'squid',
    'maybe_null': 'pig',
},
},
    {
    'id': 59,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 159,
    'id_str': [
    '24',
    '09',
    '22',
    '14',
],
    'text_data': '4b4425fcaf2342929d046856b8b57c76',
    'rand_digit': 4,
    'rand_number': 0.1182,
    'rand_signed_int': -4,
    'rand_datetime': '2000-03-03 11:59:57',
    'text_array': [
    'bfd22ed4be3a4fd2adf3ac9b94441227',
    'd91c913b67f84f3aafc50f9c1923d303',
],
    'words': 'zebra kangaroo',
    'nested': {
    'id': 159,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'ape',
    'wolf',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'deer',
},
},
    {
    'id': 60,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 160,
    'id_str': [
    '03',
    '10',
    '20',
    '12',
    '05',
],
    'text_data': 'cbc091f691774182abbae551dcc6f09f',
    'rand_digit': 4,
    'rand_number': 0.57546,
    'rand_signed_int': 7,
    'rand_datetime': '2000-11-02 16:53:06+0200',
    'text_array': [
    '08a9333789b448e08b44e972f785d53e',
    'b52648ebd54d4e8d98aacdfcad70c4c7',
],
    'words': 'scorpion jaguar',
    'nested': {
    'id': 160,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bee',
    'lion',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 'sheep',
    'maybe_null': 'mosquito',
},
},
    {
    'id': 61,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 161,
    'id_str': [
    '01',
    '24',
],
    'text_data': 'd7f62ca40e4d46ddbc3c1dfe57bdebfa',
    'rand_digit': 9,
    'rand_number': 0.55723,
    'rand_signed_int': -6,
    'rand_datetime': '2000-12-31T08:11:42.400641',
    'text_array': [
    'b4600fcaeb574707ac8834ea267d164d',
    '3a180778cfad40818e4c96826729d1a8',
],
    'words': 'butterfly goat',
    'nested': {
    'id': 161,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'dog',
    'turtle',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'mosquito',
    'maybe_null': 'tiger',
},
},
    {
    'id': 62,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 162,
    'id_str': [
    '11',
],
    'text_data': '242af4f5834c4361afb590cff148c000',
    'rand_digit': 5,
    'rand_number': 0.48131,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-30 23:28',
    'text_array': [
    'b8b145bc0b0c46e7a17c8579eaa54639',
    '60a643a7998d4dfd833ac7ea46a302f6',
],
    'words': 'butterfly duck',
    'nested': {
    'id': 162,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'horse',
    'fox',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cat',
},
},
    {
    'id': 63,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 163,
    'id_str': [
    '11',
    '30',
    '27',
    '07',
    '18',
],
    'text_data': 'da3b45dfab26456abe679d3929f7e0a6',
    'rand_digit': 7,
    'rand_number': 0.36346,
    'rand_signed_int': 10,
    'rand_datetime': '2000-05-14 01:14:29',
    'text_array': [
    '9bc295f690354102b2b5b238540466d9',
    '032199eb2f8e42f6983f2056a69cdca6',
],
    'words': 'dolphin hyena',
    'nested': {
    'id': 163,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'butterfly',
    'fish',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.13826,
    'maybe_null': None,
},
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



    def test_request_4(self):
        """测试请求 4 - POST http://localhost:6333/collections/congruence_test_collection/points/discover"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/discover")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/discover'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '2029',
}
        
        # 原始请求内容
        original_content = {
    'target': self.mutator.generate_float_array(dimension=100, normalized=True),
    'context': [
],
    'limit': 10,
    'offset': 0,
    'with_payload': True,
    'with_vector': False,
    'using': 'image',
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
        """测试请求 5 - POST http://localhost:6333/collections/congruence_test_collection/points/discover"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/discover")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/discover'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '2045',
}
        
        # 原始请求内容
        original_content = {
    'context': [
    {
    'positive': self.mutator.generate_float_array(dimension=100, normalized=True),
    'negative': 1,
},
],
    'limit': 10,
    'offset': 0,
    'with_payload': True,
    'with_vector': False,
    'using': 'image',
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
        """测试请求 6 - DELETE http://localhost:6333/collections/congruence_test_collection?timeout=60"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://localhost:6333/collections/congruence_test_collection?timeout=60")
        method = 'DELETE'
        url_path = 'http://localhost:6333/collections/congruence_test_collection?timeout=60'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '129',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'text': {
    'size': 50,
    'distance': 'Cosine',
},
    'image': {
    'size': 100,
    'distance': 'Dot',
},
    'code': {
    'size': 80,
    'distance': 'Euclid',
},
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_discovery.test_query_with_nan')
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
        TARGET_URL = args.target.strip()
    if args.output_dir:
        OUTPUT_DIR = args.output_dir
    
    # 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 实例化测试类并运行测试
    test = TestDiscoverytestQueryWithNan()
    test.run_tests()
