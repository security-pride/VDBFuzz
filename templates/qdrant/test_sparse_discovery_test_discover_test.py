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
logger = logging.getLogger('vdb_fuzzer.test.test_sparse_discovery_test_discover')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_sparse_discovery.test_discover"
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



class TestSparseDiscoverytestDiscover:
    """自动生成的VDB模糊测试类 - test_sparse_discovery.test_discover"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_sparse_discovery.test_discover"
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
    'content-length': '85',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
},
    'sparse_vectors': {
    'sparse-text': {
},
    'sparse-image': {
},
    'sparse-code': {
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
    'content-length': '1997739',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 100,
    'id_str': [
    '01',
    '16',
    '04',
    '21',
],
    'text_data': 'f2a55420413b4f4e83068a40c6fe284b',
    'rand_digit': 0,
    'rand_number': 0.09312,
    'rand_signed_int': -7,
    'rand_datetime': '2001-01-22T19:39:22.063833',
    'text_array': [
    '1c94fdf55ec04fda813185044ca45fba',
    '4bf39ca599e34ea9adee8a342ac12f0b',
],
    'words': 'dog monkey',
    'nested': {
    'id': 100,
    'rand_digit': 5,
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
],
    'word': 'elephant',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'snail',
    'bee',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe_null': 'cat',
},
},
    {
    'id': 1,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 101,
    'id_str': [
    '12',
    '28',
    '02',
    '05',
    '23',
],
    'text_data': 'c07414d97a7046999c98bbc53c37253d',
    'rand_digit': 2,
    'rand_number': 0.67608,
    'rand_signed_int': 0,
    'rand_datetime': '2000-09-03T15:09:08.166918',
    'text_array': [
    'b4b985b80e544735b845ffd31a120bc3',
    '68d539adaffa40039b90a05ba13eabd3',
],
    'words': 'camel gorilla',
    'nested': {
    'id': 101,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'zebra',
    'duck',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': 'mouse',
},
},
    {
    'id': 2,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 102,
    'id_str': [
    '21',
],
    'text_data': '86bfe40dc20c45e0b77a803a3b200635',
    'rand_digit': 5,
    'rand_number': 0.1839,
    'rand_signed_int': 3,
    'rand_datetime': '2000-03-27 19:06:50',
    'text_array': [
    'e679787b0d33488db79fbff35c286dc6',
    'e0a4b66bb9e74e64a62078212b3fc297',
],
    'words': 'dragonfly chicken',
    'nested': {
    'id': 102,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'cheetah',
    'koala',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 3,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 103,
    'id_str': [
    '07',
    '12',
    '04',
],
    'text_data': 'b69c236f574b4ea582ff07e01a2194f3',
    'rand_digit': 9,
    'rand_number': 0.1942,
    'rand_signed_int': -6,
    'rand_datetime': '2000-12-08 12:57',
    'text_array': [
    '4ac980cd31ae41acb2b9b95775f8f0eb',
    'af56d45c563c4508aed22f728608330f',
],
    'words': 'giraffe duck',
    'nested': {
    'id': 103,
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
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'butterfly',
    'sheep',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': [
    22,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'dolphin',
    'maybe_null': None,
},
},
    {
    'id': 4,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 104,
    'id_str': [
    '27',
    '04',
    '02',
    '29',
    '30',
],
    'text_data': '3dad515dee2e47df8e9ab1456083e48b',
    'rand_digit': 3,
    'rand_number': 0.5504,
    'rand_signed_int': -8,
    'rand_datetime': '2000-03-12 13:33:00.406629',
    'text_array': [
    'acfba9501f2e4a81b0272bde1e47e7d3',
    '0758dbfea58449788ac0d41dab3c6231',
],
    'words': 'octopus mouse',
    'nested': {
    'id': 104,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    7,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'zebra',
    'leopard',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'ape',
    'maybe_null': None,
},
},
    {
    'id': 5,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 105,
    'id_str': [
    '01',
    '07',
    '16',
],
    'text_data': '880b55e011624b68aee64866c5cb93eb',
    'rand_digit': 8,
    'rand_number': 0.2416,
    'rand_signed_int': 2,
    'rand_datetime': '2000-01-07',
    'text_array': [
    '56051e1fd0544c609398658da18d26b6',
    '9835b7a40f2147359a92beff607cfe93',
],
    'words': 'ant sheep',
    'nested': {
    'id': 105,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'rabbit',
    'rhino',
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
    'mixed_type': 0.95882,
    'maybe_null': 'elephant',
},
},
    {
    'id': 6,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 106,
    'id_str': [
    '03',
    '17',
    '25',
],
    'text_data': '47e7ddef6fbe4b4b90d387b58213af43',
    'rand_digit': 3,
    'rand_number': 0.83844,
    'rand_signed_int': -1,
    'rand_datetime': '2000-09-27',
    'text_array': [
    'f98d4b32abee481eaa4b87ee57b47202',
    '0f4441580932470e8600d5f8ecaee1c9',
],
    'words': 'bird cheetah',
    'nested': {
    'id': 106,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'cow',
    'fly',
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
    'maybe_null': 'chicken',
},
},
    {
    'id': 7,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 107,
    'id_str': [
    '08',
],
    'text_data': 'e355cad54fc247ebbe28e534654abe45',
    'rand_digit': 4,
    'rand_number': 0.99964,
    'rand_signed_int': -9,
    'rand_datetime': '2000-11-23T12:05:11',
    'text_array': [
    'fcd07e6b3d654f67917ea52534892ec0',
    '9c26f9ee70cf47e7873d87b578868303',
],
    'words': 'octopus cat',
    'nested': {
    'id': 107,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'fish',
    'hippo',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 8,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 108,
    'id_str': [
    '06',
    '05',
    '04',
    '01',
],
    'text_data': '32645e82f9124c05a8adabb1468bc5a5',
    'rand_digit': 4,
    'rand_number': 0.08521,
    'rand_signed_int': -10,
    'rand_datetime': '2000-08-17 06:06',
    'text_array': [
    'a0e2360498b9444a898866d6e98931a1',
    'b57ee535bd894ff78b5388cdff33463d',
],
    'words': 'panda turtle',
    'nested': {
    'id': 108,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'camel',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 2,
},
],
},
    'nested_array': [
    [
    8,
],
],
    'two_words': [
    'sloth',
    'zebra',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 'leopard',
    'maybe_null': 'shark',
},
},
    {
    'id': 9,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 109,
    'id_str': [
    '22',
],
    'text_data': 'd72861c35f454307bdc8302cfe8b3f73',
    'rand_digit': 3,
    'rand_number': 0.46188,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-04T18:19:26.127396',
    'text_array': [
    '6f7a419a73374246936ebdbd82908d07',
    '164ddd64e8e54094918416e6e47588a3',
],
    'words': 'rhino chicken',
    'nested': {
    'id': 109,
    'rand_digit': 0,
    'array': [
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
    'hello',
],
    'word': 'snail',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ant',
    'dragonfly',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'pig',
},
},
    {
    'id': 10,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 110,
    'id_str': [
    '16',
    '08',
    '16',
    '29',
    '17',
],
    'text_data': '3a8f1c7e680a4e7e88206d70aa61db84',
    'rand_digit': 6,
    'rand_number': 0.14858,
    'rand_signed_int': -5,
    'rand_datetime': '2000-12-18T15:35:26.118275-1000',
    'text_array': [
    'd7df110d8a064db9b9e0b4af49d6550d',
    'f391d5d99f38409da3e870fe540cca65',
],
    'words': 'shark lizard',
    'nested': {
    'id': 110,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'pig',
    'number': 6,
},
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
    -9,
],
],
    'two_words': [
    'elephant',
    'tiger',
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
    'mixed_type': 9,
    'maybe_null': None,
},
},
    {
    'id': 11,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 111,
    'id_str': [
],
    'text_data': '7dcb553daf724843b176dfd09cf1e668',
    'rand_digit': 5,
    'rand_number': 0.09905,
    'rand_signed_int': 5,
    'rand_datetime': '2000-03-06 16:43:57-0700',
    'text_array': [
    'e3f58f139c4f492b910fb3e3f1e2092d',
    '42fb91d7a1514670aaa8df8288747a5f',
],
    'words': 'tiger snail',
    'nested': {
    'id': 111,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
    -3,
],
    [
    -5,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'squid',
    'lobster',
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
    'mixed_type': None,
    'maybe_null': 'crab',
},
},
    {
    'id': 12,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 112,
    'id_str': [
    '08',
],
    'text_data': '0f5bc8d06fe94895a50fb8799692bd4f',
    'rand_digit': 8,
    'rand_number': 0.99519,
    'rand_signed_int': -1,
    'rand_datetime': '2000-02-22T23:25:46.067172-1100',
    'text_array': [
    '36286eb3d1e146bb950eed23eb8c9dc7',
    'f8e096f2b9174ab196abd174be0e573c',
],
    'words': 'bear dragonfly',
    'nested': {
    'id': 112,
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
    'number': 3,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'squid',
    'fox',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'giraffe',
    'maybe_null': 'pig',
},
},
    {
    'id': 13,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 113,
    'id_str': [
    '09',
],
    'text_data': 'a4f31aac5a2f49b0b904060217e34aee',
    'rand_digit': 8,
    'rand_number': 0.31572,
    'rand_signed_int': -10,
    'rand_datetime': '2001-01-18 19:08:21.590564',
    'text_array': [
    '23008fc295084df38c87a1396851795f',
    '152e2ea778a44a3a94ea4afd9c0afb80',
],
    'words': 'hippo camel',
    'nested': {
    'id': 113,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 1,
},
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
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'whale',
    'maybe_null': 'octopus',
},
},
    {
    'id': 14,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 114,
    'id_str': [
    '19',
    '20',
    '26',
    '24',
    '06',
],
    'text_data': '5724796a422140e18894833b07ed691c',
    'rand_digit': 8,
    'rand_number': 0.61253,
    'rand_signed_int': 10,
    'rand_datetime': '2000-06-19T19:08:36.035472',
    'text_array': [
    '696f18033ada4d0c9358371b15cd5ac3',
    '621cfc7d778e4d85ab5157e5064c6210',
],
    'words': 'lobster elephant',
    'nested': {
    'id': 114,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ant',
    'crab',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 5,
    'maybe': 'snail',
    'maybe_null': 'mosquito',
},
},
    {
    'id': 15,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 115,
    'id_str': [
    '06',
    '11',
    '05',
    '07',
    '27',
],
    'text_data': '16921bdbfb5d4c10ab21c3f60956b64d',
    'rand_digit': 8,
    'rand_number': 0.03722,
    'rand_signed_int': 4,
    'rand_datetime': '2000-04-25 00:09:23+0400',
    'text_array': [
    '6064747a4a9a49c2ad6be847b8440471',
    '980bb8cba3004a878852c64ab9a4d1fe',
],
    'words': 'dragonfly hyena',
    'nested': {
    'id': 115,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'goat',
    'hippo',
],
    'city': {
    'name': 'Kuala Lumpur',
    'geo': {
    'lat': 3.139003,
    'lon': 101.686855,
},
},
    'rand_tuple': [
    17,
],
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'gorilla',
    'maybe_null': None,
},
},
    {
    'id': 16,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 116,
    'id_str': [
    '11',
],
    'text_data': '43bb0133390b43399cc8e1001e11c845',
    'rand_digit': 7,
    'rand_number': 0.36946,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-14 23:25:41.408434',
    'text_array': [
    'f5f3d262de804fc3b338d12315b776e2',
    'f70d2b07ea00443bb80ecdc7c66f8424',
],
    'words': 'horse dolphin',
    'nested': {
    'id': 116,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 5,
},
],
},
    'nested_array': [
    [
    7,
],
],
    'two_words': [
    'bee',
    'mouse',
],
    'city': {
    'name': 'Barcelona',
    'geo': {
    'lat': 41.385064,
    'lon': 2.173403,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'jaguar',
},
},
    {
    'id': 17,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 117,
    'id_str': [
    '30',
    '29',
    '05',
    '02',
],
    'text_data': 'ccc03b14783d4e348110d6ecb167102a',
    'rand_digit': 7,
    'rand_number': 0.60609,
    'rand_signed_int': 4,
    'rand_datetime': '2000-02-23 12:26:59.338266',
    'text_array': [
    '7cef00426a9246a6b5b7f9f8032c1f72',
    '886db1c9753e47a5bd13eb60a1ce3ce2',
],
    'words': 'fly hyena',
    'nested': {
    'id': 117,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'cow',
    'turtle',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'scorpion',
    'maybe_null': None,
},
},
    {
    'id': 18,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 118,
    'id_str': [
    '23',
    '28',
    '20',
],
    'text_data': '120547283bda49fc8788bbc2c26b096f',
    'rand_digit': 5,
    'rand_number': 0.22219,
    'rand_signed_int': -2,
    'rand_datetime': '2000-09-15 09:23:22',
    'text_array': [
    'e76e3ad95eed4aec987c39fe87ad241e',
    'b2d1366a5b43458ea1b9f44ea5febc19',
],
    'words': 'butterfly gorilla',
    'nested': {
    'id': 118,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'duck',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'frog',
    'koala',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': 19,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 119,
    'id_str': [
    '18',
    '17',
    '01',
],
    'text_data': 'cfab9020089f45368034424ec576c0e8',
    'rand_digit': 8,
    'rand_number': 0.57944,
    'rand_signed_int': 7,
    'rand_datetime': '2000-12-12 00:47:32.417039+0100',
    'text_array': [
    'd93fddde997b4728a4ae78ff27e40bd2',
    '76413214bb8144218455609ad2a0ca32',
],
    'words': 'leopard rhino',
    'nested': {
    'id': 119,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fly',
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
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'octopus',
    'cat',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'koala',
    'maybe_null': 'grasshopper',
},
},
    {
    'id': 20,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 120,
    'id_str': [
    '15',
    '25',
    '05',
    '15',
],
    'text_data': '6667c1f3b5c34ff98250f0b28f0d463f',
    'rand_digit': 7,
    'rand_number': 0.46967,
    'rand_signed_int': -2,
    'rand_datetime': '2000-10-09 10:04:23.881919',
    'text_array': [
    'f889784699a24ed9928d27eae977a2fa',
    'ba75759cb7b740a68d061d834fbeec71',
],
    'words': 'zebra rabbit',
    'nested': {
    'id': 120,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 5,
},
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 2,
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
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'horse',
    'snake',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'fly',
    'maybe': 'cow',
},
},
    {
    'id': 21,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 121,
    'id_str': [
    '22',
    '29',
    '04',
],
    'text_data': '7810daa392174dd5a4385a31dd1b3c00',
    'rand_digit': 8,
    'rand_number': 0.90482,
    'rand_signed_int': 2,
    'rand_datetime': '2000-03-19 00:45:54.522876-1000',
    'text_array': [
    '9fd5aac5740c40d48abc905f929746f2',
    'e0d3bdfb58384d4a9d2c540f90d2481b',
],
    'words': 'lion sloth',
    'nested': {
    'id': 121,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'cat',
    'number': 2,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'whale',
    'dolphin',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'octopus',
},
},
    {
    'id': 22,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 122,
    'id_str': [
    '08',
    '11',
    '01',
    '26',
    '03',
],
    'text_data': '606a340f5c154b18bb64dd24a02acaf7',
    'rand_digit': 9,
    'rand_number': 0.46107,
    'rand_signed_int': -1,
    'rand_datetime': '2000-03-16T15:37:15',
    'text_array': [
    'd51e179258234f02b262a159b5190af6',
    'f5a6ad5614844d8d93b78fa15ea99bde',
],
    'words': 'scorpion koala',
    'nested': {
    'id': 122,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
    7,
],
],
    'two_words': [
    'ape',
    'scorpion',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': [
    45,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'frog',
},
},
    {
    'id': 23,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 123,
    'id_str': [
    '19',
    '17',
    '24',
    '03',
    '02',
],
    'text_data': '8d04c0928d694f0dba8bb280dcb6da93',
    'rand_digit': 0,
    'rand_number': 0.62595,
    'rand_signed_int': 5,
    'rand_datetime': '2001-01-21T02:00:18+0800',
    'text_array': [
    '22f67ff2787e4b84b9fa58e633ff992b',
    '5cf0459ec8b245ecb09b448577557edf',
],
    'words': 'chicken bird',
    'nested': {
    'id': 123,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'frog',
    'number': 5,
},
    {
    'nested_empty': None,
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
    'snail',
    'grasshopper',
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
    'mixed_type': True,
    'maybe': 'fox',
},
},
    {
    'id': 24,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 124,
    'id_str': [
    '10',
    '07',
],
    'text_data': 'daede7632d9e4395b1d17f46b39474a8',
    'rand_digit': 9,
    'rand_number': 0.50898,
    'rand_signed_int': 9,
    'rand_datetime': '2000-10-03T20:55:05.491668+0200',
    'text_array': [
    'd4391a354e484cb1ab54b32671050913',
    '5fcb4ee8c1cc4f9983cbfbe964eb5042',
],
    'words': 'duck dog',
    'nested': {
    'id': 124,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 4,
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
    'hello',
],
    'word': 'giraffe',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fly',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'snake',
    'chicken',
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
    'mixed_type': False,
    'maybe': 'octopus',
    'maybe_null': None,
},
},
    {
    'id': 25,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 125,
    'id_str': [
    '11',
    '22',
    '21',
    '01',
],
    'text_data': '091ba8a1395c46848e9a15c7bf01da3f',
    'rand_digit': 3,
    'rand_number': 0.56993,
    'rand_signed_int': -8,
    'rand_datetime': '2000-04-03T18:21:59.999267+01:00',
    'text_array': [
    'f2769edcf0f24acd8b09fc62bc602ae9',
    'c10f1de0999a41d78393e481ea1d98ec',
],
    'words': 'lobster dolphin',
    'nested': {
    'id': 125,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fox',
    'hyena',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'lizard',
},
},
    {
    'id': 26,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 126,
    'id_str': [
    '29',
    '15',
    '20',
],
    'text_data': '6f4fb306a61b41ada6096e6d345d2982',
    'rand_digit': 6,
    'rand_number': 0.67846,
    'rand_signed_int': -3,
    'rand_datetime': '2000-01-17 09:03',
    'text_array': [
    'ac5ce3f6f64b477c96ec67ddc567e4a5',
    '15cde75b890e4a0f999c74afb2494b9b',
],
    'words': 'hyena spider',
    'nested': {
    'id': 126,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'giraffe',
    'crab',
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
    'mixed_type': None,
    'maybe': 'lion',
},
},
    {
    'id': 27,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 127,
    'id_str': [
],
    'text_data': 'f4e2fec602f24756909aebdbbdcff6dd',
    'rand_digit': 7,
    'rand_number': 0.94977,
    'rand_signed_int': 7,
    'rand_datetime': '2000-08-06T23:07:08',
    'text_array': [
    '01fb67c351f442fc9b955dc5f3d07860',
    '9b0b4ec317a54adf9603b639d78e1260',
],
    'words': 'chicken zebra',
    'nested': {
    'id': 127,
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
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'zebra',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'lizard',
    'goat',
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
    'mixed_type': False,
    'maybe_null': None,
},
},
    {
    'id': 28,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 128,
    'id_str': [
],
    'text_data': 'a8352df73a564eb99839bb6771699259',
    'rand_digit': 8,
    'rand_number': 0.30926,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-07 12:24:09-0700',
    'text_array': [
    '4a9308b07e0d418b977a6c97ca7e93b4',
    '53af28be454e432aa671c1471971cd36',
],
    'words': 'wolf spider',
    'nested': {
    'id': 128,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lion',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'scorpion',
    'hyena',
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
    'maybe_null': 'rabbit',
},
},
    {
    'id': 29,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 129,
    'id_str': [
],
    'text_data': 'b51366a44ab241e7bbb9cf9d541c37e2',
    'rand_digit': 5,
    'rand_number': 0.69158,
    'rand_signed_int': -7,
    'rand_datetime': '2000-04-09 07:58:16',
    'text_array': [
    '735777dad90e409da211bef17140519c',
    '76313c9fc521440f89062f91cdf0a3bb',
],
    'words': 'bird fly',
    'nested': {
    'id': 129,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'fish',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fly',
    'octopus',
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
    'mixed_type': 0.95242,
    'maybe_null': None,
},
},
    {
    'id': 30,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 130,
    'id_str': [
    '07',
    '19',
],
    'text_data': '499cc47d00954310b6054645e02a7672',
    'rand_digit': 7,
    'rand_number': 0.65979,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-12T19:09:10.283940',
    'text_array': [
    'db66f6326f0c43a788ae475fe3191927',
    '3c9d7158a7d24fbf9eebe4c31aae9988',
],
    'words': 'bear goat',
    'nested': {
    'id': 130,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'mouse',
    'bee',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'zebra',
    'maybe_null': 'gorilla',
},
},
    {
    'id': 31,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 131,
    'id_str': [
    '21',
    '14',
],
    'text_data': '1b82c41959ac417492468ba1fc7b4470',
    'rand_digit': 8,
    'rand_number': 0.19256,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-13 15:24:56.265920+0300',
    'text_array': [
    '9a2e8cc0ba344f83bd6294b20a38010c',
    'df185086254242bbae46268f202355ee',
],
    'words': 'lizard gorilla',
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
    'word': 'chicken',
    'number': 2,
},
    {
    'nested_empty': None,
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
    'word': 'ant',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'butterfly',
    'monkey',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cheetah',
    'maybe_null': 'lion',
},
},
    {
    'id': 32,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 132,
    'id_str': [
    '20',
    '22',
    '13',
    '08',
],
    'text_data': 'd889d5ebe54c427585c02cf5b3a6cb17',
    'rand_digit': 0,
    'rand_number': 0.22291,
    'rand_signed_int': -7,
    'rand_datetime': '2000-07-21 16:50:09.786631-0800',
    'text_array': [
    '2b9c8f8431f84de480cbd67a6c7c3c2f',
    '834f33fc7c4d44979df17c6ba045089c',
],
    'words': 'snake lion',
    'nested': {
    'id': 132,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    7,
],
],
    'two_words': [
    'wolf',
    'mouse',
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
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': 33,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 133,
    'id_str': [
    '18',
    '05',
    '07',
    '15',
],
    'text_data': '66110bb7e26544879f0b9798d1c5c078',
    'rand_digit': 4,
    'rand_number': 0.13191,
    'rand_signed_int': 2,
    'rand_datetime': '2000-11-23T01:41:18',
    'text_array': [
    '4581f2f7ddeb4f2fa7bae77f2fa45f7c',
    '2f2af379d74c4152a31b4a96a3f60314',
],
    'words': 'cheetah fly',
    'nested': {
    'id': 133,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dog',
    'tiger',
],
    'city': {
    'name': 'Zurich',
    'geo': {
    'lat': 47.376887,
    'lon': 8.541694,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.70558,
    'maybe': 'crab',
    'maybe_null': 'rhino',
},
},
    {
    'id': 34,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 134,
    'id_str': [
    '04',
    '03',
    '13',
    '25',
    '23',
],
    'text_data': '36cd626852a74721a2a35903bcdf076d',
    'rand_digit': 2,
    'rand_number': 0.4732,
    'rand_signed_int': 10,
    'rand_datetime': '2000-12-03 11:58',
    'text_array': [
    '3dc31df3ff614af494aeb31bef799296',
    'df201442cf9c4dcc88ae51300b6e710d',
],
    'words': 'leopard gorilla',
    'nested': {
    'id': 134,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'wolf',
    'monkey',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'zebra',
},
},
    {
    'id': 35,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 135,
    'id_str': [
    '08',
    '19',
    '20',
    '16',
    '24',
],
    'text_data': '9d3792fd76a649e3ae679ae44d9d2f97',
    'rand_digit': 0,
    'rand_number': 0.00155,
    'rand_signed_int': -6,
    'rand_datetime': '2000-06-29 09:57:10.558355',
    'text_array': [
    'ec5336629e624c13baa368c32b96ff38',
    'f8ea4448c5ef4de3a394e606b5f09c76',
],
    'words': 'butterfly scorpion',
    'nested': {
    'id': 135,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 6,
},
],
},
    'nested_array': [
    [
    1,
],
],
    'two_words': [
    'jaguar',
    'tiger',
],
    'city': {
    'name': 'Zurich',
    'geo': {
    'lat': 47.376887,
    'lon': 8.541694,
},
},
    'rand_tuple': [
    79,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'snail',
    'maybe_null': 'lion',
},
},
    {
    'id': 36,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 136,
    'id_str': [
    '30',
],
    'text_data': '4e768d78829e4d10a8fba9bbac918dbb',
    'rand_digit': 2,
    'rand_number': 0.411,
    'rand_signed_int': -6,
    'rand_datetime': '2000-02-02 06:09:07+0500',
    'text_array': [
    '909cdbfc064b406ca5a68327352d4d2e',
    'e062e24e5c994be7a5795249b2c9df1a',
],
    'words': 'spider hyena',
    'nested': {
    'id': 136,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'tiger',
    'bird',
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
    'mixed_type': True,
    'maybe': 'octopus',
},
},
    {
    'id': 37,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 137,
    'id_str': [
    '10',
    '15',
    '04',
    '26',
    '04',
],
    'text_data': 'b4a7f770ef914d5ea74281ce7b76da78',
    'rand_digit': 9,
    'rand_number': 0.78698,
    'rand_signed_int': -6,
    'rand_datetime': '2000-03-16 00:40',
    'text_array': [
    '94dffc6a629449058cba841d4885488c',
    '59cb0835d610454db940d8969b948467',
],
    'words': 'ladybug wolf',
    'nested': {
    'id': 137,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fish',
    'cheetah',
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
    'mixed_type': 4,
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 38,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 138,
    'id_str': [
],
    'text_data': '8176d3597958468a829eff22e1e43b7b',
    'rand_digit': 7,
    'rand_number': 0.94451,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-18T17:13:54.469066+0300',
    'text_array': [
    'bbd799b68dd04211b9cbe87bf16fe013',
    'c7b2f121bd174a278e55cc24a50d6502',
],
    'words': 'shark fly',
    'nested': {
    'id': 138,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'rhino',
    'wolf',
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
    'mixed_type': 'sheep',
    'maybe': 'fly',
    'maybe_null': None,
},
},
    {
    'id': 39,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 139,
    'id_str': [
    '14',
    '24',
    '13',
    '22',
    '10',
],
    'text_data': '0e5c2b5af2da40249a75d8ce98933a6d',
    'rand_digit': 8,
    'rand_number': 0.53879,
    'rand_signed_int': 8,
    'rand_datetime': '2000-01-24T12:29:24.094424',
    'text_array': [
    'cb911b79eadf46f7845afd9b2eda63c5',
    '130af9c5ce414841ac3150e43d25fe6f',
],
    'words': 'bee lobster',
    'nested': {
    'id': 139,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'bear',
    'wolf',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 'scorpion',
    'maybe_null': None,
},
},
    {
    'id': 40,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 140,
    'id_str': [
    '04',
    '29',
    '29',
    '16',
],
    'text_data': '1bfc6b808e77482e84f6a34cde76bd8e',
    'rand_digit': 1,
    'rand_number': 0.90242,
    'rand_signed_int': -9,
    'rand_datetime': '2000-03-21T16:04:07',
    'text_array': [
    'a6665e9251db4264b2187d4d625ca88e',
    '5fc6c7b49e804be3b9f38abac8a4c130',
],
    'words': 'sheep snake',
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
    'word': 'gorilla',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dog',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'elephant',
    'lobster',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bird',
    'maybe_null': 'cow',
},
},
    {
    'id': 41,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 141,
    'id_str': [
    '05',
    '04',
],
    'text_data': '96fa6d313a6445c48cf99f24353db7ee',
    'rand_digit': 7,
    'rand_number': 0.89361,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-02T17:39:13.764760',
    'text_array': [
    'ad7074ebdceb462385bba95a05c8a5a1',
    '5618e51b713e4948bde228bc792f99ec',
],
    'words': 'cow crab',
    'nested': {
    'id': 141,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'octopus',
    'goat',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'snake',
    'maybe_null': 'butterfly',
},
},
    {
    'id': 42,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 142,
    'id_str': [
    '12',
],
    'text_data': '11418c7368334d54b25403946a14a9b0',
    'rand_digit': 4,
    'rand_number': 0.2966,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-17',
    'text_array': [
    'fad3c6a781954c8ea51c5e8d3359ac8f',
    '274445f1feea425f8bd7b108ba00b35d',
],
    'words': 'grasshopper horse',
    'nested': {
    'id': 142,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'frog',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'lobster',
    'monkey',
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
    'mixed_type': None,
    'maybe': 'lion',
    'maybe_null': 'lion',
},
},
    {
    'id': 43,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 143,
    'id_str': [
    '07',
    '27',
    '20',
    '17',
],
    'text_data': '6e9f49eac9014e87934aee0432fb9d57',
    'rand_digit': 7,
    'rand_number': 0.3145,
    'rand_signed_int': -8,
    'rand_datetime': '2000-06-13 06:49:36',
    'text_array': [
    '0651ce12080f4d0e920c80c6315446d1',
    '9dc848a0da0a4263821c0011ecc17eee',
],
    'words': 'leopard sloth',
    'nested': {
    'id': 143,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'chicken',
    'koala',
],
    'city': {
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 8,
    'maybe_null': 'turtle',
},
},
    {
    'id': 44,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 144,
    'id_str': [
],
    'text_data': '3f49b2d3d96b4fc78c6ab9bdd9dd06fb',
    'rand_digit': 5,
    'rand_number': 0.60714,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-13 17:02:27',
    'text_array': [
    'c441632482bc4d33be836f08a118012c',
    '37f2ce6d5e2d40bbbdc79d6f826c361c',
],
    'words': 'cheetah dragonfly',
    'nested': {
    'id': 144,
    'rand_digit': 2,
    'array': [
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
    'hello',
],
    'word': 'rhino',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 1,
},
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lion',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'goat',
    'snail',
],
    'city': {
    'name': 'Kharkiv',
    'geo': {
    'lat': 49.980812,
    'lon': 36.25272,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'spider',
    'maybe_null': 'turtle',
},
},
    {
    'id': 45,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 145,
    'id_str': [
    '17',
    '25',
    '23',
    '05',
],
    'text_data': '939043389e2d464fb99b95b8929e6cce',
    'rand_digit': 1,
    'rand_number': 0.39614,
    'rand_signed_int': 4,
    'rand_datetime': '2000-10-12 22:56:40.882836',
    'text_array': [
    'a7c3f8578b3845bab51209a93bbd2fde',
    'a12c8f51317d401e977a94fd976a247b',
],
    'words': 'panda wolf',
    'nested': {
    'id': 145,
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
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'turtle',
    'squid',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'squid',
},
},
    {
    'id': 46,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 146,
    'id_str': [
],
    'text_data': 'c99d9040c8e5499ebddb08d0e9a704e0',
    'rand_digit': 3,
    'rand_number': 0.74327,
    'rand_signed_int': 0,
    'rand_datetime': '2000-09-19T20:54:04.238214',
    'text_array': [
    'e18f758bc89d4e5884b668eea72b6461',
    '56bc5e57bcc6459590d824f27ce99528',
],
    'words': 'duck giraffe',
    'nested': {
    'id': 146,
    'rand_digit': 6,
    'array': [
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
    'word': 'hippo',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -5,
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'tiger',
    'dolphin',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': [
    16,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'lobster',
    'maybe_null': 'camel',
},
},
    {
    'id': 47,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 147,
    'id_str': [
    '18',
    '06',
],
    'text_data': '8f1a3221b978473ba4226cd49a5ff101',
    'rand_digit': 5,
    'rand_number': 0.60836,
    'rand_signed_int': -8,
    'rand_datetime': '2000-10-21 07:15:08.355621-0600',
    'text_array': [
    '0d0aed931013448da68d72bc24663db1',
    'cf8345f94b224bea85d9356e573fedaf',
],
    'words': 'frog cheetah',
    'nested': {
    'id': 147,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bird',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fish',
    'grasshopper',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 48,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 148,
    'id_str': [
],
    'text_data': '9f75529914c24c2785278e80aae049e7',
    'rand_digit': 3,
    'rand_number': 0.9631,
    'rand_signed_int': -1,
    'rand_datetime': '2000-12-10T19:18:40+1100',
    'text_array': [
    'fbac1ad3909a4cffaae6dda509a31596',
    '0fe8eea108e8455e94d49a4419f6191b',
],
    'words': 'ape lobster',
    'nested': {
    'id': 148,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'rabbit',
    'panda',
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
    'mixed_type': None,
    'maybe_null': 'rhino',
},
},
    {
    'id': 49,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 149,
    'id_str': [
    '16',
    '25',
    '16',
    '13',
    '24',
],
    'text_data': 'aaede5b645584c99b14223f4c1820433',
    'rand_digit': 1,
    'rand_number': 0.53042,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-18',
    'text_array': [
    '5c0b309d14c24985866aa468a407def8',
    '47822ad3695c47bbaf6a1a43eb422d3d',
],
    'words': 'mosquito dolphin',
    'nested': {
    'id': 149,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    4,
],
    [
    1,
],
],
    'two_words': [
    'sheep',
    'cat',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'crab',
},
},
    {
    'id': 50,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 150,
    'id_str': [
    '28',
    '20',
],
    'text_data': 'bcda1c4d1669460b874fd316d81a746b',
    'rand_digit': 4,
    'rand_number': 0.37443,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-05T17:42:46',
    'text_array': [
    'a7443384cbb349b38e57c9ee4a000e6b',
    '00ded59c7b35422482a2d1259dbf6d6b',
],
    'words': 'lobster deer',
    'nested': {
    'id': 150,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
    'number': 5,
},
    {
    'nested_empty': None,
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
    'word': 'wolf',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'snake',
    'goat',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'mouse',
},
},
    {
    'id': 51,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 151,
    'id_str': [
    '19',
    '17',
    '09',
    '18',
    '19',
],
    'text_data': 'bd5741401372434491bc407211c97ba5',
    'rand_digit': 0,
    'rand_number': 0.82075,
    'rand_signed_int': -10,
    'rand_datetime': '2000-09-15 00:37',
    'text_array': [
    'abbae1bac1c541f691370c5aa337c410',
    '100820ed8a124c83a006af0346aad15a',
],
    'words': 'butterfly kangaroo',
    'nested': {
    'id': 151,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 7,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'elephant',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'cat',
    'crab',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 7,
    'maybe': 'hyena',
    'maybe_null': 'panda',
},
},
    {
    'id': 52,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 152,
    'id_str': [
    '09',
    '09',
    '08',
    '30',
],
    'text_data': 'e335a9ad1ba549c9bd94f2831a0f2010',
    'rand_digit': 7,
    'rand_number': 0.15184,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-21T05:56:18.206875',
    'text_array': [
    'f60716abe6d74909b0c3828db9692a35',
    'df22841a3fca48a696660816dd3f88fa',
],
    'words': 'snail camel',
    'nested': {
    'id': 152,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    1,
],
],
    'two_words': [
    'hippo',
    'sheep',
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
    'mixed_type': 'panda',
    'maybe': 'camel',
    'maybe_null': None,
},
},
    {
    'id': 53,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 153,
    'id_str': [
    '09',
    '04',
    '19',
    '10',
],
    'text_data': 'a25a00c579b64fe8996ab55e9c8e0536',
    'rand_digit': 8,
    'rand_number': 0.35627,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-13T09:32:21.393882-05:00',
    'text_array': [
    '43e2f0ea0955437d9e9c4b0755e68896',
    '6dd70410e7344b80b8483fb22b89e379',
],
    'words': 'horse shark',
    'nested': {
    'id': 153,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,3__',
    'two_words': [
    'whale',
    'cat',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'fish',
    'maybe_null': 'koala',
},
},
    {
    'id': 54,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 154,
    'id_str': [
    '07',
    '22',
],
    'text_data': 'e57b948c39d84c48b1c4933f66c24f49',
    'rand_digit': 9,
    'rand_number': 0.99082,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-10T11:13:24.749434',
    'text_array': [
    '9ac4c294296e45578edb152992bb920c',
    'e9ac5150d63c4fd3a62e9036383c640f',
],
    'words': 'monkey leopard',
    'nested': {
    'id': 154,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 7,
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
    'word': 'cheetah',
    'number': 10,
},
],
},
    'nested_array': [
    [
    5,
],
    [
    -2,
],
],
    'two_words': [
    'kangaroo',
    'monkey',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': [
    12,
],
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'mosquito',
    'maybe_null': None,
},
},
    {
    'id': 55,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 155,
    'id_str': [
],
    'text_data': '1a3a78efbb02466d979e1294b54c246f',
    'rand_digit': 1,
    'rand_number': 0.66298,
    'rand_signed_int': -7,
    'rand_datetime': '2000-11-17 02:42:29-0400',
    'text_array': [
    '8e98d3fb24f740ab9bf35670421c7f93',
    'b8915b4c03d74726ad1177448ddf3980',
],
    'words': 'lobster frog',
    'nested': {
    'id': 155,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'duck',
    'bird',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'lion',
    'maybe_null': None,
},
},
    {
    'id': 56,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 156,
    'id_str': [
],
    'text_data': '6488d620500d480abf136a93ca564fa0',
    'rand_digit': 9,
    'rand_number': 0.79918,
    'rand_signed_int': 4,
    'rand_datetime': '2000-06-01 21:44',
    'text_array': [
    '33e716d6829e499185b62fadae499418',
    'd2bd9f879d9142968f9d3e6fe39e1755',
],
    'words': 'whale frog',
    'nested': {
    'id': 156,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'goat',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'shark',
    'hippo',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'deer',
    'maybe_null': 'rhino',
},
},
    {
    'id': 57,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 157,
    'id_str': [
    '07',
    '18',
],
    'text_data': '4efb33addbae43069ac67e16793a4fc4',
    'rand_digit': 8,
    'rand_number': 0.70789,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-15 19:26:30+1100',
    'text_array': [
    'd38b9d96d9834fc8941ca0502af510c3',
    '4cbdfd5c171e41228bc66c3d288dd523',
],
    'words': 'grasshopper wolf',
    'nested': {
    'id': 157,
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
    'number': 8,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 9,
},
],
},
    'nested_array': [
    [
    -4,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lizard',
    'cow',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': [
    1,
],
    'rand_bool': False,
    'mixed_type': 9,
    'maybe': 'bear',
    'maybe_null': 'dolphin',
},
},
    {
    'id': 58,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 158,
    'id_str': [
    '01',
    '30',
    '21',
    '14',
    '23',
],
    'text_data': '97edf7dd220840ca94d5dc54ccd12546',
    'rand_digit': 3,
    'rand_number': 0.03745,
    'rand_signed_int': 5,
    'rand_datetime': '2000-01-20 19:35:52.800724',
    'text_array': [
    '16d5c33c17fc4fec8641e9cfb94837b8',
    '30dab3543f124304aee964accd07810f',
],
    'words': 'spider spider',
    'nested': {
    'id': 158,
    'rand_digit': 9,
    'array': [
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
    'word': 'mosquito',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 1,
},
],
},
    'nested_array': [
    [
    -7,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -5,
],
],
    'two_words': [
    'kangaroo',
    'jaguar',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'cat',
    'maybe_null': 'grasshopper',
},
},
    {
    'id': 59,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 159,
    'id_str': [
    '05',
    '20',
    '04',
],
    'text_data': '486590b1688f4aa3bda3b366e548ec78',
    'rand_digit': 3,
    'rand_number': 0.56537,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-07',
    'text_array': [
    'bedbea89b2c54476a135da31e1361a05',
    '42553123099840989651a786a8a93fbe',
],
    'words': 'giraffe goat',
    'nested': {
    'id': 159,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dog',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'jaguar',
    'duck',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': [
    20,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'dog',
},
},
    {
    'id': 60,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 160,
    'id_str': [
    '27',
    '15',
],
    'text_data': 'b05cd56f1c134ccab0c3278e97d82478',
    'rand_digit': 5,
    'rand_number': 0.87571,
    'rand_signed_int': -7,
    'rand_datetime': '2000-07-15T14:58:38.311889',
    'text_array': [
    '473ecde97e92480a9fd9fcbaa47b857a',
    'c291a11fbc84493f9316c8ced9fd37b2',
],
    'words': 'butterfly tiger',
    'nested': {
    'id': 160,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'kangaroo',
    'crab',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.71417,
    'maybe_null': 'butterfly',
},
},
    {
    'id': 61,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 161,
    'id_str': [
    '18',
    '20',
    '17',
],
    'text_data': '0f30d12dae1d4e009cba5cf1fd14c028',
    'rand_digit': 9,
    'rand_number': 0.06956,
    'rand_signed_int': 9,
    'rand_datetime': '2001-01-29T17:32:29.268536',
    'text_array': [
    '2fbdd68ef0034b629fa63563517f7128',
    'b4cebc02ff044aa4b6368319daea79b2',
],
    'words': 'jaguar cheetah',
    'nested': {
    'id': 161,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'turtle',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -5,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lizard',
    'leopard',
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
    'mixed_type': False,
    'maybe_null': 'dog',
},
},
    {
    'id': 62,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 162,
    'id_str': [
    '13',
    '16',
    '03',
    '04',
],
    'text_data': '6ce759e8e5a34670af52d1f8f4039c7c',
    'rand_digit': 6,
    'rand_number': 0.19838,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-14 23:38:27.471113',
    'text_array': [
    '5cc679cd44cc45a2990771acbe37d0f4',
    '032e729459ce438baf23b7d369f3ba1c',
],
    'words': 'snail horse',
    'nested': {
    'id': 162,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'koala',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'cheetah',
    'ant',
],
    'city': {
    'name': 'Rome',
    'geo': {
    'lat': 41.902782,
    'lon': 12.496366,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 5,
    'maybe': 'tiger',
},
},
    {
    'id': 63,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 163,
    'id_str': [
    '27',
    '21',
    '22',
],
    'text_data': '0d603594df0a4a8d8ba5496781ffa7b0',
    'rand_digit': 7,
    'rand_number': 0.67347,
    'rand_signed_int': -4,
    'rand_datetime': '2000-06-27 17:59:49.207371',
    'text_array': [
    '680cde7fcf544f32bf07f3ae6c250dcd',
    'f35a35abc3a1471bb0b7bb41ea65f592',
],
    'words': 'chicken snail',
    'nested': {
    'id': 163,
    'rand_digit': 7,
    'array': [
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
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
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    0,
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'goat',
    'lion',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'bird',
    'maybe_null': 'snake',
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
    'content-length': '85',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
},
    'sparse_vectors': {
    'sparse-text': {
},
    'sparse-image': {
},
    'sparse-code': {
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
    'content-length': '2000092',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 100,
    'id_str': [
    '28',
    '15',
    '09',
],
    'text_data': '1f6fa168a75742c7b33a2794c62755f8',
    'rand_digit': 2,
    'rand_number': 0.45443,
    'rand_signed_int': 5,
    'rand_datetime': '2000-01-29T00:53:29',
    'text_array': [
    '52fd03d3d27a466ea8896a44f38eba87',
    '3c93bd1d68cd49698f826787ffb2fd35',
],
    'words': 'hyena octopus',
    'nested': {
    'id': 100,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hyena',
    'crab',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.71637,
    'maybe_null': None,
},
},
    {
    'id': 1,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 101,
    'id_str': [
    '03',
    '13',
    '26',
    '22',
    '14',
],
    'text_data': '2e87e3c4b8e349f198801e29524aad73',
    'rand_digit': 6,
    'rand_number': 0.02753,
    'rand_signed_int': -7,
    'rand_datetime': '2000-10-23',
    'text_array': [
    'dfe66db0dcb04661a7481a9b8bb5f224',
    '6eec0ffb78ce498cbae75e80900a9667',
],
    'words': 'bird mosquito',
    'nested': {
    'id': 101,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'frog',
    'lobster',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'dog',
},
},
    {
    'id': 2,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 102,
    'id_str': [
    '26',
    '03',
    '06',
    '15',
],
    'text_data': 'f1b52ee2fc3e48ec97db412378599dfb',
    'rand_digit': 4,
    'rand_number': 0.07306,
    'rand_signed_int': -10,
    'rand_datetime': '2000-06-09 03:51:34.097750',
    'text_array': [
    '36cd8984280944c09c784d5c2781b184',
    'b5db335f5fb34ac8b58ec8bbb4979579',
],
    'words': 'cat fox',
    'nested': {
    'id': 102,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 9,
},
    {
    'nested_empty': None,
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
    'word': 'scorpion',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'kangaroo',
    'bear',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': [
    84,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 3,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 103,
    'id_str': [
    '28',
    '20',
    '07',
    '26',
],
    'text_data': 'de152a2c980b43799736cfb577ea782d',
    'rand_digit': 7,
    'rand_number': 0.50756,
    'rand_signed_int': 9,
    'rand_datetime': '2000-03-24T11:47:25.063173-05:00',
    'text_array': [
    'a75b22cb3f8c4deb94915b7b14b21968',
    '183e1de78e284c6d86264ea5142662aa',
],
    'words': 'mouse rabbit',
    'nested': {
    'id': 103,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 5,
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
],
},
    'nested_array': [
],
    'two_words': [
    'gorilla',
    'chicken',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': None,
},
},
    {
    'id': 4,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 104,
    'id_str': [
    '29',
    '29',
    '27',
    '25',
    '29',
],
    'text_data': '6db0bb9e842d403a921610afa1f962d2',
    'rand_digit': 7,
    'rand_number': 0.20768,
    'rand_signed_int': -1,
    'rand_datetime': '2001-01-02T21:41:24.439771',
    'text_array': [
    '73622d6980f64470b7b54f01f84d2bc5',
    '46c6f53086f9485181a493c5a77a0662',
],
    'words': 'mosquito dolphin',
    'nested': {
    'id': 104,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 6,
},
    {
    'nested_empty': None,
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
    'word': 'ape',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'shark',
    'panda',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'leopard',
},
},
    {
    'id': 5,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 105,
    'id_str': [
    '09',
    '08',
    '06',
    '12',
],
    'text_data': '3778a97c167a42dbb990962fbafe6a86',
    'rand_digit': 7,
    'rand_number': 0.76789,
    'rand_signed_int': 3,
    'rand_datetime': '2000-09-17T22:20:29.873263',
    'text_array': [
    '2b323ffb14d9419aac2fc7eab2216b9f',
    '565c184586f04ae1adbed6eb7b9be2f3',
],
    'words': 'chicken cheetah',
    'nested': {
    'id': 105,
    'rand_digit': 7,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -3,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'fish',
    'horse',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': [
    50,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 6,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 106,
    'id_str': [
    '22',
    '19',
    '02',
],
    'text_data': '35d9a4d05466434b99ceb929d4b435cd',
    'rand_digit': 3,
    'rand_number': 0.40913,
    'rand_signed_int': 4,
    'rand_datetime': '2000-11-30',
    'text_array': [
    '08b50ebb3c32481f9a20f5102263a495',
    '837e160981054f039c8d1c64f35d788c',
],
    'words': 'turtle hyena',
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
    'word': 'lizard',
    'number': 1,
},
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
    'word': 'pig',
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
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bee',
    'dragonfly',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 3,
    'maybe': 'duck',
    'maybe_null': None,
},
},
    {
    'id': 7,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 107,
    'id_str': [
    '27',
    '29',
    '15',
],
    'text_data': '57c0aaacbb9c415380098fb5cae24994',
    'rand_digit': 9,
    'rand_number': 0.99802,
    'rand_signed_int': 8,
    'rand_datetime': '2000-05-18T10:48:42.270077',
    'text_array': [
    'b2075a8d04b9446999e6952ff1742c1b',
    '8dadaa461b3642c6a01365214674e0df',
],
    'words': 'giraffe mosquito',
    'nested': {
    'id': 107,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 1,
},
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
],
    'word': 'whale',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'bee',
    'octopus',
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
    'mixed_type': 0.96489,
},
},
    {
    'id': 8,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 108,
    'id_str': [
    '05',
    '29',
    '10',
    '15',
    '19',
],
    'text_data': '92b2545b96b44737babcb95fc46d7cdd',
    'rand_digit': 1,
    'rand_number': 0.20499,
    'rand_signed_int': -5,
    'rand_datetime': '2000-06-05 16:37:53.856446',
    'text_array': [
    '4f8ff38d22a94463a5790ca48ec67f3e',
    '02df7cfe0e234181a1eba53318c531ed',
],
    'words': 'snake squid',
    'nested': {
    'id': 108,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 2,
},
],
},
    'nested_array': [
    [
    2,
],
],
    'two_words': [
    'butterfly',
    'duck',
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
    'mixed_type': None,
    'maybe_null': 'jaguar',
},
},
    {
    'id': 9,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 109,
    'id_str': [
],
    'text_data': '83517347af464c2f899cd7262d1431d6',
    'rand_digit': 4,
    'rand_number': 0.88681,
    'rand_signed_int': -6,
    'rand_datetime': '2000-02-27T22:16:06',
    'text_array': [
    '6f1f3131ac954dea8f328c27bf644847',
    '12e670d21ee14adfb7a7944fe21ee43c',
],
    'words': 'rabbit bird',
    'nested': {
    'id': 109,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    4,
],
],
    'two_words': [
    'panda',
    'mosquito',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'deer',
    'maybe_null': 'crab',
},
},
    {
    'id': 10,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 110,
    'id_str': [
    '29',
    '21',
    '19',
    '07',
],
    'text_data': 'd2c2f7ec83da4643b8e4d2186ce99a79',
    'rand_digit': 8,
    'rand_number': 0.10848,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-03T05:25:41.997742+1000',
    'text_array': [
    '9d08a363f597423fadf0fdce00834bea',
    'e4a12bce9fc04b54a032684ca3c20b06',
],
    'words': 'duck frog',
    'nested': {
    'id': 110,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'monkey',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'rabbit',
    'koala',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': [
    44,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'ladybug',
},
},
    {
    'id': 11,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 111,
    'id_str': [
    '04',
    '30',
    '11',
    '14',
],
    'text_data': 'f91d0ed7d3454e3885f3bb377b60aa36',
    'rand_digit': 1,
    'rand_number': 0.40125,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-25 17:48',
    'text_array': [
    '4dc94073b6c342e4bdcf5caf3d96bf69',
    '7ec4d1fa61524d1598e6ad50fe6145c5',
],
    'words': 'cheetah fish',
    'nested': {
    'id': 111,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'chicken',
    'crab',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
},
},
    'rand_tuple': [
    18,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'chicken',
},
},
    {
    'id': 12,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 112,
    'id_str': [
    '24',
    '05',
],
    'text_data': '5641d3653ddf4e909d908db2bf419439',
    'rand_digit': 0,
    'rand_number': 0.73895,
    'rand_signed_int': 0,
    'rand_datetime': '2000-04-30 06:24:16',
    'text_array': [
    'c95fd9928b734086af3086945615ae58',
    'a508fb5494364383bd659937aed36290',
],
    'words': 'chicken grasshopper',
    'nested': {
    'id': 112,
    'rand_digit': 5,
    'array': [
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
    'hello',
],
    'word': 'mouse',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'gorilla',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'lion',
    'turtle',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': [
    68,
],
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'bee',
},
},
    {
    'id': 13,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 113,
    'id_str': [
    '01',
    '19',
    '01',
    '14',
    '12',
],
    'text_data': 'e3d73e3f72964dd5a15375d86d310628',
    'rand_digit': 1,
    'rand_number': 0.41463,
    'rand_signed_int': -10,
    'rand_datetime': '2000-06-13',
    'text_array': [
    'fc12d2cffd6244a4a516cb321769f3ec',
    'c73f2ed8bfb34c18985c27e86120e1e6',
],
    'words': 'whale mouse',
    'nested': {
    'id': 113,
    'rand_digit': 7,
    'array': [
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
    'hello',
],
    'word': 'koala',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    9,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'lion',
    'mouse',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'goat',
    'maybe_null': 'zebra',
},
},
    {
    'id': 14,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 114,
    'id_str': [
    '03',
],
    'text_data': '51721970273040f4b073dcd32dcd9de9',
    'rand_digit': 1,
    'rand_number': 0.4469,
    'rand_signed_int': 3,
    'rand_datetime': '2000-04-04 23:05',
    'text_array': [
    '53cbf1013f4449b58f0607b0b43f504c',
    '4b2855116dbf4683877a7ba8332a8c96',
],
    'words': 'lion turtle',
    'nested': {
    'id': 114,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'crab',
    'deer',
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
    'mixed_type': None,
    'maybe': 'koala',
    'maybe_null': 'cheetah',
},
},
    {
    'id': 15,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 115,
    'id_str': [
    '12',
],
    'text_data': 'cbe2c2a048244d60a75df23de0782328',
    'rand_digit': 7,
    'rand_number': 0.84502,
    'rand_signed_int': 7,
    'rand_datetime': '2000-09-20 23:08:09',
    'text_array': [
    '9d05197d323f43c2948cf0daf642c066',
    '395a838e4b694c2a8c096b78b0b68068',
],
    'words': 'wolf zebra',
    'nested': {
    'id': 115,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 2,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,2__',
    'two_words': [
    'lizard',
    'tiger',
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
    'mixed_type': None,
    'maybe': 'butterfly',
    'maybe_null': 'mosquito',
},
},
    {
    'id': 16,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 116,
    'id_str': [
    '20',
    '25',
    '28',
],
    'text_data': '6a869eb998c241f3bbfc22ca49a45e23',
    'rand_digit': 8,
    'rand_number': 0.16499,
    'rand_signed_int': -8,
    'rand_datetime': '2000-05-11T13:15:13.680722+0500',
    'text_array': [
    'ed097984c091400a859b66ab6926438a',
    'b47a38df189e4936ab860f9d676165be',
],
    'words': 'zebra pig',
    'nested': {
    'id': 116,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'horse',
    'hyena',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'bird',
},
},
    {
    'id': 17,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 117,
    'id_str': [
],
    'text_data': '2befefc0e65548069f73b9ab6716c20e',
    'rand_digit': 6,
    'rand_number': 0.596,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-01 08:12:15.252312',
    'text_array': [
    '4e5b716575e74ce59c0d3c3e4b59c7be',
    '0953808315704bdd9683214a47e874ec',
],
    'words': 'jaguar wolf',
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
    'word': 'ant',
    'number': 5,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'tiger',
    'wolf',
],
    'city': {
    'name': 'Kharkiv',
    'geo': {
    'lat': 49.980812,
    'lon': 36.25272,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 'elephant',
    'maybe_null': 'turtle',
},
},
    {
    'id': 18,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 118,
    'id_str': [
    '14',
],
    'text_data': '0f5708a6d9624ef5a2314bb208a142de',
    'rand_digit': 0,
    'rand_number': 0.71801,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-18 11:08:05.502689+1000',
    'text_array': [
    '76102fbdc5dd4d149fa1cf376cd5b873',
    '4510010ae1e2453d8a79a18efdfb79e5',
],
    'words': 'jaguar kangaroo',
    'nested': {
    'id': 118,
    'rand_digit': 6,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 7,
},
],
},
    'nested_array': [
    [
    4,
],
],
    'two_words': [
    'wolf',
    'snail',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 3,
    'maybe': 'dolphin',
    'maybe_null': None,
},
},
    {
    'id': 19,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 119,
    'id_str': [
    '09',
],
    'text_data': '102ae0d7fe3146a7bd17c61b00f7e6e8',
    'rand_digit': 0,
    'rand_number': 0.50634,
    'rand_signed_int': 2,
    'rand_datetime': '2000-09-18 06:49:24',
    'text_array': [
    '37b3cf984d7e42d2a94c6a58cf961e68',
    '652f41c81d2c4bc188ef22886bd789ba',
],
    'words': 'goat ape',
    'nested': {
    'id': 119,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 10,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 4,
},
],
},
    'nested_array': [
    [
    0,
],
],
    'two_words': [
    'spider',
    'turtle',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'gorilla',
},
},
    {
    'id': 20,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 120,
    'id_str': [
    '29',
    '08',
    '16',
    '16',
    '15',
],
    'text_data': 'c425946f67c14ba9bf336f090dd89f33',
    'rand_digit': 9,
    'rand_number': 0.7629,
    'rand_signed_int': 2,
    'rand_datetime': '2000-11-16T20:31:38.600748',
    'text_array': [
    '608992040cc342919dcda3952b8c39a7',
    '67c05dff52fa4874b04f2393ee056083',
],
    'words': 'fox ant',
    'nested': {
    'id': 120,
    'rand_digit': 8,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'chicken',
    'mouse',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'bear',
    'maybe_null': 'monkey',
},
},
    {
    'id': 21,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 121,
    'id_str': [
    '10',
    '09',
],
    'text_data': 'fd0687137be341358258e1dbd184e4f7',
    'rand_digit': 9,
    'rand_number': 0.25637,
    'rand_signed_int': -3,
    'rand_datetime': '2000-06-15 05:40:12.943785',
    'text_array': [
    '016cd550178c4b2cb0d0bd2a4cdefe72',
    'fec61c0c7d2347298d4be29ba0325e25',
],
    'words': 'turtle mouse',
    'nested': {
    'id': 121,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -7,
],
    [
    6,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'wolf',
    'rabbit',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'cat',
},
},
    {
    'id': 22,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 122,
    'id_str': [
    '05',
    '03',
    '16',
    '05',
],
    'text_data': 'ebcdf298fc2a4f67b1700304c7c8c64b',
    'rand_digit': 6,
    'rand_number': 0.44943,
    'rand_signed_int': 6,
    'rand_datetime': '2000-08-20 12:42:51-0200',
    'text_array': [
    'f2f25b805c7d435c8bfa870656a0228d',
    '6b5d7b2e375846ab9d19e599ba43c94f',
],
    'words': 'duck horse',
    'nested': {
    'id': 122,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'ladybug',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    6,
],
    [
    7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'hyena',
    'camel',
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
    'mixed_type': 2,
},
},
    {
    'id': 23,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 123,
    'id_str': [
    '01',
    '02',
],
    'text_data': '6c3bf50fc90f4ea89d5e7dfccfc798d8',
    'rand_digit': 0,
    'rand_number': 0.17584,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-30 11:15:10.542546-0300',
    'text_array': [
    'ed295c7621284159af8b6e857c73c61e',
    '3af835ecd33b46559c09df8d9d5b8c4e',
],
    'words': 'dragonfly mouse',
    'nested': {
    'id': 123,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
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
    'word': 'squid',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'elephant',
    'dolphin',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': [
    2,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cow',
    'maybe_null': 'dog',
},
},
    {
    'id': 24,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 124,
    'id_str': [
],
    'text_data': '93fd1cb89dd843959bf108fb3d9d5a1a',
    'rand_digit': 2,
    'rand_number': 0.94942,
    'rand_signed_int': -6,
    'rand_datetime': '2001-01-13 14:26:02-0300',
    'text_array': [
    '41734da53ba34db69ac1c0118cdb9af5',
    '1075ee1e5b7245c6b6386f3418539786',
],
    'words': 'sloth koala',
    'nested': {
    'id': 124,
    'rand_digit': 8,
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
    'nested_empty': [
    'hello',
],
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
    'word': 'camel',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    9,
],
],
    'two_words': [
    'lobster',
    'ape',
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
    'mixed_type': None,
    'maybe_null': 'rhino',
},
},
    {
    'id': 25,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 125,
    'id_str': [
    '24',
],
    'text_data': '090817d53d694f1d9416a67c4b09a4a4',
    'rand_digit': 3,
    'rand_number': 0.89944,
    'rand_signed_int': -9,
    'rand_datetime': '2000-07-01T09:08:04.908250',
    'text_array': [
    '0de1229315b14ec499fc1102c4109637',
    'd1d04ba6f87b472b93b5a358b3c49318',
],
    'words': 'dog rabbit',
    'nested': {
    'id': 125,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'goat',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 5,
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
    'duck',
    'kangaroo',
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
    'mixed_type': 0.47155,
    'maybe_null': 'squid',
},
},
    {
    'id': 26,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 126,
    'id_str': [
    '27',
    '27',
    '08',
    '18',
],
    'text_data': '4f179fa38c374d1889583c92dacc6aac',
    'rand_digit': 9,
    'rand_number': 0.61357,
    'rand_signed_int': -10,
    'rand_datetime': '2000-05-11T06:06:56.446525+11:00',
    'text_array': [
    '62163b27e08f4bc88b3c82c44f343d36',
    '9d11752d8bbf4ac4860b89c6da508117',
],
    'words': 'ant spider',
    'nested': {
    'id': 126,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 5,
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
],
},
    'nested_array': [
    [
],
    [
    4,
],
],
    'two_words': [
    'koala',
    'spider',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'lobster',
    'maybe_null': None,
},
},
    {
    'id': 27,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 127,
    'id_str': [
    '24',
    '27',
    '23',
],
    'text_data': 'bc4bc42d5b9e43c38c878b733e97739f',
    'rand_digit': 8,
    'rand_number': 0.88441,
    'rand_signed_int': 2,
    'rand_datetime': '2000-06-06 09:58:26.732900',
    'text_array': [
    'a0eec2a2aecd4571b62ca9620a86ffff',
    '2de9ab5cb1a247a6b1c97eb49b7ef488',
],
    'words': 'snail monkey',
    'nested': {
    'id': 127,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 8,
},
],
},
    'nested_array': [
    [
    7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bird',
    'octopus',
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
    'mixed_type': 'giraffe',
    'maybe_null': None,
},
},
    {
    'id': 28,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 128,
    'id_str': [
    '09',
    '12',
],
    'text_data': 'bd9385f59bcc44698e848c6f262ad5b9',
    'rand_digit': 9,
    'rand_number': 0.07972,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-15 11:36:41+1100',
    'text_array': [
    'b7fba69f23174be7afd9ff508a81ead3',
    '100f9afd2b76497e89293c100e54d3c7',
],
    'words': 'hyena goat',
    'nested': {
    'id': 128,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -9,
],
],
    'two_words': [
    'dog',
    'cat',
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
    'mixed_type': 0,
},
},
    {
    'id': 29,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 129,
    'id_str': [
    '25',
],
    'text_data': 'b872f9a33a8f4d88a3fc584b93605d5c',
    'rand_digit': 7,
    'rand_number': 0.46332,
    'rand_signed_int': -2,
    'rand_datetime': '2000-05-30 10:59:08.267200+1200',
    'text_array': [
    'a9f05b265a88458d89a128ba6d6a0d07',
    'b8ebf67e183840adaa79c08dc58267f5',
],
    'words': 'wolf kangaroo',
    'nested': {
    'id': 129,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'dog',
    'elephant',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': [
    63,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 30,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 130,
    'id_str': [
    '28',
    '12',
    '29',
    '13',
    '10',
],
    'text_data': '40fa17d5e3074365b4b8c5d6e6b5c962',
    'rand_digit': 1,
    'rand_number': 0.65721,
    'rand_signed_int': 4,
    'rand_datetime': '2000-08-19 19:49:04-0900',
    'text_array': [
    '53ec94eb533a47fb9772b5884287444f',
    '4b4ab84fc4a3450aa4bb3e9b1f8b9ce1',
],
    'words': 'snail lobster',
    'nested': {
    'id': 130,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 1,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    5,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ant',
    'ant',
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
    'mixed_type': 'cow',
    'maybe_null': None,
},
},
    {
    'id': 31,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 131,
    'id_str': [
    '10',
],
    'text_data': '804c017a4765406faca9d96c2f1c5ffd',
    'rand_digit': 3,
    'rand_number': 0.88111,
    'rand_signed_int': -2,
    'rand_datetime': '2000-09-19 23:56',
    'text_array': [
    'fa30fd695cd549b88cd2f02fa359d43f',
    'beda8119d7584d1bb9565baa813c7648',
],
    'words': 'scorpion horse',
    'nested': {
    'id': 131,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'frog',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    1,
],
],
    'two_words': [
    'dolphin',
    'dog',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'butterfly',
    'maybe_null': None,
},
},
    {
    'id': 32,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 132,
    'id_str': [
    '14',
    '22',
    '17',
    '03',
    '13',
],
    'text_data': 'd6a0bc2bd8424a8b81e54a26fb17695f',
    'rand_digit': 1,
    'rand_number': 0.16684,
    'rand_signed_int': -1,
    'rand_datetime': '2000-07-19 00:38',
    'text_array': [
    '9d9ca274e9564fa0b51f60b2af795275',
    'daa33c0b979e4d4694da779282e9842b',
],
    'words': 'ladybug ape',
    'nested': {
    'id': 132,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'duck',
    'koala',
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
    'mixed_type': 0.9522,
    'maybe': 'ape',
    'maybe_null': 'deer',
},
},
    {
    'id': 33,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 133,
    'id_str': [
    '06',
    '20',
    '23',
    '12',
],
    'text_data': '6cc7823e166345d0a1f6039b69a05247',
    'rand_digit': 6,
    'rand_number': 0.38555,
    'rand_signed_int': 1,
    'rand_datetime': '2000-05-28 19:42:39.829435+0800',
    'text_array': [
    '486c9658d6224f278cc5f2415a544515',
    'af4e39b995044810b1fac1bea1cac8ee',
],
    'words': 'shark scorpion',
    'nested': {
    'id': 133,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lion',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'duck',
    'kangaroo',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'horse',
},
},
    {
    'id': 34,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 134,
    'id_str': [
    '13',
    '07',
],
    'text_data': '6fbf58fb4ba24b0ea9a6b873a5b4b956',
    'rand_digit': 6,
    'rand_number': 0.72388,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-14T00:37:03.252488',
    'text_array': [
    '4037d80f18e8475cbd6c83de4e0b8a53',
    '3a10333aff3f4e928ed5afd03edf7061',
],
    'words': 'turtle dolphin',
    'nested': {
    'id': 134,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
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
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'mosquito',
    'grasshopper',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'snail',
    'maybe_null': 'snake',
},
},
    {
    'id': 35,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 135,
    'id_str': [
],
    'text_data': '0557d5d22ed046ed8e440a3434ec2e42',
    'rand_digit': 5,
    'rand_number': 0.23839,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-13 21:14:51+0200',
    'text_array': [
    '1bc39e878a324aaea7e9de1ed043a5b2',
    'd59e3440efe548f9a88dc14f67348e0b',
],
    'words': 'mosquito chicken',
    'nested': {
    'id': 135,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
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
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cow',
    'fox',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': [
    15,
],
    'rand_bool': False,
    'mixed_type': 'lobster',
    'maybe_null': None,
},
},
    {
    'id': 36,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 136,
    'id_str': [
    '21',
    '15',
    '05',
    '10',
],
    'text_data': '985e837961de49d39cf0f2a2f75ec811',
    'rand_digit': 2,
    'rand_number': 0.9697,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-16T21:50:29-0900',
    'text_array': [
    '1e8ab08658a04a1595ae49b78175ef9a',
    'b2c976b508a84c04b9f2e41cc597a656',
],
    'words': 'snail scorpion',
    'nested': {
    'id': 136,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'spider',
    'fox',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'snake',
    'maybe_null': 'ape',
},
},
    {
    'id': 37,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 137,
    'id_str': [
    '08',
],
    'text_data': '25a980d4cce2402eba7b29fec2b1be03',
    'rand_digit': 0,
    'rand_number': 0.068,
    'rand_signed_int': 6,
    'rand_datetime': '2000-03-09 12:57:15',
    'text_array': [
    'a31745a15e394f8caff78c7b1564c175',
    'f24fd830893140a59af63158d2b2c0b3',
],
    'words': 'butterfly whale',
    'nested': {
    'id': 137,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -9,
],
    [
],
],
    'two_words': [
    'rabbit',
    'chicken',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0,
    'maybe': 'crab',
},
},
    {
    'id': 38,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 138,
    'id_str': [
    '30',
],
    'text_data': '96949ca671bb445885836ce176c048bf',
    'rand_digit': 2,
    'rand_number': 0.62268,
    'rand_signed_int': 3,
    'rand_datetime': '2000-01-15 13:02:02',
    'text_array': [
    '58c30878f0614a0881138c6faed26a48',
    'ec95c15d720e4a6d888da58c9932771f',
],
    'words': 'wolf sheep',
    'nested': {
    'id': 138,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'grasshopper',
    'deer',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'mouse',
},
},
    {
    'id': 39,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 139,
    'id_str': [
    '12',
    '19',
    '13',
],
    'text_data': '98fd6e6bc8254b44906d2c1b27e9a07d',
    'rand_digit': 8,
    'rand_number': 0.80235,
    'rand_signed_int': 7,
    'rand_datetime': '2000-12-26 14:28:16.406805-0100',
    'text_array': [
    '5fe2aa5c653b477abae0ede3eb815239',
    'a085ef4514e24ad28e557230ecd8f7d9',
],
    'words': 'dolphin hippo',
    'nested': {
    'id': 139,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'gorilla',
    'spider',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': [
    62,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'ladybug',
},
},
    {
    'id': 40,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 140,
    'id_str': [
    '30',
],
    'text_data': 'eb124e72e2844a1790baabd97c850c12',
    'rand_digit': 6,
    'rand_number': 0.06581,
    'rand_signed_int': 6,
    'rand_datetime': '2000-03-11T15:03:20.328495',
    'text_array': [
    'f102f6572917442caa86ecf2068c2da1',
    'b726ea607f5f44dcb72a7c3373310916',
],
    'words': 'goat rhino',
    'nested': {
    'id': 140,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 3,
},
],
},
    'nested_array': [
    [
    -7,
],
    [
    1,
],
    [
],
    [
    1,
],
],
    'two_words': [
    'cow',
    'ladybug',
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
    'mixed_type': True,
    'maybe': 'bird',
},
},
    {
    'id': 41,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 141,
    'id_str': [
    '20',
    '25',
    '20',
],
    'text_data': 'cf7b406988cc42b9b1bf33a5a930165c',
    'rand_digit': 7,
    'rand_number': 0.81198,
    'rand_signed_int': -6,
    'rand_datetime': '2000-05-28T16:34:28.789830-04:00',
    'text_array': [
    'd1294f341c9e47b69e11ab264a51dd34',
    'e26b00acf1f04c708a2aa6f9d6fabe2d',
],
    'words': 'kangaroo cheetah',
    'nested': {
    'id': 141,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'squid',
    'fish',
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
    'mixed_type': None,
    'maybe': 'turtle',
},
},
    {
    'id': 42,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 142,
    'id_str': [
    '03',
    '28',
    '17',
],
    'text_data': 'a9088e6bbbf2458297319fd37a162af3',
    'rand_digit': 9,
    'rand_number': 0.96839,
    'rand_signed_int': -10,
    'rand_datetime': '2000-03-10T00:13:42',
    'text_array': [
    '381e30269d394f08b2383ad2047ee5b0',
    '24ed1b7c9761487da5389784d41e0355',
],
    'words': 'deer bear',
    'nested': {
    'id': 142,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    9,
],
],
    'two_words': [
    'snail',
    'koala',
],
    'city': {
    'name': 'London',
    'geo': {
    'lat': 51.507351,
    'lon': -0.127758,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'octopus',
    'maybe_null': 'ape',
},
},
    {
    'id': 43,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 143,
    'id_str': [
    '22',
    '29',
    '29',
    '15',
],
    'text_data': '8c0c2f3c1d514a9cb41e74a5b1f33397',
    'rand_digit': 2,
    'rand_number': 0.20899,
    'rand_signed_int': -5,
    'rand_datetime': '2001-01-05 11:14:15.356255-0700',
    'text_array': [
    '2d134bd60e504506a4ed9389030314b0',
    '15ca8c09cd5b45909dba5066d9eab531',
],
    'words': 'snail bee',
    'nested': {
    'id': 143,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'pig',
    'butterfly',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 'lobster',
    'maybe_null': 'fly',
},
},
    {
    'id': 44,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 144,
    'id_str': [
    '13',
    '13',
    '02',
],
    'text_data': '91d93fc1c20948db80d077c2dfd38ed6',
    'rand_digit': 5,
    'rand_number': 0.59018,
    'rand_signed_int': -10,
    'rand_datetime': '2001-01-24 13:24:39+1100',
    'text_array': [
    '3156e7ea4aaa4677825205cddafa1b7f',
    'e422843b4bf24f01b1ea0ec3e0f999a7',
],
    'words': 'lizard rabbit',
    'nested': {
    'id': 144,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 7,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'pig',
    'spider',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'lobster',
    'maybe_null': 'deer',
},
},
    {
    'id': 45,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 145,
    'id_str': [
    '09',
    '30',
],
    'text_data': '31e5467d77c543d9a188206525dbb817',
    'rand_digit': 0,
    'rand_number': 0.44983,
    'rand_signed_int': -7,
    'rand_datetime': '2000-01-06 12:13',
    'text_array': [
    'ce3b5880f30a436b97f924687345c287',
    '52b9f9f388824ca0b02061e924cfa0db',
],
    'words': 'wolf lizard',
    'nested': {
    'id': 145,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    10,
],
],
    'two_words': [
    'bird',
    'crab',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 46,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 146,
    'id_str': [
    '14',
],
    'text_data': '8945a60279cd4cdf8d63cf47b67e6a3a',
    'rand_digit': 4,
    'rand_number': 0.69979,
    'rand_signed_int': 1,
    'rand_datetime': '2000-12-18T02:16:30-0200',
    'text_array': [
    '9cad995a448549b18bccffaa2e961076',
    '2cc765416948479c88c3c34a29f66ca4',
],
    'words': 'panda wolf',
    'nested': {
    'id': 146,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 8,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 3,
},
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cat',
    'scorpion',
],
    'city': {
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'lobster',
    'maybe_null': 'wolf',
},
},
    {
    'id': 47,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 147,
    'id_str': [
    '20',
    '03',
    '02',
],
    'text_data': '9e220640e4d8459d88eb5d201186506f',
    'rand_digit': 4,
    'rand_number': 0.26474,
    'rand_signed_int': -5,
    'rand_datetime': '2001-01-22T22:32:42',
    'text_array': [
    'c5687bdaba1647b1b7d6ea2e027ccbd8',
    '73b59ffbf0944c08b0d36a83f10ed06a',
],
    'words': 'pig gorilla',
    'nested': {
    'id': 147,
    'rand_digit': 2,
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
],
    'word': 'cow',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'zebra',
    'panda',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': [
    21,
],
    'rand_bool': False,
    'mixed_type': 0.00115,
    'maybe': 'spider',
    'maybe_null': 'fish',
},
},
    {
    'id': 48,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 148,
    'id_str': [
    '08',
],
    'text_data': '31cbdb4ec95e4e129586a4f318a201d9',
    'rand_digit': 2,
    'rand_number': 0.31667,
    'rand_signed_int': 2,
    'rand_datetime': '2001-01-26T04:45:11-0700',
    'text_array': [
    'ee8a80d1ae724b068023f7100b967bf6',
    '59645ca0545b4ca58fbc438c5cba330b',
],
    'words': 'jaguar snake',
    'nested': {
    'id': 148,
    'rand_digit': 0,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'chicken',
    'sloth',
],
    'city': {
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': [
    22,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'koala',
    'maybe_null': 'elephant',
},
},
    {
    'id': 49,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 149,
    'id_str': [
    '28',
    '27',
    '28',
    '09',
    '07',
],
    'text_data': '832e3de5adbe4d27a85552ce07e0e139',
    'rand_digit': 3,
    'rand_number': 0.90283,
    'rand_signed_int': 2,
    'rand_datetime': '2000-10-25 05:56',
    'text_array': [
    '618373f11a864383994484a4d45dfbb9',
    '024b0a8ccd394fca97b848babc277739',
],
    'words': 'zebra elephant',
    'nested': {
    'id': 149,
    'rand_digit': 6,
    'array': [
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
],
    'word': 'pig',
    'number': 3,
},
],
},
    'nested_array': [
    [
    9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'spider',
    'dolphin',
],
    'city': {
    'name': 'Moscow',
    'geo': {
    'lat': 55.755826,
    'lon': 37.6173,
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
    'id': 50,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 150,
    'id_str': [
    '24',
    '06',
    '13',
    '21',
    '13',
],
    'text_data': '03074ac5b47d45f4a771e1125160470d',
    'rand_digit': 7,
    'rand_number': 0.01405,
    'rand_signed_int': 5,
    'rand_datetime': '2000-01-04T06:02:37.938806',
    'text_array': [
    '40370c6ae47145a59bcf05853d208cf7',
    '9f18bcafb9b74503a346662bbb96c83d',
],
    'words': 'sloth crab',
    'nested': {
    'id': 150,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fox',
    'ape',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.62302,
},
},
    {
    'id': 51,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 151,
    'id_str': [
    '18',
    '26',
    '23',
    '30',
    '04',
],
    'text_data': '87c421a3ee8449cc876295d52a8fc724',
    'rand_digit': 2,
    'rand_number': 0.46428,
    'rand_signed_int': 10,
    'rand_datetime': '2000-10-30T06:07:56.102543',
    'text_array': [
    '84483dc78fee4e629458b8ec1eb31282',
    'd168a2c8dcf641e49af07836d1243b9d',
],
    'words': 'kangaroo horse',
    'nested': {
    'id': 151,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
    'number': 4,
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
],
    'word': 'duck',
    'number': 5,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,3__',
    'two_words': [
    'cow',
    'leopard',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.54308,
    'maybe_null': None,
},
},
    {
    'id': 52,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 152,
    'id_str': [
    '02',
],
    'text_data': '23719bee952c424c89ec4fceddad7875',
    'rand_digit': 1,
    'rand_number': 0.18156,
    'rand_signed_int': 7,
    'rand_datetime': '2000-05-21T14:16:12+0300',
    'text_array': [
    '934aa323e0d349bf9aad078355f2c37c',
    'ec20a27f2f324485ad5197ac056d4d1d',
],
    'words': 'dolphin butterfly',
    'nested': {
    'id': 152,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bee',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 5,
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
    'nested_array': [
],
    'two_words': [
    'turtle',
    'fly',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'camel',
    'maybe_null': 'elephant',
},
},
    {
    'id': 53,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 153,
    'id_str': [
    '28',
],
    'text_data': '8f0c81122343456e97a305e27f2d31c1',
    'rand_digit': 1,
    'rand_number': 0.087,
    'rand_signed_int': 2,
    'rand_datetime': '2000-05-24 11:31',
    'text_array': [
    'f31bc78df22f44548215061056b0aa02',
    '45cfffed80054c8380b35afa7b72504b',
],
    'words': 'cat duck',
    'nested': {
    'id': 153,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
],
    [
],
],
    'two_words': [
    'lizard',
    'deer',
],
    'city': {
    'name': 'London',
    'geo': {
    'lat': 51.507351,
    'lon': -0.127758,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 54,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 154,
    'id_str': [
    '22',
    '12',
    '07',
    '08',
],
    'text_data': '9ec3070fbb244a2a8d5b82e755ad55b6',
    'rand_digit': 9,
    'rand_number': 0.56537,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-01 23:51:48.945263-1100',
    'text_array': [
    '70097ee253dd4777bd0bef73e9141043',
    '42e03745624d418895559b8aa2eead4c',
],
    'words': 'gorilla crab',
    'nested': {
    'id': 154,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 7,
},
    {
    'nested_empty': None,
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
    'word': 'ladybug',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 4,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -6,
],
],
    'two_words': [
    'bird',
    'kangaroo',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': [
    91,
],
    'rand_bool': True,
    'mixed_type': 'spider',
    'maybe_null': 'fish',
},
},
    {
    'id': 55,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 155,
    'id_str': [
    '14',
    '09',
    '03',
],
    'text_data': '68d43cf7e2674d0cb8c1912d237e84f9',
    'rand_digit': 9,
    'rand_number': 0.84771,
    'rand_signed_int': 2,
    'rand_datetime': '2001-01-08 23:24:25.196060',
    'text_array': [
    'abf4a0bacc4d4958bb8448b31e5796dd',
    'b175472297274262a49d907705103eb1',
],
    'words': 'mouse rhino',
    'nested': {
    'id': 155,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'turtle',
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
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'sloth',
    'grasshopper',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': [
    16,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'ant',
},
},
    {
    'id': 56,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 156,
    'id_str': [
    '21',
],
    'text_data': 'd517b888adf241df9dbb0e1e9e90ccae',
    'rand_digit': 8,
    'rand_number': 0.82271,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-23 07:14:07.153013',
    'text_array': [
    'a6a3a2de771442b6aab429b70f8bcaa3',
    '240e4c834f9940d382c18e858a55a7ca',
],
    'words': 'scorpion deer',
    'nested': {
    'id': 156,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'snail',
    'ladybug',
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
    'maybe_null': None,
},
},
    {
    'id': 57,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 157,
    'id_str': [
    '20',
    '20',
],
    'text_data': 'e4de22908c5c414da87cd0a5e12ecf7d',
    'rand_digit': 1,
    'rand_number': 0.2979,
    'rand_signed_int': -5,
    'rand_datetime': '2000-11-28',
    'text_array': [
    '35febf59e7884b0d8ba990c2148a0ded',
    '3511be02ccc546d4b96bd8a624c2e148',
],
    'words': 'dog cheetah',
    'nested': {
    'id': 157,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'fox',
    'shark',
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
    'mixed_type': 'grasshopper',
    'maybe': 'camel',
},
},
    {
    'id': 58,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 158,
    'id_str': [
    '23',
],
    'text_data': '68fa3af59d8f4f48b89f07f124a37dbb',
    'rand_digit': 4,
    'rand_number': 0.94683,
    'rand_signed_int': 10,
    'rand_datetime': '2000-11-17 00:14:45+0700',
    'text_array': [
    'd1c11b4aee2a4456801c891877211684',
    'd3b718a517eb4580853910fbb5683af5',
],
    'words': 'jaguar elephant',
    'nested': {
    'id': 158,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'shark',
    'koala',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': [
    8,
],
    'rand_bool': False,
    'mixed_type': True,
},
},
    {
    'id': 59,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 159,
    'id_str': [
    '05',
    '13',
],
    'text_data': 'e7c195be8df04463ab6f77c2a624a4e8',
    'rand_digit': 8,
    'rand_number': 0.57275,
    'rand_signed_int': 9,
    'rand_datetime': '2000-04-06T03:46:56.333026',
    'text_array': [
    'e026f67b85fd4bea8a802aafa3cd2f2e',
    '0b175f23b52c4787bb55f27b88149d6f',
],
    'words': 'koala rhino',
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
    'word': 'sheep',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'shark',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -1,
],
    [
    -7,
],
    [
    2,
],
],
    'two_words': [
    'grasshopper',
    'jaguar',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'monkey',
    'maybe_null': None,
},
},
    {
    'id': 60,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 160,
    'id_str': [
    '06',
    '03',
    '19',
    '20',
],
    'text_data': 'b331d72ba33c448eb6e3876a19dc908d',
    'rand_digit': 9,
    'rand_number': 0.64459,
    'rand_signed_int': -10,
    'rand_datetime': '2000-07-27 11:23',
    'text_array': [
    '6343d7688af5426caf9bd02918387a9b',
    '3bc9587c715f4b1fbbc6deade2236edc',
],
    'words': 'fish snake',
    'nested': {
    'id': 160,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'wolf',
    'number': 6,
},
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
    'word': 'zebra',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'squid',
    'deer',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 6,
    'maybe': 'whale',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 61,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 161,
    'id_str': [
    '06',
    '25',
    '21',
    '23',
    '18',
],
    'text_data': '529f9437bd0842768006ff99200eb75e',
    'rand_digit': 2,
    'rand_number': 0.38412,
    'rand_signed_int': 3,
    'rand_datetime': '2000-03-08 15:59:51.541976+0200',
    'text_array': [
    'f3dc7eb077e649598ede01ed8fa6cab4',
    'f016674670af45018404171774710d4d',
],
    'words': 'hyena goat',
    'nested': {
    'id': 161,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'horse',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 9,
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
],
    'two_words': [
    'sloth',
    'chicken',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'horse',
},
},
    {
    'id': 62,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 162,
    'id_str': [
    '07',
    '19',
    '21',
],
    'text_data': '04ce4df918324fd8b2b52aef5841d496',
    'rand_digit': 0,
    'rand_number': 0.39735,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-24T14:34:39.691942',
    'text_array': [
    'f173440e83404cb4baddcf7b507dac86',
    'bd91905f36cf447db1b91ee855eb7967',
],
    'words': 'dolphin mouse',
    'nested': {
    'id': 162,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'koala',
    'cat',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'bee',
},
},
    {
    'id': 63,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 163,
    'id_str': [
    '24',
    '29',
],
    'text_data': '080ef6b71c90499d99fed51308a9d2c1',
    'rand_digit': 1,
    'rand_number': 0.94101,
    'rand_signed_int': 10,
    'rand_datetime': '2000-11-08T16:37:26',
    'text_array': [
    'bfea96d265b1454c9b03fb4319881222',
    'f6beef0d34064b4e85c43990e2c421e7',
],
    'words': 'panda fly',
    'nested': {
    'id': 163,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'mouse',
    'elephant',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    'content-length': '141',
}
        
        # 原始请求内容
        original_content = {
    'target': 10,
    'context': [
    {
    'positive': 11,
    'negative': 19,
},
],
    'limit': 100,
    'offset': 0,
    'with_payload': True,
    'with_vector': False,
    'using': 'sparse-image',
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
    'content-length': '85',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
},
    'sparse_vectors': {
    'sparse-text': {
},
    'sparse-image': {
},
    'sparse-code': {
},
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_sparse_discovery.test_discover')
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
    test = TestSparseDiscoverytestDiscover()
    test.run_tests()
