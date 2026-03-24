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
logger = logging.getLogger('vdb_fuzzer.test.test_qdrant_client_test_multiple_vectors')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_qdrant_client.test_multiple_vectors"
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


def send_request(content, request_type="PUT", url_path="http://localhost:6333/collections/client_test?timeout=60", custom_headers=None):
    """
    发送请求到目标服务器

    Args:
        content: 请求内容
        request_type: 请求方法，默认为"PUT"
        url_path: URL路径，默认为"http://localhost:6333/collections/client_test?timeout=60"
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



class TestQdrantClienttestMultipleVectors:
    """自动生成的VDB模糊测试类 - test_qdrant_client.test_multiple_vectors"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_qdrant_client.test_multiple_vectors"
        self.test_count = 4  # 测试方法数量
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
        """测试请求 0 - PUT http://localhost:6333/collections/client_test?timeout=60"""
        logger.info(f"跳过非写请求或无内容请求: PUT http://localhost:6333/collections/client_test?timeout=60")
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/client_test?timeout=60'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '91',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'image': {
    'size': 100,
    'distance': 'Dot',
},
    'text': {
    'size': 200,
    'distance': 'Cosine',
},
},
}


        send_request(original_content, method, url_path, headers)
        return True



    def test_request_1(self):
        """测试请求 1 - PUT http://localhost:6333/collections/client_test/points?wait=false"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/client_test/points?wait=false")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/client_test/points?wait=false'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '420070',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 100,
    'id_str': [
    '20',
    '15',
    '10',
],
    'text_data': '254bb434e9bd4546bed793ede312d97c',
    'rand_digit': 3,
    'rand_number': 0.78739,
    'rand_signed_int': -9,
    'rand_datetime': '2001-01-01T08:29:49.694540',
    'text_array': [
    '6a061b6e491247bab3caf6effb138d45',
    '7dbcf7b122d94717b0736a2e643f696d',
],
    'words': 'lobster dog',
    'nested': {
    'id': 100,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    7,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'zebra',
    'turtle',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 1,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 101,
    'id_str': [
    '16',
    '23',
    '09',
    '02',
    '04',
],
    'text_data': '3de1e842114f4bfea7ec5ea7a13d5cb3',
    'rand_digit': 3,
    'rand_number': 0.56896,
    'rand_signed_int': -3,
    'rand_datetime': '2000-04-18T08:27:03.940575+08:00',
    'text_array': [
    '617a61a81fba44beb3c2d1861753a01b',
    '63c188f6b90d41b697cadf3e7d863705',
],
    'words': 'crab cheetah',
    'nested': {
    'id': 101,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'camel',
    'elephant',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 2,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 102,
    'id_str': [
    '08',
    '09',
    '13',
    '26',
    '04',
],
    'text_data': 'c10303a831d74fc2ae802ceeafd92ab0',
    'rand_digit': 9,
    'rand_number': 0.79016,
    'rand_signed_int': -2,
    'rand_datetime': '2000-10-30',
    'text_array': [
    '2b72e0d86f214f79a285af0f7bad6c64',
    '7b5de4add8b44f4e8583a4a766d81b07',
],
    'words': 'chicken grasshopper',
    'nested': {
    'id': 102,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'fish',
    'hippo',
],
    'city': {
    'name': 'Riga',
    'geo': {
    'lat': 56.949649,
    'lon': 24.105186,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'kangaroo',
    'maybe_null': 'butterfly',
},
},
    {
    'id': 3,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 103,
    'id_str': [
],
    'text_data': '6927fb13e4b84081aac4668778a9ffb1',
    'rand_digit': 8,
    'rand_number': 0.09613,
    'rand_signed_int': -2,
    'rand_datetime': '2000-04-27T15:07:33.198844',
    'text_array': [
    'd77b092678404259b0e321a940e5edaf',
    '0d13c2c61a8048099c5312b46a1c18f6',
],
    'words': 'giraffe turtle',
    'nested': {
    'id': 103,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'shark',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 5,
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
    [
    -8,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'shark',
    'cow',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': [
    43,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': None,
},
},
    {
    'id': 4,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 104,
    'id_str': [
],
    'text_data': '310b590b3d564294bdb3683a6b246710',
    'rand_digit': 4,
    'rand_number': 0.88712,
    'rand_signed_int': 6,
    'rand_datetime': '2000-05-09 02:04:13.938842+1000',
    'text_array': [
    '8bcdb087a7664ede8edea28192b73a1c',
    '7bf160a359a8443eb60b18035e858b37',
],
    'words': 'zebra cheetah',
    'nested': {
    'id': 104,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    1,
],
    [
],
],
    'two_words': [
    'rabbit',
    'koala',
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
    'mixed_type': 0.0161,
    'maybe': 'mosquito',
},
},
    {
    'id': 5,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 105,
    'id_str': [
    '24',
    '24',
    '05',
],
    'text_data': 'a3d15d2eb1024f74b5393565a7530b70',
    'rand_digit': 0,
    'rand_number': 0.42875,
    'rand_signed_int': 0,
    'rand_datetime': '2000-07-04 21:19:12.131340',
    'text_array': [
    '25371b653a6b4d9c88ddaba79f507b81',
    '5fa66c6207b148e9b0c38710a42c2a64',
],
    'words': 'ant ape',
    'nested': {
    'id': 105,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
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
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
    -10,
],
    [
    8,
],
],
    'two_words': [
    'grasshopper',
    'hyena',
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
    'mixed_type': True,
    'maybe': 'whale',
    'maybe_null': 'elephant',
},
},
    {
    'id': 6,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 106,
    'id_str': [
    '23',
    '08',
    '15',
    '03',
    '03',
],
    'text_data': '8db640e83a52470086bfa3eae60afba2',
    'rand_digit': 5,
    'rand_number': 0.99239,
    'rand_signed_int': 5,
    'rand_datetime': '2000-06-07T21:53:52.764020',
    'text_array': [
    '6acfd92bbe7347d88457a2165c61cafa',
    'db78b36b4fd747d29c1512955ad38078',
],
    'words': 'spider chicken',
    'nested': {
    'id': 106,
    'rand_digit': 6,
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
],
    'word': 'tiger',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -2,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'bee',
    'octopus',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 7,
    'maybe': 'cheetah',
    'maybe_null': None,
},
},
    {
    'id': 7,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 107,
    'id_str': [
    '08',
],
    'text_data': 'f629821693b54f36b85932316179984f',
    'rand_digit': 9,
    'rand_number': 0.53153,
    'rand_signed_int': -3,
    'rand_datetime': '2000-04-19 22:04',
    'text_array': [
    '9c80b45909c147a583f7181864d76049',
    'e8963d4f32884d6f987e3b84043b69cc',
],
    'words': 'lion camel',
    'nested': {
    'id': 107,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'pig',
    'snail',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': [
    22,
],
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'crab',
},
},
    {
    'id': 8,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 108,
    'id_str': [
    '06',
],
    'text_data': 'ba6623b58c504e99a2e5a27afaf0cf27',
    'rand_digit': 1,
    'rand_number': 0.11884,
    'rand_signed_int': 0,
    'rand_datetime': '2000-08-02 08:37:29-0300',
    'text_array': [
    '037830844fa2430a80307893cfc8f6ff',
    'f91ff040abd34f68995c81fc12fdb317',
],
    'words': 'snake whale',
    'nested': {
    'id': 108,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 1,
},
],
},
    'nested_array': [
    [
    -1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'rabbit',
    'duck',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': 9,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 109,
    'id_str': [
    '05',
    '04',
    '09',
    '23',
],
    'text_data': 'c08adf0611a74ad29a75ead60e7b4989',
    'rand_digit': 6,
    'rand_number': 0.64934,
    'rand_signed_int': 1,
    'rand_datetime': '2000-03-07 02:36:40',
    'text_array': [
    'ed30f625b844443fa87a0c7865e2a006',
    'a28b829b67fc46239820f38641ca416d',
],
    'words': 'rhino wolf',
    'nested': {
    'id': 109,
    'rand_digit': 6,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'snail',
    'horse',
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
    'maybe': 'dragonfly',
    'maybe_null': None,
},
},
    {
    'id': 10,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 110,
    'id_str': [
],
    'text_data': '1a45851abcdd4b78ab25a8263743dbc6',
    'rand_digit': 5,
    'rand_number': 0.14709,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-02T05:27:05+0300',
    'text_array': [
    '82d3f2955de94b14af0c1de6f1f43547',
    '35bbe9d983c64fadb3d1418b766c7c4e',
],
    'words': 'elephant duck',
    'nested': {
    'id': 110,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'dolphin',
    'monkey',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'chicken',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 11,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 111,
    'id_str': [
    '24',
    '18',
],
    'text_data': 'a69f500f864043dc8c1be6146f47b527',
    'rand_digit': 4,
    'rand_number': 0.77337,
    'rand_signed_int': 3,
    'rand_datetime': '2000-07-09T14:58:33.676448Z',
    'text_array': [
    'affea242cd5a4dac97bb3a670a12f854',
    'ecc3246875dc469987634ac940b4ab5a',
],
    'words': 'deer sheep',
    'nested': {
    'id': 111,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'whale',
    'frog',
],
    'city': {
    'name': 'Rome',
    'geo': {
    'lat': 41.902782,
    'lon': 12.496366,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'dolphin',
    'maybe_null': None,
},
},
    {
    'id': 12,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 112,
    'id_str': [
    '01',
    '18',
    '15',
],
    'text_data': '2cc83bb0f0bc4f3d85c6dfd7a183d4f8',
    'rand_digit': 1,
    'rand_number': 0.03975,
    'rand_signed_int': 2,
    'rand_datetime': '2000-03-07 23:58:38.337792',
    'text_array': [
    '2ff54b3a3e2c43cb9d801a98fb2321fc',
    '631394bcba354fa596af2698f3c487fb',
],
    'words': 'monkey grasshopper',
    'nested': {
    'id': 112,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'spider',
    'butterfly',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'giraffe',
},
},
    {
    'id': 13,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 113,
    'id_str': [
],
    'text_data': '64fc04e538e643d4aab559ad0b5564f5',
    'rand_digit': 4,
    'rand_number': 0.37311,
    'rand_signed_int': -1,
    'rand_datetime': '2000-12-18T19:56:18.219775+06:00',
    'text_array': [
    '9cd8a740ba1649dab4d57b019d1bea24',
    'd5a5c17bfdf54e1fb55faedec6bdec6b',
],
    'words': 'leopard zebra',
    'nested': {
    'id': 113,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'zebra',
    'duck',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.39196,
    'maybe_null': 'bird',
},
},
    {
    'id': 14,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 114,
    'id_str': [
    '12',
    '10',
    '03',
    '10',
],
    'text_data': 'c1e4702959ce45c1acac6a1749042254',
    'rand_digit': 4,
    'rand_number': 0.50489,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-11T02:35:48',
    'text_array': [
    '57906256ff0b4b73b0f58068a18f7d24',
    'c47b02ff8a594a9da8d4394d4475ba28',
],
    'words': 'hippo whale',
    'nested': {
    'id': 114,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'deer',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'giraffe',
    'mosquito',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'tiger',
    'maybe': 'koala',
    'maybe_null': None,
},
},
    {
    'id': 15,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 115,
    'id_str': [
    '29',
    '07',
    '07',
    '26',
],
    'text_data': '227f697dc8c04a5d811e9adb4b331c0a',
    'rand_digit': 0,
    'rand_number': 0.7361,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-25T20:11:56',
    'text_array': [
    'dddf2f9559a64400afe6118266b74f53',
    'c98ceca1e48749428dc2550b9bb2169b',
],
    'words': 'cheetah cat',
    'nested': {
    'id': 115,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'cheetah',
    'dolphin',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'snake',
},
},
    {
    'id': 16,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 116,
    'id_str': [
    '05',
    '05',
],
    'text_data': '66b89598f5ae43909910fd0c4e70b553',
    'rand_digit': 9,
    'rand_number': 0.45017,
    'rand_signed_int': -5,
    'rand_datetime': '2000-10-23T00:26:48',
    'text_array': [
    '147a397f676b4625a0e7ea3f37b5341e',
    'b14280a6dbb64e4faba5ad61e4ca0998',
],
    'words': 'grasshopper giraffe',
    'nested': {
    'id': 116,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cat',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'shark',
    'horse',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'lizard',
},
},
    {
    'id': 17,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 117,
    'id_str': [
    '16',
    '09',
],
    'text_data': '72b4811693d74730b552682d800a25a8',
    'rand_digit': 4,
    'rand_number': 0.99891,
    'rand_signed_int': 5,
    'rand_datetime': '2001-01-22 07:05:03+0900',
    'text_array': [
    'd7911cd88e23411ba8ad16657c6c945e',
    'd683a8ebd7bd475585a1727269f4875b',
],
    'words': 'deer fly',
    'nested': {
    'id': 117,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snake',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -5,
],
],
    'two_words': [
    'bee',
    'elephant',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.86871,
    'maybe': 'scorpion',
    'maybe_null': 'cat',
},
},
    {
    'id': 18,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 118,
    'id_str': [
    '04',
    '27',
    '05',
    '24',
    '22',
],
    'text_data': 'ca84e61f142c4234b12d293380521ea3',
    'rand_digit': 7,
    'rand_number': 0.47416,
    'rand_signed_int': -2,
    'rand_datetime': '2000-04-24T14:08:21+0800',
    'text_array': [
    '1cde3a62fb2142dd898b6f33f53f9319',
    '4daabbfa22844adaa1ba46279544d7d3',
],
    'words': 'lobster lizard',
    'nested': {
    'id': 118,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
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
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'lion',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lobster',
    'butterfly',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.92878,
    'maybe': 'dolphin',
    'maybe_null': 'koala',
},
},
    {
    'id': 19,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 119,
    'id_str': [
    '11',
    '06',
],
    'text_data': 'f8963c1c9002489ba981ed9d727a0c31',
    'rand_digit': 5,
    'rand_number': 0.10302,
    'rand_signed_int': -7,
    'rand_datetime': '2000-04-09T08:41:17+0800',
    'text_array': [
    '0cbd5dc55a9d4c8baaef7d9ec5adac82',
    '21fed264ee104fa5aeca68c2677e009e',
],
    'words': 'sloth mosquito',
    'nested': {
    'id': 119,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cheetah',
    'crab',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'butterfly',
    'maybe_null': 'koala',
},
},
    {
    'id': 20,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 120,
    'id_str': [
    '12',
    '14',
    '15',
    '04',
    '22',
],
    'text_data': '6190879a0eca49f7a2647640d99179f6',
    'rand_digit': 0,
    'rand_number': 0.49628,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-24 10:11:21-1200',
    'text_array': [
    '91fe1d19b53a4e01a794957a4cb8df4f',
    'd511a257664f408582008d52c70b297d',
],
    'words': 'giraffe pig',
    'nested': {
    'id': 120,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'fly',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    4,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'koala',
    'ant',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'cow',
},
},
    {
    'id': 21,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 121,
    'id_str': [
    '26',
    '29',
],
    'text_data': '25d619bc40514acf9f2cae64884b2632',
    'rand_digit': 6,
    'rand_number': 0.1935,
    'rand_signed_int': 5,
    'rand_datetime': '2001-01-03T11:05:09.421509+0300',
    'text_array': [
    'b1e37abfd8984fb8bc534b93b1d41504',
    '0ad2af1b1a4b43baa77c966016cb1cb9',
],
    'words': 'fish jaguar',
    'nested': {
    'id': 121,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 6,
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
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -10,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'snail',
    'sheep',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': [
    21,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'giraffe',
},
},
    {
    'id': 22,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 122,
    'id_str': [
    '20',
    '22',
],
    'text_data': 'c9ccb4ac019849bf98a05e8f5189f4db',
    'rand_digit': 8,
    'rand_number': 0.745,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-26 00:06:18',
    'text_array': [
    '27f6906f3f514924b54928931e7fbf05',
    '760191ed063241c983f7086c0a89138e',
],
    'words': 'frog hyena',
    'nested': {
    'id': 122,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 4,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 9,
},
    {
    'nested_empty': None,
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
    'word': 'frog',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -8,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'rabbit',
    'cheetah',
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
    'mixed_type': 2,
    'maybe': 'frog',
    'maybe_null': 'zebra',
},
},
    {
    'id': 23,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 123,
    'id_str': [
    '06',
],
    'text_data': 'c6aae4b325294a58a595275def262951',
    'rand_digit': 8,
    'rand_number': 0.66203,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-09T06:41:41.319617+05:00',
    'text_array': [
    '5a8b07277d6840c8a45b610fed372eef',
    '42e58eac6279466b8b8840ddbd885828',
],
    'words': 'hippo dolphin',
    'nested': {
    'id': 123,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'cow',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'scorpion',
    'jaguar',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': [
    8,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'rhino',
},
},
    {
    'id': 24,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 124,
    'id_str': [
    '10',
    '15',
],
    'text_data': '87c4ee1989d9455288abe55c1dfb7ce9',
    'rand_digit': 4,
    'rand_number': 0.54311,
    'rand_signed_int': -8,
    'rand_datetime': '2000-06-28T09:23:12.280670+0500',
    'text_array': [
    'a82b5eff5d744b24979710b214090e98',
    'ffa25148be554e9bb6590add52474007',
],
    'words': 'goat dolphin',
    'nested': {
    'id': 124,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    8,
],
],
    'two_words': [
    'whale',
    'butterfly',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 25,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 125,
    'id_str': [
    '20',
    '07',
    '15',
],
    'text_data': 'a8999cd6b62f4c26ba3547d2c0ef8d2d',
    'rand_digit': 1,
    'rand_number': 0.2779,
    'rand_signed_int': -4,
    'rand_datetime': '2000-12-15 16:37:42+1000',
    'text_array': [
    '37d8423ec44b4efb83839c0b4d649928',
    'c9a2df2f783942a8a7e1e36689d9f51b',
],
    'words': 'dog dragonfly',
    'nested': {
    'id': 125,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    9,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snake',
    'dolphin',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'dog',
},
},
    {
    'id': 26,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 126,
    'id_str': [
    '21',
    '01',
    '22',
    '30',
],
    'text_data': '14565f987f0444ae907f325cb36262d8',
    'rand_digit': 6,
    'rand_number': 0.13097,
    'rand_signed_int': -2,
    'rand_datetime': '2000-10-31T14:25:21.889145',
    'text_array': [
    'bbac66c9cfa74de4b3d3e83ed0221dab',
    '06967b49d2534c55b584b7225341112b',
],
    'words': 'horse pig',
    'nested': {
    'id': 126,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'fox',
    'number': 6,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,2__',
    'two_words': [
    'mouse',
    'pig',
],
    'city': {
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'jaguar',
},
},
    {
    'id': 27,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 127,
    'id_str': [
    '21',
    '27',
    '02',
    '05',
],
    'text_data': '31ebd244d7cd42c0be4088236f9b5d90',
    'rand_digit': 8,
    'rand_number': 0.00615,
    'rand_signed_int': 1,
    'rand_datetime': '2000-04-11 06:02:02-1100',
    'text_array': [
    '836d155c645b4e6c97af97baf2f1071c',
    '39b5364400f94d8f80721298709fa12d',
],
    'words': 'scorpion mosquito',
    'nested': {
    'id': 127,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fly',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'cheetah',
    'lobster',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'deer',
    'maybe_null': 'crab',
},
},
    {
    'id': 28,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 128,
    'id_str': [
    '30',
],
    'text_data': '0ca9f8b895bf41fab11b3571b9b4b422',
    'rand_digit': 8,
    'rand_number': 0.2304,
    'rand_signed_int': -1,
    'rand_datetime': '2000-12-29T08:17:47',
    'text_array': [
    '871e3590adce4cc2bfbad901dd3e1b93',
    '22e34c66e6a04accac10363c8ee59e50',
],
    'words': 'leopard cow',
    'nested': {
    'id': 128,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
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
    'number': 6,
},
],
},
    'nested_array': [
    [
    8,
],
],
    'two_words': [
    'shark',
    'lizard',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.37618,
    'maybe': 'jaguar',
},
},
    {
    'id': 29,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 129,
    'id_str': [
    '27',
],
    'text_data': 'c1d1c7a0b43a408a8740aab4e17aeec1',
    'rand_digit': 4,
    'rand_number': 0.75842,
    'rand_signed_int': -3,
    'rand_datetime': '2000-06-07T20:32:05.128948',
    'text_array': [
    '0cbae2bad74a433e99e0b5535dccf298',
    '4d11c05f5c5447d3bd08b67cc1a7f575',
],
    'words': 'koala ant',
    'nested': {
    'id': 129,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'elephant',
    'mouse',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': [
    11,
],
    'rand_bool': False,
    'mixed_type': 6,
    'maybe_null': 'dolphin',
},
},
    {
    'id': 30,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 130,
    'id_str': [
    '08',
    '16',
    '09',
    '24',
    '15',
],
    'text_data': 'd71ae16990d44ad2aacbcd83e8625090',
    'rand_digit': 5,
    'rand_number': 0.43433,
    'rand_signed_int': -5,
    'rand_datetime': '2000-01-08 01:43',
    'text_array': [
    'dda894977b4d4dfcbbd64b0b8eddb683',
    'a8e6c9672ff5427cb62c3032bccfb971',
],
    'words': 'grasshopper pig',
    'nested': {
    'id': 130,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'hyena',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'mosquito',
    'squid',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'wolf',
},
},
    {
    'id': 31,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 131,
    'id_str': [
    '03',
    '13',
    '11',
],
    'text_data': '4239e53f63ff4bb1b3fa357bb89a58b8',
    'rand_digit': 4,
    'rand_number': 0.3511,
    'rand_signed_int': 3,
    'rand_datetime': '2001-01-14 11:58:51+0000',
    'text_array': [
    '5d747d7686f64eac88cdcc97b19ea795',
    'd27a2a955ee34c42bb874119522e5c5d',
],
    'words': 'fox hippo',
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
    'word': 'jaguar',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'scorpion',
    'elephant',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': [
    30,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fish',
    'maybe_null': 'bee',
},
},
    {
    'id': 32,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 132,
    'id_str': [
    '15',
    '05',
    '23',
    '07',
],
    'text_data': 'c831c0b71c7a4b8b9e9238e12cbdac5a',
    'rand_digit': 9,
    'rand_number': 0.51242,
    'rand_signed_int': -7,
    'rand_datetime': '2000-05-20 13:18',
    'text_array': [
    '66423d949c7b485893f24cffe81fafdb',
    'e5866181ab8c4e0e8a197c09d9b91a15',
],
    'words': 'sheep squid',
    'nested': {
    'id': 132,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'butterfly',
    'lobster',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': [
    75,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 33,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 133,
    'id_str': [
    '29',
    '10',
    '02',
    '04',
],
    'text_data': 'a6b197050b454057bb03f1910b4026c3',
    'rand_digit': 9,
    'rand_number': 0.26335,
    'rand_signed_int': 9,
    'rand_datetime': '2000-07-30 19:34',
    'text_array': [
    'd294ed6a2a8d4036ad95b85b9c1dceb9',
    '75a1a5972285448ea37e4933cb41136a',
],
    'words': 'tiger cheetah',
    'nested': {
    'id': 133,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'camel',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'sloth',
    'chicken',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'ladybug',
},
},
    {
    'id': 34,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 134,
    'id_str': [
],
    'text_data': 'f36c6e2cb15f472eaf40cdc428dc1c3e',
    'rand_digit': 5,
    'rand_number': 0.94255,
    'rand_signed_int': -4,
    'rand_datetime': '2000-03-25 10:00:54',
    'text_array': [
    '34d3392673714d8ba8196c6ab29cfe43',
    'c31900b19df049978165a833ed0b99f2',
],
    'words': 'fly hippo',
    'nested': {
    'id': 134,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fly',
    'sheep',
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
    'maybe': 'lobster',
    'maybe_null': None,
},
},
    {
    'id': 35,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 135,
    'id_str': [
    '08',
],
    'text_data': '97815fa25d084aef8aa5e2b78ced3a43',
    'rand_digit': 9,
    'rand_number': 0.21926,
    'rand_signed_int': 5,
    'rand_datetime': '2000-06-26T07:43:38.418316',
    'text_array': [
    'd4b0e8a513a74ac592cdae7fa07dcd22',
    'e18f9f56776240afa6d794b28bd4d6c9',
],
    'words': 'chicken snake',
    'nested': {
    'id': 135,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'octopus',
    'mouse',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': [
    60,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 36,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 136,
    'id_str': [
    '13',
    '11',
    '23',
    '03',
    '28',
],
    'text_data': 'af872316ccb94b448ae1584b62d98dd7',
    'rand_digit': 9,
    'rand_number': 0.31607,
    'rand_signed_int': -9,
    'rand_datetime': '2000-03-13',
    'text_array': [
    '94e73b9f43af4f0abf4c6a8fdd26919e',
    '5a9c7772d2994f19a6e0b575c38b8618',
],
    'words': 'cheetah ladybug',
    'nested': {
    'id': 136,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    -2,
],
],
    'two_words': [
    'hyena',
    'snake',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
},
},
    {
    'id': 37,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 137,
    'id_str': [
    '29',
],
    'text_data': 'b05b97023e4247e5befbb7a3a2a2368d',
    'rand_digit': 6,
    'rand_number': 0.65757,
    'rand_signed_int': -3,
    'rand_datetime': '2000-06-26T15:42:57',
    'text_array': [
    '96a2e3cd835b4133b06e76a8311e98a8',
    '3040c2e61a6d420397b2221fcb14b795',
],
    'words': 'horse gorilla',
    'nested': {
    'id': 137,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bird',
    'giraffe',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': [
    87,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 38,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 138,
    'id_str': [
    '27',
    '29',
    '28',
    '10',
    '13',
],
    'text_data': '4cac2e0cf0314ded8fb7f4bbddf6491d',
    'rand_digit': 8,
    'rand_number': 0.88521,
    'rand_signed_int': -5,
    'rand_datetime': '2000-01-19 09:30:06',
    'text_array': [
    'e7f5a03a028f422c80f171bb4230d6b4',
    'bf2c8c7c258d4b9e8bc69a11ad06add4',
],
    'words': 'wolf shark',
    'nested': {
    'id': 138,
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
    'hello',
],
    'word': 'squid',
    'number': 1,
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
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'crab',
    'mouse',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'dragonfly',
},
},
    {
    'id': 39,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 139,
    'id_str': [
    '09',
    '08',
],
    'text_data': 'a2084629a1194b83bfc95ecef7306982',
    'rand_digit': 1,
    'rand_number': 0.67653,
    'rand_signed_int': 0,
    'rand_datetime': '2000-05-31T00:57:40.710838-0700',
    'text_array': [
    '659a5601e2ee4165a1db213da0fa6ee6',
    '94bd0d8fc86f40a0ab5eae3ce775dbcf',
],
    'words': 'whale ape',
    'nested': {
    'id': 139,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'sloth',
    'hippo',
],
    'city': {
    'name': 'Cardiff',
    'geo': {
    'lat': 51.481581,
    'lon': -3.17909,
},
},
    'rand_tuple': [
    67,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'ant',
    'maybe_null': None,
},
},
    {
    'id': 40,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 140,
    'id_str': [
    '23',
    '07',
    '09',
    '09',
],
    'text_data': '7e94ea3c18474056a2b61c0bf8e80fa5',
    'rand_digit': 8,
    'rand_number': 0.11229,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-01 15:41:20.397138+0900',
    'text_array': [
    '6a2047ef3ae04f88bdb7997e84a5f3ac',
    '78c6639f50fd47538b03c0139343bd62',
],
    'words': 'deer ant',
    'nested': {
    'id': 140,
    'rand_digit': 9,
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
    'word': 'ant',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fish',
    'bear',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'duck',
    'maybe_null': 'snail',
},
},
    {
    'id': 41,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 141,
    'id_str': [
    '24',
    '13',
    '16',
],
    'text_data': 'a770dc82c8af43cfa48a43dfdf0c89b5',
    'rand_digit': 6,
    'rand_number': 0.29506,
    'rand_signed_int': -2,
    'rand_datetime': '2000-09-30T15:03:13+1000',
    'text_array': [
    '9d30c8a339fb46ffa0caa07f995eba13',
    'e4055c6e926f4bfe97b843269a1e33a8',
],
    'words': 'kangaroo frog',
    'nested': {
    'id': 141,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -4,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'deer',
    'rabbit',
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
    'mixed_type': 0,
    'maybe_null': None,
},
},
    {
    'id': 42,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 142,
    'id_str': [
    '15',
    '17',
    '09',
],
    'text_data': 'ef9f1e64e571447fbb9b6ebda07bfe71',
    'rand_digit': 9,
    'rand_number': 0.71714,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-14 14:25:36.377199+0000',
    'text_array': [
    'ffc2234345cb4369851bc42e9c4a1ddc',
    'aad6dfcd7eaf438bb4dbb91d2868e851',
],
    'words': 'camel ape',
    'nested': {
    'id': 142,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'mosquito',
    'deer',
],
    'city': {
    'name': 'London',
    'geo': {
    'lat': 51.507351,
    'lon': -0.127758,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': None,
},
},
    {
    'id': 43,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 143,
    'id_str': [
    '25',
    '08',
    '26',
    '18',
],
    'text_data': 'cf846d42350d47419e1b192a436b5504',
    'rand_digit': 6,
    'rand_number': 0.53011,
    'rand_signed_int': 3,
    'rand_datetime': '2000-03-24T10:40:17+0500',
    'text_array': [
    '307e4649f0d846f7aadd6bc3bfdf4dab',
    '60f3a2bb37d24bdc89ade363358b88e8',
],
    'words': 'chicken spider',
    'nested': {
    'id': 143,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'leopard',
    'giraffe',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'rabbit',
},
},
    {
    'id': 44,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 144,
    'id_str': [
    '20',
    '07',
    '12',
],
    'text_data': '136ff74341614db2b56dabd15f1cd19c',
    'rand_digit': 7,
    'rand_number': 0.20913,
    'rand_signed_int': 7,
    'rand_datetime': '2000-03-03T23:55:18.011365-0400',
    'text_array': [
    'a29bfd6d422a49459fa18c8166c94060',
    'fe7781c0f141483cb768edc906fc1f11',
],
    'words': 'shark duck',
    'nested': {
    'id': 144,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    [
],
    [
    6,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'octopus',
    'sloth',
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
    'mixed_type': True,
},
},
    {
    'id': 45,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 145,
    'id_str': [
],
    'text_data': 'c7699f67b2a74fee80bb30b5dd98951a',
    'rand_digit': 4,
    'rand_number': 0.78992,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-23T02:42:23',
    'text_array': [
    '17a4e3a5bc304d2fbe3457415dbb9c64',
    'ff12cf60769f4a14949d0a2d355c4f49',
],
    'words': 'horse tiger',
    'nested': {
    'id': 145,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'snake',
    'spider',
],
    'city': {
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': [
    40,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bear',
    'maybe_null': None,
},
},
    {
    'id': 46,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 146,
    'id_str': [
    '29',
    '07',
],
    'text_data': '51d1ba04964246d1b16c4aa1aa95ce32',
    'rand_digit': 3,
    'rand_number': 0.33682,
    'rand_signed_int': -4,
    'rand_datetime': '2000-02-05 05:09:43',
    'text_array': [
    '23c371be71b345cb8052f7841374cf2f',
    '1712ff4354d243a698fd47164a27a31c',
],
    'words': 'cheetah sloth',
    'nested': {
    'id': 146,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ant',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'goat',
    'bear',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'shark',
    'maybe': 'spider',
    'maybe_null': 'leopard',
},
},
    {
    'id': 47,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 147,
    'id_str': [
    '14',
],
    'text_data': 'c92e787682304994b9dc315482a05093',
    'rand_digit': 1,
    'rand_number': 0.52937,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-28T05:47:01.834541',
    'text_array': [
    '8d69f9f18f2d493294af802989a31717',
    '7d76cfb857194813aae7033cf8279101',
],
    'words': 'kangaroo dragonfly',
    'nested': {
    'id': 147,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    9,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'elephant',
    'dragonfly',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.11105,
},
},
    {
    'id': 48,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 148,
    'id_str': [
    '02',
    '25',
    '16',
],
    'text_data': '6c759f66474f44e1a50e2b011ed2f34b',
    'rand_digit': 7,
    'rand_number': 0.87773,
    'rand_signed_int': -1,
    'rand_datetime': '2000-11-19T03:14:31+0400',
    'text_array': [
    'e57ca4ba5b154b83bbcc58ad32d38245',
    'e76b815712c74f999464ab04e227cc99',
],
    'words': 'bird bird',
    'nested': {
    'id': 148,
    'rand_digit': 0,
    'array': [
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
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'rabbit',
    'sheep',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 49,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 149,
    'id_str': [
    '15',
    '11',
    '20',
],
    'text_data': '4bf7b145c7964ab8869fb507c2f7e0d4',
    'rand_digit': 6,
    'rand_number': 0.08629,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-12 21:26:04',
    'text_array': [
    'ea742359d14b4c7c8e06b9357fab344c',
    'f3576ab721a6433f99dca73385b86cd6',
],
    'words': 'mouse gorilla',
    'nested': {
    'id': 149,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'squid',
    'butterfly',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': [
    99,
],
    'rand_bool': False,
    'mixed_type': 0,
    'maybe_null': 'frog',
},
},
    {
    'id': 50,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 150,
    'id_str': [
],
    'text_data': '448480449a404591965881d4c8fd851c',
    'rand_digit': 3,
    'rand_number': 0.68673,
    'rand_signed_int': -2,
    'rand_datetime': '2001-01-15 04:33:50-0600',
    'text_array': [
    '472871de3f584a27a3d02c60c15ca14e',
    'fee4ac72fa604f3bbc4e69c54adab6ce',
],
    'words': 'whale fish',
    'nested': {
    'id': 150,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'horse',
    'gorilla',
],
    'city': {
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': [
    9,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'octopus',
    'maybe_null': 'shark',
},
},
    {
    'id': 51,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 151,
    'id_str': [
    '09',
],
    'text_data': '8fdc8a99b71247baba2b00a4d7e66f19',
    'rand_digit': 7,
    'rand_number': 0.38026,
    'rand_signed_int': -5,
    'rand_datetime': '2000-03-09T18:50:19+0300',
    'text_array': [
    '14100422944c4703b8a64caa7c80e9f6',
    '78313228d5354309a777c75d5fd5f249',
],
    'words': 'horse snake',
    'nested': {
    'id': 151,
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
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'pig',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'gorilla',
    'monkey',
],
    'city': {
    'name': 'Kuala Lumpur',
    'geo': {
    'lat': 3.139003,
    'lon': 101.686855,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.67968,
    'maybe_null': 'frog',
},
},
    {
    'id': 52,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 152,
    'id_str': [
    '17',
    '02',
    '21',
    '18',
    '17',
],
    'text_data': 'd213891ed4eb478d9ac14b9711b9c188',
    'rand_digit': 5,
    'rand_number': 0.89534,
    'rand_signed_int': -10,
    'rand_datetime': '2000-04-12 18:36:07-0600',
    'text_array': [
    '6a81c89e38004162bccf83459487fa20',
    'ee12005859d8457bafa2c3816ec2e7ca',
],
    'words': 'jaguar squid',
    'nested': {
    'id': 152,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
    -7,
],
],
    'two_words': [
    'dolphin',
    'dolphin',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'leopard',
},
},
    {
    'id': 53,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 153,
    'id_str': [
    '10',
    '23',
    '09',
    '22',
    '23',
],
    'text_data': '065427c1a4ed460880eb2492ba76c004',
    'rand_digit': 7,
    'rand_number': 0.41901,
    'rand_signed_int': 4,
    'rand_datetime': '2000-12-03T06:59:40.300362',
    'text_array': [
    '344735a6ed6a4f2289b8a0e57c36d35a',
    '5901b794ce3049e6b6456a1035f8b1b0',
],
    'words': 'duck kangaroo',
    'nested': {
    'id': 153,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 8,
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
    'scorpion',
    'snake',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': None,
},
},
    {
    'id': 54,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 154,
    'id_str': [
    '17',
    '01',
],
    'text_data': '436492ebb28b4dea8cf4deeb54729b8b',
    'rand_digit': 7,
    'rand_number': 0.24232,
    'rand_signed_int': -5,
    'rand_datetime': '2000-01-05 07:10:48.195764+0700',
    'text_array': [
    '222fc271d6d248e4bfcacbb3fef8d896',
    '2a3073e885df4e3f901a9aee38a7449c',
],
    'words': 'rhino fly',
    'nested': {
    'id': 154,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'duck',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cat',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lizard',
    'frog',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 55,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 155,
    'id_str': [
    '25',
    '17',
    '29',
    '09',
    '24',
],
    'text_data': '34d2492eeb1f4915aa90078432bdd148',
    'rand_digit': 9,
    'rand_number': 0.17411,
    'rand_signed_int': 5,
    'rand_datetime': '2000-03-24T20:01:55-0400',
    'text_array': [
    '2180f9d6949e4d748a7bcf68ec7c65dc',
    '03e57420b225440491b9cb30bfc39237',
],
    'words': 'mosquito fox',
    'nested': {
    'id': 155,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 1,
},
    {
    'nested_empty': None,
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
],
    'word': 'snake',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'gorilla',
    'spider',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'cat',
},
},
    {
    'id': 56,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 156,
    'id_str': [
    '16',
    '16',
    '05',
],
    'text_data': '280116c826f44924b0f5839368fa3c2b',
    'rand_digit': 9,
    'rand_number': 0.01924,
    'rand_signed_int': -1,
    'rand_datetime': '2000-02-29T17:00:24.787097',
    'text_array': [
    '4f381386330a4eaea985e13503705edd',
    '4b3ad95a0fbe401ba6f7c3efde352afc',
],
    'words': 'lobster bee',
    'nested': {
    'id': 156,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'wolf',
    'lizard',
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
    'mixed_type': 9,
    'maybe_null': None,
},
},
    {
    'id': 57,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 157,
    'id_str': [
    '16',
    '08',
    '16',
    '09',
    '17',
],
    'text_data': '15ac78e1af2949fa96c4d05089a3d82d',
    'rand_digit': 9,
    'rand_number': 0.09697,
    'rand_signed_int': 7,
    'rand_datetime': '2000-02-15 19:06:18.196647',
    'text_array': [
    '8c040b3d805a46a8813d56cb614067fd',
    '621fb0a866674e018da8307fca9a3766',
],
    'words': 'octopus koala',
    'nested': {
    'id': 157,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snail',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cat',
    'butterfly',
],
    'city': {
    'name': 'Dubai',
    'geo': {
    'lat': 25.204849,
    'lon': 55.270783,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.29972,
    'maybe': 'shark',
},
},
    {
    'id': 58,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 158,
    'id_str': [
],
    'text_data': 'e3bfed54d0c74a27b0474c2e36e62e42',
    'rand_digit': 5,
    'rand_number': 0.32716,
    'rand_signed_int': -2,
    'rand_datetime': '2000-01-02T16:20:02',
    'text_array': [
    '4cb5a68975ca4895ba2e783229a57eb9',
    '46701cbe6901440d81cac01f0c0d5bff',
],
    'words': 'cat scorpion',
    'nested': {
    'id': 158,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'crab',
    'ant',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 59,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 159,
    'id_str': [
    '24',
    '02',
],
    'text_data': 'ec33cdbdb0764e8c87ee4cf057b175bb',
    'rand_digit': 3,
    'rand_number': 0.65756,
    'rand_signed_int': 0,
    'rand_datetime': '2000-01-11T10:54:44.611864+0400',
    'text_array': [
    '98382cacad504a76b6a5afb4c7381feb',
    '10baf4638b1c4550a2185305ae29faf6',
],
    'words': 'ape wolf',
    'nested': {
    'id': 159,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'panda',
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'scorpion',
    'rhino',
],
    'city': {
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 60,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 160,
    'id_str': [
    '04',
    '29',
],
    'text_data': '67a8c6c7b96e4dbf87b5cf3479495626',
    'rand_digit': 5,
    'rand_number': 0.34161,
    'rand_signed_int': 9,
    'rand_datetime': '2000-12-19',
    'text_array': [
    '9b5f141531744a70b75c15c9463aa0e2',
    '6324297f5b5e4708a0ad7db5cd259113',
],
    'words': 'goat scorpion',
    'nested': {
    'id': 160,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'turtle',
    'sheep',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': [
    58,
],
    'rand_bool': False,
    'mixed_type': 0.48913,
},
},
    {
    'id': 61,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 161,
    'id_str': [
    '26',
    '16',
    '11',
],
    'text_data': '5368dcbbdab547cc839559ec4d6ced42',
    'rand_digit': 2,
    'rand_number': 0.36265,
    'rand_signed_int': 5,
    'rand_datetime': '2000-07-22T04:51:48.415121+11:00',
    'text_array': [
    '3798c9ca315a4b4bb6385bc27f1703fd',
    'd4f14cc3d8d74c9ebb30579ea6fbd83e',
],
    'words': 'goat squid',
    'nested': {
    'id': 161,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'squid',
    'duck',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'fox',
},
},
    {
    'id': 62,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 162,
    'id_str': [
    '29',
    '09',
    '11',
    '13',
    '20',
],
    'text_data': '3ad207611f874b80a0ffb2f425785c0f',
    'rand_digit': 5,
    'rand_number': 0.81614,
    'rand_signed_int': -7,
    'rand_datetime': '2000-01-17T23:07:51+0700',
    'text_array': [
    'd8df1715b8e4461a9ed53b437fb1d832',
    '29cfab8c7c8742c185c70547db76c98d',
],
    'words': 'lobster koala',
    'nested': {
    'id': 162,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'pig',
    'sloth',
],
    'city': {
    'name': 'Cardiff',
    'geo': {
    'lat': 51.481581,
    'lon': -3.17909,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'zebra',
    'maybe_null': 'gorilla',
},
},
    {
    'id': 63,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'text': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'payload': {
    'id': 163,
    'id_str': [
    '20',
    '04',
    '05',
],
    'text_data': 'c9553c783b594f0f9ca6baa39d7d6e17',
    'rand_digit': 2,
    'rand_number': 0.25948,
    'rand_signed_int': 10,
    'rand_datetime': '2000-11-25T06:28:53.701907',
    'text_array': [
    'ec42fd2ad838484c9ffbca425a1b8b5d',
    '7c06d0b0d64e4890a72e14cb72d67fb6',
],
    'words': 'rabbit duck',
    'nested': {
    'id': 163,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 3,
},
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
    'word': 'ape',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bird',
    'butterfly',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': [
    10,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'bee',
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
        """测试请求 2 - POST http://localhost:6333/collections/client_test/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/client_test/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/client_test/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '2003',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'image',
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    'limit': 5,
    'with_payload': True,
    'with_vector': True,
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
        """测试请求 3 - DELETE http://localhost:6333/collections/client_test?timeout=60"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://localhost:6333/collections/client_test?timeout=60")
        method = 'DELETE'
        url_path = 'http://localhost:6333/collections/client_test?timeout=60'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '91',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'image': {
    'size': 100,
    'distance': 'Dot',
},
    'text': {
    'size': 200,
    'distance': 'Cosine',
},
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_qdrant_client.test_multiple_vectors')
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
    test = TestQdrantClienttestMultipleVectors()
    test.run_tests()
