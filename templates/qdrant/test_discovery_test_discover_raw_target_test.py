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
logger = logging.getLogger('vdb_fuzzer.test.test_discovery_test_discover_raw_target')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_discovery.test_discover_raw_target"
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



class TestDiscoverytestDiscoverRawTarget:
    """自动生成的VDB模糊测试类 - test_discovery.test_discover_raw_target"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_discovery.test_discover_raw_target"
        self.test_count = 6  # 测试方法数量
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
    'content-length': '138856',
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
    '13',
    '23',
    '19',
    '03',
    '10',
],
    'text_data': '70795704ba9f44c1b164151bf3f294e0',
    'rand_digit': 0,
    'rand_number': 0.04177,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-17T07:47:26+0200',
    'text_array': [
    '54cc01b211234a2c803b6cecff4e624f',
    '91235c7ef98148f8b6a55d7771a062d3',
],
    'words': 'pig panda',
    'nested': {
    'id': 100,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'crab',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'squid',
    'cheetah',
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
    'mixed_type': 0,
    'maybe': 'octopus',
    'maybe_null': None,
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
    '21',
],
    'text_data': 'eefdd514a2404b12b7d236c3621247b0',
    'rand_digit': 9,
    'rand_number': 0.65858,
    'rand_signed_int': 0,
    'rand_datetime': '2000-08-23T09:24:04-0900',
    'text_array': [
    '362541fba4e140d59bb3e0bfc22273f7',
    '62f7f542ddaa4c889501c93716dda0a1',
],
    'words': 'fox cat',
    'nested': {
    'id': 101,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 1,
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
],
    'word': 'bird',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'butterfly',
    'crab',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'duck',
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
    '11',
    '03',
    '12',
    '06',
],
    'text_data': '2259dadd7f564e8e8b355631285a56a1',
    'rand_digit': 6,
    'rand_number': 0.92673,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-11',
    'text_array': [
    '26cb4c1526e542deacb98b4a82b81358',
    '9552cafa110b4e1f983c5b024ef1e045',
],
    'words': 'cat bear',
    'nested': {
    'id': 102,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 8,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dog',
    'grasshopper',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': [
    37,
],
    'rand_bool': False,
    'mixed_type': 0.93452,
    'maybe_null': 'bee',
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
    '02',
],
    'text_data': '4dbf2fc4d6e74f1dac360e41617a3ff0',
    'rand_digit': 2,
    'rand_number': 0.85255,
    'rand_signed_int': -5,
    'rand_datetime': '2000-12-25T03:26:28.574927+0100',
    'text_array': [
    'ac7f44a0f4f642bbb6e92ff9c7158d19',
    'de7ee6b995ac499791a0dafd97399998',
],
    'words': 'hippo octopus',
    'nested': {
    'id': 103,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snake',
    'snail',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 6,
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
    '09',
    '04',
],
    'text_data': '7d5dac242b77480a8000bc67add2fcab',
    'rand_digit': 7,
    'rand_number': 0.49148,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-19 00:08:22+0300',
    'text_array': [
    '44011913297b47ba8408cc28b6590d43',
    'dc9166b145f543b29cbf28412466f4a4',
],
    'words': 'scorpion lion',
    'nested': {
    'id': 104,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'grasshopper',
    'gorilla',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
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
    '22',
],
    'text_data': 'c20371db3d384148baa5e59786de23ee',
    'rand_digit': 7,
    'rand_number': 0.21773,
    'rand_signed_int': -6,
    'rand_datetime': '2000-08-09T20:18:36',
    'text_array': [
    '77da6aa37d7a4102b388fdb7407d490a',
    'c0e7f66b89d74f3f9339e94717858245',
],
    'words': 'ladybug bee',
    'nested': {
    'id': 105,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'panda',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'grasshopper',
    'fish',
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
    'mixed_type': 0.68183,
    'maybe': 'scorpion',
    'maybe_null': 'bear',
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
    '27',
    '08',
    '10',
    '28',
    '25',
],
    'text_data': '55f0a69ced8545ca8ef43ed3eb64d814',
    'rand_digit': 9,
    'rand_number': 0.88261,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-04T00:12:01',
    'text_array': [
    '40051ec0d5f64990bbb137d1bef6a3b9',
    '9ccd07fe6ac44c22be8f99a92f59d61f',
],
    'words': 'chicken grasshopper',
    'nested': {
    'id': 106,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
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
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'whale',
    'panda',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cow',
    'maybe_null': 'bird',
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
    '28',
],
    'text_data': '81966d8bb87849438959657e804d97f1',
    'rand_digit': 2,
    'rand_number': 0.58457,
    'rand_signed_int': 9,
    'rand_datetime': '2000-03-07',
    'text_array': [
    '17000829e8e047a5b346dfe9c38f4c3f',
    '3ddae261485c457e85a6779b1da098fc',
],
    'words': 'koala crab',
    'nested': {
    'id': 107,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
    -10,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'goat',
    'bee',
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
    'mixed_type': 0.80227,
    'maybe': 'ant',
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
    '16',
],
    'text_data': '71f40c07dbac4095b9181ba1273b4495',
    'rand_digit': 4,
    'rand_number': 0.87564,
    'rand_signed_int': 3,
    'rand_datetime': '2000-06-17 01:50:50',
    'text_array': [
    'dcde19716f2244f9a713c8efd529ca85',
    '6508d6aa270146f782ab5f606c93921d',
],
    'words': 'sheep cow',
    'nested': {
    'id': 108,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bear',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bird',
    'ladybug',
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
    'mixed_type': 5,
    'maybe_null': 'snake',
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
    '10',
],
    'text_data': '3542123a1d8d4b15be483e5b0b76a06e',
    'rand_digit': 6,
    'rand_number': 0.83198,
    'rand_signed_int': 3,
    'rand_datetime': '2001-01-16T01:20:44.695398-04:00',
    'text_array': [
    'fc394fdfdb92434fb5363681f23d0ba5',
    'e2d05b1f6a254145ae31ae6b7e9bc1a6',
],
    'words': 'wolf fly',
    'nested': {
    'id': 109,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'ant',
    'butterfly',
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
    'mixed_type': 5,
    'maybe_null': None,
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
    '17',
    '29',
    '18',
    '09',
],
    'text_data': '3b26c29da45e40ddb135bad7a7a55b5e',
    'rand_digit': 8,
    'rand_number': 0.00266,
    'rand_signed_int': -9,
    'rand_datetime': '2000-11-15 08:09:39',
    'text_array': [
    '88dc9101fde04c9f8ca30815038b7324',
    '249e2861dbe5454897e728c72cd4fd7d',
],
    'words': 'horse pig',
    'nested': {
    'id': 110,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lobster',
    'bee',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'lion',
    'maybe_null': 'kangaroo',
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
    '10',
    '06',
    '13',
    '27',
    '05',
],
    'text_data': '96106af33de54759b1536a0bca43adae',
    'rand_digit': 6,
    'rand_number': 0.98538,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-03T19:40:43',
    'text_array': [
    '9bfd61084b1a46349d8f1538740d2bd5',
    '4f4e0311f1a5435797939454eb36c4d6',
],
    'words': 'tiger rhino',
    'nested': {
    'id': 111,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'deer',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'butterfly',
    'fish',
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
    '29',
],
    'text_data': '0cf037ae3a7843d382e9bd3bd42af12e',
    'rand_digit': 6,
    'rand_number': 0.32705,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-29 13:18:49',
    'text_array': [
    '65264e91469f4eb0b224c05e66ca7d7c',
    '2708069ac1f34be89711a44e8fc2c283',
],
    'words': 'giraffe cow',
    'nested': {
    'id': 112,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 1,
},
],
},
    'nested_array': [
    [
    10,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dolphin',
    'ant',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'mosquito',
    'maybe_null': 'sloth',
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
    '22',
    '10',
    '27',
    '18',
    '21',
],
    'text_data': 'fb14eec42181431eaf53d2b3ac0213e3',
    'rand_digit': 7,
    'rand_number': 0.52914,
    'rand_signed_int': -5,
    'rand_datetime': '2000-12-17T15:21:22',
    'text_array': [
    '42b39df7ce3b4181b1a51956f9683b32',
    '932852f43e3d481784cf7967602cedf0',
],
    'words': 'leopard octopus',
    'nested': {
    'id': 113,
    'rand_digit': 0,
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
    'word': 'lion',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'rabbit',
    'cow',
],
    'city': {
    'name': 'Zurich',
    'geo': {
    'lat': 47.376887,
    'lon': 8.541694,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'tiger',
    'maybe_null': 'bear',
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
],
    'text_data': 'f4d0ad0f5aed4fbd9857cf5c73b668bd',
    'rand_digit': 8,
    'rand_number': 0.27172,
    'rand_signed_int': 2,
    'rand_datetime': '2000-04-03T22:54:26.428360Z',
    'text_array': [
    'd83626c08a734254954e76907ce8975e',
    '6f77a9670f464048a1939412d1be94b4',
],
    'words': 'snail mouse',
    'nested': {
    'id': 114,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 10,
},
],
},
    'nested_array': [
    [
    5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'monkey',
    'scorpion',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
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
    '30',
    '04',
],
    'text_data': '2116484189164dbb9ac65c73899af157',
    'rand_digit': 9,
    'rand_number': 0.05984,
    'rand_signed_int': 5,
    'rand_datetime': '2000-03-26 23:44:48.272925+0700',
    'text_array': [
    'aa4df13e862d4a7db3bca3e4b655bf66',
    'b36589c8703349c39eb90b81d8c66eb6',
],
    'words': 'lobster hyena',
    'nested': {
    'id': 115,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'pig',
    'whale',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 5,
    'maybe_null': 'sloth',
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
    '10',
    '01',
    '04',
    '22',
],
    'text_data': 'c452ff93d15742d5b9e4f30871b5e547',
    'rand_digit': 6,
    'rand_number': 0.73954,
    'rand_signed_int': 9,
    'rand_datetime': '2000-12-29 04:18:02.160049+0500',
    'text_array': [
    'b8ba7533bca94889b4e94e83fe4ac7fc',
    '2fb9eee9e81a48baa9999d127511f68c',
],
    'words': 'snail fly',
    'nested': {
    'id': 116,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    [
    -7,
],
],
    'two_words': [
    'giraffe',
    'mosquito',
],
    'city': {
    'name': 'Frankfurt',
    'geo': {
    'lat': 50.110922,
    'lon': 8.682127,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'bear',
    'maybe_null': 'crab',
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
    '23',
    '09',
    '12',
    '18',
    '19',
],
    'text_data': 'e868939969a34366a27a33e26a7fec8f',
    'rand_digit': 6,
    'rand_number': 0.18663,
    'rand_signed_int': -10,
    'rand_datetime': '2000-03-15 09:10:33',
    'text_array': [
    '0cabbdb559da4cbe94960ce171041ff9',
    '89673e5d241b4c809fb74f000721e34a',
],
    'words': 'cat ant',
    'nested': {
    'id': 117,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 1,
},
],
},
    'nested_array': [
    [
    0,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'bee',
    'fly',
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
    'mixed_type': 'jaguar',
    'maybe': 'sheep',
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
    '10',
    '04',
    '14',
    '22',
],
    'text_data': 'a5632ddebe0b4830974af77bc7e0d136',
    'rand_digit': 3,
    'rand_number': 0.54531,
    'rand_signed_int': 5,
    'rand_datetime': '2000-07-31T07:07:14.342661',
    'text_array': [
    'e877c475bcf94892b0a5d7a52b3b4106',
    'aa551b2153df40e5895ca14db405835d',
],
    'words': 'ladybug mosquito',
    'nested': {
    'id': 118,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'deer',
    'sheep',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'whale',
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
    '01',
    '14',
    '15',
    '05',
    '03',
],
    'text_data': 'af52122f5ddf43fda840ea7035ea4fbc',
    'rand_digit': 2,
    'rand_number': 0.23842,
    'rand_signed_int': 2,
    'rand_datetime': '2000-05-16T18:54:11.343591',
    'text_array': [
    '37b2b5ace59147ac9ae3b7982c65132b',
    'ab57068876a94c58b45513f11fbde055',
],
    'words': 'pig butterfly',
    'nested': {
    'id': 119,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 6,
},
],
},
    'nested_array': [
    [
    -9,
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cow',
    'goat',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': [
    69,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fox',
    'maybe_null': None,
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
    '28',
    '01',
    '14',
    '05',
],
    'text_data': '9db83e0dee544c91934704cab6646e9a',
    'rand_digit': 1,
    'rand_number': 0.47482,
    'rand_signed_int': 8,
    'rand_datetime': '2000-07-15 07:46:33',
    'text_array': [
    'ba084f2482f04ae0bace9e0440c1b62d',
    '22fec5e4a72e4596b661f37ff256dae4',
],
    'words': 'frog sloth',
    'nested': {
    'id': 120,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bird',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'koala',
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
    'mixed_type': 0.0239,
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
    '29',
],
    'text_data': '14cef97631ae4290a683b29baab4dbc2',
    'rand_digit': 0,
    'rand_number': 0.6457,
    'rand_signed_int': 6,
    'rand_datetime': '2000-10-11',
    'text_array': [
    'a538657c956e4ff1801c29052964e2c2',
    '26377bf521c942aaba691b0de539ed64',
],
    'words': 'cow fish',
    'nested': {
    'id': 121,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'sloth',
    'cat',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': [
    65,
],
    'rand_bool': True,
    'mixed_type': 2,
    'maybe_null': 'dragonfly',
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
    '10',
    '11',
    '10',
    '24',
],
    'text_data': '4378833513c94bf88d744afa79a9eec5',
    'rand_digit': 8,
    'rand_number': 0.46775,
    'rand_signed_int': -6,
    'rand_datetime': '2000-02-08 09:32:14+0900',
    'text_array': [
    'cc8c2694b9bd46e290cbb1bba76bdc50',
    '89b11b2b459b4c969311675368bab985',
],
    'words': 'ant elephant',
    'nested': {
    'id': 122,
    'rand_digit': 2,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'hyena',
    'zebra',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.5571,
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
    'text_data': '85d9144a811f4bcf9480df8ce1f1eb8d',
    'rand_digit': 2,
    'rand_number': 0.44699,
    'rand_signed_int': 1,
    'rand_datetime': '2000-03-30 08:20',
    'text_array': [
    'dbf96c7d152f4baebcbe842cd31a4e24',
    '341e058892d643d1bfedda3cabc38c09',
],
    'words': 'lizard lizard',
    'nested': {
    'id': 123,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lion',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'scorpion',
    'gorilla',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'ape',
    'maybe_null': 'deer',
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
    'text_data': '95e24238771c4730a95bbcbc2be129db',
    'rand_digit': 5,
    'rand_number': 0.57989,
    'rand_signed_int': 2,
    'rand_datetime': '2000-06-10T12:28:32',
    'text_array': [
    'f4c3982d59564f289758f0ae90c69386',
    '9aa7720e27dc47e8ad074ffbad1c28bd',
],
    'words': 'deer goat',
    'nested': {
    'id': 124,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'octopus',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 9,
},
],
},
    'nested_array': [
    [
    -4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'chicken',
    'panda',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'ladybug',
    'maybe_null': 'lizard',
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
    '23',
],
    'text_data': '7b154cedead640eb8f42ce3eefff2d3f',
    'rand_digit': 8,
    'rand_number': 0.64245,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-09T11:22:18',
    'text_array': [
    '0401a970dbef4a5c9f4168ef8ac0119e',
    'ecbd9337f23f4174b445037f92f030a9',
],
    'words': 'whale snail',
    'nested': {
    'id': 125,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'horse',
    'jaguar',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'rabbit',
    'maybe_null': 'goat',
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
    '22',
    '16',
],
    'text_data': '0712914cdc344e5f86cd7cd5b11c0fef',
    'rand_digit': 6,
    'rand_number': 0.81034,
    'rand_signed_int': 7,
    'rand_datetime': '2000-06-06 12:25:51.960578+0600',
    'text_array': [
    '8445bddf28f94347ad2cff1ba7b5fed6',
    'd0544f728ac44369b41c341d67bb599a',
],
    'words': 'gorilla chicken',
    'nested': {
    'id': 126,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'camel',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'frog',
    'goat',
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
    'mixed_type': 0.66961,
    'maybe': 'mouse',
    'maybe_null': 'sloth',
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
    '08',
    '22',
],
    'text_data': '5c120e88ead9404a8a644d7f66a2ad6d',
    'rand_digit': 1,
    'rand_number': 0.27282,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-22T06:15:53',
    'text_array': [
    '9ee71046ba1548a98fa9e9614d3490b2',
    '244e76015c374417a829b0ae4e3c8a4e',
],
    'words': 'dog fly',
    'nested': {
    'id': 127,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'bird',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    4,
],
],
    'two_words': [
    'horse',
    'chicken',
],
    'city': {
    'name': 'Kuala Lumpur',
    'geo': {
    'lat': 3.139003,
    'lon': 101.686855,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
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
    '24',
    '04',
    '14',
],
    'text_data': '1a5773fae05841c8be8554844453a11b',
    'rand_digit': 7,
    'rand_number': 0.82655,
    'rand_signed_int': 10,
    'rand_datetime': '2001-01-02 10:58:53-0800',
    'text_array': [
    '81c7d618ad0249e9b8e239621e69c597',
    '4deff2c3467449b7aa1a4fbdaf21a7ef',
],
    'words': 'bear fly',
    'nested': {
    'id': 128,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'shark',
    'sloth',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'lizard',
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
    '05',
],
    'text_data': 'b2042d7b97f54efcbb75713580544702',
    'rand_digit': 2,
    'rand_number': 0.9249,
    'rand_signed_int': 2,
    'rand_datetime': '2000-03-12T00:17:31.006367+0700',
    'text_array': [
    'b2c210c9c7ff4880a8b50275038e4bfa',
    '9723e933c8624811a6655a2ba97d5317',
],
    'words': 'dolphin squid',
    'nested': {
    'id': 129,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
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
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'rabbit',
    'hippo',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.61086,
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
    '02',
    '01',
],
    'text_data': '7fd3fc3f56c04c86af2889f75bc2962f',
    'rand_digit': 0,
    'rand_number': 0.20833,
    'rand_signed_int': 6,
    'rand_datetime': '2000-11-25 10:12',
    'text_array': [
    'a36c47e041f84f5d9b7f872bbd99e18c',
    '3a6ccd953ec1421fa128eadb5e94f714',
],
    'words': 'panda lobster',
    'nested': {
    'id': 130,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snake',
    'duck',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': [
    29,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': None,
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
    '20',
    '22',
    '14',
    '20',
],
    'text_data': 'aa035ed6feea41a08ed7119612b48859',
    'rand_digit': 4,
    'rand_number': 0.0281,
    'rand_signed_int': 0,
    'rand_datetime': '2000-06-09',
    'text_array': [
    '655e4f583f1c48ea82a92ca2831f06bf',
    '87b3ab0044f84d95a6f2db3f1073a25f',
],
    'words': 'cheetah lizard',
    'nested': {
    'id': 131,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 2,
},
],
},
    'nested_array': [
    [
    -2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'snake',
    'leopard',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': [
    83,
],
    'rand_bool': False,
    'mixed_type': True,
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
    '17',
    '12',
    '03',
    '17',
    '29',
],
    'text_data': '0f2f21cd2fce4a3e89772f926dfb82bb',
    'rand_digit': 3,
    'rand_number': 0.71409,
    'rand_signed_int': 3,
    'rand_datetime': '2000-10-23T23:04:41.994224-0100',
    'text_array': [
    'a468c7ee3b904709be5c3204e3565e26',
    'e48039e876d9410c91f8554a9e8ac836',
],
    'words': 'snail snake',
    'nested': {
    'id': 132,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 6,
},
    {
    'nested_empty': None,
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
    'word': 'lobster',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'gorilla',
    'dog',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': 'snail',
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
    '05',
    '22',
],
    'text_data': '2d5ed9b7fd09490faf9bdea739c037c9',
    'rand_digit': 5,
    'rand_number': 0.53628,
    'rand_signed_int': 4,
    'rand_datetime': '2000-02-13T00:31:21.274202+0200',
    'text_array': [
    '890343bb2f4e4989ba0d5dd297abe4a7',
    '04d9f9f7e0184902bbca66fc49de28cf',
],
    'words': 'fish monkey',
    'nested': {
    'id': 133,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snail',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'pig',
    'wolf',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'frog',
    'maybe_null': 'monkey',
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
    '01',
    '15',
    '29',
    '29',
    '16',
],
    'text_data': 'ba0ddca986b4456cba3a789cd286b890',
    'rand_digit': 6,
    'rand_number': 0.24268,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-26',
    'text_array': [
    '7fa6dcab91cb40a9ae4b7d2e6d0a6f83',
    '886c01329db64edb99867694599799bc',
],
    'words': 'dolphin koala',
    'nested': {
    'id': 134,
    'rand_digit': 6,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'dolphin',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    [
    9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -1,
],
],
    'two_words': [
    'dolphin',
    'bird',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': [
    1,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '09',
    '17',
],
    'text_data': '965a55ebd8ff43c3b1837a46baf80fb2',
    'rand_digit': 4,
    'rand_number': 0.57724,
    'rand_signed_int': -8,
    'rand_datetime': '2000-03-20 04:49:08',
    'text_array': [
    '486771e5658b4606b687b30d883315af',
    '4883a007e23f49149e3edfe47b784d6f',
],
    'words': 'elephant kangaroo',
    'nested': {
    'id': 135,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'wolf',
    'sloth',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': [
    93,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'scorpion',
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
    '14',
    '17',
    '10',
    '11',
    '29',
],
    'text_data': '72ce82c082cd47f99784a3a5e125aa85',
    'rand_digit': 0,
    'rand_number': 0.61721,
    'rand_signed_int': -1,
    'rand_datetime': '2000-01-28 09:54:35.940767',
    'text_array': [
    '6463f866d2464467b57c769a6a3003b0',
    '57f5da9407b04a7d91a3a0d1f698544e',
],
    'words': 'squid lion',
    'nested': {
    'id': 136,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fly',
    'giraffe',
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
    'mixed_type': 9,
    'maybe': 'ant',
    'maybe_null': 'elephant',
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
    '20',
    '28',
    '12',
    '04',
    '14',
],
    'text_data': '84c6a22a26f0495ea25ca90ae53b66e7',
    'rand_digit': 4,
    'rand_number': 0.80249,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-06 02:05',
    'text_array': [
    'ce59d339bf2647a3a56c2f691c3a1450',
    '54100587a762401aab6c460ab030e671',
],
    'words': 'squid turtle',
    'nested': {
    'id': 137,
    'rand_digit': 5,
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
    'word': 'duck',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -5,
],
],
    'two_words': [
    'leopard',
    'lion',
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
    'mixed_type': 8,
    'maybe': 'mouse',
    'maybe_null': 'snail',
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
    '13',
    '25',
    '22',
],
    'text_data': '3e652cec9619465ab4d07ce336527e99',
    'rand_digit': 3,
    'rand_number': 0.24419,
    'rand_signed_int': 5,
    'rand_datetime': '2000-04-13T21:10:34.540192',
    'text_array': [
    '22253f9c376f4fe7a9b040ccc121d0fc',
    'd7a155969bdd477980cb55cafdc430cc',
],
    'words': 'goat whale',
    'nested': {
    'id': 138,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'chicken',
    'goat',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': [
    18,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'dolphin',
    'maybe_null': 'chicken',
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
    '04',
    '19',
    '19',
],
    'text_data': '440bfc424e77470aa9a8b784a629e600',
    'rand_digit': 9,
    'rand_number': 0.63459,
    'rand_signed_int': 0,
    'rand_datetime': '2000-04-07',
    'text_array': [
    '21b1fbe54ac84ff392d808c0338a14dd',
    '9b5b03b26f97440083d3a60fed503078',
],
    'words': 'kangaroo panda',
    'nested': {
    'id': 139,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 8,
},
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
    'hello',
],
    'word': 'cat',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'scorpion',
    'cat',
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
    'mixed_type': 0.99654,
    'maybe': 'mouse',
    'maybe_null': 'koala',
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
    '09',
    '15',
],
    'text_data': 'ab540c41cf9c45cd9334d5e0f5e90fa7',
    'rand_digit': 1,
    'rand_number': 0.34025,
    'rand_signed_int': -7,
    'rand_datetime': '2000-07-12T07:13:15.369353-1000',
    'text_array': [
    '360567400deb4f08aca39975ba24988b',
    'deebb00b2dd8486daba742fa8e2e67fc',
],
    'words': 'rhino ape',
    'nested': {
    'id': 140,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 6,
},
],
},
    'nested_array': [
    [
    -6,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'panda',
    'horse',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'wolf',
    'maybe_null': None,
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
    '01',
    '19',
],
    'text_data': '166bb316ce424652a543aeb9b4fba03d',
    'rand_digit': 3,
    'rand_number': 0.22976,
    'rand_signed_int': 0,
    'rand_datetime': '2000-01-03 10:59:18.450017+1100',
    'text_array': [
    '042232376c0848489abd6c276731ecae',
    '051feeec6b93485092a86497d905b36f',
],
    'words': 'pig koala',
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
    'word': 'tiger',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'camel',
    'lion',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': [
    0,
],
    'rand_bool': False,
    'mixed_type': 0.99976,
    'maybe': 'cow',
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
    '16',
    '15',
],
    'text_data': 'cfd8b46cc12f4fd68db54bd8d94afca8',
    'rand_digit': 6,
    'rand_number': 0.41743,
    'rand_signed_int': 0,
    'rand_datetime': '2000-09-10T05:22:17.757327+0700',
    'text_array': [
    'fa50bf42e994408896b8eca5b99ba7db',
    '7aa89358934c49f08a81b7c77a09c899',
],
    'words': 'mouse mouse',
    'nested': {
    'id': 142,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    10,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'duck',
    'rhino',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': [
    67,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'octopus',
    'maybe_null': 'duck',
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
    '14',
    '22',
    '04',
    '25',
    '07',
],
    'text_data': 'aaf993bd768847ae893b09cf069e6be0',
    'rand_digit': 3,
    'rand_number': 0.35798,
    'rand_signed_int': 3,
    'rand_datetime': '2000-03-25T13:31:11.260552',
    'text_array': [
    'b35aa6b4930344d0b234411ed3e2e4c9',
    '48853e7e2acb4290b9f57d2396fb5413',
],
    'words': 'spider tiger',
    'nested': {
    'id': 143,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'shark',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'dragonfly',
    'koala',
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
    'maybe': 'cheetah',
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
    '06',
    '07',
    '05',
],
    'text_data': 'b2bc7e101f2f48ff97a092b09f580f62',
    'rand_digit': 7,
    'rand_number': 0.71556,
    'rand_signed_int': 3,
    'rand_datetime': '2001-01-23T16:15:19.950393+08:00',
    'text_array': [
    '204f064d0fdc4be0bd3e02e994dd4f67',
    '3cf1195af6ea4b76befebc3da5ce2ba2',
],
    'words': 'grasshopper shark',
    'nested': {
    'id': 144,
    'rand_digit': 8,
    'array': [
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'fox',
    'sheep',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': [
    76,
],
    'rand_bool': False,
    'mixed_type': 4,
    'maybe': 'giraffe',
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
    '29',
    '16',
    '25',
    '23',
    '30',
],
    'text_data': '62c38e758c1247b7b4d54be126221aa4',
    'rand_digit': 1,
    'rand_number': 0.14958,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-01T04:33:22',
    'text_array': [
    '3a654f570bba470c9b32a7c1413023c2',
    'f0462b2efe714ccf862a33e9dfa458cc',
],
    'words': 'cow leopard',
    'nested': {
    'id': 145,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bear',
    'rhino',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'jaguar',
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
    '23',
],
    'text_data': '753e5333550940d5a21670798f908e7a',
    'rand_digit': 0,
    'rand_number': 0.37606,
    'rand_signed_int': 0,
    'rand_datetime': '2001-01-06 18:50:14.625625',
    'text_array': [
    'e7d19c1d4c46462f8a9b697816afb7d0',
    '9d9a065ede9a4c59a26d862705f95b30',
],
    'words': 'giraffe monkey',
    'nested': {
    'id': 146,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'panda',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    8,
],
],
    'two_words': [
    'bird',
    'hyena',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'chicken',
    'maybe_null': 'snail',
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
    'text_data': 'ec49f4cd32bc4c21b68e9aefbc034c99',
    'rand_digit': 3,
    'rand_number': 0.99257,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-17T06:54:28+1100',
    'text_array': [
    '4e87fad692574007ad6f0a4032681b83',
    'ab7dec054402409dbf670bd7e835c93f',
],
    'words': 'spider turtle',
    'nested': {
    'id': 147,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'mouse',
    'butterfly',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
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
    '07',
    '11',
    '11',
    '24',
],
    'text_data': 'cb2d4e256c034364b06798c76e2152e4',
    'rand_digit': 9,
    'rand_number': 0.44094,
    'rand_signed_int': 7,
    'rand_datetime': '2000-08-31 21:04:40.555439-1100',
    'text_array': [
    '1a9e83a2445b45e6ae2560c2823e05ad',
    'dc5dd4dd50af46adafaa4c053af8c2c2',
],
    'words': 'turtle pig',
    'nested': {
    'id': 148,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ape',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'lobster',
    'scorpion',
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
    'mixed_type': 'deer',
    'maybe_null': 'crab',
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
    '20',
],
    'text_data': '1fb2808d3a4c4d1ca2d1bb35c1f9d234',
    'rand_digit': 0,
    'rand_number': 0.53655,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-14T02:11:26+0400',
    'text_array': [
    '7aaad7a7ed3f4273b2738168b957ed72',
    'bf83f11331534cdd8ec27270a0e89fef',
],
    'words': 'chicken frog',
    'nested': {
    'id': 149,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'lizard',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'grasshopper',
    'hippo',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': [
    19,
],
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'mouse',
    'maybe_null': 'scorpion',
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
    '03',
    '17',
    '23',
],
    'text_data': '6c6f3864368847eb84eb9b5fcfcf190b',
    'rand_digit': 3,
    'rand_number': 0.12954,
    'rand_signed_int': -3,
    'rand_datetime': '2000-08-30 20:21:40-0200',
    'text_array': [
    'bbc0d66067784c2fac6143673d30f5ea',
    'ddea8a2ad1134e58967b934ff2e8813c',
],
    'words': 'octopus hippo',
    'nested': {
    'id': 150,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 3,
},
    {
    'nested_empty': None,
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
    'word': 'leopard',
    'number': 9,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_4,2__',
    'two_words': [
    'rabbit',
    'pig',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.66741,
    'maybe': 'gorilla',
    'maybe_null': None,
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
    '19',
    '18',
],
    'text_data': 'b3acd5158044437a953f781bc56745ed',
    'rand_digit': 6,
    'rand_number': 0.39408,
    'rand_signed_int': 9,
    'rand_datetime': '2000-06-24',
    'text_array': [
    '892b2060e6174169ae5f6483cab5f26c',
    '19dff94589334018b6d86dc38a553bbe',
],
    'words': 'tiger tiger',
    'nested': {
    'id': 151,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 9,
},
],
},
    'nested_array': [
    [
    7,
],
    [
],
],
    'two_words': [
    'monkey',
    'mosquito',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.78519,
    'maybe': 'tiger',
    'maybe_null': 'mouse',
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
    '15',
    '19',
    '07',
],
    'text_data': 'f6c7b35db72d45bf9da3da3bad176837',
    'rand_digit': 0,
    'rand_number': 0.6241,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-09T21:09:11-1000',
    'text_array': [
    'd23c05135faa43fb8e76444d067962c6',
    'cc47a828c74e48728f53b5eb58b0bb4c',
],
    'words': 'crab frog',
    'nested': {
    'id': 152,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
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
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'cow',
    'mosquito',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': [
    92,
],
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'fly',
    'maybe_null': 'goat',
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
    '12',
],
    'text_data': '9b000034423945bfa4b276dfb6e8f293',
    'rand_digit': 2,
    'rand_number': 0.24812,
    'rand_signed_int': -1,
    'rand_datetime': '2000-03-18 10:07',
    'text_array': [
    'c99f47a752724ef4ba25ce5f208f3048',
    '905ac89bbf644b99ba258598f1ccd504',
],
    'words': 'tiger dragonfly',
    'nested': {
    'id': 153,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'panda',
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
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -9,
],
],
    'two_words': [
    'grasshopper',
    'goat',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': [
    26,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '08',
    '26',
    '04',
],
    'text_data': 'af992e6ab7c341d3ae21bbfd7583aac5',
    'rand_digit': 9,
    'rand_number': 0.34806,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-31T02:45:13+0100',
    'text_array': [
    '5a959dce6edc4146919ffe31948a2b7d',
    '045a14ad3813485a8e70bb90ec0c52e8',
],
    'words': 'panda mouse',
    'nested': {
    'id': 154,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 3,
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
    'word': 'zebra',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snail',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'sloth',
    'monkey',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 1,
    'maybe': 'fly',
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
    '05',
],
    'text_data': 'd02020cf38954df9a64eb128d98dca17',
    'rand_digit': 0,
    'rand_number': 0.03569,
    'rand_signed_int': 10,
    'rand_datetime': '2000-05-24 01:22:05.111630',
    'text_array': [
    '501c1a7da72e41e1b6d5b0575533aee1',
    '37f9af0f96df44ffa57c2db08191d68c',
],
    'words': 'kangaroo octopus',
    'nested': {
    'id': 155,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'bear',
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
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fly',
    'tiger',
],
    'city': {
    'name': 'Athens',
    'geo': {
    'lat': 37.98381,
    'lon': 23.727539,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 3,
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
    '11',
    '12',
    '15',
],
    'text_data': '69cc645dde9c47eb9215a8cc8e0672e4',
    'rand_digit': 4,
    'rand_number': 0.09016,
    'rand_signed_int': -4,
    'rand_datetime': '2000-05-23',
    'text_array': [
    'a04aebb01cbc46c19a6b676921dc0e31',
    '7ed34792353f479aada39fd4e6670b01',
],
    'words': 'squid frog',
    'nested': {
    'id': 156,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,3__',
    'two_words': [
    'mouse',
    'hyena',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'cheetah',
    'maybe_null': 'spider',
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
    '18',
    '27',
    '08',
    '20',
],
    'text_data': '9f57fcd3742b413a99c1bac7fc892e11',
    'rand_digit': 1,
    'rand_number': 0.99028,
    'rand_signed_int': 5,
    'rand_datetime': '2000-02-03 09:02:54.500518',
    'text_array': [
    '0fbe25f658ac499ba318e60edff2f1ce',
    '8a8ba43935ac4e10b0482159cb76b506',
],
    'words': 'hyena turtle',
    'nested': {
    'id': 157,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dolphin',
    'camel',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': [
    56,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'bear',
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
    '05',
],
    'text_data': '96c4acbccb934a5787d74e8736c342d4',
    'rand_digit': 7,
    'rand_number': 0.56716,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-07',
    'text_array': [
    '8088d0ae37fe42ca96622f96ca10eb0a',
    '2a269bcad5574888a1f1e49cbf06b842',
],
    'words': 'elephant zebra',
    'nested': {
    'id': 158,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
    -3,
],
],
    'two_words': [
    'grasshopper',
    'dragonfly',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cat',
    'maybe_null': 'fox',
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
    '12',
],
    'text_data': 'dd931f07f12b4b46b6bac6bdcc4efdc0',
    'rand_digit': 7,
    'rand_number': 0.51758,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-24T18:51:54.288774',
    'text_array': [
    '8b26b9125b2b4eea93d5ccf1bf54d459',
    'a0bcd70ee09e4427b132647a7b35e198',
],
    'words': 'cat frog',
    'nested': {
    'id': 159,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bear',
    'goat',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.64493,
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
    '13',
    '16',
],
    'text_data': '380a39d6b8ef48c98c9fa6b8a0a9d9bc',
    'rand_digit': 4,
    'rand_number': 0.46264,
    'rand_signed_int': 3,
    'rand_datetime': '2000-04-14 10:23:10.006861',
    'text_array': [
    'ad8dd7aa651c4befabd6c47e900947b1',
    'a9d532c59abd4a278338f53f02a5abfb',
],
    'words': 'chicken lizard',
    'nested': {
    'id': 160,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ant',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'kangaroo',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'crab',
    'spider',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'hyena',
    'maybe': 'squid',
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
    'text_data': '21622a84c8184ec995d558f33b4b8212',
    'rand_digit': 6,
    'rand_number': 0.89386,
    'rand_signed_int': 7,
    'rand_datetime': '2001-01-29T19:08:29.803650+07:00',
    'text_array': [
    '125dca9f580d445da2e41c0fc2403880',
    '4ac4d3bafc194806b7cd18f52820dca8',
],
    'words': 'ape panda',
    'nested': {
    'id': 161,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 10,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'lion',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'monkey',
    'bear',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'kangaroo',
    'maybe': 'frog',
    'maybe_null': 'chicken',
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
    '19',
],
    'text_data': '241a59be8d69484782854805ffdc7788',
    'rand_digit': 6,
    'rand_number': 0.73241,
    'rand_signed_int': -6,
    'rand_datetime': '2000-03-21T02:25:00',
    'text_array': [
    '2a1fe1a8096b4757a380aefb93ac98e1',
    'd193552e6b0b44818d4e47dbbeaf4628',
],
    'words': 'bear whale',
    'nested': {
    'id': 162,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
    6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'elephant',
    'lizard',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'sloth',
    'maybe_null': 'pig',
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
    '15',
    '23',
    '25',
    '03',
    '04',
],
    'text_data': '7ad95ddb96ad42a584f84243bcea3cb4',
    'rand_digit': 5,
    'rand_number': 0.73421,
    'rand_signed_int': -2,
    'rand_datetime': '2000-01-17 02:06',
    'text_array': [
    'fadd356444794f8a96d7b70a32c8a06d',
    '8872e1d111a940c88ddb0d43b135036d',
],
    'words': 'rabbit deer',
    'nested': {
    'id': 163,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bird',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'jaguar',
    'lizard',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': [
    8,
],
    'rand_bool': True,
    'mixed_type': 0.25593,
    'maybe': 'ape',
    'maybe_null': 'kangaroo',
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
    'content-length': '136987',
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
    '11',
    '16',
    '03',
    '20',
],
    'text_data': 'dfb19cef997b48d6a7c839ed1e0857cf',
    'rand_digit': 3,
    'rand_number': 0.86146,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-05',
    'text_array': [
    '1b6822997d96474797834c81261c83b0',
    '443fe42590154c1b9bda0e8b6849f6ab',
],
    'words': 'cat whale',
    'nested': {
    'id': 100,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 3,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_4,3__',
    'two_words': [
    'koala',
    'bear',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'grasshopper',
    'maybe_null': 'elephant',
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
    '05',
    '08',
    '25',
    '15',
],
    'text_data': '508b7ff9a83d46cc849af73c286ce7e8',
    'rand_digit': 9,
    'rand_number': 0.19286,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-02T13:58:22.158306-0500',
    'text_array': [
    'bf40d2ef0dee46b2b8eed8738edf5eb7',
    'de80ef821be74710bd7aad297827944e',
],
    'words': 'octopus lobster',
    'nested': {
    'id': 101,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'koala',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': [
    82,
],
    'rand_bool': False,
    'mixed_type': 0.76062,
    'maybe_null': 'zebra',
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
    '16',
    '03',
    '07',
],
    'text_data': '826db21c9b184412b68067c79521230e',
    'rand_digit': 1,
    'rand_number': 0.74991,
    'rand_signed_int': 8,
    'rand_datetime': '2000-08-19',
    'text_array': [
    'c055f75f008849999e1cc18a39eab7cf',
    'a813280631d54849be20a3e3d26aaef2',
],
    'words': 'kangaroo fox',
    'nested': {
    'id': 102,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'octopus',
    'pig',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
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
    '08',
    '10',
],
    'text_data': '175f545c266c4e29aae3836d2e567701',
    'rand_digit': 9,
    'rand_number': 0.08651,
    'rand_signed_int': -6,
    'rand_datetime': '2000-01-27T12:17:08.034588',
    'text_array': [
    '67d6244f3cde49318a9c43a33ff0b3e4',
    'c6e6eb3c43ff427bbe2685010b09f289',
],
    'words': 'crab lobster',
    'nested': {
    'id': 103,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'frog',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'turtle',
    'sheep',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': [
    25,
],
    'rand_bool': False,
    'mixed_type': 0.89769,
    'maybe': 'rhino',
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
    '22',
    '28',
    '19',
],
    'text_data': '5d1ec8a997084c189339ccbaa833ea2c',
    'rand_digit': 5,
    'rand_number': 0.51926,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-17 06:57:48.113030+0700',
    'text_array': [
    'cf56f2cd1cb74f62887b07f9dac8b9f8',
    'a3dacdc76aa844d7b4c43c82c593fc36',
],
    'words': 'panda crab',
    'nested': {
    'id': 104,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cat',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'bee',
    'wolf',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'lobster',
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
    '09',
    '08',
    '20',
],
    'text_data': '8f7ebea1bbf44fb8b12fb41a2fe18b93',
    'rand_digit': 0,
    'rand_number': 0.49623,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-10T19:53:33',
    'text_array': [
    '939ab231d9964055972bbc71f9605034',
    '67ad4cacfdd24142a77478c324cbbc38',
],
    'words': 'cow spider',
    'nested': {
    'id': 105,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 3,
},
],
},
    'nested_array': [
    [
    5,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bee',
    'sloth',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'fox',
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
    '15',
    '01',
    '08',
    '26',
],
    'text_data': 'e443140d84e647608a3045216e977aff',
    'rand_digit': 4,
    'rand_number': 0.06361,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-22T01:22:07.874653',
    'text_array': [
    '6c6037d55eff4fe5a998ed82f3c133a7',
    '59736ed81a5043cd9a37ece26c3f65f3',
],
    'words': 'panda snake',
    'nested': {
    'id': 106,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    8,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fox',
    'turtle',
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
    'mixed_type': True,
    'maybe_null': 'bear',
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
],
    'text_data': 'c69b2c215312461d9eda1b23047b4c18',
    'rand_digit': 7,
    'rand_number': 0.44524,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-16 01:38:37',
    'text_array': [
    'dbbeab7cbc55479c9bc523b3f669aa7b',
    '26e137ef151040d685ced2994a64d42a',
],
    'words': 'bee camel',
    'nested': {
    'id': 107,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'dog',
    'deer',
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
    'mixed_type': 3,
    'maybe': 'frog',
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
    '22',
    '23',
    '16',
    '25',
    '08',
],
    'text_data': '3a66522949a840cbb3dde61058e2bad0',
    'rand_digit': 5,
    'rand_number': 0.11207,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-08T23:24:04-0900',
    'text_array': [
    '0047fe5ce51146b7bb23fb020176b9cc',
    'df01a7ecb05349a98eaf88ee171e6dbc',
],
    'words': 'grasshopper monkey',
    'nested': {
    'id': 108,
    'rand_digit': 2,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 7,
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
    'word': 'elephant',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -3,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    4,
],
],
    'two_words': [
    'fly',
    'dog',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'rhino',
    'maybe_null': None,
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
    '10',
    '13',
],
    'text_data': '28fed0a9d4d545d3b94272ee37dd6d0a',
    'rand_digit': 7,
    'rand_number': 0.98509,
    'rand_signed_int': 8,
    'rand_datetime': '2000-07-08T10:12:43.314387',
    'text_array': [
    '94c6a4f5a01b4511bc300b5818bc2ffc',
    '43209b71004b423494210ca523cd0463',
],
    'words': 'bee duck',
    'nested': {
    'id': 109,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'monkey',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'fly',
    'leopard',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.03162,
    'maybe_null': 'leopard',
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
    '11',
],
    'text_data': '3729986936094f7abbe7e4c15f8cb5db',
    'rand_digit': 5,
    'rand_number': 0.17723,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-12T06:05:30.770679',
    'text_array': [
    '00607789161e43c19c3ba5bd4a10f8d8',
    '9180704f1f0f4385a6efb668f09e2bb0',
],
    'words': 'chicken hippo',
    'nested': {
    'id': 110,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    0,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'spider',
    'elephant',
],
    'city': {
    'name': 'Zurich',
    'geo': {
    'lat': 47.376887,
    'lon': 8.541694,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 7,
    'maybe': 'deer',
    'maybe_null': 'whale',
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
    '11',
    '26',
    '18',
    '14',
    '12',
],
    'text_data': 'd6b50b419cde4506a2952bd8fa9a0dae',
    'rand_digit': 4,
    'rand_number': 0.76639,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-09 20:20:27+0700',
    'text_array': [
    '473704e0bb184414a3845e455a3e51ce',
    '8c8092b59f9f4e7da2590f85a6112615',
],
    'words': 'kangaroo cow',
    'nested': {
    'id': 111,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'dog',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'ant',
    'cat',
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
    'maybe_null': 'wolf',
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
    '01',
    '04',
],
    'text_data': '2d3e511f00394723b4e334177291f00b',
    'rand_digit': 1,
    'rand_number': 0.89697,
    'rand_signed_int': 0,
    'rand_datetime': '2000-11-22 15:55:28.224500',
    'text_array': [
    'e7948f85af08419abb7ee70f26079d0e',
    '2714f4cfa1a44a9eabb28dae097fb83e',
],
    'words': 'fly turtle',
    'nested': {
    'id': 112,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'squid',
    'lizard',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': [
    39,
],
    'rand_bool': False,
    'mixed_type': 5,
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
],
    'text_data': '3a07a42c4c1c479ea9a1a2e76757f311',
    'rand_digit': 2,
    'rand_number': 0.22562,
    'rand_signed_int': 2,
    'rand_datetime': '2000-09-23 13:46',
    'text_array': [
    '8db37934f91a4256a8ef673e075a74b2',
    '204548b2709b4b0eb33d7180d98c3aea',
],
    'words': 'koala sheep',
    'nested': {
    'id': 113,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'cow',
    'gorilla',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 9,
    'maybe_null': None,
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
],
    'text_data': '37b385690ee64d338b8ff8be77da992c',
    'rand_digit': 4,
    'rand_number': 0.72368,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-27T19:29:32.362357-0900',
    'text_array': [
    '6caade3a1b3a49afa9983154ed787316',
    'fefbaf13dbc34578a58ab536709f4c37',
],
    'words': 'fly dog',
    'nested': {
    'id': 114,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
    'number': 4,
},
],
},
    'nested_array': [
    [
    -7,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'rabbit',
    'bee',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'deer',
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
    '10',
],
    'text_data': 'c892630a2bf545d78314a1346797f2b0',
    'rand_digit': 4,
    'rand_number': 0.56173,
    'rand_signed_int': 1,
    'rand_datetime': '2000-12-28T08:13:42.772260',
    'text_array': [
    '18cef9ec20d5446f962c76055b369635',
    'cdad447d05bd42c79e5af07e255e2d73',
],
    'words': 'koala spider',
    'nested': {
    'id': 115,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 7,
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
    'hello',
],
    'word': 'elephant',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'pig',
    'fox',
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
    'mixed_type': 6,
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
    '16',
    '28',
    '19',
    '25',
],
    'text_data': '8cb08f4521dd4915ade34914297af2c2',
    'rand_digit': 2,
    'rand_number': 0.68646,
    'rand_signed_int': -2,
    'rand_datetime': '2000-09-07T03:29:48.957664+0600',
    'text_array': [
    'a68e952950774820bf4396c77a583c8d',
    '5c9da81f2d84480bb462a8af94c9f6a3',
],
    'words': 'octopus gorilla',
    'nested': {
    'id': 116,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'gorilla',
    'fox',
],
    'city': {
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'mosquito',
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
    '03',
    '28',
    '06',
    '09',
    '10',
],
    'text_data': '04a12fd70d964577b3d2534c77f2cd55',
    'rand_digit': 6,
    'rand_number': 0.53912,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-24T03:26:23.183164',
    'text_array': [
    '3ed56945d32a4206bf0c2a3484dd370a',
    'f435a758be2d4ae2a972cf61c1609f57',
],
    'words': 'shark dog',
    'nested': {
    'id': 117,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'monkey',
    'frog',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '07',
    '04',
    '21',
    '11',
    '28',
],
    'text_data': 'd3604df85195406f8dc5852e39633bd8',
    'rand_digit': 6,
    'rand_number': 0.64071,
    'rand_signed_int': 2,
    'rand_datetime': '2000-05-02 09:36',
    'text_array': [
    '5432821c1470464ca08de69407005d7a',
    '6c7574985c66407085a54201df00d054',
],
    'words': 'zebra whale',
    'nested': {
    'id': 118,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'wolf',
    'number': 2,
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
    'word': 'camel',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    0,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snail',
    'sheep',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'sheep',
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
],
    'text_data': '0e7449948d694ed4b5ccc69ef2c815b7',
    'rand_digit': 7,
    'rand_number': 0.93606,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-05T10:10:57+0000',
    'text_array': [
    'ad87c264ecc240b3b3a7e39a25309315',
    'be306dac1d7f4572b67c64aa13cd86f5',
],
    'words': 'grasshopper monkey',
    'nested': {
    'id': 119,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fox',
    'number': 9,
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
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'zebra',
    'ladybug',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
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
    '02',
    '05',
    '15',
    '23',
    '22',
],
    'text_data': '6533befc1dfa45c590832b15f00c077e',
    'rand_digit': 8,
    'rand_number': 0.15003,
    'rand_signed_int': -8,
    'rand_datetime': '2000-08-01 23:09:17',
    'text_array': [
    '5d03e8bc4160434a9df12b45af6a95d6',
    'bcc33a8af317434e906ceecfab073d38',
],
    'words': 'cow crab',
    'nested': {
    'id': 120,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'cat',
    'ape',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': [
    43,
],
    'rand_bool': False,
    'mixed_type': 'zebra',
    'maybe': 'scorpion',
    'maybe_null': None,
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
    '16',
    '29',
    '02',
],
    'text_data': '6d9cdbdb934e4d32b10a814c798d455b',
    'rand_digit': 4,
    'rand_number': 0.61979,
    'rand_signed_int': 5,
    'rand_datetime': '2000-11-12T15:27:17.875082+0000',
    'text_array': [
    'f90b3fb0cc3e4f3781af40e91788e962',
    'e4071c87687d44648aab3457c272925f',
],
    'words': 'dragonfly lizard',
    'nested': {
    'id': 121,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 6,
},
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
    'word': 'dog',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'chicken',
    'lizard',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': [
    65,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'octopus',
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
    '09',
    '16',
],
    'text_data': '047a678a900e4f5aa0d6c7f940d2137c',
    'rand_digit': 2,
    'rand_number': 0.27864,
    'rand_signed_int': 1,
    'rand_datetime': '2001-01-13T14:21:57.499241',
    'text_array': [
    '2811debb61e54d36a5b525aa972f76c5',
    'f67fdab21d6b432c981a2f750e5eafce',
],
    'words': 'fly zebra',
    'nested': {
    'id': 122,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'snake',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'cat',
    'chicken',
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
    'mixed_type': 1,
    'maybe': 'fox',
    'maybe_null': None,
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
    '26',
    '28',
],
    'text_data': '2c8b357f26d54dfa8ff554d167516451',
    'rand_digit': 5,
    'rand_number': 0.39586,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-23 07:00:07-0100',
    'text_array': [
    '1d5b3b97bad244e1826a4ced950f738c',
    'f7bae6f16a8240deb5bca4be14608054',
],
    'words': 'panda lobster',
    'nested': {
    'id': 123,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'goat',
    'dog',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.43109,
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
    '24',
    '16',
],
    'text_data': '7f4cbf173b0541ec915bbfa988ca2c4d',
    'rand_digit': 1,
    'rand_number': 0.92672,
    'rand_signed_int': 7,
    'rand_datetime': '2000-09-09T11:18:26+0900',
    'text_array': [
    '2a9cab95ac6b49fda0e14f3c06a379fe',
    '7085f6f100d548cab3f0be77798eab8b',
],
    'words': 'turtle lion',
    'nested': {
    'id': 124,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 8,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'deer',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -2,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lion',
    'zebra',
],
    'city': {
    'name': 'Barcelona',
    'geo': {
    'lat': 41.385064,
    'lon': 2.173403,
},
},
    'rand_tuple': [
    16,
],
    'rand_bool': False,
    'mixed_type': 'crab',
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
],
    'text_data': 'ee0829143cf94eca8feedf40c91133a7',
    'rand_digit': 6,
    'rand_number': 0.32388,
    'rand_signed_int': -10,
    'rand_datetime': '2000-07-01T10:07:43.932194',
    'text_array': [
    '55f8442097224cfdae87ba245bc37bca',
    'd4054e343a8146c89ad6c3fe7622802e',
],
    'words': 'ape monkey',
    'nested': {
    'id': 125,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lion',
    'tiger',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'gorilla',
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
    '15',
    '18',
],
    'text_data': '2cdec746d0484ef6a4d049ed64c50db3',
    'rand_digit': 3,
    'rand_number': 0.4971,
    'rand_signed_int': 0,
    'rand_datetime': '2000-07-15 07:49:29+0600',
    'text_array': [
    '8e8fa1b7ae79452e9b950273dbf262f7',
    '0f67e6afb09c47d1843ea48b9d39d376',
],
    'words': 'hippo dolphin',
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
    'word': 'giraffe',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'squid',
    'number': 5,
},
],
},
    'nested_array': [
    [
    -2,
],
],
    'two_words': [
    'octopus',
    'camel',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 2,
    'maybe': 'sheep',
    'maybe_null': None,
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
    '16',
    '20',
    '17',
    '25',
],
    'text_data': 'f978b4b4489d40648024a57cf397d72e',
    'rand_digit': 5,
    'rand_number': 0.70261,
    'rand_signed_int': -5,
    'rand_datetime': '2000-01-21 00:40',
    'text_array': [
    '5e74fa0a46a44570bd4e33c5a495576b',
    '8ed72626a4fd48e49e7dc43d324bb762',
],
    'words': 'cow deer',
    'nested': {
    'id': 127,
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
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'ape',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'horse',
    'mosquito',
],
    'city': {
    'name': 'Kuala Lumpur',
    'geo': {
    'lat': 3.139003,
    'lon': 101.686855,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'lion',
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
],
    'text_data': 'a2c0f1b603884f96aeb32a68dc6ffe4a',
    'rand_digit': 6,
    'rand_number': 0.79025,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-11 20:13',
    'text_array': [
    '139ee4e195c4489eb4f818441ba846e4',
    'ef4e0e3cdc4a4d0caaaabbe14142d7e9',
],
    'words': 'goat spider',
    'nested': {
    'id': 128,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
    8,
],
    [
],
    [
],
    [
],
],
    'two_words': [
    'dragonfly',
    'dragonfly',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 'lobster',
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
    '10',
    '21',
    '05',
],
    'text_data': '7f60a7efd8524723945219299fa82657',
    'rand_digit': 9,
    'rand_number': 0.50502,
    'rand_signed_int': 3,
    'rand_datetime': '2000-01-16T06:47:01+0700',
    'text_array': [
    'cbcfcf8f300e4d7184d6175eedc54db8',
    '8b4c7bfb8a5244238a7bdc099e553c4b',
],
    'words': 'sloth snake',
    'nested': {
    'id': 129,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'duck',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'wolf',
    'zebra',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': [
    84,
],
    'rand_bool': False,
    'mixed_type': 6,
    'maybe': 'hyena',
    'maybe_null': 'goat',
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
    '17',
    '03',
    '28',
    '14',
    '13',
],
    'text_data': 'c6c100a3cd1d439398b2c6ae9dc949dd',
    'rand_digit': 5,
    'rand_number': 0.91522,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-31',
    'text_array': [
    'cfab30b778de408a972147f6a6cbb7b0',
    'f596cfdaad46457bb4f7d7d7f0ba222f',
],
    'words': 'lizard goat',
    'nested': {
    'id': 130,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
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
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'squid',
    'crab',
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
    'mixed_type': 5,
    'maybe_null': 'hippo',
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
    '01',
    '18',
    '25',
],
    'text_data': '2eaf606a4dd749a2ac2790df81cdcf95',
    'rand_digit': 3,
    'rand_number': 0.68631,
    'rand_signed_int': 4,
    'rand_datetime': '2000-08-27T01:37:20.878037',
    'text_array': [
    '41378632f2504192b8ebc2ed493bb81a',
    '077f19df60704bfa87c2fa05cfa878c4',
],
    'words': 'octopus frog',
    'nested': {
    'id': 131,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lion',
    'butterfly',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'fox',
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
    '08',
],
    'text_data': '5cb77dcb03fa4f7f9b1b7c2b2e655459',
    'rand_digit': 6,
    'rand_number': 0.2453,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-07T19:48:46.972825-1000',
    'text_array': [
    '9388cb6d892d4151b1a6a767f99f794b',
    '004fda4b4d334d38a33af6722244a89f',
],
    'words': 'ape dog',
    'nested': {
    'id': 132,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'spider',
    'lion',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
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
    '16',
    '08',
    '22',
],
    'text_data': '796e43a96af04300a093318ef5f59605',
    'rand_digit': 2,
    'rand_number': 0.73074,
    'rand_signed_int': 1,
    'rand_datetime': '2000-09-30T03:23:31.300117-0700',
    'text_array': [
    '8458622b737541e2be31ccbfb95e2a93',
    '9c61f8ec321842e881a4340588581e50',
],
    'words': 'fox grasshopper',
    'nested': {
    'id': 133,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'crab',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'hippo',
    'lizard',
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
],
    'text_data': '42ba0ad8b64a4097b37e368ac118121c',
    'rand_digit': 4,
    'rand_number': 0.69475,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-24 03:35',
    'text_array': [
    'b27b65200a494ae6a1e7279c93e1a80a',
    '2bb805036ecf48c7a0a137f0a092ecc0',
],
    'words': 'dolphin lobster',
    'nested': {
    'id': 134,
    'rand_digit': 7,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'dragonfly',
    'duck',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'bee',
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
    '02',
    '22',
    '09',
],
    'text_data': 'e200ea9ae6984794b5b79634927a8101',
    'rand_digit': 3,
    'rand_number': 0.80315,
    'rand_signed_int': -2,
    'rand_datetime': '2000-09-19T14:50:47',
    'text_array': [
    '50a85efe897a4624b1c32834226957e6',
    '0878195ae9dd4384ae328ae2ae98c4ed',
],
    'words': 'tiger snake',
    'nested': {
    'id': 135,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'goat',
    'squid',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    'text_data': '644b6fe0ddb54e7baa9659e44f509d71',
    'rand_digit': 6,
    'rand_number': 0.25948,
    'rand_signed_int': 7,
    'rand_datetime': '2000-06-02 22:06:55',
    'text_array': [
    'b3646b595ef04d10bfcc69130ff5da67',
    'b1ddf62ffbc04c408f75a00b0e3900c7',
],
    'words': 'chicken wolf',
    'nested': {
    'id': 136,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'turtle',
    'zebra',
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
    'mixed_type': 0.65777,
    'maybe_null': 'wolf',
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
    '15',
    '20',
    '15',
    '15',
    '13',
],
    'text_data': '4bd5200053d04112aea4f7d5b2fbd2db',
    'rand_digit': 2,
    'rand_number': 0.0651,
    'rand_signed_int': 1,
    'rand_datetime': '2000-10-21 23:38:34',
    'text_array': [
    '593d41e3952f4bc78b125beaee4ad2a6',
    'bda55ff8e87a43728bdcce144fbeb820',
],
    'words': 'deer crab',
    'nested': {
    'id': 137,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lizard',
    'lizard',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'panda',
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
    '27',
    '30',
    '02',
],
    'text_data': '2c1fe01915a74fb58ce2f3ecced147ca',
    'rand_digit': 4,
    'rand_number': 0.16699,
    'rand_signed_int': -6,
    'rand_datetime': '2001-01-14 06:27:52-1100',
    'text_array': [
    'c3b3fe712694466bb94cdda53ff80fb3',
    'd6bcc798832e43ee8ddebbea3c927cf1',
],
    'words': 'frog giraffe',
    'nested': {
    'id': 138,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 3,
},
],
},
    'nested_array': [
    [
    9,
],
],
    'two_words': [
    'octopus',
    'panda',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'whale',
    'maybe_null': None,
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
    '28',
],
    'text_data': '45ad1c91e8f641929751a7e854234763',
    'rand_digit': 3,
    'rand_number': 0.72463,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-11 22:58',
    'text_array': [
    '1512f4d9d2f646ecb9bacc194554aa40',
    '8b4eed7c5c294687ae4495dfa8b48ff9',
],
    'words': 'frog goat',
    'nested': {
    'id': 139,
    'rand_digit': 6,
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
    'word': 'goat',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'hippo',
    'zebra',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': [
    93,
],
    'rand_bool': True,
    'mixed_type': False,
    'maybe_null': 'chicken',
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
    'text_data': '02f4644754474a669e2a7c67ea1d2e79',
    'rand_digit': 7,
    'rand_number': 0.81133,
    'rand_signed_int': 5,
    'rand_datetime': '2000-08-27T22:57:07.889733+1100',
    'text_array': [
    '70d5bef8b30f4a0f92e5cdfe90d6468a',
    '0526ed2043e641eda3e7c2a01d250c49',
],
    'words': 'rhino tiger',
    'nested': {
    'id': 140,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bird',
    'horse',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'jaguar',
    'maybe_null': 'hippo',
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
    '13',
],
    'text_data': '22808d39449d41fb8a25c920f3355b79',
    'rand_digit': 2,
    'rand_number': 0.89105,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-18',
    'text_array': [
    '764649e6771e40e1bd39df11da9028db',
    'c1a0128b6a9c4fc193aca4052b1e3dca',
],
    'words': 'koala cat',
    'nested': {
    'id': 141,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 6,
},
    {
    'nested_empty': None,
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
],
    'word': 'wolf',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'camel',
    'hippo',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': [
    2,
],
    'rand_bool': False,
    'mixed_type': 0.06051,
    'maybe_null': None,
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
    '10',
    '15',
    '04',
],
    'text_data': '048b6a0e7950410297ca31a55cb8e013',
    'rand_digit': 7,
    'rand_number': 0.01407,
    'rand_signed_int': -8,
    'rand_datetime': '2000-03-29 18:54:45.472051-1200',
    'text_array': [
    'f1a16b4a0942431db6c9e47510321381',
    '6c173b512ce742af9b45bd8eba6185d6',
],
    'words': 'whale koala',
    'nested': {
    'id': 142,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dragonfly',
    'cow',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
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
    '20',
    '09',
],
    'text_data': 'd987b8241132433e9b0fe9ac9d7a0b17',
    'rand_digit': 9,
    'rand_number': 0.98941,
    'rand_signed_int': 0,
    'rand_datetime': '2000-12-19 02:30',
    'text_array': [
    'b81f26172d3e433e821c9aef82f5a33c',
    '39ccef802c3d447c9774b086733af4f3',
],
    'words': 'gorilla koala',
    'nested': {
    'id': 143,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'bear',
    'rhino',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': [
    85,
],
    'rand_bool': True,
    'mixed_type': False,
    'maybe_null': 'sloth',
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
    '18',
    '19',
    '24',
    '09',
],
    'text_data': '7341953a20db45608def72d2c7e18115',
    'rand_digit': 1,
    'rand_number': 0.02955,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-20 18:36:41.587030-0200',
    'text_array': [
    '4b578ab0b9bb4e76b93f4a19eb279058',
    '94decab3984f4648af3003428b24db43',
],
    'words': 'pig dragonfly',
    'nested': {
    'id': 144,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'rhino',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'snail',
    'maybe_null': 'ant',
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
    '01',
    '15',
    '22',
    '21',
],
    'text_data': '6123c2d9f6fd4e5d8933f08b2b749415',
    'rand_digit': 4,
    'rand_number': 0.07108,
    'rand_signed_int': 7,
    'rand_datetime': '2001-01-18T20:53:03',
    'text_array': [
    '993c62acc03f45fb887510c38d736e56',
    'e90ad23eb50b4514bcf2ef7f9f069e89',
],
    'words': 'dolphin lion',
    'nested': {
    'id': 145,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    5,
],
],
    'two_words': [
    'bee',
    'lizard',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
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
    '20',
],
    'text_data': '9aaf304adb04451692418f96af0b2f5d',
    'rand_digit': 9,
    'rand_number': 0.5891,
    'rand_signed_int': -7,
    'rand_datetime': '2000-03-29T06:33:02.213475',
    'text_array': [
    '6251e319fbe1401b9ebcf223c0d7e2d0',
    '02d0b0123e614318ba884c01cb3becde',
],
    'words': 'fox hyena',
    'nested': {
    'id': 146,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,2__',
    'two_words': [
    'duck',
    'lion',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'dragonfly',
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
    '25',
],
    'text_data': '90a1202dd36d430f98d96f88c55530d4',
    'rand_digit': 3,
    'rand_number': 0.56591,
    'rand_signed_int': -1,
    'rand_datetime': '2000-10-04T02:49:56',
    'text_array': [
    '24a333d35243494fb6e6c874f60f5ccd',
    '8c7521235104405ea1390e520c825c75',
],
    'words': 'duck camel',
    'nested': {
    'id': 147,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'camel',
    'rhino',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'jaguar',
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
    '09',
    '07',
],
    'text_data': '1351ee81f4dd4ecdacb817337cbe7c1e',
    'rand_digit': 8,
    'rand_number': 0.16328,
    'rand_signed_int': 5,
    'rand_datetime': '2000-04-08T09:06:11.424248-1000',
    'text_array': [
    '3cdad61242274053a7da14f7e30542b4',
    'ce8f85f5616e45fbb4b9d485a1e85b9c',
],
    'words': 'squid ant',
    'nested': {
    'id': 148,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'goat',
    'bear',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 'hyena',
    'maybe': 'bear',
    'maybe_null': None,
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
    '11',
],
    'text_data': 'c948c0caca874d6395e4b5ca52cd1e12',
    'rand_digit': 7,
    'rand_number': 0.84285,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-27T15:30:46+0300',
    'text_array': [
    'a7d2218568a44e51985db49424f76f27',
    '9ae5b68fb9a74b4f82d2aa40f226d30b',
],
    'words': 'squid lizard',
    'nested': {
    'id': 149,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 7,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fox',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'monkey',
    'cat',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'lizard',
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
    '20',
    '16',
    '27',
    '27',
    '24',
],
    'text_data': '70060ce6132a4c2891cbecb339869880',
    'rand_digit': 6,
    'rand_number': 0.1312,
    'rand_signed_int': 1,
    'rand_datetime': '2000-09-05T09:19:40.335611-0500',
    'text_array': [
    'fbee8c8a2b17461fb53290fe0ac7a390',
    '88bee83cb91b4de6aae84e072f23f09a',
],
    'words': 'cow cat',
    'nested': {
    'id': 150,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    4,
],
    [
],
],
    'two_words': [
    'crab',
    'cheetah',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
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
    '21',
    '23',
    '07',
],
    'text_data': '32922a57644849cc8a79721593bc80de',
    'rand_digit': 2,
    'rand_number': 0.84375,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-04 15:32:18-0800',
    'text_array': [
    'd0f41294d9cd48f8b3b129202946eb5b',
    'ceace0d6e4a5464f86fc26db7fd5a23b',
],
    'words': 'ant sloth',
    'nested': {
    'id': 151,
    'rand_digit': 7,
    'array': [
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
    'hello',
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
    'word': 'chicken',
    'number': 8,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'mosquito',
    'cheetah',
],
    'city': {
    'name': 'Athens',
    'geo': {
    'lat': 37.98381,
    'lon': 23.727539,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'rhino',
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
    '08',
],
    'text_data': 'aceba79af94245b9a1bd2f79f047f6e7',
    'rand_digit': 9,
    'rand_number': 0.02287,
    'rand_signed_int': 0,
    'rand_datetime': '2001-01-22T08:57:14.413500+0700',
    'text_array': [
    '10a0e3277fc148d5a6f73c435179aecf',
    'babbfb9903b8459492a95f98a3456c26',
],
    'words': 'zebra wolf',
    'nested': {
    'id': 152,
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
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ape',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'dragonfly',
    'snake',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.44435,
    'maybe_null': None,
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
],
    'text_data': '3153f649939a4f2a82211daf7288c0ef',
    'rand_digit': 9,
    'rand_number': 0.0098,
    'rand_signed_int': 8,
    'rand_datetime': '2000-05-18 10:54:16',
    'text_array': [
    'a327b45f2d0d46cd961e7a560a44edb2',
    '87942ea01b3748d88d85ba8e6d7c2fc0',
],
    'words': 'ant leopard',
    'nested': {
    'id': 153,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'deer',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'horse',
    'dragonfly',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'octopus',
    'maybe_null': 'ape',
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
    '13',
    '22',
],
    'text_data': '25c68ca3aabe42febc631cd2d8d14999',
    'rand_digit': 7,
    'rand_number': 0.37174,
    'rand_signed_int': -10,
    'rand_datetime': '2000-02-29T01:10:22.017939+04:00',
    'text_array': [
    '5e5926314e814d7293a71f267e64b068',
    '420d32b2d1114f578c89bf6a3da76568',
],
    'words': 'rabbit goat',
    'nested': {
    'id': 154,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'lizard',
    'fox',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
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
    '26',
    '16',
    '12',
    '18',
    '10',
],
    'text_data': 'd53760b881fb4e46903ea9b9787ee25c',
    'rand_digit': 9,
    'rand_number': 0.72906,
    'rand_signed_int': 5,
    'rand_datetime': '2001-01-16T22:18:27.558440-09:00',
    'text_array': [
    '362008a1711743488a7dfe58fbd1276c',
    'd30d279c439c4affa3a4b5445c559012',
],
    'words': 'fly chicken',
    'nested': {
    'id': 155,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'horse',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'goat',
    'cheetah',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'leopard',
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
    '29',
],
    'text_data': '2081b25783a14251b238cedf1174b23d',
    'rand_digit': 7,
    'rand_number': 0.07325,
    'rand_signed_int': -4,
    'rand_datetime': '2000-03-04T03:52:19.556652',
    'text_array': [
    'baa8b9fd1bd24049a290ad64d982fc16',
    '2edf3d4fbf074f37bc0f6853d2bf3d5e',
],
    'words': 'fish zebra',
    'nested': {
    'id': 156,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 7,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,2__',
    'two_words': [
    'sheep',
    'frog',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'duck',
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
    '15',
    '14',
],
    'text_data': 'bfc0a3f8c815407bb83b3635bd655961',
    'rand_digit': 3,
    'rand_number': 0.68026,
    'rand_signed_int': -9,
    'rand_datetime': '2000-02-12T04:12:56.964303',
    'text_array': [
    '22450671c2ab4d738d5b5177cf8e3185',
    'ef5a3f53143846368756ced1277625dc',
],
    'words': 'fly camel',
    'nested': {
    'id': 157,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'ant',
    'cow',
],
    'city': {
    'name': 'Cardiff',
    'geo': {
    'lat': 51.481581,
    'lon': -3.17909,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': 'koala',
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
    '28',
    '30',
    '29',
],
    'text_data': 'a96f4ff4f54944d58701591c3190d438',
    'rand_digit': 5,
    'rand_number': 0.44345,
    'rand_signed_int': 5,
    'rand_datetime': '2000-06-22',
    'text_array': [
    '8d5c8977703d4667bd95907976e5455b',
    '297ce63e6349407eb404c91bd3709f23',
],
    'words': 'camel frog',
    'nested': {
    'id': 158,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'lizard',
    'duck',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': [
    3,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
],
    'text_data': '983051f788224f66918345a8b8d2508e',
    'rand_digit': 9,
    'rand_number': 0.15143,
    'rand_signed_int': -5,
    'rand_datetime': '2000-10-27',
    'text_array': [
    'e8a55d70d09c41ccba441299e2945dbd',
    'e82308faf8d54a6eb6ec3dea221e58e5',
],
    'words': 'butterfly crab',
    'nested': {
    'id': 159,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 2,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'horse',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'goat',
    'ant',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 1,
    'maybe_null': 'rhino',
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
    '02',
    '21',
    '14',
    '06',
    '10',
],
    'text_data': '6d677e2d40f84d5dab9dc918a25d3ed5',
    'rand_digit': 2,
    'rand_number': 0.05663,
    'rand_signed_int': 0,
    'rand_datetime': '2000-10-02 11:38:43.753979',
    'text_array': [
    'e2c57d2b93d3432ebf34a23e91bde496',
    '2722329a451049299ea1f176d535cabd',
],
    'words': 'frog cow',
    'nested': {
    'id': 160,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 7,
},
],
},
    'nested_array': [
    [
    -3,
],
    [
    1,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'wolf',
    'spider',
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
    'mixed_type': 0.52538,
    'maybe': 'bird',
    'maybe_null': 'sheep',
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
    '07',
    '01',
    '16',
],
    'text_data': 'ea51a56e1eb7420f8808397905fb2d7f',
    'rand_digit': 9,
    'rand_number': 0.51525,
    'rand_signed_int': -8,
    'rand_datetime': '2000-06-06T09:15:35.061825-0100',
    'text_array': [
    'e2fd0706b5fc4d529a1f44d366efc7f7',
    '97a282958d2a47ae87966e8829ef34f0',
],
    'words': 'cheetah hyena',
    'nested': {
    'id': 161,
    'rand_digit': 7,
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
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'goat',
    'elephant',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 8,
    'maybe': 'leopard',
    'maybe_null': 'cheetah',
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
    '01',
    '30',
    '17',
],
    'text_data': '0b6ccfa430cb4480931f84f9509f5ce9',
    'rand_digit': 5,
    'rand_number': 0.49515,
    'rand_signed_int': -10,
    'rand_datetime': '2000-04-02 15:46:51.295383+0300',
    'text_array': [
    '58dad3c1904746db8d5c7cce03ce5bd1',
    '746a921c443e4c609dd61178dd99eb01',
],
    'words': 'ladybug panda',
    'nested': {
    'id': 162,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    [
    1,
],
    [
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'sheep',
    'snake',
],
    'city': {
    'name': 'Cardiff',
    'geo': {
    'lat': 51.481581,
    'lon': -3.17909,
},
},
    'rand_tuple': [
    87,
],
    'rand_bool': False,
    'mixed_type': 'pig',
    'maybe_null': 'koala',
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
    '26',
],
    'text_data': 'e5e784db56e7496b8a379d28cff97c8f',
    'rand_digit': 6,
    'rand_number': 0.45469,
    'rand_signed_int': 3,
    'rand_datetime': '2000-02-19T04:22:42+1000',
    'text_array': [
    '4eef46a463844b45be0b7e4d5fdf4f67',
    '5c4be618b2fd4baaaf19692f84b3eae2',
],
    'words': 'sheep squid',
    'nested': {
    'id': 163,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'spider',
    'gorilla',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 3,
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
    'content-length': '724',
}
        
        # 原始请求内容
        original_content = {
    'target': self.mutator.generate_float_array(dimension=100, normalized=True),
    'context': [
    {
    'positive': 10,
    'negative': 19,
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



    def test_request_5(self):
        """测试请求 5 - DELETE http://localhost:6333/collections/congruence_test_collection?timeout=60"""
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_discovery.test_discover_raw_target')
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
    test = TestDiscoverytestDiscoverRawTarget()
    test.run_tests()
