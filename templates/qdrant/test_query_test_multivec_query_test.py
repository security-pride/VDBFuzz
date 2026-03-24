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
logger = logging.getLogger('vdb_fuzzer.test.test_query_test_multivec_query')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_query.test_multivec_query"
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



class TestQuerytestMultivecQuery:
    """自动生成的VDB模糊测试类 - test_query.test_multivec_query"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_query.test_multivec_query"
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
    'content-length': '285',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'multi-text': {
    'size': 50,
    'distance': 'Cosine',
    'multivector_config': {
    'comparator': 'max_sim',
},
},
    'multi-image': {
    'size': 100,
    'distance': 'Dot',
    'multivector_config': {
    'comparator': 'max_sim',
},
},
    'multi-code': {
    'size': 80,
    'distance': 'Euclid',
    'multivector_config': {
    'comparator': 'max_sim',
},
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
    'content-length': '514508',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 100,
    'id_str': [
    '27',
    '08',
],
    'text_data': 'a3db7a7240a1462382ea36485ef5df6e',
    'rand_digit': 5,
    'rand_number': 0.5534,
    'rand_signed_int': -6,
    'rand_datetime': '2000-07-25',
    'text_array': [
    '4ce7471f64e84d1183d6e17a90c5eb21',
    '1886c34fdfc84b87abfb9ab9ee5b2de6',
],
    'words': 'cat cheetah',
    'nested': {
    'id': 100,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 7,
},
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
],
    'word': 'fox',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'chicken',
    'cat',
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
    'mixed_type': True,
    'maybe': 'leopard',
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 101,
    'id_str': [
    '16',
    '10',
    '13',
    '16',
    '06',
],
    'text_data': '4b9ed24f5ca44d62905f1fc1ae1291a3',
    'rand_digit': 1,
    'rand_number': 0.82209,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-03T13:09:31.967211',
    'text_array': [
    '0c9fdc5fb5ff4e4fb7a78f3b6b9ec795',
    '06c41c2947d1461698b02aea0a8c872b',
],
    'words': 'scorpion koala',
    'nested': {
    'id': 101,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 2,
},
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
    'hello',
],
    'word': 'ant',
    'number': 10,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'sheep',
    'gorilla',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': [
    26,
],
    'rand_bool': False,
    'mixed_type': 'dragonfly',
    'maybe': 'bee',
},
},
    {
    'id': 2,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 102,
    'id_str': [
    '28',
],
    'text_data': '403a94098c3c4eeaaa0b1ee5bf68b845',
    'rand_digit': 9,
    'rand_number': 0.88906,
    'rand_signed_int': -2,
    'rand_datetime': '2000-11-27T17:38:11.879311+1200',
    'text_array': [
    '98c0aec636f44f3b9eba4b5fd4af9478',
    '784d35bf9ea14c038408b8fb8f82a4f9',
],
    'words': 'fox ant',
    'nested': {
    'id': 102,
    'rand_digit': 9,
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
],
    'word': 'bear',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'hyena',
    'zebra',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': [
    19,
],
    'rand_bool': False,
    'mixed_type': 0.94659,
    'maybe_null': None,
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 103,
    'id_str': [
    '15',
    '24',
],
    'text_data': 'ffe1a3963b33418797e89c2bb55fe9b4',
    'rand_digit': 1,
    'rand_number': 0.13496,
    'rand_signed_int': -7,
    'rand_datetime': '2000-07-24 17:38:36+0200',
    'text_array': [
    '6ebcedc4d6024c5f814b420237ca0384',
    '2ed0da17de7b4fdeb4a9013bedefc648',
],
    'words': 'sloth tiger',
    'nested': {
    'id': 103,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'scorpion',
    'leopard',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'cat',
    'maybe_null': None,
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 104,
    'id_str': [
    '17',
],
    'text_data': 'b0c75fbf621c4669b72bf9709cb87f79',
    'rand_digit': 9,
    'rand_number': 0.69838,
    'rand_signed_int': -9,
    'rand_datetime': '2000-04-02',
    'text_array': [
    '8d29719271684e9696298f1a0a79cce3',
    '187b81a892e8498c9145dfe884628367',
],
    'words': 'goat rabbit',
    'nested': {
    'id': 104,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'ape',
    'spider',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': [
    56,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'octopus',
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 105,
    'id_str': [
    '13',
    '18',
    '30',
    '28',
],
    'text_data': 'b1dddb1d07b4426e96e347ab619219ef',
    'rand_digit': 2,
    'rand_number': 0.60604,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-26T22:13:53',
    'text_array': [
    '17437c177c3d417094a2c5028b73bdbe',
    '7362e3e156c34736ad43c261dd5709b8',
],
    'words': 'lion grasshopper',
    'nested': {
    'id': 105,
    'rand_digit': 0,
    'array': [
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
    'word': 'mouse',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 8,
},
],
},
    'nested_array': [
    [
    -2,
],
    [
],
],
    'two_words': [
    'cheetah',
    'camel',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 106,
    'id_str': [
    '23',
    '20',
],
    'text_data': '1eb1d52001314be2b11587e047f90cc6',
    'rand_digit': 0,
    'rand_number': 0.7348,
    'rand_signed_int': 10,
    'rand_datetime': '2000-03-01T00:04:20.294265',
    'text_array': [
    '06922487cb624103b208d97da103a009',
    'dd4af797196b45819a06ef030825e22c',
],
    'words': 'zebra rhino',
    'nested': {
    'id': 106,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'snail',
    'ape',
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
    'mixed_type': None,
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 107,
    'id_str': [
    '30',
],
    'text_data': 'e68eb4d7274240999154687116cfdb50',
    'rand_digit': 9,
    'rand_number': 0.64939,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-02 04:25:04.838926',
    'text_array': [
    '82c8911d3d3c431eae50c1e83c1ac1f2',
    '6748c77e977248f79f323a8087586b78',
],
    'words': 'rabbit frog',
    'nested': {
    'id': 107,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'rabbit',
    'number': 3,
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
],
},
    'nested_array': [
],
    'two_words': [
    'duck',
    'tiger',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'duck',
    'maybe_null': None,
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 108,
    'id_str': [
    '24',
    '02',
],
    'text_data': '2264697fba9e463bab8a2ccab41eb16d',
    'rand_digit': 6,
    'rand_number': 0.9458,
    'rand_signed_int': -2,
    'rand_datetime': '2000-05-08 11:46:39.564968',
    'text_array': [
    '3af6acaf4397490a9a335085defc715e',
    'c6b7b3a4296046ee99655e17bb2437f5',
],
    'words': 'dolphin goat',
    'nested': {
    'id': 108,
    'rand_digit': 8,
    'array': [
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
    'word': 'sheep',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 4,
},
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
],
    [
],
],
    'two_words': [
    'ape',
    'tiger',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.0934,
    'maybe': 'sloth',
    'maybe_null': 'kangaroo',
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 109,
    'id_str': [
    '03',
    '29',
    '02',
    '11',
],
    'text_data': '5a77b058769e4a93a93c0ab65c9d1d15',
    'rand_digit': 1,
    'rand_number': 0.85163,
    'rand_signed_int': 1,
    'rand_datetime': '2000-04-21 04:00:17.876706',
    'text_array': [
    '174f28e1a645452dac5c1150483a409d',
    '9a04302d9f57409f821df35779e79d4f',
],
    'words': 'fly shark',
    'nested': {
    'id': 109,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 2,
},
],
},
    'nested_array': [
    [
    -9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'monkey',
    'bird',
],
    'city': {
    'name': 'Athens',
    'geo': {
    'lat': 37.98381,
    'lon': 23.727539,
},
},
    'rand_tuple': [
    62,
],
    'rand_bool': False,
    'mixed_type': 0.61105,
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 110,
    'id_str': [
    '09',
],
    'text_data': 'f2bd68f3088449b18e0158aa9951aa38',
    'rand_digit': 4,
    'rand_number': 0.58586,
    'rand_signed_int': 0,
    'rand_datetime': '2000-03-22 21:16:35+0700',
    'text_array': [
    '32e2e1f7ba3848488f953ef0b5f20136',
    '22a0432dca294910a15655692acdbfea',
],
    'words': 'koala turtle',
    'nested': {
    'id': 110,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 9,
},
],
},
    'nested_array': [
    [
    4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'kangaroo',
    'fox',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'ladybug',
    'maybe_null': 'hyena',
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 111,
    'id_str': [
    '20',
    '16',
    '15',
    '07',
],
    'text_data': 'ca182937da8b49eaa7c943d58fdb372e',
    'rand_digit': 1,
    'rand_number': 0.32049,
    'rand_signed_int': -9,
    'rand_datetime': '2000-11-26T10:11:44.297187',
    'text_array': [
    'c5ea71648c6144038e2b5ef6202162d4',
    '1967300c97a1442fb8b0c248f64f932f',
],
    'words': 'ladybug dragonfly',
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
    'word': 'bird',
    'number': 3,
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
    'word': 'snake',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -9,
],
],
    'two_words': [
    'elephant',
    'snail',
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
    'mixed_type': 0,
    'maybe': 'dolphin',
    'maybe_null': 'sheep',
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 112,
    'id_str': [
    '11',
    '30',
    '02',
],
    'text_data': '0538338b508843cfaa65bee1ab7f1319',
    'rand_digit': 4,
    'rand_number': 0.96037,
    'rand_signed_int': 5,
    'rand_datetime': '2000-01-15T06:51:05.471398',
    'text_array': [
    'd8f3f4ad216e4eac80edd39bdb58f9d1',
    '7a863003b65c4e9896752b9f9cb2ca13',
],
    'words': 'chicken bird',
    'nested': {
    'id': 112,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dog',
    'bee',
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
    'mixed_type': 'grasshopper',
    'maybe_null': 'shark',
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 113,
    'id_str': [
    '12',
    '29',
    '25',
    '27',
],
    'text_data': '244f00728aad4a10bcc7d135ad93671e',
    'rand_digit': 6,
    'rand_number': 0.44981,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-12T08:45:55.204681',
    'text_array': [
    '8e4b3196429348db8cd752b696a36e42',
    'dbde01368a0b48878d91170d04b0c46c',
],
    'words': 'bird bear',
    'nested': {
    'id': 113,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 4,
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
    'word': 'turtle',
    'number': 3,
},
],
},
    'nested_array': [
    [
    -6,
],
],
    'two_words': [
    'fish',
    'duck',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'jaguar',
    'maybe': 'shark',
    'maybe_null': None,
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 114,
    'id_str': [
    '01',
    '20',
],
    'text_data': '64c769ee33d54925be54cbd2e0072472',
    'rand_digit': 6,
    'rand_number': 0.62086,
    'rand_signed_int': -10,
    'rand_datetime': '2000-11-19T21:42:35.603658',
    'text_array': [
    '72246e2e1146442b844ac614a3925b83',
    '74666396ab3b4a718a3693528fb4660e',
],
    'words': 'gorilla crab',
    'nested': {
    'id': 114,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 1,
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
],
},
    'nested_array': [
],
    'two_words': [
    'chicken',
    'snake',
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
    'mixed_type': 0.97557,
    'maybe': 'scorpion',
    'maybe_null': None,
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 115,
    'id_str': [
    '16',
    '18',
    '19',
],
    'text_data': '84e96adae1c74ddcbad149b8fab3c6fe',
    'rand_digit': 2,
    'rand_number': 0.25923,
    'rand_signed_int': -4,
    'rand_datetime': '2000-01-10 02:30',
    'text_array': [
    'a99ad32b01994bbaa43812b466a157ec',
    '43ba6c9fbc52491e8c7e0577abfd5047',
],
    'words': 'butterfly shark',
    'nested': {
    'id': 115,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 10,
},
],
},
    'nested_array': [
    [
    6,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'shark',
    'dragonfly',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 116,
    'id_str': [
    '29',
    '10',
    '21',
    '29',
],
    'text_data': '27beb7067f004c2f8e875af3010ca0cc',
    'rand_digit': 7,
    'rand_number': 0.2656,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-05',
    'text_array': [
    '435955db37d244c8b15d25a1cfc688d4',
    '6873c533b3ea4f48961e16a78ee0aad0',
],
    'words': 'tiger bear',
    'nested': {
    'id': 116,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'mosquito',
    'number': 4,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'snail',
    'ladybug',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.09535,
    'maybe': 'dragonfly',
    'maybe_null': 'lobster',
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 117,
    'id_str': [
    '08',
    '06',
    '07',
    '26',
    '12',
],
    'text_data': 'edb8fd63c799427d9d9dd87fc2733350',
    'rand_digit': 9,
    'rand_number': 0.98238,
    'rand_signed_int': -7,
    'rand_datetime': '2000-07-23T05:51:24.477417+12:00',
    'text_array': [
    '1f9e23141a69475bb84c9e90b66618e3',
    'db0a1a52c6864d5199e70d411e1fd09d',
],
    'words': 'lizard monkey',
    'nested': {
    'id': 117,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'mouse',
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
    82,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 18,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 118,
    'id_str': [
    '16',
    '03',
],
    'text_data': 'ec002638dd934a4caabcd6377e793f21',
    'rand_digit': 3,
    'rand_number': 0.28667,
    'rand_signed_int': -2,
    'rand_datetime': '2001-01-02 01:02:33.156852',
    'text_array': [
    'fb8a8cc4fdbc4b3788444ce8abce2dfe',
    'f2316cd518794932b56541d29f3db3ba',
],
    'words': 'leopard mosquito',
    'nested': {
    'id': 118,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    7,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'duck',
    'shark',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'fish',
    'maybe': 'bear',
    'maybe_null': 'panda',
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
],
    'text_data': '749ad522c0d44f849b3ee43d19f13d46',
    'rand_digit': 5,
    'rand_number': 0.0251,
    'rand_signed_int': 4,
    'rand_datetime': '2000-04-13',
    'text_array': [
    '9526d0228c2546f3a59f74a3b102dd8e',
    '549a1813f7f746d98f1633d3a8595350',
],
    'words': 'tiger dolphin',
    'nested': {
    'id': 119,
    'rand_digit': 5,
    'array': [
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
    'word': 'shark',
    'number': 5,
},
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
],
    'word': 'jaguar',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -3,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'sheep',
    'ant',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'shark',
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 120,
    'id_str': [
    '27',
    '21',
    '17',
    '11',
    '21',
],
    'text_data': '92883455110549caa791e10f28fd27bf',
    'rand_digit': 6,
    'rand_number': 0.10128,
    'rand_signed_int': 8,
    'rand_datetime': '2000-04-05 13:09:05',
    'text_array': [
    'e9db8af43182410f99484e531ea4e9fa',
    '01491863547c4cd3ab08993a35f11571',
],
    'words': 'squid horse',
    'nested': {
    'id': 120,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'wolf',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
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
    'squid',
    'camel',
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
    'maybe_null': 'ant',
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 121,
    'id_str': [
    '06',
    '11',
    '25',
    '12',
],
    'text_data': '60d95093bc8e4875a41ebbb495ff9442',
    'rand_digit': 3,
    'rand_number': 0.80536,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-22T02:39:48.760020-05:00',
    'text_array': [
    'c22209cf7491446e8480cb9ce87a17bc',
    '5ba3cc421dcb451fa70d6380ee1675d2',
],
    'words': 'whale koala',
    'nested': {
    'id': 121,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 3,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 6,
},
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
    [
    -6,
],
],
    'two_words': [
    'bird',
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
    'mixed_type': 'rhino',
    'maybe': 'mosquito',
    'maybe_null': None,
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
],
    'text_data': '87657f683b794af582373331c959afff',
    'rand_digit': 4,
    'rand_number': 0.03937,
    'rand_signed_int': -6,
    'rand_datetime': '2000-11-18T23:17:53.894067-0300',
    'text_array': [
    '3809653d78074e15b610264ae8de291c',
    '1b441ecfeea845bf9b422c0ce2cb7786',
],
    'words': 'shark hippo',
    'nested': {
    'id': 122,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 3,
},
],
},
    'nested_array': [
    [
    -10,
],
    [
],
    [
    -7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'shark',
    'snail',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'gorilla',
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 123,
    'id_str': [
    '14',
    '28',
    '26',
    '19',
],
    'text_data': '807d9a3b167e4595a4e49f70d17a1540',
    'rand_digit': 8,
    'rand_number': 0.05929,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-20T01:59:59.200443+0700',
    'text_array': [
    '041019cc4c8d4e7eb08dee5be61d4ba5',
    'd52b07ecf23c48e28ff880a282669856',
],
    'words': 'crab leopard',
    'nested': {
    'id': 123,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
    10,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    1,
],
],
    'two_words': [
    'cheetah',
    'camel',
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
    'mixed_type': None,
    'maybe': 'kangaroo',
    'maybe_null': 'shark',
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 124,
    'id_str': [
    '27',
    '25',
    '13',
    '26',
],
    'text_data': '5250f121df7d41de81a30fd7f0806096',
    'rand_digit': 1,
    'rand_number': 0.44691,
    'rand_signed_int': 2,
    'rand_datetime': '2000-03-07',
    'text_array': [
    '6435a8d3062b4799a3c395c5de54cfc3',
    'fca981ecb5d443f7947366852104d9e5',
],
    'words': 'bee scorpion',
    'nested': {
    'id': 124,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'camel',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'octopus',
    'leopard',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': [
    93,
],
    'rand_bool': False,
    'mixed_type': 0.05741,
    'maybe': 'butterfly',
    'maybe_null': None,
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
    '21',
    '12',
    '26',
    '30',
    '11',
],
    'text_data': 'b844b91a092c4f628fc6466b20ba00f2',
    'rand_digit': 0,
    'rand_number': 0.14627,
    'rand_signed_int': -2,
    'rand_datetime': '2000-01-19T14:15:29-1200',
    'text_array': [
    '64b502f346634b13b4ccd1469bde0d50',
    '975ec274f2314895a0f2df22cff4777d',
],
    'words': 'bird lion',
    'nested': {
    'id': 125,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
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
],
    'word': 'frog',
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
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
    -9,
],
],
    'two_words': [
    'crab',
    'fish',
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
    'mixed_type': 0.85314,
    'maybe': 'sloth',
    'maybe_null': 'jaguar',
},
},
    {
    'id': 26,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 126,
    'id_str': [
    '13',
    '13',
    '16',
    '22',
],
    'text_data': '7656abbedb874a9ea2eb5c0f30c9a7d4',
    'rand_digit': 7,
    'rand_number': 0.35178,
    'rand_signed_int': -4,
    'rand_datetime': '2000-05-12 05:08:43.441672-0700',
    'text_array': [
    '195f7456d81e492e9b5b39eed6620bc1',
    '8e8a9a1acd034c858055811934069f17',
],
    'words': 'dog goat',
    'nested': {
    'id': 126,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
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
    'number': 7,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'monkey',
    'pig',
],
    'city': {
    'name': 'Dubai',
    'geo': {
    'lat': 25.204849,
    'lon': 55.270783,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 8,
    'maybe_null': 'sheep',
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 127,
    'id_str': [
    '30',
    '10',
    '23',
    '27',
    '14',
],
    'text_data': '7dae773f4cbb483cbf1698a3a06561e6',
    'rand_digit': 7,
    'rand_number': 0.21317,
    'rand_signed_int': 6,
    'rand_datetime': '2000-03-12 15:58:56+0500',
    'text_array': [
    '0a76403701f0491c8967f735c35d3f8a',
    '53e26ca6f807498eaf5db6321ce997a3',
],
    'words': 'grasshopper bee',
    'nested': {
    'id': 127,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'elephant',
    'butterfly',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'deer',
    'maybe_null': 'lizard',
},
},
    {
    'id': 28,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 128,
    'id_str': [
    '14',
    '17',
    '06',
    '23',
],
    'text_data': '9e3bbc82bdaf4761988d65a8352f93a5',
    'rand_digit': 3,
    'rand_number': 0.02949,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-02T10:50:33.203464',
    'text_array': [
    'b01b79c7e8b04303b65618afabd25f75',
    '0393e0bb63ba48a7923b50240435fcd5',
],
    'words': 'ant horse',
    'nested': {
    'id': 128,
    'rand_digit': 7,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'dog',
    'fly',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'chicken',
    'maybe_null': 'ant',
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
    '13',
    '27',
    '18',
    '06',
    '08',
],
    'text_data': 'd41e43cc7dcf472994ef6a5d9efddcd4',
    'rand_digit': 0,
    'rand_number': 0.08317,
    'rand_signed_int': 8,
    'rand_datetime': '2000-03-20T21:09:03',
    'text_array': [
    '0b71332f71b44a4f9e98d3968ddc9ed3',
    '830154ebc5bb4183b0a7b828d99dfc2f',
],
    'words': 'rhino tiger',
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
    'word': 'zebra',
    'number': 7,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'spider',
    'squid',
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
    'mixed_type': 5,
    'maybe': 'mosquito',
    'maybe_null': 'goat',
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 130,
    'id_str': [
],
    'text_data': '743680dd8dd7474fb412661e7acf97a1',
    'rand_digit': 4,
    'rand_number': 0.32282,
    'rand_signed_int': 8,
    'rand_datetime': '2000-11-16 19:30:11.482499',
    'text_array': [
    'd91cce6d891843ba935098db2741b3e5',
    '250a39aaad4849dbba9fa62cd5c4c138',
],
    'words': 'mouse bear',
    'nested': {
    'id': 130,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'whale',
    'chicken',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': [
    100,
],
    'rand_bool': False,
    'mixed_type': 'crab',
    'maybe_null': 'sheep',
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 131,
    'id_str': [
    '22',
],
    'text_data': '2bc3c91045304982ae50859502b74d0e',
    'rand_digit': 6,
    'rand_number': 0.48405,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-16T04:38:33-0800',
    'text_array': [
    '31b2311e774c4604bc63b38eaff62430',
    'dbea6e756b584df1b058b49b43eb7931',
],
    'words': 'shark dragonfly',
    'nested': {
    'id': 131,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'duck',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'kangaroo',
    'dog',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 32,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 132,
    'id_str': [
    '25',
    '03',
    '19',
    '26',
    '03',
],
    'text_data': '07ee5e7a06284765ad5cf67d705090b9',
    'rand_digit': 4,
    'rand_number': 0.51553,
    'rand_signed_int': -3,
    'rand_datetime': '2000-12-12 19:12:33',
    'text_array': [
    '24303195f4d34f0eab94024b21809def',
    'e2b2ad935a314310bace420601650319',
],
    'words': 'bee leopard',
    'nested': {
    'id': 132,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
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
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'hyena',
    'lizard',
],
    'city': {
    'name': 'Moscow',
    'geo': {
    'lat': 55.755826,
    'lon': 37.6173,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 3,
    'maybe_null': None,
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 133,
    'id_str': [
    '16',
],
    'text_data': 'b4b58a1b8c4b431aacf59eb9a3e36db3',
    'rand_digit': 7,
    'rand_number': 0.24407,
    'rand_signed_int': 9,
    'rand_datetime': '2000-07-06 05:47:46.927230',
    'text_array': [
    '9ffe2805685449bb9b3d3ccbb60636f8',
    'e9bb53163e1d4ab3ab7188113b0a113b',
],
    'words': 'turtle fox',
    'nested': {
    'id': 133,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'crab',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -9,
],
    [
    -4,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'hippo',
    'sloth',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': [
    1,
],
    'rand_bool': False,
    'mixed_type': 0.322,
    'maybe': 'deer',
    'maybe_null': 'bird',
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 134,
    'id_str': [
    '07',
    '20',
    '03',
    '11',
    '22',
],
    'text_data': '2b1dde45f2ee41fb806d1d7ec2af86f2',
    'rand_digit': 7,
    'rand_number': 0.43744,
    'rand_signed_int': -4,
    'rand_datetime': '2000-02-25 02:41:39.520162-1000',
    'text_array': [
    '340ea3adcc214ab0b3dcbe188e4ee02a',
    '9ab2cee4948e4f67a0adadc9fa33205d',
],
    'words': 'dolphin gorilla',
    'nested': {
    'id': 134,
    'rand_digit': 2,
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
    'word': 'camel',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lobster',
    'mosquito',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
},
},
    {
    'id': 35,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 135,
    'id_str': [
    '08',
],
    'text_data': '5397c004abfd476ab05d8d149b04d58d',
    'rand_digit': 4,
    'rand_number': 0.14229,
    'rand_signed_int': -2,
    'rand_datetime': '2000-04-05 03:50',
    'text_array': [
    '62be5fee202546bfb36eb8a37e4782ad',
    '5b80b70c64174f6a82feb591f697929e',
],
    'words': 'bird octopus',
    'nested': {
    'id': 135,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lion',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'cat',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mouse',
    'horse',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'dragonfly',
    'maybe_null': None,
},
},
    {
    'id': 36,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 136,
    'id_str': [
    '04',
    '23',
    '18',
    '25',
    '06',
],
    'text_data': '437080f71db54556b862fbdf41187be8',
    'rand_digit': 2,
    'rand_number': 0.88263,
    'rand_signed_int': -6,
    'rand_datetime': '2000-07-11 16:43:28.279404',
    'text_array': [
    '765737873c7e4c0d916e5a0471b66beb',
    '301a62da1f5e4e7db8475c36d534c883',
],
    'words': 'squid fly',
    'nested': {
    'id': 136,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'horse',
    'dolphin',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'pig',
    'maybe_null': None,
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
    '05',
    '06',
    '01',
    '29',
    '06',
],
    'text_data': '4dc135824bf5447fa7367630297049c0',
    'rand_digit': 0,
    'rand_number': 0.27439,
    'rand_signed_int': 8,
    'rand_datetime': '2000-01-18 11:15:19-0300',
    'text_array': [
    'c4167bab79884072a60f269e0f124346',
    '400cd45f65e84ebc9bca817c5bba1dd5',
],
    'words': 'fox cheetah',
    'nested': {
    'id': 137,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fox',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'goat',
    'chicken',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 38,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 138,
    'id_str': [
    '24',
    '10',
    '12',
],
    'text_data': '7855ecb2f66e49e5b865b3d082eaa804',
    'rand_digit': 6,
    'rand_number': 0.63071,
    'rand_signed_int': 7,
    'rand_datetime': '2000-12-13 07:48:35.110393',
    'text_array': [
    '9122e5b6ef8943468406d82838396024',
    '39b72dda1f6946e89e5cae4ac46a4910',
],
    'words': 'cheetah wolf',
    'nested': {
    'id': 138,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    [
    9,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -2,
],
],
    'two_words': [
    'deer',
    'sloth',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'lobster',
    'maybe_null': 'hyena',
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 139,
    'id_str': [
    '28',
],
    'text_data': '829eed573d3146aea8d5b1c6935b89ce',
    'rand_digit': 4,
    'rand_number': 0.58485,
    'rand_signed_int': -10,
    'rand_datetime': '2000-01-31T16:27:37.538309',
    'text_array': [
    '9de53f2164f34d5f9a65c42203963e0f',
    '3665dcdef9b84aa7a432d444aa13c547',
],
    'words': 'sheep rabbit',
    'nested': {
    'id': 139,
    'rand_digit': 1,
    'array': [
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
    [
],
    [
],
    [
],
],
    'two_words': [
    'giraffe',
    'chicken',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'pig',
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 140,
    'id_str': [
    '01',
],
    'text_data': '9b82ed46ec9f4641b64b00a22b15a2fa',
    'rand_digit': 9,
    'rand_number': 0.17883,
    'rand_signed_int': 4,
    'rand_datetime': '2000-06-07 14:23:03.288678',
    'text_array': [
    'f0944ea13b454606b160d407becc5981',
    '0df4621d099e4e21a0a89a5f4e4a0dc3',
],
    'words': 'dragonfly shark',
    'nested': {
    'id': 140,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 6,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,3__',
    'two_words': [
    'fish',
    'monkey',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'horse',
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 141,
    'id_str': [
    '27',
    '23',
    '16',
    '18',
],
    'text_data': 'dff18a184e414b37ab0afb1721843374',
    'rand_digit': 3,
    'rand_number': 0.42264,
    'rand_signed_int': 10,
    'rand_datetime': '2000-01-23 23:09',
    'text_array': [
    'b26ffb85ee814be1840c590b23332c78',
    '3b03453e3cf04c2ab1a5f939f5553b0d',
],
    'words': 'sloth dolphin',
    'nested': {
    'id': 141,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 5,
},
],
},
    'nested_array': [
    [
    2,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'lizard',
    'gorilla',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'pig',
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 142,
    'id_str': [
    '22',
    '05',
    '27',
    '25',
    '10',
],
    'text_data': '0e9316a6b7b74678aa6b8936bb735158',
    'rand_digit': 0,
    'rand_number': 0.26683,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-26T19:45:55.538316+04:00',
    'text_array': [
    '809c3a8910064c93b4dd6eabf6cd1a32',
    '764a0c6f25c8404d83d06c6dea8bea94',
],
    'words': 'lobster snake',
    'nested': {
    'id': 142,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'fly',
    'horse',
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
    'mixed_type': 'dog',
    'maybe': 'gorilla',
    'maybe_null': None,
},
},
    {
    'id': 43,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 143,
    'id_str': [
    '08',
    '28',
    '27',
],
    'text_data': 'ee1aa63880f644cd9ca16226a0c56560',
    'rand_digit': 7,
    'rand_number': 0.1257,
    'rand_signed_int': 5,
    'rand_datetime': '2000-05-30',
    'text_array': [
    'c4598e1d09b14806a167bbc62d234e67',
    'e10bd74beb504efead94d586d9077362',
],
    'words': 'frog ant',
    'nested': {
    'id': 143,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'cow',
    'crab',
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
    'mixed_type': 0.39746,
    'maybe': 'crab',
    'maybe_null': None,
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 144,
    'id_str': [
    '11',
    '21',
    '20',
    '22',
    '07',
],
    'text_data': '6c4a1c572e2f4e1d8af6012f7c2e95ce',
    'rand_digit': 7,
    'rand_number': 0.62877,
    'rand_signed_int': -9,
    'rand_datetime': '2000-12-12T11:51:08.790676-07:00',
    'text_array': [
    '7a659e5052724fa1b0a81459c14ef180',
    '60105f9ac18f4ad8b0c5360ad1cd9bb4',
],
    'words': 'snail turtle',
    'nested': {
    'id': 144,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snail',
    'octopus',
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
    'mixed_type': None,
    'maybe': 'cheetah',
    'maybe_null': 'horse',
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 145,
    'id_str': [
],
    'text_data': '366f97a08c6145ac928cd43094960ed4',
    'rand_digit': 7,
    'rand_number': 0.4918,
    'rand_signed_int': 7,
    'rand_datetime': '2000-02-25',
    'text_array': [
    'e1ad15df17be42fa9b342fbb05c43969',
    '6056d3a9761a4b388b8506eb2c900d6c',
],
    'words': 'horse monkey',
    'nested': {
    'id': 145,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
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
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'sheep',
    'bird',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.31161,
    'maybe': 'cow',
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
    '09',
    '24',
    '19',
    '02',
],
    'text_data': '114f147deddc4dceba1dc28790094e05',
    'rand_digit': 5,
    'rand_number': 0.91656,
    'rand_signed_int': -5,
    'rand_datetime': '2000-07-14 18:34:13.888096',
    'text_array': [
    '78eb9f9f471340148e3246daf08a7551',
    '4d65ab0d64134094bf7da3220ed642d2',
],
    'words': 'fly wolf',
    'nested': {
    'id': 146,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,3__',
    'two_words': [
    'lizard',
    'shark',
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
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': 47,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 147,
    'id_str': [
    '08',
    '01',
    '25',
],
    'text_data': 'b355a5381db04e97b747c4eeef8ad1b2',
    'rand_digit': 8,
    'rand_number': 0.10492,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-28 22:23:54.935813',
    'text_array': [
    '99c6ea75782f40d888484f69905b15a3',
    'c768ef8df86d4db483c24e101ab3f48b',
],
    'words': 'goat snake',
    'nested': {
    'id': 147,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'jaguar',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'chicken',
    'ant',
],
    'city': {
    'name': 'Barcelona',
    'geo': {
    'lat': 41.385064,
    'lon': 2.173403,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'lobster',
    'maybe_null': 'sheep',
},
},
    {
    'id': 48,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 148,
    'id_str': [
    '04',
    '14',
],
    'text_data': 'ed936a8b807b4c09bbffa9a60417a2c8',
    'rand_digit': 9,
    'rand_number': 0.90871,
    'rand_signed_int': -2,
    'rand_datetime': '2000-10-15',
    'text_array': [
    'fa8c31bf8f29416b8402d74260b023dd',
    '4a2b1a0f7304490fa4cc92efce361cec',
],
    'words': 'ant cheetah',
    'nested': {
    'id': 148,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 1,
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
],
},
    'nested_array': [
    [
    9,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -10,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hyena',
    'pig',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'octopus',
    'maybe': 'frog',
    'maybe_null': None,
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 149,
    'id_str': [
    '15',
],
    'text_data': '2fcceae2ffea4f7996c864617e8e1f96',
    'rand_digit': 8,
    'rand_number': 0.97829,
    'rand_signed_int': 4,
    'rand_datetime': '2000-12-11T14:59:12+0100',
    'text_array': [
    'c29ec45c9f1b49199d2fb62583ab36e7',
    '5417c12a6efa440f91517c90f7d3b958',
],
    'words': 'fox hyena',
    'nested': {
    'id': 149,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 2,
},
],
},
    'nested_array': [
    [
    -9,
],
    [
    3,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    6,
],
],
    'two_words': [
    'butterfly',
    'snail',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'ladybug',
},
},
    {
    'id': 50,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 150,
    'id_str': [
    '15',
    '18',
    '26',
    '15',
    '28',
],
    'text_data': '360edfde5eae4bd8a7a3288d254abc25',
    'rand_digit': 1,
    'rand_number': 0.06679,
    'rand_signed_int': 7,
    'rand_datetime': '2000-07-12 07:24:54',
    'text_array': [
    '7f3dbfeb3af54afbbc250e549eefe09a',
    '779113161617498483c918f5f468a2ad',
],
    'words': 'sloth crab',
    'nested': {
    'id': 150,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'camel',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -2,
],
    [
    -4,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dolphin',
    'horse',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'frog',
},
},
    {
    'id': 51,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 151,
    'id_str': [
    '24',
    '13',
    '08',
    '11',
],
    'text_data': 'b4cd5f5943f74b619c72e0e43f5f1f8c',
    'rand_digit': 5,
    'rand_number': 0.32747,
    'rand_signed_int': -1,
    'rand_datetime': '2000-06-19 22:34:51-0300',
    'text_array': [
    '5abff1b523ba4998ab27ec4358e7a9bb',
    'ec07df4da9c14abb88902b1633fe7f90',
],
    'words': 'horse rhino',
    'nested': {
    'id': 151,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'goat',
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
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'scorpion',
    'dragonfly',
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
    'mixed_type': 2,
},
},
    {
    'id': 52,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 152,
    'id_str': [
    '17',
    '21',
    '17',
],
    'text_data': 'ae71537aeb684bb2a28c846d07ffd13c',
    'rand_digit': 4,
    'rand_number': 0.36299,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-01T16:16:03.435819-1100',
    'text_array': [
    '6f1dd2c13c894c7a86a87122a2ee7324',
    '7303f95c364c4c01ba6aedfffb6d67ad',
],
    'words': 'dragonfly turtle',
    'nested': {
    'id': 152,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'pig',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'crab',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bear',
    'grasshopper',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': [
    2,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'turtle',
},
},
    {
    'id': 53,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 153,
    'id_str': [
    '26',
    '21',
],
    'text_data': 'e31693c7f77149d5b293a1a1a68b968a',
    'rand_digit': 4,
    'rand_number': 0.45373,
    'rand_signed_int': 1,
    'rand_datetime': '2000-10-04 00:44:26.777485+1100',
    'text_array': [
    '6b0c934a5cd14282b0c23354ca5d54c9',
    '169d649c52b949b495672c3612338af5',
],
    'words': 'lizard mosquito',
    'nested': {
    'id': 153,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'fox',
    'rhino',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': [
    10,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'leopard',
    'maybe_null': 'koala',
},
},
    {
    'id': 54,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 154,
    'id_str': [
    '19',
    '19',
    '26',
    '20',
],
    'text_data': 'f40ee07a220544e6a949899086e889a7',
    'rand_digit': 9,
    'rand_number': 0.78602,
    'rand_signed_int': 3,
    'rand_datetime': '2000-03-06 18:26',
    'text_array': [
    '98c718777ad14b24a82bf71d40c8fd39',
    'c0a9d8b860644b4f8d4d3a879099304e',
],
    'words': 'butterfly ant',
    'nested': {
    'id': 154,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
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
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
],
    [
],
],
    'two_words': [
    'zebra',
    'leopard',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'octopus',
    'maybe': 'cat',
},
},
    {
    'id': 55,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 155,
    'id_str': [
    '19',
],
    'text_data': '1109058b54c347709d4251bdb90c16d0',
    'rand_digit': 0,
    'rand_number': 0.90727,
    'rand_signed_int': 3,
    'rand_datetime': '2000-06-16T17:39:08.304795',
    'text_array': [
    '9d84ef6092e14d2d950f25ce386cbd74',
    'd2692e4ae4aa4390bb5730a277f77c38',
],
    'words': 'zebra ant',
    'nested': {
    'id': 155,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'kangaroo',
    'mosquito',
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
    'mixed_type': 0.36199,
    'maybe': 'lion',
},
},
    {
    'id': 56,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 156,
    'id_str': [
    '25',
],
    'text_data': '680b77a8af514c65a9160b2ae94671fd',
    'rand_digit': 2,
    'rand_number': 0.51019,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-15 22:42:00',
    'text_array': [
    'b6507b2b993f4c3ab063e2c8e8f6ac33',
    '4fe485cb422042e482fffb131933ddfe',
],
    'words': 'grasshopper crab',
    'nested': {
    'id': 156,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'rabbit',
    'mouse',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'ape',
},
},
    {
    'id': 57,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 157,
    'id_str': [
    '02',
    '12',
],
    'text_data': '7ae4f77632834254ab2c0900a269a219',
    'rand_digit': 3,
    'rand_number': 0.37315,
    'rand_signed_int': 4,
    'rand_datetime': '2000-07-24T10:25:46.453244',
    'text_array': [
    'a8c2c5853a6644c692d53d0fe9b81aef',
    '4348fa30642b49be9445f9f4a3c05bf0',
],
    'words': 'mosquito rabbit',
    'nested': {
    'id': 157,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'butterfly',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'sheep',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'panda',
    'lizard',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'bird',
},
},
    {
    'id': 58,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 158,
    'id_str': [
    '11',
    '17',
    '24',
    '15',
    '11',
],
    'text_data': 'd6fd68dadcc748358caf7e598852bf6c',
    'rand_digit': 3,
    'rand_number': 0.18551,
    'rand_signed_int': 2,
    'rand_datetime': '2000-04-05 13:53:14.639512-0400',
    'text_array': [
    'e07745e962334a93a8a2f0e4205d52a1',
    'cb4421ad1b0d431d954bee0b6717de38',
],
    'words': 'jaguar wolf',
    'nested': {
    'id': 158,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lizard',
    'monkey',
],
    'city': {
    'name': 'Copenhagen',
    'geo': {
    'lat': 55.676097,
    'lon': 12.568337,
},
},
    'rand_tuple': [
    89,
],
    'rand_bool': True,
    'mixed_type': 'tiger',
    'maybe_null': 'hyena',
},
},
    {
    'id': 59,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 159,
    'id_str': [
    '06',
    '22',
],
    'text_data': '2d41aec0ae194bef983a925c3bf5aa4c',
    'rand_digit': 8,
    'rand_number': 0.92441,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-21T13:37:50',
    'text_array': [
    '2c3b3a622fa349b3bc9b65cd29e6c268',
    '4ad3b3b8fd394318aef5bf67bfc5e70d',
],
    'words': 'mosquito butterfly',
    'nested': {
    'id': 159,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lizard',
    'hyena',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 'ape',
    'maybe': 'rabbit',
    'maybe_null': None,
},
},
    {
    'id': 60,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 160,
    'id_str': [
    '05',
],
    'text_data': 'ac859b9a43c04b1c98f1a849ea296d27',
    'rand_digit': 7,
    'rand_number': 0.2725,
    'rand_signed_int': 7,
    'rand_datetime': '2000-11-26T06:02:56.660575+1100',
    'text_array': [
    '00116015a4474c92864f61de15969ae3',
    '0a1f5870930c4641a4e5c585580390b3',
],
    'words': 'koala tiger',
    'nested': {
    'id': 160,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'whale',
    'rabbit',
],
    'city': {
    'name': 'Frankfurt',
    'geo': {
    'lat': 50.110922,
    'lon': 8.682127,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'spider',
},
},
    {
    'id': 61,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 161,
    'id_str': [
],
    'text_data': 'e55665e828864e56a4731097f5ac01bf',
    'rand_digit': 6,
    'rand_number': 0.79303,
    'rand_signed_int': 7,
    'rand_datetime': '2000-12-26T13:47:09.830466-12:00',
    'text_array': [
    'ef8ab5066dcd48f399351fadd7394040',
    '52c5cb6388874bba9fbfca56b539c68c',
],
    'words': 'lobster sheep',
    'nested': {
    'id': 161,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 6,
},
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
],
    'word': 'pig',
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
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'goat',
    'chicken',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'dragonfly',
    'maybe_null': None,
},
},
    {
    'id': 62,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 162,
    'id_str': [
],
    'text_data': 'e8d310f3d155476dbe832bb38a591f0a',
    'rand_digit': 3,
    'rand_number': 0.71891,
    'rand_signed_int': 0,
    'rand_datetime': '2000-04-17T08:29:57.389229+1100',
    'text_array': [
    'ff7c8bd673fc4538876e3ec44a3f13e5',
    '55991139c32b4a82bfb1a1e0ca192eb1',
],
    'words': 'zebra hippo',
    'nested': {
    'id': 162,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 7,
},
],
},
    'nested_array': [
    [
    10,
],
    [
    -5,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    6,
],
    [
    -6,
],
],
    'two_words': [
    'frog',
    'mosquito',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'ladybug',
},
},
    {
    'id': 63,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 163,
    'id_str': [
    '27',
],
    'text_data': 'b9cf8bee86084d5f8bd710d80b0e6742',
    'rand_digit': 0,
    'rand_number': 0.54289,
    'rand_signed_int': 2,
    'rand_datetime': '2000-08-21T20:28:44.141465',
    'text_array': [
    'f886de8d983f468997a9e068d8fd4bd5',
    'e24e69b891fd40f380b957c6aa95ed3e',
],
    'words': 'cow jaguar',
    'nested': {
    'id': 163,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 2,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'squid',
    'ant',
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
    'mixed_type': False,
    'maybe': 'turtle',
    'maybe_null': 'chicken',
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
        """测试请求 2 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/query")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/query'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '987',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': '__FLOAT_MULTI_DIM_3,50__',
},
    'using': 'multi-text',
    'limit': 10,
    'with_vector': False,
    'with_payload': True,
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
        """测试请求 3 - DELETE http://localhost:6333/collections/congruence_test_collection?timeout=60"""
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
    'content-length': '285',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'multi-text': {
    'size': 50,
    'distance': 'Cosine',
    'multivector_config': {
    'comparator': 'max_sim',
},
},
    'multi-image': {
    'size': 100,
    'distance': 'Dot',
    'multivector_config': {
    'comparator': 'max_sim',
},
},
    'multi-code': {
    'size': 80,
    'distance': 'Euclid',
    'multivector_config': {
    'comparator': 'max_sim',
},
},
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_query.test_multivec_query')
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
    test = TestQuerytestMultivecQuery()
    test.run_tests()
