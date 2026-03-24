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
logger = logging.getLogger('vdb_fuzzer.test.test_sparse_discovery_test_context_many_pairs')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_sparse_discovery.test_context_many_pairs"
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



class TestSparseDiscoverytestContextManyPairs:
    """自动生成的VDB模糊测试类 - test_sparse_discovery.test_context_many_pairs"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_sparse_discovery.test_context_many_pairs"
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
    'content-length': '1998861',
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
],
    'text_data': '567718c329914358a08d0e7023e97480',
    'rand_digit': 0,
    'rand_number': 0.16146,
    'rand_signed_int': -6,
    'rand_datetime': '2000-01-09 10:20:32-0300',
    'text_array': [
    '9bc31f8797844f8ebce4a5f308059719',
    'eac851d5c9ec42cd8f72ef1072bca304',
],
    'words': 'camel ant',
    'nested': {
    'id': 100,
    'rand_digit': 9,
    'array': [
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
],
    'two_words': [
    'kangaroo',
    'panda',
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
    'maybe': 'spider',
    'maybe_null': 'deer',
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
    '30',
],
    'text_data': 'e89032a7bf044e7ab9995863b4c98a08',
    'rand_digit': 7,
    'rand_number': 0.42868,
    'rand_signed_int': 9,
    'rand_datetime': '2000-09-21 00:28:06',
    'text_array': [
    '7237f1b2f9334c40a7f66083bbff047b',
    '7fdb4c51382c46d6ad65bd8476aa67a9',
],
    'words': 'koala mouse',
    'nested': {
    'id': 101,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'gorilla',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'mosquito',
    'snail',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.68901,
    'maybe': 'mouse',
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
    '05',
],
    'text_data': '948862e316a44ccdb3f07593d9b7910c',
    'rand_digit': 9,
    'rand_number': 0.0984,
    'rand_signed_int': -2,
    'rand_datetime': '2000-05-07T03:15:38',
    'text_array': [
    'e1c089dc248f43529c98ec07579364d6',
    '13b9c1f0ecdf4ec0bf5c9342c7234939',
],
    'words': 'crab pig',
    'nested': {
    'id': 102,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cheetah',
    'elephant',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': [
    100,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'hyena',
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
],
    'text_data': '4bc35a73a171468fa85244d4d2edbfd7',
    'rand_digit': 1,
    'rand_number': 0.36056,
    'rand_signed_int': 3,
    'rand_datetime': '2000-09-15 19:45:14',
    'text_array': [
    '856d1729f9394033b485a5aa08eaed7f',
    '173c61a5e7f44fffb4868c3c6802d828',
],
    'words': 'shark zebra',
    'nested': {
    'id': 103,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'shark',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fish',
    'mouse',
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
    'mixed_type': None,
    'maybe_null': 'hyena',
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
],
    'text_data': '644cc2dba1ea4c09ad15af2fb9ae7285',
    'rand_digit': 5,
    'rand_number': 0.01108,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-17T00:52:14-0900',
    'text_array': [
    '60417c4d12cf441dbe02f8bcdc4c5d62',
    '9dc9f59802664e94b906bf4783dbcfe3',
],
    'words': 'elephant panda',
    'nested': {
    'id': 104,
    'rand_digit': 2,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -3,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'scorpion',
    'chicken',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': [
    89,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'goat',
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
],
    'text_data': '2a46ac9298114d10b13a63e177720528',
    'rand_digit': 8,
    'rand_number': 0.10753,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-05 23:14:09-1100',
    'text_array': [
    '743de818f6cc46f385aa09cb1415b568',
    '97fe5fb191cc4a9e8a05e2968b34de79',
],
    'words': 'frog panda',
    'nested': {
    'id': 105,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 6,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'frog',
    'ant',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cat',
    'maybe_null': 'ant',
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
    '23',
    '16',
],
    'text_data': 'e512b0ac39f14e7c830261a85e7611f5',
    'rand_digit': 4,
    'rand_number': 0.21495,
    'rand_signed_int': 2,
    'rand_datetime': '2000-10-20T05:03:28.105450-0800',
    'text_array': [
    '0dbc986b882a492281471192ab0ab023',
    '4311959191804a5c925c7a14a57cd7d8',
],
    'words': 'horse horse',
    'nested': {
    'id': 106,
    'rand_digit': 4,
    'array': [
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
    'word': 'lizard',
    'number': 2,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dog',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'lion',
    'mosquito',
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
    'mixed_type': 0.8685,
    'maybe_null': 'mouse',
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
    '30',
    '18',
],
    'text_data': '6e6f5019cb9946bf8531bde2dd8f9725',
    'rand_digit': 0,
    'rand_number': 0.03084,
    'rand_signed_int': -7,
    'rand_datetime': '2000-09-19 07:30:06+1100',
    'text_array': [
    '8d535c3997644de2a45b188f91f8e34b',
    '095d1dd7b8b14a3f86b761fbfa5138f5',
],
    'words': 'crab giraffe',
    'nested': {
    'id': 107,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'turtle',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'grasshopper',
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
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'dolphin',
    'scorpion',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'ladybug',
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
    '19',
],
    'text_data': 'cc5edd6a0e3141638992aaa19731fd4e',
    'rand_digit': 6,
    'rand_number': 0.15057,
    'rand_signed_int': 5,
    'rand_datetime': '2000-07-24T16:34:34',
    'text_array': [
    'd201067e872d4eefab4ac003a15127f1',
    'bb7494438cc64df79e59c8a89251d9f4',
],
    'words': 'frog snake',
    'nested': {
    'id': 108,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 10,
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
    {
    'nested_empty': None,
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
    'word': 'rabbit',
    'number': 1,
},
],
},
    'nested_array': [
    [
    -1,
],
],
    'two_words': [
    'spider',
    'shark',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'mosquito',
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
    '13',
    '17',
    '02',
    '17',
],
    'text_data': 'e5a8612e5fc64280aae49da9bcad3a2e',
    'rand_digit': 2,
    'rand_number': 0.4896,
    'rand_signed_int': 4,
    'rand_datetime': '2000-11-27 15:59',
    'text_array': [
    'b4a16468a3ee4e13999dda1e180feb24',
    'f3660c502af54570ba5b37730e4b5b9b',
],
    'words': 'cat fish',
    'nested': {
    'id': 109,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'panda',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'cow',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'cheetah',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
    -5,
],
],
    'two_words': [
    'snail',
    'turtle',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '01',
    '19',
    '22',
],
    'text_data': 'e1b0af04d4f643b2adc836ce69f35269',
    'rand_digit': 0,
    'rand_number': 0.38523,
    'rand_signed_int': 0,
    'rand_datetime': '2000-07-29T13:30:52',
    'text_array': [
    'e1fa01bb68b7401c8d5cc7a328c3b383',
    '9906bac6d7f94d9cb294bf6b3d384128',
],
    'words': 'jaguar cow',
    'nested': {
    'id': 110,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'kangaroo',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'lobster',
    'cheetah',
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
    'mixed_type': 0.04329,
    'maybe': 'hippo',
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
    '14',
    '11',
    '13',
    '15',
],
    'text_data': '2afb5dddfbfd4f87abd1e2efcfe665cd',
    'rand_digit': 4,
    'rand_number': 0.96178,
    'rand_signed_int': 6,
    'rand_datetime': '2000-03-15T03:18:04',
    'text_array': [
    '32ad6eb8b949482294fd48c1e0789dc1',
    'f80bff7a5976418f9a4bd08d8e80425d',
],
    'words': 'deer goat',
    'nested': {
    'id': 111,
    'rand_digit': 9,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fly',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    4,
],
],
    'two_words': [
    'sloth',
    'fish',
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
    'mixed_type': 'cheetah',
    'maybe': 'jaguar',
    'maybe_null': None,
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
    '17',
    '04',
    '22',
    '30',
    '14',
],
    'text_data': 'a397e9e4d14c4761bb405b64ddcca20c',
    'rand_digit': 0,
    'rand_number': 0.91062,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-20T15:08:04.047060',
    'text_array': [
    '4b5e65cdfb9a4937af9514b7c04808e9',
    'fe8fcc74de34487b80c5c592c82a4b54',
],
    'words': 'ant rabbit',
    'nested': {
    'id': 112,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 1,
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
    'word': 'whale',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    0,
],
],
    'two_words': [
    'duck',
    'dragonfly',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': None,
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
    '11',
    '02',
    '29',
],
    'text_data': '2fc08b0c014e4006be805a4fa7874054',
    'rand_digit': 1,
    'rand_number': 0.62596,
    'rand_signed_int': 0,
    'rand_datetime': '2000-05-08T21:07:20.187901+0200',
    'text_array': [
    '8c94c08ca0da45838028052a5017687b',
    '69912ac797644ec69c82ec0ed416bf23',
],
    'words': 'leopard bear',
    'nested': {
    'id': 113,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fly',
    'mouse',
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
    'mixed_type': True,
    'maybe_null': None,
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
    '18',
    '23',
    '21',
    '17',
],
    'text_data': 'ae5e52b9525643e0a4a7c8e910ee99eb',
    'rand_digit': 9,
    'rand_number': 0.63621,
    'rand_signed_int': 8,
    'rand_datetime': '2000-03-08 08:18:09',
    'text_array': [
    '8ea83db7db224910a3b44d79b7a4811f',
    '21a517491c8c48728744a28e2dc12c09',
],
    'words': 'ape giraffe',
    'nested': {
    'id': 114,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'leopard',
    'duck',
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
    'mixed_type': None,
    'maybe': 'jaguar',
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
    '23',
    '04',
],
    'text_data': '1b88d4df2431486caa16c435045d5a8e',
    'rand_digit': 7,
    'rand_number': 0.40638,
    'rand_signed_int': -9,
    'rand_datetime': '2000-03-27T16:57:01.126856-04:00',
    'text_array': [
    'f01ae67f17b4481681528ad61976e058',
    'f8d3fdb8683d45b386a1c0de58932293',
],
    'words': 'cheetah fox',
    'nested': {
    'id': 115,
    'rand_digit': 7,
    'array': [
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
    'hello',
],
    'word': 'lobster',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dragonfly',
    'rhino',
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
    'mixed_type': True,
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
    '06',
    '01',
    '22',
],
    'text_data': '031a0186443246668d1d281c5ac3e445',
    'rand_digit': 3,
    'rand_number': 0.57017,
    'rand_signed_int': 10,
    'rand_datetime': '2000-02-21T19:31:24.517301',
    'text_array': [
    'c20b9bcf78964e179c7e30804eeb8000',
    '8345f3e0c11941be852b98e3ec253b53',
],
    'words': 'lizard hyena',
    'nested': {
    'id': 116,
    'rand_digit': 6,
    'array': [
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
    'word': 'deer',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dolphin',
    'squid',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.43171,
    'maybe': 'spider',
    'maybe_null': None,
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
    '13',
    '05',
    '07',
    '10',
    '28',
],
    'text_data': '3cce4acce9b24ef38c498800d6d479ee',
    'rand_digit': 3,
    'rand_number': 0.19007,
    'rand_signed_int': 2,
    'rand_datetime': '2000-03-08 17:00:28.469325',
    'text_array': [
    'e23c9cf2d91845c58dfdcb6ad1d13e7d',
    '532d7fdc413e4135b988faa337da21ae',
],
    'words': 'koala mouse',
    'nested': {
    'id': 117,
    'rand_digit': 1,
    'array': [
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
    'hello',
],
    'word': 'gorilla',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 5,
},
],
},
    'nested_array': [
    [
    -4,
],
],
    'two_words': [
    'deer',
    'monkey',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': [
    6,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
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
    '16',
],
    'text_data': '53d885fe0929444ba40ed087ada580dc',
    'rand_digit': 2,
    'rand_number': 0.0851,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-27 21:42:14+0900',
    'text_array': [
    'c87759d58c1e4b1eafd62a9dcb105acf',
    '3c638cf3b8a2422192072354753eac0a',
],
    'words': 'dolphin rabbit',
    'nested': {
    'id': 118,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    9,
],
],
    'two_words': [
    'cheetah',
    'butterfly',
],
    'city': {
    'name': 'Moscow',
    'geo': {
    'lat': 55.755826,
    'lon': 37.6173,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '01',
    '09',
    '22',
],
    'text_data': 'c8ae19dfebef4fb9a7431f2f9d26b69a',
    'rand_digit': 0,
    'rand_number': 0.15857,
    'rand_signed_int': 3,
    'rand_datetime': '2000-04-18 04:52:46-1200',
    'text_array': [
    '570827bacf964b36b7af0d4548aa9dcd',
    '9e7524a92b9140c99c6840ca01079ee6',
],
    'words': 'tiger zebra',
    'nested': {
    'id': 119,
    'rand_digit': 3,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ape',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'wolf',
    'cow',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fox',
    'maybe_null': None,
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
    '25',
    '12',
],
    'text_data': 'a5f2b80ddcad48278556ac593f80281b',
    'rand_digit': 2,
    'rand_number': 0.59605,
    'rand_signed_int': -2,
    'rand_datetime': '2000-03-31 01:12:01',
    'text_array': [
    'bfe2ee8707c2453da580fc2d61f4f285',
    '4f22005f3e2e4827bb945e862efe3adc',
],
    'words': 'dragonfly zebra',
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
    'word': 'butterfly',
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
    'number': 4,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dog',
    'squid',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 'ladybug',
    'maybe': 'camel',
    'maybe_null': 'bee',
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
    '04',
    '05',
    '04',
    '28',
    '09',
],
    'text_data': '86745935dcfd4d0fbb6e5b86cc287d5e',
    'rand_digit': 2,
    'rand_number': 0.65582,
    'rand_signed_int': -10,
    'rand_datetime': '2001-01-13',
    'text_array': [
    'a02069b283eb492ebecf7fe188b5cf2b',
    '71e770a01b5347bc978094c7eecad47a',
],
    'words': 'rabbit rhino',
    'nested': {
    'id': 121,
    'rand_digit': 2,
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
    'word': 'bird',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'duck',
    'fox',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'lizard',
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
    '06',
    '15',
    '20',
    '05',
    '08',
],
    'text_data': 'cde940bb2c7a4fedaa50fb1bfbf14e37',
    'rand_digit': 9,
    'rand_number': 0.74107,
    'rand_signed_int': 1,
    'rand_datetime': '2000-02-15 19:03:13',
    'text_array': [
    '026deb46403947b8bb2c8c372bde2d22',
    'b88c41e4419e463b89f3d5a15d206ea8',
],
    'words': 'dragonfly camel',
    'nested': {
    'id': 122,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'crab',
    'tiger',
],
    'city': {
    'name': 'Rome',
    'geo': {
    'lat': 41.902782,
    'lon': 12.496366,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'frog',
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
    '22',
    '22',
    '07',
    '13',
],
    'text_data': 'c45c5b1a9e8e461c81d86e9e2b498b2b',
    'rand_digit': 2,
    'rand_number': 0.59604,
    'rand_signed_int': 8,
    'rand_datetime': '2000-01-25T18:12:33-0300',
    'text_array': [
    '58ebaa315cd44152a4e1d7dbaff97b06',
    'bb8b0075257c4551a3808a3067549d99',
],
    'words': 'rhino butterfly',
    'nested': {
    'id': 123,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    [
    -4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'octopus',
    'deer',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': [
    22,
],
    'rand_bool': True,
    'mixed_type': 'panda',
    'maybe': 'fly',
    'maybe_null': 'jaguar',
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
    '05',
    '30',
    '26',
],
    'text_data': '62c632ef8f1d42d98a6097934b940e20',
    'rand_digit': 5,
    'rand_number': 0.03631,
    'rand_signed_int': -9,
    'rand_datetime': '2000-12-09T02:51:17.405635+0900',
    'text_array': [
    '1c3f50d9bd3e41779edcba5c2db34b9a',
    'a15a132fa7ba411a94df31bf264d83c8',
],
    'words': 'ladybug dolphin',
    'nested': {
    'id': 124,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    5,
],
],
    'two_words': [
    'lizard',
    'hyena',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': [
    7,
],
    'rand_bool': False,
    'mixed_type': 'squid',
    'maybe_null': 'koala',
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
    '28',
    '14',
],
    'text_data': '47a10c8906264c878c5a834c1580845e',
    'rand_digit': 1,
    'rand_number': 0.96756,
    'rand_signed_int': -8,
    'rand_datetime': '2000-01-29T21:59:47.323751',
    'text_array': [
    '9f7d7ae476304c2b8938f80cfd2e3e1b',
    '30a3128b97e84e36b7dc44b401d1e08a',
],
    'words': 'jaguar fish',
    'nested': {
    'id': 125,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 1,
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
],
    'two_words': [
    'cow',
    'fly',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': [
    40,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'turtle',
    'maybe_null': 'crab',
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
],
    'text_data': '873f816a81f5402694ba9e5418d5b4ba',
    'rand_digit': 3,
    'rand_number': 0.62574,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-28 00:01:48+0700',
    'text_array': [
    '36a37d2b7d1d4580ba34e90f9ba1e9f3',
    'd7336856c2c9440687af7e8c223393bc',
],
    'words': 'monkey jaguar',
    'nested': {
    'id': 126,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 7,
},
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
    'word': 'mosquito',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'mosquito',
    'lobster',
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
    'mixed_type': 7,
    'maybe': 'fox',
    'maybe_null': 'chicken',
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
    'text_data': '5f570160c8fc497380381dda2bbf207d',
    'rand_digit': 6,
    'rand_number': 0.2273,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-02T05:45:48',
    'text_array': [
    '043a1aec68c1456fa47d002a95e5fabc',
    'ce4c3c577141449581f843a99d1bdbd5',
],
    'words': 'dolphin turtle',
    'nested': {
    'id': 127,
    'rand_digit': 0,
    'array': [
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
    'word': 'rhino',
    'number': 3,
},
],
},
    'nested_array': [
    [
    -2,
],
    [
],
    [
],
    [
    -1,
],
],
    'two_words': [
    'cow',
    'jaguar',
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
    'mixed_type': 0.83274,
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
    '20',
    '19',
    '19',
    '09',
    '04',
],
    'text_data': '214b547baaec400893a71ec78b961994',
    'rand_digit': 8,
    'rand_number': 0.21946,
    'rand_signed_int': -7,
    'rand_datetime': '2000-09-14T17:43:08.473283',
    'text_array': [
    '0c62e8810d50475a92f06621f53dd08c',
    '0a6e6c447bf04055995d8e49f958e59b',
],
    'words': 'duck sheep',
    'nested': {
    'id': 128,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 3,
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
    'word': 'chicken',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dragonfly',
    'bee',
],
    'city': {
    'name': 'London',
    'geo': {
    'lat': 51.507351,
    'lon': -0.127758,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 6,
    'maybe_null': 'wolf',
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
    '14',
    '19',
],
    'text_data': '4aee3f1814894ee3971e6c54973f6ea2',
    'rand_digit': 1,
    'rand_number': 0.9176,
    'rand_signed_int': 8,
    'rand_datetime': '2000-08-13T16:54:59.760043',
    'text_array': [
    'f081617701664c2da4653dd1e300f264',
    '30bc7a81b7dc44dfacb86e102b1b3667',
],
    'words': 'shark panda',
    'nested': {
    'id': 129,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'bird',
    'tiger',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': [
    58,
],
    'rand_bool': True,
    'mixed_type': 0.24108,
    'maybe': 'wolf',
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
    '04',
],
    'text_data': '4c83d0838c824e078d9bd4673decc3f4',
    'rand_digit': 8,
    'rand_number': 0.53722,
    'rand_signed_int': 7,
    'rand_datetime': '2000-02-16',
    'text_array': [
    'a0040230b5fc4e7dbdf1906efd104b41',
    'db07352bb75042309751c211fe602c89',
],
    'words': 'chicken bee',
    'nested': {
    'id': 130,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'grasshopper',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'bear',
    'shark',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
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
    '07',
    '25',
    '03',
    '12',
    '28',
],
    'text_data': '5814830deb0440a580d96838ea833293',
    'rand_digit': 1,
    'rand_number': 0.59072,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-18T08:31:22+0400',
    'text_array': [
    '14090de00d9e4c3faa066463f1da182a',
    'e21d3cdc9f664515a5de0874dc8f54fc',
],
    'words': 'tiger sheep',
    'nested': {
    'id': 131,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'mouse',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 4,
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
    'nested_array': [
    [
    -10,
],
],
    'two_words': [
    'snake',
    'elephant',
],
    'city': {
    'name': 'Riga',
    'geo': {
    'lat': 56.949649,
    'lon': 24.105186,
},
},
    'rand_tuple': [
    76,
],
    'rand_bool': False,
    'mixed_type': 'dolphin',
    'maybe': 'cheetah',
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
    '24',
],
    'text_data': 'dc41cb7cf6984e348bcdec8e73f73358',
    'rand_digit': 9,
    'rand_number': 0.89406,
    'rand_signed_int': -7,
    'rand_datetime': '2001-01-02 16:05:33',
    'text_array': [
    '30022f00b5d5477a9079b434a599888d',
    'a0f604a202ca4a8780494530554e76fa',
],
    'words': 'lobster fly',
    'nested': {
    'id': 132,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'wolf',
    'squid',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': [
    12,
],
    'rand_bool': False,
    'mixed_type': 1,
    'maybe': 'shark',
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
    '26',
],
    'text_data': '528538105d5e436c8367d7dc7d3a4521',
    'rand_digit': 4,
    'rand_number': 0.69426,
    'rand_signed_int': -9,
    'rand_datetime': '2000-12-25 10:45:17.364902',
    'text_array': [
    'a619e1c53c654cf8b1c1284dcfa5fbd0',
    '3ed250d5120742438a880b50456b9fcf',
],
    'words': 'snake bee',
    'nested': {
    'id': 133,
    'rand_digit': 5,
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
    'word': 'mosquito',
    'number': 1,
},
],
},
    'nested_array': [
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
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 'cow',
    'maybe': 'chicken',
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
    '28',
    '12',
    '27',
    '06',
],
    'text_data': 'a5d01f95f6e740f0804a5ad023b6e15e',
    'rand_digit': 5,
    'rand_number': 0.37021,
    'rand_signed_int': 10,
    'rand_datetime': '2001-01-19T21:26:55.938746+1000',
    'text_array': [
    '1880c7acc01847699acd538974c78e81',
    '88a4d3df0297428a93cd226d9e62ca49',
],
    'words': 'lion fish',
    'nested': {
    'id': 134,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    0,
],
    [
    0,
],
],
    'two_words': [
    'pig',
    'elephant',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'ant',
    'maybe_null': None,
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
    '29',
    '16',
    '08',
],
    'text_data': 'c51ca82f41c24287b665e866dc49d6f4',
    'rand_digit': 7,
    'rand_number': 0.71749,
    'rand_signed_int': -8,
    'rand_datetime': '2000-08-24T04:41:34.860623-08:00',
    'text_array': [
    '75a2901060d346ae8d3a6c9e2c72c411',
    '587ffcf6629243f38f2293fe86c73841',
],
    'words': 'leopard rhino',
    'nested': {
    'id': 135,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 9,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
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
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'squid',
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
    25,
],
    'rand_bool': False,
    'mixed_type': 0.27706,
    'maybe': 'cat',
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
],
    'text_data': '61ae82ca96cf479691da72ecda2f9266',
    'rand_digit': 1,
    'rand_number': 0.07216,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-28T10:52:53.840069',
    'text_array': [
    '9d5d263b36774f2e9110df99bdcb3786',
    '1ee838373c5e4dc6b708fe92062a6107',
],
    'words': 'bird elephant',
    'nested': {
    'id': 136,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    10,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fish',
    'kangaroo',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
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
    '17',
],
    'text_data': 'a80e48ca949543d099084b5f3fe28239',
    'rand_digit': 5,
    'rand_number': 0.36146,
    'rand_signed_int': -5,
    'rand_datetime': '2000-02-27T14:42:43.232553+1200',
    'text_array': [
    '8785f4c8abdf45be87f87fdb51effb25',
    'b393fecdb1a34fcaaee8480427ab796e',
],
    'words': 'rabbit zebra',
    'nested': {
    'id': 137,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'giraffe',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'grasshopper',
    'elephant',
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
    'mixed_type': 0.08861,
    'maybe': 'frog',
    'maybe_null': 'hyena',
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
    '06',
],
    'text_data': 'ca8a67ecd7dd432a9b28038b3a239ef0',
    'rand_digit': 1,
    'rand_number': 0.06613,
    'rand_signed_int': 4,
    'rand_datetime': '2000-02-13 00:03:56-0500',
    'text_array': [
    'edfaf37d1bef45daa02b337f64ff6256',
    '3c3cc343c2984679834c8d61c575fb1c',
],
    'words': 'shark dragonfly',
    'nested': {
    'id': 138,
    'rand_digit': 4,
    'array': [
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 10,
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
    'crab',
    'whale',
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
    'mixed_type': 0.23012,
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
    '03',
],
    'text_data': 'd961408e04e84066a65987fab0964b4b',
    'rand_digit': 6,
    'rand_number': 0.14826,
    'rand_signed_int': 3,
    'rand_datetime': '2000-01-16 18:59:55.171599+0800',
    'text_array': [
    '0b317c7ac83c4e159160ea571833078c',
    '25b68bdad7da4fc8b7326e190decc022',
],
    'words': 'deer ape',
    'nested': {
    'id': 139,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 3,
},
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
    'nested_array': [
],
    'two_words': [
    'butterfly',
    'pig',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'spider',
    'maybe_null': 'pig',
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
    '14',
    '27',
    '07',
    '13',
],
    'text_data': 'c48bc26ffa6343d7a653ce0054d395ac',
    'rand_digit': 6,
    'rand_number': 0.75456,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-21T03:22:27.897352',
    'text_array': [
    '23cfbf1fb38f454c8b2606d7949d6f3c',
    '522493f389fd430bb128ca0f976ba170',
],
    'words': 'elephant lizard',
    'nested': {
    'id': 140,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'butterfly',
    'dolphin',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': [
    70,
],
    'rand_bool': False,
    'mixed_type': 0.84085,
    'maybe': 'gorilla',
    'maybe_null': 'fox',
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
    '23',
    '30',
],
    'text_data': 'a532160962264a5fb79e60bea780f249',
    'rand_digit': 5,
    'rand_number': 0.35989,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-28T07:13:46.616972',
    'text_array': [
    'aa28d35086d44cb3bb079e3448e282bd',
    'c8614cfa6f994c8a9d606ffd0670b381',
],
    'words': 'rabbit rabbit',
    'nested': {
    'id': 141,
    'rand_digit': 6,
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
],
},
    'nested_array': [
],
    'two_words': [
    'spider',
    'koala',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.87044,
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
    '21',
    '25',
],
    'text_data': '1fcc57b34a6c495cb79d2efae0bccd61',
    'rand_digit': 3,
    'rand_number': 0.62522,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-01 06:16:32.176061',
    'text_array': [
    '579b89ff1bb2413dad54da6732f93436',
    '5dbf61e55f9340a29f15092c66d93ff9',
],
    'words': 'pig rabbit',
    'nested': {
    'id': 142,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'pig',
    'bird',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': [
    8,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
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
    '09',
    '29',
    '29',
    '02',
    '08',
],
    'text_data': '0490589a45cf4ee9b34717466925e645',
    'rand_digit': 4,
    'rand_number': 0.85288,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-14 01:21:45.698021',
    'text_array': [
    'f330d4ba224a4c8b81644989f1410e00',
    'dc1e631559414e899867b7ab0c3cb4a1',
],
    'words': 'scorpion snail',
    'nested': {
    'id': 143,
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
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'whale',
    'cow',
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
    'maybe_null': None,
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
    '22',
    '01',
    '22',
],
    'text_data': '7534d2a6f0384d18b88af691190b1a98',
    'rand_digit': 6,
    'rand_number': 0.29345,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-11 09:19:42+0000',
    'text_array': [
    '48a64c1163aa4587a259760cb9dd9026',
    '2ac6eddd9cb64e8ca3621af275f6573f',
],
    'words': 'mosquito lobster',
    'nested': {
    'id': 144,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    8,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ladybug',
    'frog',
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
    'mixed_type': 0.24557,
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
],
    'text_data': '825b8c360dbe458293856dd055182779',
    'rand_digit': 2,
    'rand_number': 0.13034,
    'rand_signed_int': -6,
    'rand_datetime': '2000-09-25T10:49:25',
    'text_array': [
    'd12daf10aef2439d92cc6f2db423f1ec',
    '0b34ed35dfd2416a867d0e040d1f9efb',
],
    'words': 'rabbit spider',
    'nested': {
    'id': 145,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'wolf',
    'cheetah',
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
    'maybe': 'ape',
    'maybe_null': 'giraffe',
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
    '18',
    '04',
    '27',
    '02',
    '09',
],
    'text_data': 'addccda27b644623b6942ae1fd59de7c',
    'rand_digit': 0,
    'rand_number': 0.2136,
    'rand_signed_int': 4,
    'rand_datetime': '2000-12-02T18:03:05',
    'text_array': [
    'c0fe5905bf1240498e566f50d3ada0f9',
    '44f2ca9e09a34d51bbc3725ccd5cf52f',
],
    'words': 'tiger spider',
    'nested': {
    'id': 146,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'monkey',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    [
    2,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'gorilla',
    'lizard',
],
    'city': {
    'name': 'Rome',
    'geo': {
    'lat': 41.902782,
    'lon': 12.496366,
},
},
    'rand_tuple': [
    24,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'snail',
    'maybe_null': 'snake',
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
    '28',
    '06',
],
    'text_data': '0cff7ee6fd8b4ba5aaada622c5924042',
    'rand_digit': 7,
    'rand_number': 0.84228,
    'rand_signed_int': -4,
    'rand_datetime': '2000-02-02 19:14:14',
    'text_array': [
    '30fbee75c24840a3902923476fdecf4f',
    '6bcd20793a054013a34852f0132439da',
],
    'words': 'grasshopper ape',
    'nested': {
    'id': 147,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ape',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'cheetah',
    'jaguar',
],
    'city': {
    'name': 'Cardiff',
    'geo': {
    'lat': 51.481581,
    'lon': -3.17909,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.04112,
    'maybe': 'sloth',
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
    'text_data': '9f84d2f3e5184544a84aa315f384b4f4',
    'rand_digit': 0,
    'rand_number': 0.19549,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-25T21:50:21.331182',
    'text_array': [
    '65210865aab04f3ebdd7c4294c5b4415',
    'f0851573f9df44b2bf9828dc35bc8f0a',
],
    'words': 'spider crab',
    'nested': {
    'id': 148,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 5,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'sheep',
    'ape',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
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
],
    'text_data': '3939b60a3ecc499f812f20efb7a207d0',
    'rand_digit': 3,
    'rand_number': 0.64385,
    'rand_signed_int': -2,
    'rand_datetime': '2000-03-30T22:51:50-0500',
    'text_array': [
    'c9a6e2787ae64e3b851e90027fc60a59',
    'db64173055834eaeb20036ed92028923',
],
    'words': 'hyena bear',
    'nested': {
    'id': 149,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 7,
},
],
},
    'nested_array': [
    [
    -8,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'mouse',
    'lobster',
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
    'mixed_type': 0.12018,
    'maybe': 'panda',
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
    '03',
    '01',
    '28',
    '17',
    '04',
],
    'text_data': 'f44beb1a2cdb4c56ada73f1bbd48d311',
    'rand_digit': 6,
    'rand_number': 0.05888,
    'rand_signed_int': -4,
    'rand_datetime': '2000-07-30 08:45:58',
    'text_array': [
    '60c3ee8b96114d9193268aefb50de12c',
    '96da3dd0e9934b49bd0b1f7e476b1f4c',
],
    'words': 'snail koala',
    'nested': {
    'id': 150,
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
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'octopus',
    'octopus',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'bird',
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
    '29',
    '26',
    '11',
],
    'text_data': 'd9a337d241ae49949a55c1784ff5929d',
    'rand_digit': 9,
    'rand_number': 0.87072,
    'rand_signed_int': 5,
    'rand_datetime': '2000-06-02 04:50:38+0000',
    'text_array': [
    '4ae445c0e11548c991e006031776ca4d',
    'ac81380b434a4d13beca5e88652d8349',
],
    'words': 'tiger gorilla',
    'nested': {
    'id': 151,
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
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'crab',
    'tiger',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'rhino',
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
    '12',
],
    'text_data': '81eae638607b461db1af7ec6adbdffb9',
    'rand_digit': 4,
    'rand_number': 0.12341,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-25T13:12:30+0100',
    'text_array': [
    'ac2dcae45d93459b88e475aacb431c9e',
    'c6175cca30ec42b6b1d8b3f5c03699b6',
],
    'words': 'ant monkey',
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
    'word': 'butterfly',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'wolf',
    'bee',
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
    '03',
    '28',
],
    'text_data': '1d8180cf3059443abf4ae822b719869b',
    'rand_digit': 6,
    'rand_number': 0.80495,
    'rand_signed_int': -4,
    'rand_datetime': '2000-06-23',
    'text_array': [
    '61fd4e98b9f04b019eda049fa7ac7569',
    'cacfe8c624ae40dfaa3a21dae2be5798',
],
    'words': 'hyena turtle',
    'nested': {
    'id': 153,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'squid',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bee',
    'koala',
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
    'mixed_type': True,
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
    '25',
    '30',
    '13',
    '05',
    '10',
],
    'text_data': '35bce501b4944ad0a182ebc2347d9365',
    'rand_digit': 2,
    'rand_number': 0.83909,
    'rand_signed_int': 8,
    'rand_datetime': '2000-11-06 10:35:26.363613-0300',
    'text_array': [
    '62e15ab3f29149b995b90e33d27831b1',
    '98f75a8f93ab4f26a2772a0c91c13b7f',
],
    'words': 'hyena hippo',
    'nested': {
    'id': 154,
    'rand_digit': 3,
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
    'hello',
],
    'word': 'grasshopper',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    10,
],
    [
],
],
    'two_words': [
    'elephant',
    'panda',
],
    'city': {
    'name': 'Kharkiv',
    'geo': {
    'lat': 49.980812,
    'lon': 36.25272,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '11',
    '01',
    '29',
],
    'text_data': '2add07b2aabe40af8007b27d9cfabd3e',
    'rand_digit': 5,
    'rand_number': 0.61277,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-23T05:51:52.054078',
    'text_array': [
    '5e46177c5a884e7fa053e163de8cf03e',
    '42a2c1dd83f246999cfa2295fee1d4d0',
],
    'words': 'ladybug bee',
    'nested': {
    'id': 155,
    'rand_digit': 3,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
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
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'whale',
    'lion',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'bee',
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
    '05',
    '02',
],
    'text_data': 'e0f390f1ad2644b2b7d7196a65ce300f',
    'rand_digit': 9,
    'rand_number': 0.6789,
    'rand_signed_int': -3,
    'rand_datetime': '2001-01-23T20:59:10-1100',
    'text_array': [
    'ad3cb5466bee4cc8b4b2e6f9262898ef',
    'b2977e1925d94135adbd600822d56496',
],
    'words': 'shark bird',
    'nested': {
    'id': 156,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'kangaroo',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    9,
],
],
    'two_words': [
    'zebra',
    'rhino',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': [
    89,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'hyena',
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
    '01',
    '08',
    '07',
],
    'text_data': '5221408dc76447a08f66b2a3aa43e77c',
    'rand_digit': 3,
    'rand_number': 0.40394,
    'rand_signed_int': -5,
    'rand_datetime': '2000-10-30 19:24:44',
    'text_array': [
    '617fa0a8c4274702b8bc1c8a99c68c12',
    'c27a0c92da9d4771abfae37e00e22ccf',
],
    'words': 'grasshopper frog',
    'nested': {
    'id': 157,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'shark',
    'bee',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 9,
    'maybe': 'grasshopper',
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
],
    'text_data': 'ee6e643d2aff4a0685981a3293ba44df',
    'rand_digit': 2,
    'rand_number': 0.67414,
    'rand_signed_int': 5,
    'rand_datetime': '2000-05-21 17:34:08',
    'text_array': [
    '4c862ec2f3114f398b4edf90fb09e3e0',
    'eef888057a2d4e62b5772e3c70f760a4',
],
    'words': 'dog hippo',
    'nested': {
    'id': 158,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fly',
    'monkey',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': [
    45,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'hippo',
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
    '28',
    '18',
],
    'text_data': '0d193bbcc0dc41599686d2d94c4d0a03',
    'rand_digit': 5,
    'rand_number': 0.6994,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-12T01:00:03.229948-09:00',
    'text_array': [
    '72049c857a4643759e975ffb8f4b0491',
    '6f5b10dd72df4dc1a400b767ac95f91f',
],
    'words': 'squid koala',
    'nested': {
    'id': 159,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'kangaroo',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lion',
    'lizard',
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
    '07',
    '12',
    '30',
    '13',
    '06',
],
    'text_data': 'e090f746635540b5a7eda892a54326d8',
    'rand_digit': 9,
    'rand_number': 0.17088,
    'rand_signed_int': 8,
    'rand_datetime': '2000-05-26T13:19:28.483192Z',
    'text_array': [
    'c1b5fa4194df428dada8682a1c7bfe84',
    '46540ce18f0d4bf9bf2cded7d3b8ac85',
],
    'words': 'grasshopper camel',
    'nested': {
    'id': 160,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 1,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 3,
},
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
],
    'word': 'turtle',
    'number': 2,
},
],
},
    'nested_array': [
    [
    -1,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'bear',
    'spider',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 'cow',
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
],
    'text_data': '8f5f7b9de7fa485d807015fca4de3103',
    'rand_digit': 1,
    'rand_number': 0.03627,
    'rand_signed_int': 10,
    'rand_datetime': '2000-11-25T05:04:57',
    'text_array': [
    '3d075aae1f7f4c9cbcc5d04fd194d7db',
    '4196f4cd04c742b9b02d5c30797b5276',
],
    'words': 'bee turtle',
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
    'word': 'shark',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dolphin',
    'deer',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': [
    100,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'deer',
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
    '25',
],
    'text_data': '456ba19d1da24154b6d8bc28cf3bf97d',
    'rand_digit': 9,
    'rand_number': 0.42474,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-03T23:26:08.060861',
    'text_array': [
    '84e91ebea7f943df9d6a31386dfa9d3b',
    '38459b08eead4ad0bfa84c46159f6f63',
],
    'words': 'turtle ladybug',
    'nested': {
    'id': 162,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 10,
},
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'dragonfly',
    'snail',
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
    'maybe_null': 'cow',
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
    '25',
    '08',
],
    'text_data': 'dd9beda9baa24010b28147767a763fc4',
    'rand_digit': 0,
    'rand_number': 0.90105,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-27 16:58',
    'text_array': [
    'aa7bf5394332458da0728d16703b2ce3',
    'cd240942934043738887e6a8b9d379f7',
],
    'words': 'turtle kangaroo',
    'nested': {
    'id': 163,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 6,
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
    'word': 'elephant',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 1,
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
    'leopard',
    'tiger',
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
    'mixed_type': 8,
    'maybe_null': 'dog',
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
    'content-length': '1999218',
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
    '08',
    '15',
    '21',
    '02',
],
    'text_data': 'be423be50072410f80de636349054d6d',
    'rand_digit': 2,
    'rand_number': 0.08944,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-08 05:16:55.620017',
    'text_array': [
    '3587261acd0c4e25a60da32af9ff8e40',
    '5f3f3f10cc01441c916e33a5ec5a08b6',
],
    'words': 'elephant mouse',
    'nested': {
    'id': 100,
    'rand_digit': 7,
    'array': [
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
    'nested_empty': [
    'hello',
],
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
    'word': 'rabbit',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 8,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_3,2__',
    'two_words': [
    'fish',
    'pig',
],
    'city': {
    'name': 'Barcelona',
    'geo': {
    'lat': 41.385064,
    'lon': 2.173403,
},
},
    'rand_tuple': [
    62,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'whale',
    'maybe_null': 'camel',
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
],
    'text_data': '766beda7bddb4dca9c198e9c500536af',
    'rand_digit': 9,
    'rand_number': 0.63967,
    'rand_signed_int': -9,
    'rand_datetime': '2000-08-15 15:11:56',
    'text_array': [
    'd8420b7d96ac44e7a0144447e1deb15f',
    '5610820d09574cb493f84a7cb299c96d',
],
    'words': 'giraffe horse',
    'nested': {
    'id': 101,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 2,
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
    'hello',
],
    'word': 'camel',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'cheetah',
    'frog',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 0,
    'maybe_null': 'bee',
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
    '30',
    '10',
],
    'text_data': 'aab20b1225f94391bee9ae33b339c635',
    'rand_digit': 4,
    'rand_number': 0.87633,
    'rand_signed_int': 5,
    'rand_datetime': '2000-07-29T23:34:11.681858+07:00',
    'text_array': [
    'd3ddff1b908647119e513e7bc9a8fd32',
    '53f04564c2ea4a33a220f02afe0a1627',
],
    'words': 'duck octopus',
    'nested': {
    'id': 102,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'butterfly',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'squid',
    'pig',
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
    'mixed_type': 8,
    'maybe_null': None,
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
    '24',
],
    'text_data': '86db54d1ac82449a98056a0602e5703f',
    'rand_digit': 7,
    'rand_number': 0.07741,
    'rand_signed_int': -2,
    'rand_datetime': '2000-01-09T03:59:02.414590',
    'text_array': [
    'f293bfb0046d40b0962bfd0a1ee25b78',
    '399b101175af4c48a82eb532f93f7579',
],
    'words': 'elephant ladybug',
    'nested': {
    'id': 103,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 2,
},
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
    'hello',
],
    'word': 'whale',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'elephant',
    'turtle',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': [
    35,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'kangaroo',
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
    '09',
    '27',
],
    'text_data': '2b4ef70ea59843e5abba9f08ddd9848b',
    'rand_digit': 0,
    'rand_number': 0.47499,
    'rand_signed_int': 7,
    'rand_datetime': '2000-04-24 07:46:04.485929-0800',
    'text_array': [
    '6ab17e99951c42188a05dc0237915de1',
    '7bd96507503343aebf22b583f83721d9',
],
    'words': 'duck dog',
    'nested': {
    'id': 104,
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
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mosquito',
    'panda',
],
    'city': {
    'name': 'Athens',
    'geo': {
    'lat': 37.98381,
    'lon': 23.727539,
},
},
    'rand_tuple': [
    66,
],
    'rand_bool': False,
    'mixed_type': 1,
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
    '20',
    '03',
],
    'text_data': 'a5772455c061440ebddba1189f431ea0',
    'rand_digit': 7,
    'rand_number': 0.89117,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-27',
    'text_array': [
    '509be312a6fd417ea8e2e5e2346960c9',
    '0cbc1887707d42f185c72f6336a7b26a',
],
    'words': 'fox kangaroo',
    'nested': {
    'id': 105,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 8,
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
    {
    'nested_empty': None,
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
    'word': 'tiger',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'panda',
    'squid',
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
    'maybe': 'dolphin',
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
    '30',
],
    'text_data': '6cb605c451334b43a44d75891f70510f',
    'rand_digit': 9,
    'rand_number': 0.19751,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-22T06:42:53',
    'text_array': [
    '65212765edb649d2a4f3f3a8a77ab178',
    'dd230300e2334ad9945fc0ddfdc54ecd',
],
    'words': 'whale hyena',
    'nested': {
    'id': 106,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 7,
},
],
},
    'nested_array': [
    [
    -1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dolphin',
    'sloth',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'tiger',
    'maybe_null': 'tiger',
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
    '25',
],
    'text_data': 'd7e4fe89807940599b3c8e4b8b4363f0',
    'rand_digit': 7,
    'rand_number': 0.68519,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-13T04:39:58-1200',
    'text_array': [
    '4387e7013f7c410ba18a84c4905db6d8',
    'fdac1953b2f0401b849af8313aab82f0',
],
    'words': 'spider camel',
    'nested': {
    'id': 107,
    'rand_digit': 1,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ape',
    'number': 3,
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
],
},
    'nested_array': [
],
    'two_words': [
    'mouse',
    'mouse',
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
    'mixed_type': None,
    'maybe': 'fly',
    'maybe_null': 'cheetah',
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
    '12',
    '25',
    '12',
    '04',
],
    'text_data': 'c164d0288a86447690f3538df3b4ed0b',
    'rand_digit': 2,
    'rand_number': 0.593,
    'rand_signed_int': 9,
    'rand_datetime': '2000-06-23 12:57:52.399175-0400',
    'text_array': [
    'ca7dc3b85d61408482919d012b7a26aa',
    '132ec45706834dcc91705c1a3e5edb7f',
],
    'words': 'bear chicken',
    'nested': {
    'id': 108,
    'rand_digit': 5,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    4,
],
],
    'two_words': [
    'lion',
    'pig',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'horse',
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
    '23',
    '09',
],
    'text_data': '6e1ae3931e564e8d9e8f39644c08f498',
    'rand_digit': 4,
    'rand_number': 0.22449,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-18T06:03:32.927682+1100',
    'text_array': [
    'fcd8a8f0b67c43e4b9b02e8e9c45c320',
    'fbb7caa95bc843bdbbf65bbe63322166',
],
    'words': 'dolphin cow',
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
    'word': 'snail',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ape',
    'koala',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.87334,
    'maybe': 'koala',
    'maybe_null': 'elephant',
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
    '18',
    '25',
],
    'text_data': 'ea1e8f6bf6354a8da18f24949de0bb77',
    'rand_digit': 9,
    'rand_number': 0.46342,
    'rand_signed_int': 0,
    'rand_datetime': '2000-12-02T01:30:40',
    'text_array': [
    'ae5f275062344e5a9d2a5ca11047c6d2',
    '04ee425b7bda470788a44bc5b4765a7b',
],
    'words': 'elephant goat',
    'nested': {
    'id': 110,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 3,
},
],
},
    'nested_array': [
    [
    -5,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'giraffe',
    'panda',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': [
    74,
],
    'rand_bool': False,
    'mixed_type': None,
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
    '23',
    '22',
    '08',
    '16',
],
    'text_data': '9245eb39099b427392414a7de474b432',
    'rand_digit': 6,
    'rand_number': 0.9558,
    'rand_signed_int': 7,
    'rand_datetime': '2000-01-27T03:04:51.932806-08:00',
    'text_array': [
    'fcf5eaef596c49629e474a8d50ddc778',
    'cd62731ebb284825a5f9e98fb3205cdc',
],
    'words': 'bird horse',
    'nested': {
    'id': 111,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 6,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 1,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    0,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'rabbit',
    'wolf',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'cheetah',
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
    '12',
    '23',
    '25',
    '29',
],
    'text_data': '94ee86758edf49b49ecab7560e04be50',
    'rand_digit': 7,
    'rand_number': 0.00679,
    'rand_signed_int': 1,
    'rand_datetime': '2000-07-25 18:10:22.766213',
    'text_array': [
    'ad0c58cb5ed9485b98a7e0468d6f400c',
    'bdb5acbf3c734cbd9eb399741c9c01e0',
],
    'words': 'duck elephant',
    'nested': {
    'id': 112,
    'rand_digit': 0,
    'array': [
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
    'word': 'mouse',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bear',
    'cow',
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
    'mixed_type': 0.62878,
    'maybe_null': 'sheep',
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
    '17',
],
    'text_data': '4cecf0174c9b4fb9ba4e060bc6453a2e',
    'rand_digit': 4,
    'rand_number': 0.80115,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-31',
    'text_array': [
    'f4dbe58dc955448b8caa068c4762d40c',
    '4aa3824ace184e8292651d027f377146',
],
    'words': 'deer chicken',
    'nested': {
    'id': 113,
    'rand_digit': 5,
    'array': [
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
],
    'word': 'ladybug',
    'number': 4,
},
],
},
    'nested_array': [
    [
    2,
],
],
    'two_words': [
    'whale',
    'ladybug',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bee',
    'maybe_null': 'bee',
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
    '09',
    '14',
],
    'text_data': 'a0e1378009a34fa3813ed3494351d09a',
    'rand_digit': 0,
    'rand_number': 0.97297,
    'rand_signed_int': -4,
    'rand_datetime': '2000-02-10 16:21:28-0700',
    'text_array': [
    '517ee88a55fc450181a3dd29e527fca5',
    'c2fe882e3d40408681d9181e53d2ddad',
],
    'words': 'dog bird',
    'nested': {
    'id': 114,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mosquito',
    'ant',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
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
    '21',
],
    'text_data': '3ab2c77b4f5648c39499499c35f57d52',
    'rand_digit': 5,
    'rand_number': 0.27698,
    'rand_signed_int': 0,
    'rand_datetime': '2000-01-31T16:54:07.887905+09:00',
    'text_array': [
    '993866127dd84d2cbe266107f833c880',
    '1cbe9a8a3bb94f3f864b174c50198d98',
],
    'words': 'monkey dolphin',
    'nested': {
    'id': 115,
    'rand_digit': 1,
    'array': [
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
],
    'word': 'shark',
    'number': 3,
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
    'word': 'ant',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -1,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ant',
    'deer',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': [
    74,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '23',
],
    'text_data': '44dab9bc66f846e78eb330dfe3557ec7',
    'rand_digit': 0,
    'rand_number': 0.6751,
    'rand_signed_int': -3,
    'rand_datetime': '2000-09-12 05:33:47-1000',
    'text_array': [
    'fdc870f3c9a940afaed322c667065363',
    '45491aa3a8cb42b996b76050c2af338e',
],
    'words': 'leopard turtle',
    'nested': {
    'id': 116,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 1,
},
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
    'word': 'whale',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 6,
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
    'pig',
    'ladybug',
],
    'city': {
    'name': 'London',
    'geo': {
    'lat': 51.507351,
    'lon': -0.127758,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 9,
    'maybe_null': 'gorilla',
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
    '19',
],
    'text_data': '516b3d8927694205b031d75b7a06de76',
    'rand_digit': 5,
    'rand_number': 0.4095,
    'rand_signed_int': -7,
    'rand_datetime': '2000-01-28T09:10:47.018183',
    'text_array': [
    '06ec7254b5e14221b6aba3de45194355',
    '0af6f0bef73f45ad8fa946e2da3412f9',
],
    'words': 'crab wolf',
    'nested': {
    'id': 117,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'squid',
    'ape',
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
    'mixed_type': True,
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
    '26',
    '01',
],
    'text_data': '7b0df8e2ba224f4482e13580ac2b5d09',
    'rand_digit': 2,
    'rand_number': 0.04022,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-14T11:51:40-0400',
    'text_array': [
    'b0c632b94b58499badcb4a23bc7666a5',
    '419911681c994f1bb2ac4fde5279b10b',
],
    'words': 'lobster fox',
    'nested': {
    'id': 118,
    'rand_digit': 6,
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
    'word': 'giraffe',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'hyena',
    'fly',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': [
    35,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bird',
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
    '12',
    '16',
    '21',
    '02',
    '09',
],
    'text_data': '5af415cad30c4ca2843d5e4599c5ad5d',
    'rand_digit': 4,
    'rand_number': 0.31637,
    'rand_signed_int': -7,
    'rand_datetime': '2000-07-24 18:56:25+1000',
    'text_array': [
    'd1b826e11216417194f6a808c81c1d8e',
    '77fec9ec34a54e07b49bec87b2424c0a',
],
    'words': 'ape fish',
    'nested': {
    'id': 119,
    'rand_digit': 7,
    'array': [
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'giraffe',
    'deer',
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
    'maybe_null': 'cheetah',
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
    '19',
    '20',
    '11',
    '01',
],
    'text_data': 'c7de0ab28bce499f8a3936cd4f618a31',
    'rand_digit': 9,
    'rand_number': 0.2354,
    'rand_signed_int': 9,
    'rand_datetime': '2000-01-29 14:52:41-0100',
    'text_array': [
    'ee06f678c16b4bfab209ea8d3823e121',
    '8e5db9292cb5480ca38cccda9e8494bf',
],
    'words': 'sheep grasshopper',
    'nested': {
    'id': 120,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 5,
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
    'grasshopper',
    'fly',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'deer',
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
    '15',
],
    'text_data': 'b4a10a11571842e5a5ed2a0d4fa2dce9',
    'rand_digit': 7,
    'rand_number': 0.10698,
    'rand_signed_int': 2,
    'rand_datetime': '2000-02-16T13:23:08.666407+0400',
    'text_array': [
    '02f5ebca72774603ad900ad7531550cf',
    '9519efa2d2f14c0c8aaff0b350c071ff',
],
    'words': 'sloth hyena',
    'nested': {
    'id': 121,
    'rand_digit': 5,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'goat',
    'number': 4,
},
],
},
    'nested_array': [
    [
    -10,
],
    [
    -1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ant',
    'rhino',
],
    'city': {
    'name': 'Dubai',
    'geo': {
    'lat': 25.204849,
    'lon': 55.270783,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.8707,
    'maybe': 'bear',
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
    '06',
],
    'text_data': 'a6d19b2498464df0a11f6e1fd47755ed',
    'rand_digit': 4,
    'rand_number': 0.46075,
    'rand_signed_int': 0,
    'rand_datetime': '2001-01-09 20:44',
    'text_array': [
    'bb7794e26d2f4acebdd2274ad6cd85f9',
    'e61372ab522249d88a960c6aca82e4c8',
],
    'words': 'pig lion',
    'nested': {
    'id': 122,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 4,
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
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'dog',
    'goat',
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
    'mixed_type': 0,
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
    '11',
    '12',
],
    'text_data': 'fd5ee394d61b4c459df1b4fcb507bb80',
    'rand_digit': 7,
    'rand_number': 0.67438,
    'rand_signed_int': -7,
    'rand_datetime': '2000-09-03 15:10:17.977991',
    'text_array': [
    '040a86dfbaff4ab4ad3e1beaf71d54fb',
    '2eb0b83123094d8f8db7d1dc5b90809e',
],
    'words': 'fly dragonfly',
    'nested': {
    'id': 123,
    'rand_digit': 6,
    'array': [
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
],
    'word': 'camel',
    'number': 2,
},
],
},
    'nested_array': [
    [
    -5,
],
],
    'two_words': [
    'crab',
    'hyena',
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
    'mixed_type': 0.87103,
    'maybe': 'bird',
    'maybe_null': 'hyena',
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
    '08',
    '12',
    '01',
    '10',
],
    'text_data': '3a77318a8af04dea9487c7e961ecc75a',
    'rand_digit': 0,
    'rand_number': 0.35954,
    'rand_signed_int': -2,
    'rand_datetime': '2000-11-24 17:05:23.397261',
    'text_array': [
    '2d96b27107744029a465768f0253791d',
    'd4fa9259da8341418bf8ecf155a6e1c3',
],
    'words': 'fox panda',
    'nested': {
    'id': 124,
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
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -8,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'hippo',
    'panda',
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
    'mixed_type': False,
    'maybe_null': 'cat',
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
    '30',
    '13',
],
    'text_data': '8db7f31bd3d4478ab4eb7da7342efa8d',
    'rand_digit': 1,
    'rand_number': 0.80244,
    'rand_signed_int': 3,
    'rand_datetime': '2000-01-21T00:38:23.382089+0600',
    'text_array': [
    '2437c64f61974f8793ecb66dc8dac233',
    '13f5f011498349da8378804956a9c130',
],
    'words': 'mouse butterfly',
    'nested': {
    'id': 125,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -8,
],
],
    'two_words': [
    'frog',
    'leopard',
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
    'mixed_type': 0.02865,
    'maybe_null': 'rabbit',
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
    '28',
    '29',
    '10',
    '19',
],
    'text_data': '217192c17e124bc583b7f5fdc438818f',
    'rand_digit': 3,
    'rand_number': 0.33446,
    'rand_signed_int': -6,
    'rand_datetime': '2000-04-28T08:23:39.647649',
    'text_array': [
    'dce2a6b7ec6d45878f7d3d12dcbd4806',
    'fc333ae70b5b4135bc0dd9485194a55f',
],
    'words': 'scorpion deer',
    'nested': {
    'id': 126,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bird',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'hippo',
    'duck',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': [
    98,
],
    'rand_bool': False,
    'mixed_type': None,
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
    '17',
],
    'text_data': '8eff4b35b5844f05afd2e94a2d091b5c',
    'rand_digit': 2,
    'rand_number': 0.14529,
    'rand_signed_int': -3,
    'rand_datetime': '2000-06-09 10:57:26.072743',
    'text_array': [
    'e5a9a8cc3276420fbadd53a70ccb2698',
    'ff123ada06cf44d5ae19f726da250a55',
],
    'words': 'ant butterfly',
    'nested': {
    'id': 127,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 7,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,2__',
    'two_words': [
    'shark',
    'goat',
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
    'mixed_type': False,
    'maybe': 'sheep',
    'maybe_null': 'fly',
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
    '14',
    '26',
    '28',
],
    'text_data': '52b495382761425bb7a5f3855ec70b69',
    'rand_digit': 9,
    'rand_number': 0.9357,
    'rand_signed_int': 0,
    'rand_datetime': '2000-08-20T18:54:10.533041',
    'text_array': [
    '7996d00f9fa541e0b04c4a1c1dfbad52',
    '1d5c002a2f404027849f029d460ad3b0',
],
    'words': 'koala rhino',
    'nested': {
    'id': 128,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 3,
},
],
},
    'nested_array': [
    [
    1,
],
    [
    4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    0,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'kangaroo',
    'ladybug',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'bird',
    'maybe_null': 'shark',
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
    '05',
    '21',
    '30',
],
    'text_data': '139c8cbbe4844cba9f16458977842b9c',
    'rand_digit': 2,
    'rand_number': 0.19939,
    'rand_signed_int': -10,
    'rand_datetime': '2000-03-31T11:02:00.263858Z',
    'text_array': [
    'a8adf276b367432d83d781b8e64f562f',
    'b096e63367714c6e8156af7ebeb6b708',
],
    'words': 'spider goat',
    'nested': {
    'id': 129,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'frog',
    'pig',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bee',
    'maybe_null': 'mosquito',
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
    '03',
    '13',
],
    'text_data': '534588aa59c24f7bb6b08b42427ed95c',
    'rand_digit': 9,
    'rand_number': 0.93667,
    'rand_signed_int': -7,
    'rand_datetime': '2000-06-30T22:24:18+0900',
    'text_array': [
    '05c46a64773646898ae26acf7b2069be',
    '91cb853b306f40ebafb59178f3a05ca2',
],
    'words': 'whale mosquito',
    'nested': {
    'id': 130,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 3,
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
],
},
    'nested_array': [
    [
    5,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'dragonfly',
    'koala',
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
    'mixed_type': 'chicken',
    'maybe': 'grasshopper',
    'maybe_null': 'koala',
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
    '24',
    '08',
],
    'text_data': 'c7b2ff34738f4bd894c8c0511bff72c6',
    'rand_digit': 0,
    'rand_number': 0.37,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-15 04:00',
    'text_array': [
    '603cf31a3ade4790804c2fc50330a164',
    'a5ca2ff3b07a40d4ada06db90d67b71a',
],
    'words': 'jaguar octopus',
    'nested': {
    'id': 131,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snail',
    'camel',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': [
    76,
],
    'rand_bool': False,
    'mixed_type': 6,
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
    '03',
],
    'text_data': '102c6a92bc024659b8bf9495a9a7d941',
    'rand_digit': 2,
    'rand_number': 0.27035,
    'rand_signed_int': -5,
    'rand_datetime': '2000-10-13T00:05:50.208293+0700',
    'text_array': [
    'ba15f67eb00d4ab88ce6c30c4c517dad',
    '6146cf3621124eec902b728a5ba64bcf',
],
    'words': 'sheep bear',
    'nested': {
    'id': 132,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'deer',
    'bee',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.423,
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
    '05',
    '18',
    '27',
    '05',
    '09',
],
    'text_data': 'd94a5470a3164d26bd71e98587d959b3',
    'rand_digit': 2,
    'rand_number': 0.34421,
    'rand_signed_int': -9,
    'rand_datetime': '2000-11-02 20:04',
    'text_array': [
    '57be3c7be8494860a42710250b014b7f',
    '56ef7841ef364fffa88a2f5eb65a56f9',
],
    'words': 'sheep hippo',
    'nested': {
    'id': 133,
    'rand_digit': 2,
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
    'word': 'kangaroo',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
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
    'fly',
    'snake',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
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
    '06',
],
    'text_data': '786d4e087452463c9341ec765e7fe505',
    'rand_digit': 6,
    'rand_number': 0.26381,
    'rand_signed_int': -8,
    'rand_datetime': '2000-09-16 22:40',
    'text_array': [
    '1be6e7a09ad04f19b5c1f2e88a190704',
    'ed4cf12feb1a412b912f9aa08e143c6f',
],
    'words': 'bear pig',
    'nested': {
    'id': 134,
    'rand_digit': 5,
    'array': [
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
    'word': 'elephant',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'horse',
    'fly',
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
    'mixed_type': 'ladybug',
    'maybe': 'lizard',
    'maybe_null': 'grasshopper',
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
    '14',
    '17',
],
    'text_data': '1b525672f7c043f983c3d06c48d4a01c',
    'rand_digit': 9,
    'rand_number': 0.87304,
    'rand_signed_int': 5,
    'rand_datetime': '2001-01-28T00:56:42.228973',
    'text_array': [
    'd5760bdac173411fa4be4d1b044c5d5d',
    '8572361921814bada6beb0d7c7ea299c',
],
    'words': 'camel zebra',
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
    'word': 'bear',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    0,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'grasshopper',
    'fly',
],
    'city': {
    'name': 'Dubai',
    'geo': {
    'lat': 25.204849,
    'lon': 55.270783,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 3,
    'maybe': 'chicken',
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
    '06',
    '21',
    '04',
    '13',
],
    'text_data': '3769b9cf4a944694ba3f3c96b0e4dfc3',
    'rand_digit': 2,
    'rand_number': 0.32713,
    'rand_signed_int': 0,
    'rand_datetime': '2001-01-30T07:40:57.805041',
    'text_array': [
    'd08d7843c63b467b94e31fa0dd5932c6',
    'ec84c4f45dad4cdd9b0fd57899e45c0a',
],
    'words': 'spider spider',
    'nested': {
    'id': 136,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'pig',
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
    'horse',
    'goat',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': [
    27,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'squid',
    'maybe_null': None,
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
],
    'text_data': '875c128e9f5b4781b92daeaf59b934f8',
    'rand_digit': 3,
    'rand_number': 0.17126,
    'rand_signed_int': 2,
    'rand_datetime': '2000-08-19T06:58:01-0200',
    'text_array': [
    'cc042aa06c2341a2b733e765906ff94b',
    'bdbdc8ef197b4f5bb604ff0db08a5e2e',
],
    'words': 'pig frog',
    'nested': {
    'id': 137,
    'rand_digit': 9,
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
    'word': 'ant',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'chicken',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'camel',
    'cheetah',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'deer',
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
    'text_data': '85ed908ee95344ae95f74ca34a679866',
    'rand_digit': 2,
    'rand_number': 0.62321,
    'rand_signed_int': -6,
    'rand_datetime': '2000-12-30T23:30:54-1100',
    'text_array': [
    '397310ecb3454de8b7227c99bb185ac7',
    '4d0ffed4dd8742dc974968ee164c0df6',
],
    'words': 'goat lizard',
    'nested': {
    'id': 138,
    'rand_digit': 5,
    'array': [
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
],
    'word': 'snake',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'ape',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lizard',
    'bear',
],
    'city': {
    'name': 'Johannesburg',
    'geo': {
    'lat': -26.204103,
    'lon': 28.047305,
},
},
    'rand_tuple': [
    38,
],
    'rand_bool': False,
    'mixed_type': 7,
    'maybe': 'crab',
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
    '04',
    '08',
    '01',
    '21',
    '29',
],
    'text_data': '8f76d8011e6f465382234068e8353de3',
    'rand_digit': 0,
    'rand_number': 0.22767,
    'rand_signed_int': -4,
    'rand_datetime': '2000-02-14T06:21:48',
    'text_array': [
    '41a2869970324716b12ccf4dadcffaf2',
    'e8914a9709274ced93e4d8a637cd7f76',
],
    'words': 'scorpion bird',
    'nested': {
    'id': 139,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'wolf',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '23',
    '05',
    '11',
    '18',
],
    'text_data': 'e28bdc3d18cf4e5faa64ee0f7ac6ab17',
    'rand_digit': 5,
    'rand_number': 0.70106,
    'rand_signed_int': 6,
    'rand_datetime': '2000-11-19T04:42:53.311616',
    'text_array': [
    'c4e978dcd844452389504f0fc40edbe2',
    '658ff9c3811b4fe59ffefc91622f1b82',
],
    'words': 'whale tiger',
    'nested': {
    'id': 140,
    'rand_digit': 3,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 7,
},
],
},
    'nested_array': [
    [
    -2,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'goat',
    'mosquito',
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
    'mixed_type': 0.82061,
    'maybe': 'jaguar',
    'maybe_null': 'whale',
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
    '06',
    '11',
    '27',
],
    'text_data': 'fb1457ab75dd4224911aba2f5ea3c306',
    'rand_digit': 8,
    'rand_number': 0.08784,
    'rand_signed_int': -10,
    'rand_datetime': '2000-02-15T09:40:34-0700',
    'text_array': [
    '1e9049395b704bccba63638c9d200243',
    'c6bfa362b30f4460b5743b23d7cc26f9',
],
    'words': 'panda ant',
    'nested': {
    'id': 141,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 1,
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
    'snake',
    'dog',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
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
],
    'text_data': '38757d51be7b46d68d6c43687391b2f3',
    'rand_digit': 1,
    'rand_number': 0.68302,
    'rand_signed_int': -5,
    'rand_datetime': '2000-07-06T00:58:32.914366-1200',
    'text_array': [
    '4fecf0a801d24056b76a2312a757edd9',
    '1c9a8c5b4d7841d48fc44c016411537d',
],
    'words': 'camel cow',
    'nested': {
    'id': 142,
    'rand_digit': 0,
    'array': [
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
    'word': 'cat',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'fox',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'monkey',
    'gorilla',
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
    'mixed_type': False,
    'maybe_null': 'ant',
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
    '30',
    '15',
    '16',
    '08',
],
    'text_data': '1cfdc357d7274c24a14ecffa6b68af83',
    'rand_digit': 8,
    'rand_number': 0.55986,
    'rand_signed_int': 9,
    'rand_datetime': '2000-02-22 18:41:54',
    'text_array': [
    'a0da1a788aa44867bd965fea60b2b79a',
    '1c237757c5064f2d87c6afaa2bd4dbac',
],
    'words': 'scorpion tiger',
    'nested': {
    'id': 143,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    2,
],
    [
    -8,
],
],
    'two_words': [
    'koala',
    'cheetah',
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
    'mixed_type': 'camel',
    'maybe_null': None,
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
    '26',
    '27',
    '12',
],
    'text_data': '5c06645c501e4062990b37e6bda04f0c',
    'rand_digit': 5,
    'rand_number': 0.72008,
    'rand_signed_int': -3,
    'rand_datetime': '2000-01-27 06:20:25.017178',
    'text_array': [
    '076201bd2f434c1fa0e21ec48f527063',
    '8e5334079e1b4d0f9368a586bb84f862',
],
    'words': 'dolphin fox',
    'nested': {
    'id': 144,
    'rand_digit': 9,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 4,
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
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'horse',
    'whale',
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
    'mixed_type': False,
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
    '16',
],
    'text_data': 'b510168eb0fd4003b4258f8bc187aa17',
    'rand_digit': 4,
    'rand_number': 0.69371,
    'rand_signed_int': 9,
    'rand_datetime': '2000-02-01T08:24:10.076887',
    'text_array': [
    '3d48ead099814d9c826c773a08ed27f8',
    'cb18ace705144a228b74b5b06382505e',
],
    'words': 'monkey horse',
    'nested': {
    'id': 145,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snake',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snail',
    'monkey',
],
    'city': {
    'name': 'Riga',
    'geo': {
    'lat': 56.949649,
    'lon': 24.105186,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'elephant',
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
    '15',
    '04',
    '20',
    '19',
],
    'text_data': '5cb68703ba0648f8825599a763aaf3f3',
    'rand_digit': 4,
    'rand_number': 0.28836,
    'rand_signed_int': -6,
    'rand_datetime': '2000-02-12',
    'text_array': [
    '603c44f65b6c489a984a07ee8447b517',
    '982209823ae04036b69b10b82cafd33a',
],
    'words': 'shark sheep',
    'nested': {
    'id': 146,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 7,
},
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
],
    'word': 'pig',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
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
    'horse',
    'cat',
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
    'mixed_type': None,
    'maybe': 'octopus',
    'maybe_null': 'jaguar',
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
    '14',
    '13',
],
    'text_data': '5e7e4b49d34242a1add24e9a85feec18',
    'rand_digit': 5,
    'rand_number': 0.26092,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-09 17:14:50.707784+1200',
    'text_array': [
    '551591ef27c54d08ad122ff119ee037e',
    '0fb5e7df491a46bea7d95e7cf3983e8d',
],
    'words': 'cheetah lion',
    'nested': {
    'id': 147,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
    -8,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    8,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'sloth',
    'deer',
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
    'mixed_type': 'sloth',
    'maybe_null': 'lobster',
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
    '27',
    '23',
    '27',
    '02',
    '12',
],
    'text_data': 'd1f56a0c1d49461fb1c2e70a2ba82c7f',
    'rand_digit': 4,
    'rand_number': 0.08004,
    'rand_signed_int': 10,
    'rand_datetime': '2000-02-23T13:36:26.655902+12:00',
    'text_array': [
    '009ed5248af744db9d31107b885c2e39',
    'cd9e5d4bd3bb4246b2da96606bc4b57d',
],
    'words': 'hippo lobster',
    'nested': {
    'id': 148,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
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
    'hello',
],
    'word': 'rhino',
    'number': 4,
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
    'word': 'bear',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'sheep',
    'grasshopper',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': [
    5,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'dragonfly',
    'maybe_null': None,
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
    '26',
    '19',
    '05',
],
    'text_data': '6543ee63d4e049b39bccfa730873c231',
    'rand_digit': 3,
    'rand_number': 0.29899,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-09T20:12:15.323940',
    'text_array': [
    '812e35d9f9294cf7a021d7800c5590f2',
    '1638f8d464e1406f84a6f9e3bd7487dc',
],
    'words': 'crab ladybug',
    'nested': {
    'id': 149,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snake',
    'number': 6,
},
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
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
    'number': 7,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    4,
],
],
    'two_words': [
    'octopus',
    'cheetah',
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
    'maybe_null': 'chicken',
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
],
    'text_data': 'd77bb11c6d73469da13b487b08323afb',
    'rand_digit': 3,
    'rand_number': 0.38906,
    'rand_signed_int': 4,
    'rand_datetime': '2000-08-10',
    'text_array': [
    'd9e5cd0404df435798b79603691f00bb',
    'c1bdf40f68634e3a9e889ff44cb02b90',
],
    'words': 'wolf gorilla',
    'nested': {
    'id': 150,
    'rand_digit': 4,
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
    'word': 'panda',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'butterfly',
    'bird',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
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
    '15',
    '02',
    '22',
    '26',
    '28',
],
    'text_data': '42cfb513cb2441409b8b24ec6fd34a23',
    'rand_digit': 7,
    'rand_number': 0.60613,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-16 23:51',
    'text_array': [
    'f0968874155840c5b8d21f696cb4a909',
    'a447d0296e764a0e85c63da2870e5bc1',
],
    'words': 'squid fly',
    'nested': {
    'id': 151,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'hyena',
    'bee',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': [
    100,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '03',
],
    'text_data': 'a2c36a9e2f8c48aaae67298a57dedbc5',
    'rand_digit': 4,
    'rand_number': 0.29564,
    'rand_signed_int': -7,
    'rand_datetime': '2000-02-20',
    'text_array': [
    '11467afaa4384c53986ab826c1f9293f',
    'ad4dcbcc7543418589bfcaf8ee127016',
],
    'words': 'cow rabbit',
    'nested': {
    'id': 152,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
    3,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'turtle',
    'lizard',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'dog',
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
    '24',
    '14',
    '22',
],
    'text_data': 'b517e724ec694c9ab8175b0880adbbe2',
    'rand_digit': 7,
    'rand_number': 0.53639,
    'rand_signed_int': -2,
    'rand_datetime': '2000-11-29 21:53:04.528514+0400',
    'text_array': [
    '0aeb6d8b26134efb8f315f059b424a5f',
    'f2b70a8a45d34a76a302d6428e7324d3',
],
    'words': 'snake lion',
    'nested': {
    'id': 153,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'duck',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'dolphin',
    'mosquito',
],
    'city': {
    'name': 'Seoul',
    'geo': {
    'lat': 37.566535,
    'lon': 126.977969,
},
},
    'rand_tuple': [
    69,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
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
    '15',
    '07',
    '15',
],
    'text_data': 'b28c365b5901485e813f7d439258f7b8',
    'rand_digit': 7,
    'rand_number': 0.56319,
    'rand_signed_int': -4,
    'rand_datetime': '2000-06-19T01:05:27.050245',
    'text_array': [
    '7e479dd4034f40d0ba09c4ce90ac17ad',
    '3c16fe3b51e3475092ad5e0a27dc55f8',
],
    'words': 'ant butterfly',
    'nested': {
    'id': 154,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'zebra',
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
    'mixed_type': 'cow',
    'maybe': 'mosquito',
    'maybe_null': 'leopard',
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
    'text_data': '0fd428d040d84241bc1598eded739288',
    'rand_digit': 7,
    'rand_number': 0.4774,
    'rand_signed_int': -9,
    'rand_datetime': '2000-02-29',
    'text_array': [
    '774e4a2d1aa6405f9899f76a352b9773',
    '0b7335ea0d134936bef4035dc78e2779',
],
    'words': 'scorpion kangaroo',
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
    'word': 'goat',
    'number': 1,
},
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'scorpion',
    'tiger',
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
    'mixed_type': 6,
    'maybe': 'snail',
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
    'text_data': 'f92017df0628413b9b4d59557c04f51a',
    'rand_digit': 2,
    'rand_number': 0.16646,
    'rand_signed_int': -9,
    'rand_datetime': '2000-09-13T21:03:00.868081+0400',
    'text_array': [
    '1596e159339c484c80330f901d6fe733',
    'ceeadb8963f646c3b099d324ea8bf12b',
],
    'words': 'dolphin jaguar',
    'nested': {
    'id': 156,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 2,
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
],
    'word': 'ape',
    'number': 8,
},
],
},
    'nested_array': [
    [
    -2,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ape',
    'bear',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'cow',
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
],
    'text_data': '9bfaa20a96604bebbd8e1f542054deb8',
    'rand_digit': 9,
    'rand_number': 0.72573,
    'rand_signed_int': 3,
    'rand_datetime': '2000-05-13 12:09:13.168048-1000',
    'text_array': [
    '3049403e0f934381b139a832ad7b2f9a',
    '6bde13a4802f4ce58c63be6346769202',
],
    'words': 'ant elephant',
    'nested': {
    'id': 157,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 6,
},
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
],
    'word': 'bird',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'jaguar',
    'mouse',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 'hippo',
    'maybe': 'fish',
    'maybe_null': 'sheep',
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
    '24',
],
    'text_data': '7dd6fa73578f4ce8842604239acc5c9d',
    'rand_digit': 8,
    'rand_number': 0.58425,
    'rand_signed_int': 3,
    'rand_datetime': '2001-01-15 10:00:59.249729',
    'text_array': [
    '8a1bb7b9d4304716b36b7bb71056b88f',
    '5fcb9dc9fd7c4a4b80fdab66998a1ec6',
],
    'words': 'bird cheetah',
    'nested': {
    'id': 158,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'bird',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 1,
},
],
},
    'nested_array': [
    [
    -9,
],
    [
    1,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fish',
    'fox',
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
    'mixed_type': None,
    'maybe': 'gorilla',
    'maybe_null': None,
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
    '25',
    '22',
    '09',
    '14',
],
    'text_data': '56cb86d1c3824c5e886f950765afa19d',
    'rand_digit': 1,
    'rand_number': 0.73286,
    'rand_signed_int': -8,
    'rand_datetime': '2000-02-27 04:00:52-1200',
    'text_array': [
    'f5d5cc133972440a87889fecaf5f0756',
    '689269a2bcbc478db7438d023667ff81',
],
    'words': 'grasshopper bee',
    'nested': {
    'id': 159,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'shark',
    'scorpion',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'frog',
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
],
    'text_data': 'e48a17dd38ff45e7b9b762c8839aa7c8',
    'rand_digit': 7,
    'rand_number': 0.93501,
    'rand_signed_int': 8,
    'rand_datetime': '2000-12-11 23:21:12',
    'text_array': [
    'a4f7420219784ff5a6c53eba7bf8b76a',
    'dbb67f2bed064561a72d700146595e12',
],
    'words': 'bee bird',
    'nested': {
    'id': 160,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'lion',
    'ape',
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
    'mixed_type': 'dragonfly',
    'maybe_null': 'mosquito',
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
    '28',
],
    'text_data': 'd79e9479649c41309a980151d02e4376',
    'rand_digit': 5,
    'rand_number': 0.93756,
    'rand_signed_int': -1,
    'rand_datetime': '2000-07-16T23:34:22.068850+05:00',
    'text_array': [
    'e541ff21478940e1a09c9b8efc4b5a00',
    '0da584b166a143d394f56a3874c99586',
],
    'words': 'wolf whale',
    'nested': {
    'id': 161,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'lobster',
    'ape',
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
    'maybe_null': None,
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
],
    'text_data': 'ce2b376996d94084800dc8c72d2f6eb4',
    'rand_digit': 0,
    'rand_number': 0.32353,
    'rand_signed_int': -2,
    'rand_datetime': '2000-01-17',
    'text_array': [
    '38abfb1139664cccb00f32e9b1f7e36e',
    '9dbc3f4e8b864a9798b69402c7b047bf',
],
    'words': 'snake cow',
    'nested': {
    'id': 162,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'cheetah',
    'camel',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': [
    86,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'wolf',
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
    '19',
    '14',
],
    'text_data': 'c7d0bd328174464a91b4ea272046c18e',
    'rand_digit': 1,
    'rand_number': 0.50753,
    'rand_signed_int': -3,
    'rand_datetime': '2000-05-11T09:16:08.806174',
    'text_array': [
    '21ab44bf096b4aa38cd4073dce63522c',
    'aad65b1795c74713a47332ff90368a8a',
],
    'words': 'fly monkey',
    'nested': {
    'id': 163,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'cheetah',
    'dog',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': [
    81,
],
    'rand_bool': False,
    'mixed_type': 0.19362,
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
    'content-length': '10551',
}
        
        # 原始请求内容
        original_content = {
    'context': [
    {
    'positive': 11,
    'negative': 19,
},
    {
    'positive': 100,
    'negative': 199,
},
    {
    'positive': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'negative': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
},
    {
    'positive': 30,
    'negative': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
},
    {
    'positive': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'negative': 15,
},
],
    'limit': 200,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_sparse_discovery.test_context_many_pairs')
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
    test = TestSparseDiscoverytestContextManyPairs()
    test.run_tests()
