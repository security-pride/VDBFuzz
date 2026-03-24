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
logger = logging.getLogger('vdb_fuzzer.test.test_sparse_updates_test_upload_uuid_in_batches')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_sparse_updates.test_upload_uuid_in_batches"
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



class TestSparseUpdatestestUploadUuidInBatches:
    """自动生成的VDB模糊测试类 - test_sparse_updates.test_upload_uuid_in_batches"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_sparse_updates.test_upload_uuid_in_batches"
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
    'content-length': '200',
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
    'content-length': '1999138',
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
    '21',
],
    'text_data': 'fed70fafded74bf99574a0ddca11255f',
    'rand_digit': 5,
    'rand_number': 0.05834,
    'rand_signed_int': 0,
    'rand_datetime': '2000-05-29T03:57:05.251436Z',
    'text_array': [
    '42885116a6f84b6bbcb6cdc72c887f15',
    '83609d1abd824dea8d36284dd7cd5cff',
],
    'words': 'hippo octopus',
    'nested': {
    'id': 100,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 6,
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
],
},
    'nested_array': [
    [
    4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'duck',
    'sloth',
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
    'mixed_type': 6,
    'maybe_null': 'goat',
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
    '29',
    '24',
],
    'text_data': 'aa9d808e39db4a3d803eec95d852285b',
    'rand_digit': 4,
    'rand_number': 0.78795,
    'rand_signed_int': -9,
    'rand_datetime': '2000-09-05 18:44:56',
    'text_array': [
    '7c46c3dfcec24e86bdb7528daae15caf',
    'b2347820e4ea4caab6f1bd7633dc8f5f',
],
    'words': 'butterfly rhino',
    'nested': {
    'id': 101,
    'rand_digit': 1,
    'array': [
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'deer',
    'dog',
],
    'city': {
    'name': 'Kuala Lumpur',
    'geo': {
    'lat': 3.139003,
    'lon': 101.686855,
},
},
    'rand_tuple': [
    36,
],
    'rand_bool': False,
    'mixed_type': 8,
    'maybe_null': None,
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
    '25',
    '02',
],
    'text_data': '9c1c6c475ce24261a3a1e4c5761c631c',
    'rand_digit': 7,
    'rand_number': 0.38202,
    'rand_signed_int': -4,
    'rand_datetime': '2000-08-29T20:15:58-1100',
    'text_array': [
    '112d9c5763d646b187cc7dcd583c60f6',
    'b35106754ad24c01bc84f5c237f25fc3',
],
    'words': 'squid duck',
    'nested': {
    'id': 102,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'zebra',
    'cat',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'rabbit',
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
    '29',
],
    'text_data': '2084dd06e7c14827b14c272d4b9f3ef3',
    'rand_digit': 6,
    'rand_number': 0.1735,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-05',
    'text_array': [
    'a774284089ab4b529ba1dc62b6d375e8',
    'e400401201e446aba3ef6cc19c1bdb0b',
],
    'words': 'panda panda',
    'nested': {
    'id': 103,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'duck',
    'number': 2,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'hyena',
    'leopard',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': [
    74,
],
    'rand_bool': True,
    'mixed_type': False,
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
    '14',
    '17',
    '03',
],
    'text_data': 'd5d491ff10a64395b3607449bbd46a67',
    'rand_digit': 7,
    'rand_number': 0.42865,
    'rand_signed_int': 3,
    'rand_datetime': '2000-04-03T11:20:13.107456',
    'text_array': [
    '20d13e078eb1406b919a36f3676b7f66',
    'a8054f6a14a440c6b7c9ffaa4b989008',
],
    'words': 'ladybug wolf',
    'nested': {
    'id': 104,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
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
],
    'word': 'sloth',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'gorilla',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    4,
],
],
    'two_words': [
    'giraffe',
    'ape',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'pig',
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
    '28',
    '24',
    '25',
    '30',
    '12',
],
    'text_data': 'd889973aff0a4546bbb93349a5c51921',
    'rand_digit': 6,
    'rand_number': 0.13428,
    'rand_signed_int': -8,
    'rand_datetime': '2000-01-06 01:30:22.081188',
    'text_array': [
    'dfa8796e3eed4ddbaef0cf56686a0017',
    '8e9237f9245845008b940c58f0358354',
],
    'words': 'goat grasshopper',
    'nested': {
    'id': 105,
    'rand_digit': 6,
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
    'hello',
],
    'word': 'bee',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cheetah',
    'dragonfly',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
],
    'text_data': 'd6cf9a475b3c41c7bfd72b8af9434c36',
    'rand_digit': 1,
    'rand_number': 0.86514,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-12T05:35:27',
    'text_array': [
    '41e3c0578fe3429189f9dc65ce1b4f88',
    '3e5b921c1da44b219de779dd3eb8aef7',
],
    'words': 'grasshopper whale',
    'nested': {
    'id': 106,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 3,
},
],
},
    'nested_array': [
    [
    0,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'bird',
    'bear',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.40726,
    'maybe_null': 'pig',
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
],
    'text_data': '073c914abf484f42b7cfcb4064203a5a',
    'rand_digit': 8,
    'rand_number': 0.18427,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-18T05:30:32+0800',
    'text_array': [
    '89c68752f9f246fb867f7e02e88f53c2',
    '616c7b98d7114b1b85651ce9342d26bc',
],
    'words': 'leopard hippo',
    'nested': {
    'id': 107,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 8,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'rhino',
    'rhino',
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
    'mixed_type': 0.12791,
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
    '15',
    '25',
    '15',
    '10',
],
    'text_data': 'ac7afb2dd9994ee0a4a4c35a32bcf94e',
    'rand_digit': 3,
    'rand_number': 0.66659,
    'rand_signed_int': 1,
    'rand_datetime': '2000-08-17 07:10',
    'text_array': [
    '3a5bb87566134e5f909554a4e830d23c',
    'aeb8e796d4bd4b14816c97ec4c334ae9',
],
    'words': 'grasshopper tiger',
    'nested': {
    'id': 108,
    'rand_digit': 9,
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
    'word': 'fly',
    'number': 4,
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
],
    'word': 'snail',
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
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fish',
    'dragonfly',
],
    'city': {
    'name': 'Rome',
    'geo': {
    'lat': 41.902782,
    'lon': 12.496366,
},
},
    'rand_tuple': [
    57,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'fish',
    'maybe_null': 'lizard',
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
    '10',
    '13',
    '05',
    '22',
    '10',
],
    'text_data': '7ed1e0185d82461696e9a5b433670194',
    'rand_digit': 5,
    'rand_number': 0.0128,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-28 19:56:33-0400',
    'text_array': [
    '3072dff0973d485ab1318506c4f1ba6a',
    '7d89ba9f64f044af9e5fb303ebc26043',
],
    'words': 'lobster frog',
    'nested': {
    'id': 109,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'bear',
    'ant',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': [
    22,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '30',
],
    'text_data': '3470cbe727fd4c859ffb446a13c31728',
    'rand_digit': 1,
    'rand_number': 0.15838,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-18T17:57:27-0400',
    'text_array': [
    'e154c47700ce4f08a4f0e527f2d72be6',
    '33fca3519d91490abe0f29fdff026979',
],
    'words': 'dragonfly snail',
    'nested': {
    'id': 110,
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
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'kangaroo',
    'fish',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'deer',
    'maybe_null': 'cheetah',
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
    '01',
],
    'text_data': '9403c8dce5a9420a878f94a5e4703b08',
    'rand_digit': 9,
    'rand_number': 0.17881,
    'rand_signed_int': 0,
    'rand_datetime': '2000-02-10 03:18:57.256929-0300',
    'text_array': [
    'be12246813f34f8b8fe78e92b6b4eb0a',
    '262db0f270344deea90138ed07e63608',
],
    'words': 'cat rabbit',
    'nested': {
    'id': 111,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'duck',
    'sloth',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
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
    '06',
    '28',
    '24',
    '22',
],
    'text_data': '368a6a088ee44d1c92af9fb3d1f01e5a',
    'rand_digit': 9,
    'rand_number': 0.8535,
    'rand_signed_int': 7,
    'rand_datetime': '2001-01-13 23:10:44.190109+1000',
    'text_array': [
    '42ae58d3656b48049e2e7c23df4bd6ff',
    '4e885500308f4d2197b7aac455a48640',
],
    'words': 'mouse monkey',
    'nested': {
    'id': 112,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 3,
},
    {
    'nested_empty': None,
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
    'word': 'ladybug',
    'number': 4,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'cow',
    'wolf',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'zebra',
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
    '24',
    '22',
    '19',
],
    'text_data': '560d3e2166ee4bf09baa408d8fad5479',
    'rand_digit': 7,
    'rand_number': 0.60938,
    'rand_signed_int': 9,
    'rand_datetime': '2000-01-09 04:19:37-0200',
    'text_array': [
    '4389499d671c4792a0f9efed194df3b8',
    '0e5d290e77ae442ea0009637948d9751',
],
    'words': 'ladybug bear',
    'nested': {
    'id': 113,
    'rand_digit': 6,
    'array': [
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
    'word': 'frog',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    8,
],
],
    'two_words': [
    'sheep',
    'lobster',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.65811,
    'maybe_null': 'ladybug',
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
    '21',
    '03',
],
    'text_data': 'cb5c545f2a824b65a1fc78ac72b29216',
    'rand_digit': 8,
    'rand_number': 0.36399,
    'rand_signed_int': 10,
    'rand_datetime': '2000-01-15T14:09:14.664037+0700',
    'text_array': [
    '5a2666d933af4b9e90fbcfb709301f02',
    'c604f823e80b429baa9e4474dbad9a9a',
],
    'words': 'fox crab',
    'nested': {
    'id': 114,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 8,
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
],
    'two_words': [
    'rabbit',
    'scorpion',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'ant',
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
    '09',
    '19',
],
    'text_data': 'ee46988e828349c9a0ade7d90de0b749',
    'rand_digit': 2,
    'rand_number': 0.65334,
    'rand_signed_int': -5,
    'rand_datetime': '2000-03-28',
    'text_array': [
    'aa2accf1658f45da81e0974e59b6d69d',
    '0c29e47dc2c04d4bbbcdfbed1e16224d',
],
    'words': 'wolf tiger',
    'nested': {
    'id': 115,
    'rand_digit': 5,
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
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'mouse',
    'number': 10,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,5__',
    'two_words': [
    'leopard',
    'duck',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
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
    '21',
],
    'text_data': 'e8efa88621f94aa1b7b2441708c75ecf',
    'rand_digit': 5,
    'rand_number': 0.35131,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-14T08:56:05-0100',
    'text_array': [
    'bfc954f46c2d4cfda15d77094831cee2',
    '6daaf5c24c3647f3b3bd3c654fa0c8ee',
],
    'words': 'lizard elephant',
    'nested': {
    'id': 116,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'crab',
    'number': 7,
},
],
},
    'nested_array': [
    [
    0,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'snake',
    'octopus',
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
    'maybe_null': 'mosquito',
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
    '18',
],
    'text_data': '079a584ec7074f2993a7f1de4f9e2b38',
    'rand_digit': 2,
    'rand_number': 0.24832,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-13T03:43:48.997941+01:00',
    'text_array': [
    'c95d54ace8f04af9a5c9522b8d0ef18c',
    '478e281d98d04051955f9f00f3c7610d',
],
    'words': 'snake bird',
    'nested': {
    'id': 117,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 7,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -2,
],
],
    'two_words': [
    'cheetah',
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
    'rand_bool': True,
    'mixed_type': True,
    'maybe_null': 'bee',
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
    '05',
],
    'text_data': 'd5ec74772dc94464b6bc4985f2449437',
    'rand_digit': 8,
    'rand_number': 0.40309,
    'rand_signed_int': 9,
    'rand_datetime': '2000-09-12T03:34:02.412197',
    'text_array': [
    '490fa40dc9ee44849244068ac1af9902',
    '18e3c661fa28492c9993c5e4c284d257',
],
    'words': 'cheetah lobster',
    'nested': {
    'id': 118,
    'rand_digit': 5,
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
],
    'word': 'snake',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    [
    9,
],
],
    'two_words': [
    'lion',
    'duck',
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
    'mixed_type': None,
    'maybe_null': 'deer',
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
    '30',
    '28',
    '17',
],
    'text_data': 'f75a78a7976040a392d83fc26737607e',
    'rand_digit': 4,
    'rand_number': 0.64933,
    'rand_signed_int': -7,
    'rand_datetime': '2000-05-31',
    'text_array': [
    '444b749fb9da4fc2b93c5096d01bfe99',
    'f5e07af68221433b9b0a484193bbc276',
],
    'words': 'sheep butterfly',
    'nested': {
    'id': 119,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'shark',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 7,
},
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
],
    'word': 'ape',
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
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'snail',
    'squid',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'koala',
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
    '21',
    '02',
],
    'text_data': 'f0a44a2a1ab74f6bab4934e857167bd0',
    'rand_digit': 6,
    'rand_number': 0.35225,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-16 02:26:38.179656',
    'text_array': [
    'fd19fd1f465b493c8c72477e16ccdb33',
    'f3d3b178af354f41bec7297c7c560190',
],
    'words': 'fox pig',
    'nested': {
    'id': 120,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'duck',
    'camel',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'goat',
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
    '14',
    '02',
    '07',
],
    'text_data': 'adf2d13ee4e047268fa4d1087b220fe3',
    'rand_digit': 9,
    'rand_number': 0.36901,
    'rand_signed_int': 8,
    'rand_datetime': '2000-04-01 11:26',
    'text_array': [
    '80bf9dcd51434d4b8a817d67897b51f3',
    'ad7e031ca0a14a6caf508a8edf9e8cce',
],
    'words': 'zebra rabbit',
    'nested': {
    'id': 121,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'spider',
    'spider',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fox',
    'maybe_null': None,
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
    '10',
    '22',
    '05',
],
    'text_data': 'a8963cb077ae481dbe799cb4fcfe3c3b',
    'rand_digit': 1,
    'rand_number': 0.49687,
    'rand_signed_int': 2,
    'rand_datetime': '2000-10-20 19:21:07.275336',
    'text_array': [
    'c2b3eb83ea3f4cb0a363ec5da46e13e2',
    'bef84cb571c6402dac073fe86d051178',
],
    'words': 'panda leopard',
    'nested': {
    'id': 122,
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
    'number': 6,
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
],
    'two_words': [
    'spider',
    'scorpion',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'elephant',
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
    '06',
    '24',
    '07',
    '16',
    '30',
],
    'text_data': '61eba794821a4916bbdc667520344aaa',
    'rand_digit': 5,
    'rand_number': 0.14351,
    'rand_signed_int': -4,
    'rand_datetime': '2000-06-05 01:26:46.609161',
    'text_array': [
    '2eed2d15090d4246a3ad252b4da2e42f',
    '943fbac84fb34eb1ac0adff20e44938a',
],
    'words': 'sheep camel',
    'nested': {
    'id': 123,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    7,
],
],
    'two_words': [
    'snake',
    'elephant',
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
    'mixed_type': 0.15173,
    'maybe': 'leopard',
    'maybe_null': 'cow',
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
    '18',
],
    'text_data': '2c0e0b8ea97647899f8ef1e59310b19c',
    'rand_digit': 7,
    'rand_number': 0.02533,
    'rand_signed_int': -4,
    'rand_datetime': '2000-12-21',
    'text_array': [
    '814f8c1a9f3e407c9c5839b6be17450d',
    '54cdd0cee3b74a53a327ed19f0d3c6ca',
],
    'words': 'mosquito frog',
    'nested': {
    'id': 124,
    'rand_digit': 8,
    'array': [
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
],
    'word': 'dragonfly',
    'number': 1,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 9,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lion',
    'lizard',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'crab',
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
],
    'text_data': 'dee935d7e67046df9fdd08b1bceb5816',
    'rand_digit': 4,
    'rand_number': 0.18276,
    'rand_signed_int': 10,
    'rand_datetime': '2000-03-25T01:51:34.702772+06:00',
    'text_array': [
    '3710cf80654047ce99e8d326380429f7',
    'adcc7eed1de74db5a3609326719f06f3',
],
    'words': 'deer dog',
    'nested': {
    'id': 125,
    'rand_digit': 2,
    'array': [
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
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    5,
],
],
    'two_words': [
    'sheep',
    'fly',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'scorpion',
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
    '12',
    '11',
    '14',
    '05',
    '28',
],
    'text_data': '93de6276e622413d9876b39d33931945',
    'rand_digit': 7,
    'rand_number': 0.93343,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-24T18:11:13.165567',
    'text_array': [
    '49a49b0934094c24b29fafa77497ca5f',
    '20ca05ff36b74dfbbd92e4ee969de709',
],
    'words': 'giraffe rhino',
    'nested': {
    'id': 126,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 9,
},
],
},
    'nested_array': [
    [
    -6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hyena',
    'koala',
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
    'mixed_type': True,
    'maybe': 'bear',
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
    '03',
    '16',
    '23',
    '22',
],
    'text_data': 'edc486c949f242b784faaafa951d9e9a',
    'rand_digit': 5,
    'rand_number': 0.32194,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-12T23:28:38.603440',
    'text_array': [
    'd1fe6094e75e42adbc7a8d199307d973',
    'c589872a3215464dab481f44a9f380ad',
],
    'words': 'horse tiger',
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
    'word': 'whale',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    3,
],
],
    'two_words': [
    'hippo',
    'koala',
],
    'city': {
    'name': 'Athens',
    'geo': {
    'lat': 37.98381,
    'lon': 23.727539,
},
},
    'rand_tuple': [
    40,
],
    'rand_bool': False,
    'mixed_type': 'lizard',
    'maybe': 'dolphin',
    'maybe_null': 'dog',
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
    '13',
    '20',
    '25',
],
    'text_data': 'a10073f1902a40b7849659bae075d288',
    'rand_digit': 6,
    'rand_number': 0.46669,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-03 01:31',
    'text_array': [
    'fea0542639aa4792a82eb56c777da7a2',
    '314d6085b6054cf48f4e7d7406506405',
],
    'words': 'chicken cow',
    'nested': {
    'id': 128,
    'rand_digit': 5,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'gorilla',
    'frog',
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
    'mixed_type': 'whale',
    'maybe_null': 'horse',
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
    '12',
    '25',
    '23',
],
    'text_data': 'd51cbcb9a42344c18d9f2ff45e2f85ca',
    'rand_digit': 8,
    'rand_number': 0.07273,
    'rand_signed_int': 8,
    'rand_datetime': '2000-12-14T14:36:25+0500',
    'text_array': [
    '126c30b140a14be9973f264abead2ab1',
    '699b0bf9268644b382a55c89dcf3f972',
],
    'words': 'hippo snail',
    'nested': {
    'id': 129,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'panda',
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'sloth',
    'shark',
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
    '16',
    '23',
    '02',
],
    'text_data': '21cfd16b6c36471ab8f0c9dfce29cdb4',
    'rand_digit': 6,
    'rand_number': 0.28256,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-28T19:05:31+0100',
    'text_array': [
    '677e69b959854b8fba79c6fa0009931a',
    'c16fd84502ca47c2983039354c07a5df',
],
    'words': 'duck mouse',
    'nested': {
    'id': 130,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lion',
    'number': 8,
},
    {
    'nested_empty': None,
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
],
    'word': 'dog',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fly',
    'camel',
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
    'mixed_type': 0.57645,
    'maybe': 'sheep',
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
    '16',
],
    'text_data': '7c23080ea14e4c4dbe0233c8d9404c7a',
    'rand_digit': 4,
    'rand_number': 0.52884,
    'rand_signed_int': -7,
    'rand_datetime': '2000-09-19T15:58:35',
    'text_array': [
    '4a6af0887dd6404ba1bd0da0578a4746',
    '8b1183cb672246b69b3033517d78a44c',
],
    'words': 'mosquito lion',
    'nested': {
    'id': 131,
    'rand_digit': 2,
    'array': [
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
    'word': 'snail',
    'number': 6,
},
    {
    'nested_empty': None,
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
    'word': 'sheep',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    [
    -2,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'whale',
    'mouse',
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
    'mixed_type': False,
    'maybe': 'fox',
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
    '11',
    '08',
    '14',
],
    'text_data': '049dfd490401470290ee1547bef966ba',
    'rand_digit': 2,
    'rand_number': 0.09828,
    'rand_signed_int': -3,
    'rand_datetime': '2000-02-24T11:42:51+0000',
    'text_array': [
    '3bb33c3bc9b940948dab833ba8d977c6',
    '8d033c54620647e58f5bf03164a37f23',
],
    'words': 'rhino scorpion',
    'nested': {
    'id': 132,
    'rand_digit': 1,
    'array': [
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
    'word': 'fly',
    'number': 7,
},
    {
    'nested_empty': None,
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
    'word': 'gorilla',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    4,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'koala',
    'snake',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cow',
    'maybe_null': 'giraffe',
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
    '01',
    '28',
],
    'text_data': 'e91e64ddf1d94bda9574b87597f0531b',
    'rand_digit': 1,
    'rand_number': 0.64105,
    'rand_signed_int': 8,
    'rand_datetime': '2000-08-25',
    'text_array': [
    'ad148b892fed4ac0b416f3b0bc8cbc4c',
    '14b8e53879a840d38f5dcf32052fd836',
],
    'words': 'elephant fox',
    'nested': {
    'id': 133,
    'rand_digit': 0,
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
    'word': 'cheetah',
    'number': 5,
},
],
},
    'nested_array': [
    [
    8,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ladybug',
    'shark',
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
    'mixed_type': False,
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
    '05',
    '06',
    '27',
],
    'text_data': '3c39b68bd67a4f21a8b0a8198faeacba',
    'rand_digit': 2,
    'rand_number': 0.6614,
    'rand_signed_int': -8,
    'rand_datetime': '2000-04-06 03:40:11',
    'text_array': [
    '381555d5631947ae939bcf404bce033c',
    '83ef20edc01847228ad8dddd73b53179',
],
    'words': 'panda spider',
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
    'word': 'wolf',
    'number': 5,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'bird',
    'octopus',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'frog',
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
    'text_data': 'fd85ba82a9c5449ab7ca549cb7fd21c9',
    'rand_digit': 4,
    'rand_number': 0.47302,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-08T21:13:28-0300',
    'text_array': [
    '7ff81145d2c943128b4cfc94a63cb8c1',
    'b1f36d60da144807bde97e91b215c5c6',
],
    'words': 'sloth lion',
    'nested': {
    'id': 135,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'sloth',
    'dolphin',
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
    'mixed_type': False,
    'maybe': 'crab',
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
    '02',
    '28',
],
    'text_data': 'a0863a17463b4441bb69af59464c9359',
    'rand_digit': 6,
    'rand_number': 0.63759,
    'rand_signed_int': 8,
    'rand_datetime': '2000-06-16T19:12:27.262020',
    'text_array': [
    'cac86efd5b31473488eed150459629b3',
    '2a6160429ff54355a433ea8e13d27d1d',
],
    'words': 'spider sheep',
    'nested': {
    'id': 136,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 1,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 4,
},
],
},
    'nested_array': [
    [
    -3,
],
    [
],
],
    'two_words': [
    'ant',
    'octopus',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
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
    '24',
    '20',
    '19',
    '30',
],
    'text_data': '0a7aa7219e524ffeb28d7d4bb7a1e86a',
    'rand_digit': 7,
    'rand_number': 0.09325,
    'rand_signed_int': -3,
    'rand_datetime': '2000-06-06T19:46:37',
    'text_array': [
    'fb8113c201fb412cbca850259b4f31e2',
    '6df94cb00a4849f98863fae9d28524c6',
],
    'words': 'hyena crab',
    'nested': {
    'id': 137,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'zebra',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'squid',
    'squid',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
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
    '12',
    '09',
    '28',
    '29',
    '19',
],
    'text_data': '986524f4200d4f24bc0c0e3bcb493aa7',
    'rand_digit': 6,
    'rand_number': 0.78288,
    'rand_signed_int': 3,
    'rand_datetime': '2000-03-31T10:33:18.793387',
    'text_array': [
    '98b508fde1324fefa052c9c879cf0468',
    '1e591f4eaeb24957bf3644ddcfb9ef0f',
],
    'words': 'cheetah monkey',
    'nested': {
    'id': 138,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'fox',
    'pig',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
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
],
    'text_data': '373dc7f031b44662b7328ad85434cff5',
    'rand_digit': 1,
    'rand_number': 0.1557,
    'rand_signed_int': 10,
    'rand_datetime': '2000-09-02T21:21:59-1200',
    'text_array': [
    '0ec5546b7ae04d1ea8fac27f3259e18b',
    'ad55fae5def44940a3cc20f2a838149b',
],
    'words': 'bear chicken',
    'nested': {
    'id': 139,
    'rand_digit': 3,
    'array': [
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
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'butterfly',
    'lion',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'turtle',
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
    '26',
],
    'text_data': '3688c981ef8f4efba3f5d927cea9eb39',
    'rand_digit': 8,
    'rand_number': 0.55164,
    'rand_signed_int': 5,
    'rand_datetime': '2000-02-14T04:12:42.668906-08:00',
    'text_array': [
    '58ccd03c05624011bb2a214d1644cb19',
    '864f4065183e45618294c0c349089404',
],
    'words': 'hyena snake',
    'nested': {
    'id': 140,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cow',
    'cow',
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
    'mixed_type': 3,
    'maybe_null': None,
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
    '26',
    '06',
],
    'text_data': '8e2e00cb01994e3aa0c77fbf73f0a1d0',
    'rand_digit': 0,
    'rand_number': 0.3333,
    'rand_signed_int': -7,
    'rand_datetime': '2000-03-19T08:35:30.105267',
    'text_array': [
    '951e7d8fad554b0f92689b8c3a7da826',
    'ffc7317ed6774c80b6855d3bb0837643',
],
    'words': 'turtle crab',
    'nested': {
    'id': 141,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'number': 5,
},
],
},
    'nested_array': [
    [
    8,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'wolf',
    'camel',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 4,
    'maybe': 'shark',
    'maybe_null': 'zebra',
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
    '17',
    '09',
    '13',
],
    'text_data': 'f3044dcc24ce4093a2e745363de42f2e',
    'rand_digit': 8,
    'rand_number': 0.06032,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-27 04:08',
    'text_array': [
    '4b4c571aabd549fd90471883c06e03e7',
    'f1426aa379034a358e4789052aaa8407',
],
    'words': 'fly cheetah',
    'nested': {
    'id': 142,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'cheetah',
    'panda',
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
    'mixed_type': 3,
    'maybe': 'sheep',
    'maybe_null': 'duck',
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
    '14',
    '15',
],
    'text_data': '4ed98d0cb4974b338f3f30bcebc1e5eb',
    'rand_digit': 3,
    'rand_number': 0.18965,
    'rand_signed_int': -1,
    'rand_datetime': '2000-02-10',
    'text_array': [
    '2589b97dd8f7449e88eac1071009e4cc',
    '0399611b754c4388992732e2673205dd',
],
    'words': 'rhino bird',
    'nested': {
    'id': 143,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bear',
    'gorilla',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'frog',
    'maybe_null': 'fish',
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
    '14',
    '29',
    '03',
    '15',
    '08',
],
    'text_data': '5d4cb7ac2a6a460b9c85ce56c3c32d55',
    'rand_digit': 6,
    'rand_number': 0.9471,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-01T21:39:35.053217',
    'text_array': [
    '6655850327134d47a53c11dca264b22b',
    '37644de3f7e54230bb27d1a503ab8e5b',
],
    'words': 'sheep fish',
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
    'number': 9,
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
    'hello',
],
    'word': 'butterfly',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 7,
},
],
},
    'nested_array': [
    [
    -9,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -8,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'monkey',
    'monkey',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '20',
    '19',
    '12',
    '20',
],
    'text_data': '8f933db1255441d58f9738889e41a892',
    'rand_digit': 9,
    'rand_number': 0.82006,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-23',
    'text_array': [
    'b0eb388e840c4053a59901fd9f112146',
    '04dbc6164bff495e971f1c020f36c626',
],
    'words': 'squid bee',
    'nested': {
    'id': 145,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 4,
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
    'ape',
    'snake',
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
    'mixed_type': True,
    'maybe': 'monkey',
    'maybe_null': 'rhino',
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
    '13',
    '12',
    '11',
],
    'text_data': 'a594ae9811e54d01b74db12514595c83',
    'rand_digit': 1,
    'rand_number': 0.29657,
    'rand_signed_int': 8,
    'rand_datetime': '2000-01-22 19:29:31',
    'text_array': [
    '9560731d65b64d10aff9b99085a54f66',
    'bf17c16306c345b985f63c5f1ed1f5b3',
],
    'words': 'spider bear',
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
    'word': 'frog',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'shark',
    'number': 8,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    3,
],
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
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'kangaroo',
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
    '19',
    '04',
    '01',
    '12',
    '17',
],
    'text_data': '314c8194a976404eaf1857eb52a5b452',
    'rand_digit': 2,
    'rand_number': 0.36655,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-12T03:35:34.208048',
    'text_array': [
    '35f1544fd24a473c9314dfed03e542df',
    '41c2c57f4e9849cca8423f317217036b',
],
    'words': 'cow snake',
    'nested': {
    'id': 147,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'panda',
    'tiger',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'horse',
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
    '13',
    '29',
],
    'text_data': '87ad7bf2a9c3403e90be5f4a6596741a',
    'rand_digit': 4,
    'rand_number': 0.61971,
    'rand_signed_int': -8,
    'rand_datetime': '2000-01-06 00:33:11.425604',
    'text_array': [
    'ac52a29302bd43328efb775dca94ff83',
    '725f7672302f45eaafa8bda073941ce5',
],
    'words': 'panda turtle',
    'nested': {
    'id': 148,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'turtle',
    'giraffe',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'hyena',
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
    '05',
    '23',
    '17',
    '15',
    '13',
],
    'text_data': '402072c747344616a6601ab7d2c25ad9',
    'rand_digit': 6,
    'rand_number': 0.34249,
    'rand_signed_int': 6,
    'rand_datetime': '2000-05-20 02:20:40-0100',
    'text_array': [
    '8a940d0a2a0f422b8847e5af9281ed58',
    'ac17cade63284a6d9b47c65b481b872a',
],
    'words': 'dragonfly lion',
    'nested': {
    'id': 149,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 1,
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
],
    'word': 'wolf',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'spider',
    'whale',
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
    'mixed_type': 'rabbit',
    'maybe': 'squid',
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
    '16',
    '27',
    '12',
    '18',
    '16',
],
    'text_data': '1216f603e6f24488b25269050f65162b',
    'rand_digit': 2,
    'rand_number': 0.24106,
    'rand_signed_int': -8,
    'rand_datetime': '2000-08-12 07:09:44.510770-1100',
    'text_array': [
    '997acf91bce049c684c590a68d1aedc7',
    '8b58cfbf019748ba899c5c914f1fcbf0',
],
    'words': 'bear giraffe',
    'nested': {
    'id': 150,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'goat',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'shark',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'octopus',
    'frog',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': [
    9,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': 'dolphin',
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
    '10',
    '24',
    '16',
    '12',
],
    'text_data': '1ff5107682a8445cbe77f5e59f9dc8c4',
    'rand_digit': 0,
    'rand_number': 0.27389,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-05 08:44:23.098067',
    'text_array': [
    'dbb298a9b69d47809557d1e0134da485',
    'b627e57a26bf455eb84773c8e30c087c',
],
    'words': 'hyena whale',
    'nested': {
    'id': 151,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'octopus',
    'turtle',
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
    'mixed_type': True,
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
],
    'text_data': '3c2362909b9746d8abb46387ac3b2ca2',
    'rand_digit': 5,
    'rand_number': 0.63774,
    'rand_signed_int': 9,
    'rand_datetime': '2000-07-28T01:25:25.256112',
    'text_array': [
    '3964deb609bd40a28bfadcd2e18485eb',
    '05fd626eb54540689747d11cb516b5e9',
],
    'words': 'elephant kangaroo',
    'nested': {
    'id': 152,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'dolphin',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bird',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'bird',
    'sloth',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'butterfly',
    'maybe_null': 'bear',
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
    '29',
    '17',
    '22',
    '29',
    '27',
],
    'text_data': 'e435409c8c20433c88ad638fb8d43f17',
    'rand_digit': 0,
    'rand_number': 0.43869,
    'rand_signed_int': 3,
    'rand_datetime': '2000-10-30 16:21:02',
    'text_array': [
    '4e5dbafc4bab46aebdda9eeb65776a49',
    '9681a2e4d18d4b368b9de0906720e9e6',
],
    'words': 'snake dog',
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
    'word': 'chicken',
    'number': 1,
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
    'word': 'snail',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'leopard',
    'hippo',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'horse',
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
    '20',
],
    'text_data': '12ae86ef76244d39a22a79d25153b1c2',
    'rand_digit': 2,
    'rand_number': 0.73768,
    'rand_signed_int': -7,
    'rand_datetime': '2000-07-01',
    'text_array': [
    'c46c102f237742e9b8cde1ae1666c4c3',
    'ef741e529c13412a8823384e48afd646',
],
    'words': 'octopus koala',
    'nested': {
    'id': 154,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 6,
},
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
],
    'word': 'monkey',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'ape',
    'pig',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
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
    '25',
],
    'text_data': '52516d5c2f054f6ba9861fa9edf03dfa',
    'rand_digit': 0,
    'rand_number': 0.47244,
    'rand_signed_int': -3,
    'rand_datetime': '2000-12-14T03:04:46',
    'text_array': [
    'c19f40f865f24edfb66738e4865fe665',
    '8e3d09d6459f47caacf9b6a962144b81',
],
    'words': 'hyena giraffe',
    'nested': {
    'id': 155,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'scorpion',
    'dragonfly',
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
    '28',
    '24',
    '26',
    '26',
],
    'text_data': 'efed0ea5ccdb46b5aed62d63a4b79099',
    'rand_digit': 6,
    'rand_number': 0.6884,
    'rand_signed_int': -6,
    'rand_datetime': '2000-05-25T10:49:22.944110-0100',
    'text_array': [
    'dd2a67cb90e94fd48e0461f96c7d23d9',
    'cdbab0b2626f42f2bdc70a727258983b',
],
    'words': 'scorpion tiger',
    'nested': {
    'id': 156,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
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
    'number': 1,
},
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
    'sloth',
    'shark',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.57397,
    'maybe': 'grasshopper',
    'maybe_null': 'fish',
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
    '17',
],
    'text_data': '2f50359ae49d4b9f97f1eeb72016054e',
    'rand_digit': 7,
    'rand_number': 0.86961,
    'rand_signed_int': -2,
    'rand_datetime': '2000-12-18T05:15:06.975386+08:00',
    'text_array': [
    '371e928c66014f979cc7bd73ccf3eb80',
    '38c0302374e5438ebf3121d3df641ec0',
],
    'words': 'mouse cheetah',
    'nested': {
    'id': 157,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 1,
},
    {
    'nested_empty': None,
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
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'grasshopper',
    'fish',
],
    'city': {
    'name': 'Copenhagen',
    'geo': {
    'lat': 55.676097,
    'lon': 12.568337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'chicken',
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
    '17',
    '03',
    '18',
    '29',
    '02',
],
    'text_data': 'f3825ec27c5c4742b6aabfe79a643b59',
    'rand_digit': 8,
    'rand_number': 0.46331,
    'rand_signed_int': -7,
    'rand_datetime': '2000-04-30T16:12:21.514797+1100',
    'text_array': [
    '0c65af8cc8b34937ae5e4840a1236561',
    'e43511297cac4b4f8372721157a41045',
],
    'words': 'whale ant',
    'nested': {
    'id': 158,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'cat',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'zebra',
    'fish',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': [
    83,
],
    'rand_bool': False,
    'mixed_type': 5,
    'maybe': 'goat',
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
    '06',
    '29',
    '16',
],
    'text_data': 'f02a8098159d4cada5ea9ba5ea04d5a4',
    'rand_digit': 8,
    'rand_number': 0.89922,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-24 19:37:00.817437',
    'text_array': [
    '36b276dc5e3f4f71b934d6f96663a31c',
    'b0248117694f4469b89b7958356d9b12',
],
    'words': 'mouse ant',
    'nested': {
    'id': 159,
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
    'word': 'bear',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -6,
],
    [
],
],
    'two_words': [
    'hyena',
    'cat',
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
    'maybe': 'chicken',
    'maybe_null': 'ladybug',
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
    '11',
    '03',
    '30',
    '05',
    '27',
],
    'text_data': 'cafe65198df4428aba41ba47de371359',
    'rand_digit': 0,
    'rand_number': 0.36874,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-03 11:31',
    'text_array': [
    'c9a64aa7ab5a4785a3cf4015e73a81da',
    '2489b1499116409bb16a9265d5aeafcf',
],
    'words': 'wolf rabbit',
    'nested': {
    'id': 160,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'lion',
    'grasshopper',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
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
    'text_data': '7a0befdf305940f8a4cc62baf650902d',
    'rand_digit': 1,
    'rand_number': 0.87534,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-24 22:45:16-0500',
    'text_array': [
    'e5b8cfd1a23e45da94e916f41975642c',
    '4ee7c762b37341aa95fa9caae5570b02',
],
    'words': 'ant zebra',
    'nested': {
    'id': 161,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 10,
},
],
},
    'nested_array': [
    [
    5,
],
    [
    3,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'crab',
    'shark',
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
    'mixed_type': 1,
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
],
    'text_data': '9d6a4a3a448c469aab635105574cb541',
    'rand_digit': 9,
    'rand_number': 0.54774,
    'rand_signed_int': -1,
    'rand_datetime': '2000-01-07T04:45:10-1000',
    'text_array': [
    '962dc03ae1754b12999535c320eae628',
    '02b3586b3c2a41f4b46505dc030e5f28',
],
    'words': 'lobster snake',
    'nested': {
    'id': 162,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dolphin',
    'fox',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': [
    32,
],
    'rand_bool': False,
    'mixed_type': 'camel',
    'maybe': 'fox',
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
    '24',
    '04',
],
    'text_data': '7fb7a1ec64ea431eb82623d52c287893',
    'rand_digit': 4,
    'rand_number': 0.27578,
    'rand_signed_int': -7,
    'rand_datetime': '2001-01-16 18:45:23',
    'text_array': [
    'f6c1a5c7c6ad4121838c9ec36d99a32b',
    '4f2f4fe52da541c88174bc95a5839a03',
],
    'words': 'hyena dragonfly',
    'nested': {
    'id': 163,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'ant',
    'wolf',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
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



    def test_request_2(self):
        """测试请求 2 - PUT http://localhost:6333/collections/congruence_test_collection/points?wait=true"""
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
    'content-length': '3120522',
}
        
        # 原始请求内容
        original_content = {
    'batch': {
    'ids': [
    '467b32b1-8aef-44c0-8f24-f7157a0b0821',
    '34b29782-e7fb-4e95-a601-e0cd6c444c77',
    '8cacfa95-e33d-48ba-8537-5ba57336762b',
    '47f13448-7061-4888-9c0f-9bd8f7703036',
    '4e5873e1-a2ac-448e-a95a-5f1dd2ff9cc5',
    '609a8cdd-dc3b-4cf5-b4bb-347536ed4a5d',
    '3ea36120-1c0e-409f-8cb9-df07756f357e',
    '24361677-2ab4-49c1-a13a-90245aaf501a',
    '19d0563c-63a5-45bb-aab1-7fd970ac48f1',
    '67d5d5bf-7359-4b63-9013-64d4ffe41bc8',
    'a2171ca4-e5c0-422e-ae69-07505fa9450e',
    '1b485ab0-df18-4646-a4db-5cf85705e0d8',
    'f5aefd37-7ef0-445c-8198-13f6a33fb640',
    '6dfca1cc-249d-449a-8eb6-4c3c6628675f',
    'e79282f9-52d9-4cb4-ac89-773ceb9cb8f9',
    'cbd2648c-24e0-409b-a131-1dd040cca2dc',
    '6c11bb70-ea99-48f3-8d4f-eb80585d1dda',
    'c467ede4-5136-4174-b05b-7ad22b674fce',
    'fc1c5313-7d12-4fb4-a731-5b4e97a129c6',
    '488cde47-09df-4c92-b3e1-34a42ab4d4a4',
    'f4801bdc-cef7-4613-beb4-f930a031dabc',
    '8a33825d-3d44-4815-88bd-3bde301def65',
    'ba1526fd-87c3-47e6-8202-bbafabe93846',
    '4846509f-ee5c-43e9-8d9a-454d8aa500ec',
    '0007484d-6d54-4bb7-97e3-db7a973340ec',
    '6ee47f59-a245-4f52-bbb9-3eb94a073193',
    '4bdedfb7-1cae-4074-977d-502c0fe714d4',
    'a120b829-7dcf-449a-bc55-c55bbb6465ae',
    '83ab387b-9c03-4cbc-a9c6-94cfd323330c',
    '7d0f8986-7807-4578-b39d-4333058add7d',
    'bcc5d9c6-0d94-4c8d-ac99-4a888afc72dd',
    '68f6b0bb-4cbf-4621-a60d-7d37cd1a83d0',
    '50c50892-0e24-40a6-ac7c-48df0ad10089',
    '12755a58-1b0a-4cbf-b670-453a6f67e162',
    '828a66fa-6dbd-42ab-9bc3-030e9e6f43f5',
    'f08faa65-dbda-4d91-9b52-fe8fa8d9cc7c',
    'ddd13941-356c-4112-9bfa-b226347eebd3',
    '4865dc7d-b4b4-436a-9c01-ea323eb8b65d',
    '541dd0d7-93c0-49ab-97a2-b0851a696f16',
    'dd799d83-8644-4c9f-80ed-bb932233cd08',
    '9557d666-4824-4328-a463-239fab6ac6f1',
    '20c54bd4-d3b6-4975-bf8e-b0abed3570c9',
    '07d6bb69-ab26-45fd-8386-ce58ce54db7b',
    '288b7b45-bc34-48f1-9f39-265f4aa36e57',
    '46622532-04e2-415f-9d3e-fa7b1b4f6716',
    '1de27084-3556-4a62-b11d-587ce49b876e',
    '698b49fb-c176-4add-a83b-34fb11f9d2f3',
    '83fcd6cc-c6a0-4a8a-94ca-58d4560bfb16',
    '44bb049b-e7ed-4172-80c8-552e685a3571',
    'e499e6f7-4229-4454-90ec-d69aa177bd4b',
    '46eb0b35-8444-42c8-a893-3b93e4820359',
    '840e519e-7d80-464c-91f5-c09a91291424',
    '6f0607fd-63b1-464c-a54f-283eb0285094',
    '2e6dc76b-9c2b-4512-aa39-76cac616b4c7',
    'ae3fb6e6-16bc-4a09-a223-5d8a1af0986b',
    '50bfe958-4a08-4d5e-bdc0-6c6391caaf32',
    'ef38d7cf-06dc-4b86-b2fc-a9611e4a0a0a',
    '676669e0-a92c-492d-b105-8f1d6eb3311c',
    '44916873-6c52-47c8-9e1a-a694568c6562',
    'fa0366c6-16db-445e-9d2e-1f506b67353a',
    'e99543f2-a7a1-4db1-bea4-1c4a8810101a',
    '1b6d749f-73ed-469f-8c9d-248e8ee8e445',
    'ec526f4c-a0ef-4f81-9f9b-27acc79f6a52',
    'c8a5937a-4930-4c1b-94e8-a982e60d0580',
    '4a7fe7e9-326d-4d37-9e86-5d90134a3c68',
    '79e2e2d9-b0a9-4c62-92ae-9178119e221b',
    'a3c86628-8070-437f-b55a-8bb9bad89db1',
    '8670503f-1b4f-4f46-94d6-17d4a1752f1d',
    '15c8afc3-8f1d-400a-b147-37e1072de91b',
    '65a8b9fa-7db9-4471-9bfb-6b61afed10a3',
    '22a6bca4-2fc6-4a4f-8109-b878d20af5de',
    'e4a11b88-dbdb-4c5e-aa4a-90e77c87429c',
    'b962b0f9-14b3-4025-86f1-5acf7e6de957',
    '9788f23e-a446-47a6-b55b-77e7b9ad25fd',
    '31c63e5f-51ba-45a4-9737-eacdf79ee6a1',
    '127c3ea2-13d8-447d-acc6-f92b1e086075',
    '2a63128c-7af1-4b05-aafb-dd4ba3b1b75e',
    '86c8c0ae-5eff-4f74-9535-d7093b6cae84',
    'fde4f472-ee96-4049-baa7-406fd8e03b27',
    '2d38ce66-25f4-42b4-bc33-06438f200475',
    '60260dbd-ba03-45ea-942c-04d672dbcd02',
    '7687643f-73af-459c-ad31-d5137fdb568f',
    '71dc501c-507f-45bc-83f8-1128b3def807',
    'c2f6736b-0e1a-465d-9273-9d4f70864528',
    '186021c8-927f-4d2e-912a-0f6357da8b17',
    '64516d64-87bb-45cd-8374-7e74b262a412',
    'e64ca3d1-c379-41ac-836b-f748f84c4e53',
    '1e9f4283-4b6c-4874-8ef1-61d144d8335e',
    'e2374631-b197-4811-a080-11825d27a83a',
    '53a82d87-0e3a-4ee0-a946-1d86e9e6fed4',
    '1b850dad-d476-4b77-b4de-7ea721dcb316',
    '364cca30-7bdf-4eb9-ad16-6b866afab44c',
    'e27c5ae0-e92c-4f4a-b027-0b6f4a486edf',
    '3516f446-ce29-4a05-a7c7-3d242b7369f6',
    '463ed9ee-e4ed-46b0-bf0a-091fc712c41c',
    '7207df1f-307a-4800-9b3e-0b93aacf0494',
    'df72fc0f-abcd-4047-b10e-93a78c78ef84',
    'f72a6bcf-e465-4574-87ff-92c715b4435c',
    '61d02171-9a10-4ccc-b07e-2a9703908307',
    'b11307e4-85dc-4c85-85fe-8c4982675b58',
],
    'vectors': {
    'sparse-text': [
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
],
    'sparse-image': [
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
],
    'sparse-code': [
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
    {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
],
},
    'payloads': [
    {
    'id': 100,
    'id_str': [
    '21',
],
    'text_data': 'fed70fafded74bf99574a0ddca11255f',
    'rand_digit': 5,
    'rand_number': 0.05834,
    'rand_signed_int': 0,
    'rand_datetime': '2000-05-29T03:57:05.251436Z',
    'text_array': [
    '42885116a6f84b6bbcb6cdc72c887f15',
    '83609d1abd824dea8d36284dd7cd5cff',
],
    'words': 'hippo octopus',
    'nested': {
    'id': 100,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 6,
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
],
},
    'nested_array': [
    [
    4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'duck',
    'sloth',
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
    'mixed_type': 6,
    'maybe_null': 'goat',
},
    {
    'id': 101,
    'id_str': [
    '29',
    '24',
],
    'text_data': 'aa9d808e39db4a3d803eec95d852285b',
    'rand_digit': 4,
    'rand_number': 0.78795,
    'rand_signed_int': -9,
    'rand_datetime': '2000-09-05 18:44:56',
    'text_array': [
    '7c46c3dfcec24e86bdb7528daae15caf',
    'b2347820e4ea4caab6f1bd7633dc8f5f',
],
    'words': 'butterfly rhino',
    'nested': {
    'id': 101,
    'rand_digit': 1,
    'array': [
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'deer',
    'dog',
],
    'city': {
    'name': 'Kuala Lumpur',
    'geo': {
    'lat': 3.139003,
    'lon': 101.686855,
},
},
    'rand_tuple': [
    36,
],
    'rand_bool': False,
    'mixed_type': 8,
    'maybe_null': None,
},
    {
    'id': 102,
    'id_str': [
    '25',
    '02',
],
    'text_data': '9c1c6c475ce24261a3a1e4c5761c631c',
    'rand_digit': 7,
    'rand_number': 0.38202,
    'rand_signed_int': -4,
    'rand_datetime': '2000-08-29T20:15:58-1100',
    'text_array': [
    '112d9c5763d646b187cc7dcd583c60f6',
    'b35106754ad24c01bc84f5c237f25fc3',
],
    'words': 'squid duck',
    'nested': {
    'id': 102,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'zebra',
    'cat',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'rabbit',
},
    {
    'id': 103,
    'id_str': [
    '29',
],
    'text_data': '2084dd06e7c14827b14c272d4b9f3ef3',
    'rand_digit': 6,
    'rand_number': 0.1735,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-05',
    'text_array': [
    'a774284089ab4b529ba1dc62b6d375e8',
    'e400401201e446aba3ef6cc19c1bdb0b',
],
    'words': 'panda panda',
    'nested': {
    'id': 103,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'duck',
    'number': 2,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'hyena',
    'leopard',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': [
    74,
],
    'rand_bool': True,
    'mixed_type': False,
},
    {
    'id': 104,
    'id_str': [
    '14',
    '17',
    '03',
],
    'text_data': 'd5d491ff10a64395b3607449bbd46a67',
    'rand_digit': 7,
    'rand_number': 0.42865,
    'rand_signed_int': 3,
    'rand_datetime': '2000-04-03T11:20:13.107456',
    'text_array': [
    '20d13e078eb1406b919a36f3676b7f66',
    'a8054f6a14a440c6b7c9ffaa4b989008',
],
    'words': 'ladybug wolf',
    'nested': {
    'id': 104,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
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
],
    'word': 'sloth',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'gorilla',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    4,
],
],
    'two_words': [
    'giraffe',
    'ape',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'pig',
},
    {
    'id': 105,
    'id_str': [
    '28',
    '24',
    '25',
    '30',
    '12',
],
    'text_data': 'd889973aff0a4546bbb93349a5c51921',
    'rand_digit': 6,
    'rand_number': 0.13428,
    'rand_signed_int': -8,
    'rand_datetime': '2000-01-06 01:30:22.081188',
    'text_array': [
    'dfa8796e3eed4ddbaef0cf56686a0017',
    '8e9237f9245845008b940c58f0358354',
],
    'words': 'goat grasshopper',
    'nested': {
    'id': 105,
    'rand_digit': 6,
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
    'hello',
],
    'word': 'bee',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cheetah',
    'dragonfly',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
    {
    'id': 106,
    'id_str': [
],
    'text_data': 'd6cf9a475b3c41c7bfd72b8af9434c36',
    'rand_digit': 1,
    'rand_number': 0.86514,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-12T05:35:27',
    'text_array': [
    '41e3c0578fe3429189f9dc65ce1b4f88',
    '3e5b921c1da44b219de779dd3eb8aef7',
],
    'words': 'grasshopper whale',
    'nested': {
    'id': 106,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 3,
},
],
},
    'nested_array': [
    [
    0,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'bird',
    'bear',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.40726,
    'maybe_null': 'pig',
},
    {
    'id': 107,
    'id_str': [
],
    'text_data': '073c914abf484f42b7cfcb4064203a5a',
    'rand_digit': 8,
    'rand_number': 0.18427,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-18T05:30:32+0800',
    'text_array': [
    '89c68752f9f246fb867f7e02e88f53c2',
    '616c7b98d7114b1b85651ce9342d26bc',
],
    'words': 'leopard hippo',
    'nested': {
    'id': 107,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 8,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'rhino',
    'rhino',
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
    'mixed_type': 0.12791,
},
    {
    'id': 108,
    'id_str': [
    '15',
    '25',
    '15',
    '10',
],
    'text_data': 'ac7afb2dd9994ee0a4a4c35a32bcf94e',
    'rand_digit': 3,
    'rand_number': 0.66659,
    'rand_signed_int': 1,
    'rand_datetime': '2000-08-17 07:10',
    'text_array': [
    '3a5bb87566134e5f909554a4e830d23c',
    'aeb8e796d4bd4b14816c97ec4c334ae9',
],
    'words': 'grasshopper tiger',
    'nested': {
    'id': 108,
    'rand_digit': 9,
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
    'word': 'fly',
    'number': 4,
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
],
    'word': 'snail',
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
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fish',
    'dragonfly',
],
    'city': {
    'name': 'Rome',
    'geo': {
    'lat': 41.902782,
    'lon': 12.496366,
},
},
    'rand_tuple': [
    57,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'fish',
    'maybe_null': 'lizard',
},
    {
    'id': 109,
    'id_str': [
    '10',
    '13',
    '05',
    '22',
    '10',
],
    'text_data': '7ed1e0185d82461696e9a5b433670194',
    'rand_digit': 5,
    'rand_number': 0.0128,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-28 19:56:33-0400',
    'text_array': [
    '3072dff0973d485ab1318506c4f1ba6a',
    '7d89ba9f64f044af9e5fb303ebc26043',
],
    'words': 'lobster frog',
    'nested': {
    'id': 109,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'bear',
    'ant',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': [
    22,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
    {
    'id': 110,
    'id_str': [
    '30',
],
    'text_data': '3470cbe727fd4c859ffb446a13c31728',
    'rand_digit': 1,
    'rand_number': 0.15838,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-18T17:57:27-0400',
    'text_array': [
    'e154c47700ce4f08a4f0e527f2d72be6',
    '33fca3519d91490abe0f29fdff026979',
],
    'words': 'dragonfly snail',
    'nested': {
    'id': 110,
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
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'kangaroo',
    'fish',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'deer',
    'maybe_null': 'cheetah',
},
    {
    'id': 111,
    'id_str': [
    '01',
],
    'text_data': '9403c8dce5a9420a878f94a5e4703b08',
    'rand_digit': 9,
    'rand_number': 0.17881,
    'rand_signed_int': 0,
    'rand_datetime': '2000-02-10 03:18:57.256929-0300',
    'text_array': [
    'be12246813f34f8b8fe78e92b6b4eb0a',
    '262db0f270344deea90138ed07e63608',
],
    'words': 'cat rabbit',
    'nested': {
    'id': 111,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'duck',
    'sloth',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
},
    {
    'id': 112,
    'id_str': [
    '06',
    '28',
    '24',
    '22',
],
    'text_data': '368a6a088ee44d1c92af9fb3d1f01e5a',
    'rand_digit': 9,
    'rand_number': 0.8535,
    'rand_signed_int': 7,
    'rand_datetime': '2001-01-13 23:10:44.190109+1000',
    'text_array': [
    '42ae58d3656b48049e2e7c23df4bd6ff',
    '4e885500308f4d2197b7aac455a48640',
],
    'words': 'mouse monkey',
    'nested': {
    'id': 112,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 3,
},
    {
    'nested_empty': None,
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
    'word': 'ladybug',
    'number': 4,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'cow',
    'wolf',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'zebra',
},
    {
    'id': 113,
    'id_str': [
    '24',
    '22',
    '19',
],
    'text_data': '560d3e2166ee4bf09baa408d8fad5479',
    'rand_digit': 7,
    'rand_number': 0.60938,
    'rand_signed_int': 9,
    'rand_datetime': '2000-01-09 04:19:37-0200',
    'text_array': [
    '4389499d671c4792a0f9efed194df3b8',
    '0e5d290e77ae442ea0009637948d9751',
],
    'words': 'ladybug bear',
    'nested': {
    'id': 113,
    'rand_digit': 6,
    'array': [
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
    'word': 'frog',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    8,
],
],
    'two_words': [
    'sheep',
    'lobster',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.65811,
    'maybe_null': 'ladybug',
},
    {
    'id': 114,
    'id_str': [
    '21',
    '03',
],
    'text_data': 'cb5c545f2a824b65a1fc78ac72b29216',
    'rand_digit': 8,
    'rand_number': 0.36399,
    'rand_signed_int': 10,
    'rand_datetime': '2000-01-15T14:09:14.664037+0700',
    'text_array': [
    '5a2666d933af4b9e90fbcfb709301f02',
    'c604f823e80b429baa9e4474dbad9a9a',
],
    'words': 'fox crab',
    'nested': {
    'id': 114,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 8,
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
],
    'two_words': [
    'rabbit',
    'scorpion',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'ant',
},
    {
    'id': 115,
    'id_str': [
    '09',
    '19',
],
    'text_data': 'ee46988e828349c9a0ade7d90de0b749',
    'rand_digit': 2,
    'rand_number': 0.65334,
    'rand_signed_int': -5,
    'rand_datetime': '2000-03-28',
    'text_array': [
    'aa2accf1658f45da81e0974e59b6d69d',
    '0c29e47dc2c04d4bbbcdfbed1e16224d',
],
    'words': 'wolf tiger',
    'nested': {
    'id': 115,
    'rand_digit': 5,
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
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'mouse',
    'number': 10,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,5__',
    'two_words': [
    'leopard',
    'duck',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': None,
},
    {
    'id': 116,
    'id_str': [
    '21',
],
    'text_data': 'e8efa88621f94aa1b7b2441708c75ecf',
    'rand_digit': 5,
    'rand_number': 0.35131,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-14T08:56:05-0100',
    'text_array': [
    'bfc954f46c2d4cfda15d77094831cee2',
    '6daaf5c24c3647f3b3bd3c654fa0c8ee',
],
    'words': 'lizard elephant',
    'nested': {
    'id': 116,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'crab',
    'number': 7,
},
],
},
    'nested_array': [
    [
    0,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'snake',
    'octopus',
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
    'maybe_null': 'mosquito',
},
    {
    'id': 117,
    'id_str': [
    '18',
],
    'text_data': '079a584ec7074f2993a7f1de4f9e2b38',
    'rand_digit': 2,
    'rand_number': 0.24832,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-13T03:43:48.997941+01:00',
    'text_array': [
    'c95d54ace8f04af9a5c9522b8d0ef18c',
    '478e281d98d04051955f9f00f3c7610d',
],
    'words': 'snake bird',
    'nested': {
    'id': 117,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 7,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -2,
],
],
    'two_words': [
    'cheetah',
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
    'rand_bool': True,
    'mixed_type': True,
    'maybe_null': 'bee',
},
    {
    'id': 118,
    'id_str': [
    '05',
],
    'text_data': 'd5ec74772dc94464b6bc4985f2449437',
    'rand_digit': 8,
    'rand_number': 0.40309,
    'rand_signed_int': 9,
    'rand_datetime': '2000-09-12T03:34:02.412197',
    'text_array': [
    '490fa40dc9ee44849244068ac1af9902',
    '18e3c661fa28492c9993c5e4c284d257',
],
    'words': 'cheetah lobster',
    'nested': {
    'id': 118,
    'rand_digit': 5,
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
],
    'word': 'snake',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    [
    9,
],
],
    'two_words': [
    'lion',
    'duck',
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
    'mixed_type': None,
    'maybe_null': 'deer',
},
    {
    'id': 119,
    'id_str': [
    '30',
    '28',
    '17',
],
    'text_data': 'f75a78a7976040a392d83fc26737607e',
    'rand_digit': 4,
    'rand_number': 0.64933,
    'rand_signed_int': -7,
    'rand_datetime': '2000-05-31',
    'text_array': [
    '444b749fb9da4fc2b93c5096d01bfe99',
    'f5e07af68221433b9b0a484193bbc276',
],
    'words': 'sheep butterfly',
    'nested': {
    'id': 119,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'shark',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 7,
},
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
],
    'word': 'ape',
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
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'snail',
    'squid',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'koala',
},
    {
    'id': 120,
    'id_str': [
    '21',
    '02',
],
    'text_data': 'f0a44a2a1ab74f6bab4934e857167bd0',
    'rand_digit': 6,
    'rand_number': 0.35225,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-16 02:26:38.179656',
    'text_array': [
    'fd19fd1f465b493c8c72477e16ccdb33',
    'f3d3b178af354f41bec7297c7c560190',
],
    'words': 'fox pig',
    'nested': {
    'id': 120,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'duck',
    'camel',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'goat',
},
    {
    'id': 121,
    'id_str': [
    '14',
    '02',
    '07',
],
    'text_data': 'adf2d13ee4e047268fa4d1087b220fe3',
    'rand_digit': 9,
    'rand_number': 0.36901,
    'rand_signed_int': 8,
    'rand_datetime': '2000-04-01 11:26',
    'text_array': [
    '80bf9dcd51434d4b8a817d67897b51f3',
    'ad7e031ca0a14a6caf508a8edf9e8cce',
],
    'words': 'zebra rabbit',
    'nested': {
    'id': 121,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'spider',
    'spider',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fox',
    'maybe_null': None,
},
    {
    'id': 122,
    'id_str': [
    '10',
    '22',
    '05',
],
    'text_data': 'a8963cb077ae481dbe799cb4fcfe3c3b',
    'rand_digit': 1,
    'rand_number': 0.49687,
    'rand_signed_int': 2,
    'rand_datetime': '2000-10-20 19:21:07.275336',
    'text_array': [
    'c2b3eb83ea3f4cb0a363ec5da46e13e2',
    'bef84cb571c6402dac073fe86d051178',
],
    'words': 'panda leopard',
    'nested': {
    'id': 122,
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
    'number': 6,
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
],
    'two_words': [
    'spider',
    'scorpion',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'elephant',
},
    {
    'id': 123,
    'id_str': [
    '06',
    '24',
    '07',
    '16',
    '30',
],
    'text_data': '61eba794821a4916bbdc667520344aaa',
    'rand_digit': 5,
    'rand_number': 0.14351,
    'rand_signed_int': -4,
    'rand_datetime': '2000-06-05 01:26:46.609161',
    'text_array': [
    '2eed2d15090d4246a3ad252b4da2e42f',
    '943fbac84fb34eb1ac0adff20e44938a',
],
    'words': 'sheep camel',
    'nested': {
    'id': 123,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    7,
],
],
    'two_words': [
    'snake',
    'elephant',
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
    'mixed_type': 0.15173,
    'maybe': 'leopard',
    'maybe_null': 'cow',
},
    {
    'id': 124,
    'id_str': [
    '18',
],
    'text_data': '2c0e0b8ea97647899f8ef1e59310b19c',
    'rand_digit': 7,
    'rand_number': 0.02533,
    'rand_signed_int': -4,
    'rand_datetime': '2000-12-21',
    'text_array': [
    '814f8c1a9f3e407c9c5839b6be17450d',
    '54cdd0cee3b74a53a327ed19f0d3c6ca',
],
    'words': 'mosquito frog',
    'nested': {
    'id': 124,
    'rand_digit': 8,
    'array': [
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
],
    'word': 'dragonfly',
    'number': 1,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 9,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lion',
    'lizard',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'crab',
},
    {
    'id': 125,
    'id_str': [
],
    'text_data': 'dee935d7e67046df9fdd08b1bceb5816',
    'rand_digit': 4,
    'rand_number': 0.18276,
    'rand_signed_int': 10,
    'rand_datetime': '2000-03-25T01:51:34.702772+06:00',
    'text_array': [
    '3710cf80654047ce99e8d326380429f7',
    'adcc7eed1de74db5a3609326719f06f3',
],
    'words': 'deer dog',
    'nested': {
    'id': 125,
    'rand_digit': 2,
    'array': [
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
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    5,
],
],
    'two_words': [
    'sheep',
    'fly',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'scorpion',
},
    {
    'id': 126,
    'id_str': [
    '12',
    '11',
    '14',
    '05',
    '28',
],
    'text_data': '93de6276e622413d9876b39d33931945',
    'rand_digit': 7,
    'rand_number': 0.93343,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-24T18:11:13.165567',
    'text_array': [
    '49a49b0934094c24b29fafa77497ca5f',
    '20ca05ff36b74dfbbd92e4ee969de709',
],
    'words': 'giraffe rhino',
    'nested': {
    'id': 126,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 9,
},
],
},
    'nested_array': [
    [
    -6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hyena',
    'koala',
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
    'mixed_type': True,
    'maybe': 'bear',
},
    {
    'id': 127,
    'id_str': [
    '03',
    '16',
    '23',
    '22',
],
    'text_data': 'edc486c949f242b784faaafa951d9e9a',
    'rand_digit': 5,
    'rand_number': 0.32194,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-12T23:28:38.603440',
    'text_array': [
    'd1fe6094e75e42adbc7a8d199307d973',
    'c589872a3215464dab481f44a9f380ad',
],
    'words': 'horse tiger',
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
    'word': 'whale',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    3,
],
],
    'two_words': [
    'hippo',
    'koala',
],
    'city': {
    'name': 'Athens',
    'geo': {
    'lat': 37.98381,
    'lon': 23.727539,
},
},
    'rand_tuple': [
    40,
],
    'rand_bool': False,
    'mixed_type': 'lizard',
    'maybe': 'dolphin',
    'maybe_null': 'dog',
},
    {
    'id': 128,
    'id_str': [
    '13',
    '20',
    '25',
],
    'text_data': 'a10073f1902a40b7849659bae075d288',
    'rand_digit': 6,
    'rand_number': 0.46669,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-03 01:31',
    'text_array': [
    'fea0542639aa4792a82eb56c777da7a2',
    '314d6085b6054cf48f4e7d7406506405',
],
    'words': 'chicken cow',
    'nested': {
    'id': 128,
    'rand_digit': 5,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'gorilla',
    'frog',
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
    'mixed_type': 'whale',
    'maybe_null': 'horse',
},
    {
    'id': 129,
    'id_str': [
    '12',
    '25',
    '23',
],
    'text_data': 'd51cbcb9a42344c18d9f2ff45e2f85ca',
    'rand_digit': 8,
    'rand_number': 0.07273,
    'rand_signed_int': 8,
    'rand_datetime': '2000-12-14T14:36:25+0500',
    'text_array': [
    '126c30b140a14be9973f264abead2ab1',
    '699b0bf9268644b382a55c89dcf3f972',
],
    'words': 'hippo snail',
    'nested': {
    'id': 129,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'panda',
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'sloth',
    'shark',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
    {
    'id': 130,
    'id_str': [
    '16',
    '23',
    '02',
],
    'text_data': '21cfd16b6c36471ab8f0c9dfce29cdb4',
    'rand_digit': 6,
    'rand_number': 0.28256,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-28T19:05:31+0100',
    'text_array': [
    '677e69b959854b8fba79c6fa0009931a',
    'c16fd84502ca47c2983039354c07a5df',
],
    'words': 'duck mouse',
    'nested': {
    'id': 130,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lion',
    'number': 8,
},
    {
    'nested_empty': None,
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
],
    'word': 'dog',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fly',
    'camel',
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
    'mixed_type': 0.57645,
    'maybe': 'sheep',
},
    {
    'id': 131,
    'id_str': [
    '16',
],
    'text_data': '7c23080ea14e4c4dbe0233c8d9404c7a',
    'rand_digit': 4,
    'rand_number': 0.52884,
    'rand_signed_int': -7,
    'rand_datetime': '2000-09-19T15:58:35',
    'text_array': [
    '4a6af0887dd6404ba1bd0da0578a4746',
    '8b1183cb672246b69b3033517d78a44c',
],
    'words': 'mosquito lion',
    'nested': {
    'id': 131,
    'rand_digit': 2,
    'array': [
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
    'word': 'snail',
    'number': 6,
},
    {
    'nested_empty': None,
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
    'word': 'sheep',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    [
    -2,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'whale',
    'mouse',
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
    'mixed_type': False,
    'maybe': 'fox',
    'maybe_null': None,
},
    {
    'id': 132,
    'id_str': [
    '11',
    '08',
    '14',
],
    'text_data': '049dfd490401470290ee1547bef966ba',
    'rand_digit': 2,
    'rand_number': 0.09828,
    'rand_signed_int': -3,
    'rand_datetime': '2000-02-24T11:42:51+0000',
    'text_array': [
    '3bb33c3bc9b940948dab833ba8d977c6',
    '8d033c54620647e58f5bf03164a37f23',
],
    'words': 'rhino scorpion',
    'nested': {
    'id': 132,
    'rand_digit': 1,
    'array': [
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
    'word': 'fly',
    'number': 7,
},
    {
    'nested_empty': None,
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
    'word': 'gorilla',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    4,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'koala',
    'snake',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cow',
    'maybe_null': 'giraffe',
},
    {
    'id': 133,
    'id_str': [
    '01',
    '28',
],
    'text_data': 'e91e64ddf1d94bda9574b87597f0531b',
    'rand_digit': 1,
    'rand_number': 0.64105,
    'rand_signed_int': 8,
    'rand_datetime': '2000-08-25',
    'text_array': [
    'ad148b892fed4ac0b416f3b0bc8cbc4c',
    '14b8e53879a840d38f5dcf32052fd836',
],
    'words': 'elephant fox',
    'nested': {
    'id': 133,
    'rand_digit': 0,
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
    'word': 'cheetah',
    'number': 5,
},
],
},
    'nested_array': [
    [
    8,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ladybug',
    'shark',
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
    'mixed_type': False,
},
    {
    'id': 134,
    'id_str': [
    '05',
    '06',
    '27',
],
    'text_data': '3c39b68bd67a4f21a8b0a8198faeacba',
    'rand_digit': 2,
    'rand_number': 0.6614,
    'rand_signed_int': -8,
    'rand_datetime': '2000-04-06 03:40:11',
    'text_array': [
    '381555d5631947ae939bcf404bce033c',
    '83ef20edc01847228ad8dddd73b53179',
],
    'words': 'panda spider',
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
    'word': 'wolf',
    'number': 5,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'bird',
    'octopus',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'frog',
},
    {
    'id': 135,
    'id_str': [
],
    'text_data': 'fd85ba82a9c5449ab7ca549cb7fd21c9',
    'rand_digit': 4,
    'rand_number': 0.47302,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-08T21:13:28-0300',
    'text_array': [
    '7ff81145d2c943128b4cfc94a63cb8c1',
    'b1f36d60da144807bde97e91b215c5c6',
],
    'words': 'sloth lion',
    'nested': {
    'id': 135,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'sloth',
    'dolphin',
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
    'mixed_type': False,
    'maybe': 'crab',
},
    {
    'id': 136,
    'id_str': [
    '02',
    '28',
],
    'text_data': 'a0863a17463b4441bb69af59464c9359',
    'rand_digit': 6,
    'rand_number': 0.63759,
    'rand_signed_int': 8,
    'rand_datetime': '2000-06-16T19:12:27.262020',
    'text_array': [
    'cac86efd5b31473488eed150459629b3',
    '2a6160429ff54355a433ea8e13d27d1d',
],
    'words': 'spider sheep',
    'nested': {
    'id': 136,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 1,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 4,
},
],
},
    'nested_array': [
    [
    -3,
],
    [
],
],
    'two_words': [
    'ant',
    'octopus',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
    {
    'id': 137,
    'id_str': [
    '24',
    '20',
    '19',
    '30',
],
    'text_data': '0a7aa7219e524ffeb28d7d4bb7a1e86a',
    'rand_digit': 7,
    'rand_number': 0.09325,
    'rand_signed_int': -3,
    'rand_datetime': '2000-06-06T19:46:37',
    'text_array': [
    'fb8113c201fb412cbca850259b4f31e2',
    '6df94cb00a4849f98863fae9d28524c6',
],
    'words': 'hyena crab',
    'nested': {
    'id': 137,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'zebra',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'squid',
    'squid',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
},
    {
    'id': 138,
    'id_str': [
    '12',
    '09',
    '28',
    '29',
    '19',
],
    'text_data': '986524f4200d4f24bc0c0e3bcb493aa7',
    'rand_digit': 6,
    'rand_number': 0.78288,
    'rand_signed_int': 3,
    'rand_datetime': '2000-03-31T10:33:18.793387',
    'text_array': [
    '98b508fde1324fefa052c9c879cf0468',
    '1e591f4eaeb24957bf3644ddcfb9ef0f',
],
    'words': 'cheetah monkey',
    'nested': {
    'id': 138,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'fox',
    'pig',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
},
    {
    'id': 139,
    'id_str': [
],
    'text_data': '373dc7f031b44662b7328ad85434cff5',
    'rand_digit': 1,
    'rand_number': 0.1557,
    'rand_signed_int': 10,
    'rand_datetime': '2000-09-02T21:21:59-1200',
    'text_array': [
    '0ec5546b7ae04d1ea8fac27f3259e18b',
    'ad55fae5def44940a3cc20f2a838149b',
],
    'words': 'bear chicken',
    'nested': {
    'id': 139,
    'rand_digit': 3,
    'array': [
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
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'butterfly',
    'lion',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'turtle',
    'maybe_null': None,
},
    {
    'id': 140,
    'id_str': [
    '26',
],
    'text_data': '3688c981ef8f4efba3f5d927cea9eb39',
    'rand_digit': 8,
    'rand_number': 0.55164,
    'rand_signed_int': 5,
    'rand_datetime': '2000-02-14T04:12:42.668906-08:00',
    'text_array': [
    '58ccd03c05624011bb2a214d1644cb19',
    '864f4065183e45618294c0c349089404',
],
    'words': 'hyena snake',
    'nested': {
    'id': 140,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cow',
    'cow',
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
    'mixed_type': 3,
    'maybe_null': None,
},
    {
    'id': 141,
    'id_str': [
    '26',
    '06',
],
    'text_data': '8e2e00cb01994e3aa0c77fbf73f0a1d0',
    'rand_digit': 0,
    'rand_number': 0.3333,
    'rand_signed_int': -7,
    'rand_datetime': '2000-03-19T08:35:30.105267',
    'text_array': [
    '951e7d8fad554b0f92689b8c3a7da826',
    'ffc7317ed6774c80b6855d3bb0837643',
],
    'words': 'turtle crab',
    'nested': {
    'id': 141,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'number': 5,
},
],
},
    'nested_array': [
    [
    8,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'wolf',
    'camel',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 4,
    'maybe': 'shark',
    'maybe_null': 'zebra',
},
    {
    'id': 142,
    'id_str': [
    '17',
    '09',
    '13',
],
    'text_data': 'f3044dcc24ce4093a2e745363de42f2e',
    'rand_digit': 8,
    'rand_number': 0.06032,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-27 04:08',
    'text_array': [
    '4b4c571aabd549fd90471883c06e03e7',
    'f1426aa379034a358e4789052aaa8407',
],
    'words': 'fly cheetah',
    'nested': {
    'id': 142,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'cheetah',
    'panda',
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
    'mixed_type': 3,
    'maybe': 'sheep',
    'maybe_null': 'duck',
},
    {
    'id': 143,
    'id_str': [
    '14',
    '15',
],
    'text_data': '4ed98d0cb4974b338f3f30bcebc1e5eb',
    'rand_digit': 3,
    'rand_number': 0.18965,
    'rand_signed_int': -1,
    'rand_datetime': '2000-02-10',
    'text_array': [
    '2589b97dd8f7449e88eac1071009e4cc',
    '0399611b754c4388992732e2673205dd',
],
    'words': 'rhino bird',
    'nested': {
    'id': 143,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bear',
    'gorilla',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'frog',
    'maybe_null': 'fish',
},
    {
    'id': 144,
    'id_str': [
    '14',
    '29',
    '03',
    '15',
    '08',
],
    'text_data': '5d4cb7ac2a6a460b9c85ce56c3c32d55',
    'rand_digit': 6,
    'rand_number': 0.9471,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-01T21:39:35.053217',
    'text_array': [
    '6655850327134d47a53c11dca264b22b',
    '37644de3f7e54230bb27d1a503ab8e5b',
],
    'words': 'sheep fish',
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
    'number': 9,
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
    'hello',
],
    'word': 'butterfly',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 7,
},
],
},
    'nested_array': [
    [
    -9,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -8,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'monkey',
    'monkey',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
    {
    'id': 145,
    'id_str': [
    '20',
    '19',
    '12',
    '20',
],
    'text_data': '8f933db1255441d58f9738889e41a892',
    'rand_digit': 9,
    'rand_number': 0.82006,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-23',
    'text_array': [
    'b0eb388e840c4053a59901fd9f112146',
    '04dbc6164bff495e971f1c020f36c626',
],
    'words': 'squid bee',
    'nested': {
    'id': 145,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 4,
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
    'ape',
    'snake',
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
    'mixed_type': True,
    'maybe': 'monkey',
    'maybe_null': 'rhino',
},
    {
    'id': 146,
    'id_str': [
    '13',
    '12',
    '11',
],
    'text_data': 'a594ae9811e54d01b74db12514595c83',
    'rand_digit': 1,
    'rand_number': 0.29657,
    'rand_signed_int': 8,
    'rand_datetime': '2000-01-22 19:29:31',
    'text_array': [
    '9560731d65b64d10aff9b99085a54f66',
    'bf17c16306c345b985f63c5f1ed1f5b3',
],
    'words': 'spider bear',
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
    'word': 'frog',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'shark',
    'number': 8,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    3,
],
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
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'kangaroo',
},
    {
    'id': 147,
    'id_str': [
    '19',
    '04',
    '01',
    '12',
    '17',
],
    'text_data': '314c8194a976404eaf1857eb52a5b452',
    'rand_digit': 2,
    'rand_number': 0.36655,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-12T03:35:34.208048',
    'text_array': [
    '35f1544fd24a473c9314dfed03e542df',
    '41c2c57f4e9849cca8423f317217036b',
],
    'words': 'cow snake',
    'nested': {
    'id': 147,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'panda',
    'tiger',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'horse',
},
    {
    'id': 148,
    'id_str': [
    '13',
    '29',
],
    'text_data': '87ad7bf2a9c3403e90be5f4a6596741a',
    'rand_digit': 4,
    'rand_number': 0.61971,
    'rand_signed_int': -8,
    'rand_datetime': '2000-01-06 00:33:11.425604',
    'text_array': [
    'ac52a29302bd43328efb775dca94ff83',
    '725f7672302f45eaafa8bda073941ce5',
],
    'words': 'panda turtle',
    'nested': {
    'id': 148,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'turtle',
    'giraffe',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'hyena',
},
    {
    'id': 149,
    'id_str': [
    '05',
    '23',
    '17',
    '15',
    '13',
],
    'text_data': '402072c747344616a6601ab7d2c25ad9',
    'rand_digit': 6,
    'rand_number': 0.34249,
    'rand_signed_int': 6,
    'rand_datetime': '2000-05-20 02:20:40-0100',
    'text_array': [
    '8a940d0a2a0f422b8847e5af9281ed58',
    'ac17cade63284a6d9b47c65b481b872a',
],
    'words': 'dragonfly lion',
    'nested': {
    'id': 149,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 1,
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
],
    'word': 'wolf',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'spider',
    'whale',
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
    'mixed_type': 'rabbit',
    'maybe': 'squid',
    'maybe_null': None,
},
    {
    'id': 150,
    'id_str': [
    '16',
    '27',
    '12',
    '18',
    '16',
],
    'text_data': '1216f603e6f24488b25269050f65162b',
    'rand_digit': 2,
    'rand_number': 0.24106,
    'rand_signed_int': -8,
    'rand_datetime': '2000-08-12 07:09:44.510770-1100',
    'text_array': [
    '997acf91bce049c684c590a68d1aedc7',
    '8b58cfbf019748ba899c5c914f1fcbf0',
],
    'words': 'bear giraffe',
    'nested': {
    'id': 150,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'goat',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'shark',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'octopus',
    'frog',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': [
    9,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': 'dolphin',
},
    {
    'id': 151,
    'id_str': [
    '10',
    '24',
    '16',
    '12',
],
    'text_data': '1ff5107682a8445cbe77f5e59f9dc8c4',
    'rand_digit': 0,
    'rand_number': 0.27389,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-05 08:44:23.098067',
    'text_array': [
    'dbb298a9b69d47809557d1e0134da485',
    'b627e57a26bf455eb84773c8e30c087c',
],
    'words': 'hyena whale',
    'nested': {
    'id': 151,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'octopus',
    'turtle',
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
    'mixed_type': True,
    'maybe_null': None,
},
    {
    'id': 152,
    'id_str': [
],
    'text_data': '3c2362909b9746d8abb46387ac3b2ca2',
    'rand_digit': 5,
    'rand_number': 0.63774,
    'rand_signed_int': 9,
    'rand_datetime': '2000-07-28T01:25:25.256112',
    'text_array': [
    '3964deb609bd40a28bfadcd2e18485eb',
    '05fd626eb54540689747d11cb516b5e9',
],
    'words': 'elephant kangaroo',
    'nested': {
    'id': 152,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'dolphin',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bird',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'bird',
    'sloth',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'butterfly',
    'maybe_null': 'bear',
},
    {
    'id': 153,
    'id_str': [
    '29',
    '17',
    '22',
    '29',
    '27',
],
    'text_data': 'e435409c8c20433c88ad638fb8d43f17',
    'rand_digit': 0,
    'rand_number': 0.43869,
    'rand_signed_int': 3,
    'rand_datetime': '2000-10-30 16:21:02',
    'text_array': [
    '4e5dbafc4bab46aebdda9eeb65776a49',
    '9681a2e4d18d4b368b9de0906720e9e6',
],
    'words': 'snake dog',
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
    'word': 'chicken',
    'number': 1,
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
    'word': 'snail',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'leopard',
    'hippo',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'horse',
    'maybe_null': None,
},
    {
    'id': 154,
    'id_str': [
    '20',
],
    'text_data': '12ae86ef76244d39a22a79d25153b1c2',
    'rand_digit': 2,
    'rand_number': 0.73768,
    'rand_signed_int': -7,
    'rand_datetime': '2000-07-01',
    'text_array': [
    'c46c102f237742e9b8cde1ae1666c4c3',
    'ef741e529c13412a8823384e48afd646',
],
    'words': 'octopus koala',
    'nested': {
    'id': 154,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 6,
},
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
],
    'word': 'monkey',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'ape',
    'pig',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': None,
},
    {
    'id': 155,
    'id_str': [
    '25',
],
    'text_data': '52516d5c2f054f6ba9861fa9edf03dfa',
    'rand_digit': 0,
    'rand_number': 0.47244,
    'rand_signed_int': -3,
    'rand_datetime': '2000-12-14T03:04:46',
    'text_array': [
    'c19f40f865f24edfb66738e4865fe665',
    '8e3d09d6459f47caacf9b6a962144b81',
],
    'words': 'hyena giraffe',
    'nested': {
    'id': 155,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'scorpion',
    'dragonfly',
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
    'maybe_null': None,
},
    {
    'id': 156,
    'id_str': [
    '28',
    '24',
    '26',
    '26',
],
    'text_data': 'efed0ea5ccdb46b5aed62d63a4b79099',
    'rand_digit': 6,
    'rand_number': 0.6884,
    'rand_signed_int': -6,
    'rand_datetime': '2000-05-25T10:49:22.944110-0100',
    'text_array': [
    'dd2a67cb90e94fd48e0461f96c7d23d9',
    'cdbab0b2626f42f2bdc70a727258983b',
],
    'words': 'scorpion tiger',
    'nested': {
    'id': 156,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
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
    'number': 1,
},
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
    'sloth',
    'shark',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.57397,
    'maybe': 'grasshopper',
    'maybe_null': 'fish',
},
    {
    'id': 157,
    'id_str': [
    '17',
],
    'text_data': '2f50359ae49d4b9f97f1eeb72016054e',
    'rand_digit': 7,
    'rand_number': 0.86961,
    'rand_signed_int': -2,
    'rand_datetime': '2000-12-18T05:15:06.975386+08:00',
    'text_array': [
    '371e928c66014f979cc7bd73ccf3eb80',
    '38c0302374e5438ebf3121d3df641ec0',
],
    'words': 'mouse cheetah',
    'nested': {
    'id': 157,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 1,
},
    {
    'nested_empty': None,
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
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'grasshopper',
    'fish',
],
    'city': {
    'name': 'Copenhagen',
    'geo': {
    'lat': 55.676097,
    'lon': 12.568337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'chicken',
},
    {
    'id': 158,
    'id_str': [
    '17',
    '03',
    '18',
    '29',
    '02',
],
    'text_data': 'f3825ec27c5c4742b6aabfe79a643b59',
    'rand_digit': 8,
    'rand_number': 0.46331,
    'rand_signed_int': -7,
    'rand_datetime': '2000-04-30T16:12:21.514797+1100',
    'text_array': [
    '0c65af8cc8b34937ae5e4840a1236561',
    'e43511297cac4b4f8372721157a41045',
],
    'words': 'whale ant',
    'nested': {
    'id': 158,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'cat',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'zebra',
    'fish',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': [
    83,
],
    'rand_bool': False,
    'mixed_type': 5,
    'maybe': 'goat',
},
    {
    'id': 159,
    'id_str': [
    '06',
    '29',
    '16',
],
    'text_data': 'f02a8098159d4cada5ea9ba5ea04d5a4',
    'rand_digit': 8,
    'rand_number': 0.89922,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-24 19:37:00.817437',
    'text_array': [
    '36b276dc5e3f4f71b934d6f96663a31c',
    'b0248117694f4469b89b7958356d9b12',
],
    'words': 'mouse ant',
    'nested': {
    'id': 159,
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
    'word': 'bear',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -6,
],
    [
],
],
    'two_words': [
    'hyena',
    'cat',
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
    'maybe': 'chicken',
    'maybe_null': 'ladybug',
},
    {
    'id': 160,
    'id_str': [
    '11',
    '03',
    '30',
    '05',
    '27',
],
    'text_data': 'cafe65198df4428aba41ba47de371359',
    'rand_digit': 0,
    'rand_number': 0.36874,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-03 11:31',
    'text_array': [
    'c9a64aa7ab5a4785a3cf4015e73a81da',
    '2489b1499116409bb16a9265d5aeafcf',
],
    'words': 'wolf rabbit',
    'nested': {
    'id': 160,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'lion',
    'grasshopper',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
    {
    'id': 161,
    'id_str': [
],
    'text_data': '7a0befdf305940f8a4cc62baf650902d',
    'rand_digit': 1,
    'rand_number': 0.87534,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-24 22:45:16-0500',
    'text_array': [
    'e5b8cfd1a23e45da94e916f41975642c',
    '4ee7c762b37341aa95fa9caae5570b02',
],
    'words': 'ant zebra',
    'nested': {
    'id': 161,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 10,
},
],
},
    'nested_array': [
    [
    5,
],
    [
    3,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'crab',
    'shark',
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
    'mixed_type': 1,
    'maybe_null': None,
},
    {
    'id': 162,
    'id_str': [
],
    'text_data': '9d6a4a3a448c469aab635105574cb541',
    'rand_digit': 9,
    'rand_number': 0.54774,
    'rand_signed_int': -1,
    'rand_datetime': '2000-01-07T04:45:10-1000',
    'text_array': [
    '962dc03ae1754b12999535c320eae628',
    '02b3586b3c2a41f4b46505dc030e5f28',
],
    'words': 'lobster snake',
    'nested': {
    'id': 162,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dolphin',
    'fox',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': [
    32,
],
    'rand_bool': False,
    'mixed_type': 'camel',
    'maybe': 'fox',
    'maybe_null': 'cow',
},
    {
    'id': 163,
    'id_str': [
    '24',
    '04',
],
    'text_data': '7fb7a1ec64ea431eb82623d52c287893',
    'rand_digit': 4,
    'rand_number': 0.27578,
    'rand_signed_int': -7,
    'rand_datetime': '2001-01-16 18:45:23',
    'text_array': [
    'f6c1a5c7c6ad4121838c9ec36d99a32b',
    '4f2f4fe52da541c88174bc95a5839a03',
],
    'words': 'hyena dragonfly',
    'nested': {
    'id': 163,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'ant',
    'wolf',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': None,
},
    {
    'id': 164,
    'id_str': [
    '18',
    '23',
],
    'text_data': '7beb50aa86374e42849a8c855c398fab',
    'rand_digit': 8,
    'rand_number': 0.90178,
    'rand_signed_int': -10,
    'rand_datetime': '2000-09-28',
    'text_array': [
    '2eb9e4e7cfd049aa9de8d68e7710be82',
    'e858e1c047b74b479a0622f8c881d67f',
],
    'words': 'cow monkey',
    'nested': {
    'id': 164,
    'rand_digit': 3,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
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
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 6,
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'leopard',
    'ape',
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
    'mixed_type': False,
    'maybe': 'fish',
    'maybe_null': None,
},
    {
    'id': 165,
    'id_str': [
],
    'text_data': '70e374af331c42329fc6df4dcdf99385',
    'rand_digit': 2,
    'rand_number': 0.90622,
    'rand_signed_int': -3,
    'rand_datetime': '2000-05-02 05:42:33.498467-0700',
    'text_array': [
    '276de6d6528143debfd4134446aa0586',
    'cd1548706fdc4fc49f34750915095b64',
],
    'words': 'hippo elephant',
    'nested': {
    'id': 165,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'bee',
    'zebra',
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
    'mixed_type': 'lion',
    'maybe_null': None,
},
    {
    'id': 166,
    'id_str': [
    '17',
],
    'text_data': 'bf88de8c1cc14094b84837e2bfde674a',
    'rand_digit': 1,
    'rand_number': 0.5156,
    'rand_signed_int': 8,
    'rand_datetime': '2000-04-26 16:54:18.656219-1200',
    'text_array': [
    'b15eeed74f704599a8c06b41c44b58a1',
    'b80bbb5779dc439c994986577c747dd8',
],
    'words': 'sloth shark',
    'nested': {
    'id': 166,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 6,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    3,
],
],
    'two_words': [
    'lobster',
    'cat',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 'sheep',
    'maybe': 'cheetah',
    'maybe_null': 'butterfly',
},
    {
    'id': 167,
    'id_str': [
    '19',
    '13',
    '03',
    '23',
],
    'text_data': 'baf8ea21fff34de6afd9127f4869e16d',
    'rand_digit': 4,
    'rand_number': 0.86165,
    'rand_signed_int': -3,
    'rand_datetime': '2000-05-11T00:17:13.144717-0400',
    'text_array': [
    '1b04bb4e1a174a9ebdb1db66bb010683',
    'ce3f443e1878412fa4eda7e5d39b1414',
],
    'words': 'zebra whale',
    'nested': {
    'id': 167,
    'rand_digit': 8,
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
],
    'word': 'lobster',
    'number': 9,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    5,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'butterfly',
    'sheep',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 1,
    'maybe_null': 'spider',
},
    {
    'id': 168,
    'id_str': [
    '20',
],
    'text_data': 'f4954aefc6c14697a87fff7c4f40affb',
    'rand_digit': 3,
    'rand_number': 0.2338,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-07T05:41:04.235002',
    'text_array': [
    '8baf8ee18b9a49f1b87d0f5d2c954fa0',
    '9ed983761cd544c6a1546487fe4e8480',
],
    'words': 'fish lobster',
    'nested': {
    'id': 168,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'jaguar',
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
    'number': 7,
},
],
},
    'nested_array': [
    [
    -9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lizard',
    'horse',
],
    'city': {
    'name': 'Riga',
    'geo': {
    'lat': 56.949649,
    'lon': 24.105186,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 'chicken',
    'maybe_null': 'koala',
},
    {
    'id': 169,
    'id_str': [
    '15',
    '16',
],
    'text_data': '65fada4dec704712909426c38ec6f4a5',
    'rand_digit': 0,
    'rand_number': 0.93841,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-14T19:05:21',
    'text_array': [
    'e40bf09d9faa4082ad30c7a23e37c672',
    'ec00d2f16c4e4067851f1ea54359aa22',
],
    'words': 'bear fish',
    'nested': {
    'id': 169,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'hyena',
    'number': 2,
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
    'hello',
],
    'word': 'mouse',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'wolf',
    'monkey',
],
    'city': {
    'name': 'Moscow',
    'geo': {
    'lat': 55.755826,
    'lon': 37.6173,
},
},
    'rand_tuple': [
    64,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'cheetah',
    'maybe_null': None,
},
    {
    'id': 170,
    'id_str': [
    '20',
    '28',
    '07',
],
    'text_data': '811e14d6cb5d4fc080339a3f7b401f68',
    'rand_digit': 8,
    'rand_number': 0.17172,
    'rand_signed_int': -2,
    'rand_datetime': '2001-01-03 18:15:00.859750',
    'text_array': [
    '6a605fea558a41329867adb2393b3099',
    '608b36604df24c61b4b56fa8d8f77277',
],
    'words': 'squid rabbit',
    'nested': {
    'id': 170,
    'rand_digit': 3,
    'array': [
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
    'hello',
],
    'word': 'mouse',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'spider',
    'turtle',
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
    'maybe': 'ladybug',
},
    {
    'id': 171,
    'id_str': [
    '02',
    '12',
    '05',
    '03',
    '30',
],
    'text_data': 'c4b04d6dd0f84f29b50a91d9d59d1ba2',
    'rand_digit': 4,
    'rand_number': 0.95439,
    'rand_signed_int': 4,
    'rand_datetime': '2000-07-27T18:50:07.844519',
    'text_array': [
    '90d9188489be4404a48357412d595ea0',
    'fa182e74f9e042e2910ab444612fc019',
],
    'words': 'ant grasshopper',
    'nested': {
    'id': 171,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dragonfly',
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
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'cheetah',
    'hyena',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 2,
    'maybe_null': 'horse',
},
    {
    'id': 172,
    'id_str': [
    '27',
    '09',
    '24',
    '03',
],
    'text_data': 'd63cd3b327404dc9ba4a157fee59d191',
    'rand_digit': 6,
    'rand_number': 0.29454,
    'rand_signed_int': -6,
    'rand_datetime': '2000-07-06T00:06:27.708602',
    'text_array': [
    '24db4bb851ac41c9be55634969cd5793',
    'f25f961dd8d8419096783e91683910bd',
],
    'words': 'cheetah deer',
    'nested': {
    'id': 172,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 5,
},
    {
    'nested_empty': None,
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
    'word': 'dragonfly',
    'number': 2,
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
    'sheep',
    'cheetah',
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
    'mixed_type': False,
    'maybe': 'rhino',
},
    {
    'id': 173,
    'id_str': [
    '11',
    '13',
    '01',
    '30',
    '22',
],
    'text_data': '8e8d072d719e42a49ba3a426f78bd83d',
    'rand_digit': 3,
    'rand_number': 0.65101,
    'rand_signed_int': 3,
    'rand_datetime': '2000-05-31 13:03:48',
    'text_array': [
    '9fadcf760774405483862d53372bdb08',
    '5bfe5df6ca8a4eef8e7426b25e0e5129',
],
    'words': 'spider deer',
    'nested': {
    'id': 173,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 1,
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
    'hello',
],
    'word': 'shark',
    'number': 10,
},
    {
    'nested_empty': None,
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
],
    'word': 'wolf',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -8,
],
    [
    -1,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hippo',
    'cat',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'spider',
},
    {
    'id': 174,
    'id_str': [
    '25',
    '19',
    '30',
],
    'text_data': 'd7f1350bb60345d28005d528621130b9',
    'rand_digit': 2,
    'rand_number': 0.55578,
    'rand_signed_int': 9,
    'rand_datetime': '2000-03-09 11:30:45.793104',
    'text_array': [
    '84ead8fbddb24206a361e7922097e97f',
    'b7e4e708383e44ce90d87484e58f89e0',
],
    'words': 'ladybug dolphin',
    'nested': {
    'id': 174,
    'rand_digit': 9,
    'array': [
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
],
    'word': 'camel',
    'number': 7,
},
    {
    'nested_empty': None,
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
    'word': 'dolphin',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'butterfly',
    'hippo',
],
    'city': {
    'name': 'Riga',
    'geo': {
    'lat': 56.949649,
    'lon': 24.105186,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'leopard',
},
    {
    'id': 175,
    'id_str': [
],
    'text_data': 'f3bfb84f2b6e4d27bc756ff686a17077',
    'rand_digit': 5,
    'rand_number': 0.24677,
    'rand_signed_int': -8,
    'rand_datetime': '2000-05-30T16:50:54.582164',
    'text_array': [
    'ed3115f51708476eb63c24bdf1a19fca',
    'aa572b7dffa24dc48c7e033ee94deba3',
],
    'words': 'cow goat',
    'nested': {
    'id': 175,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    1,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'duck',
    'spider',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
    {
    'id': 176,
    'id_str': [
    '15',
    '21',
    '22',
],
    'text_data': '45cca70185324e4b81e5ab3bab985ed5',
    'rand_digit': 4,
    'rand_number': 0.1009,
    'rand_signed_int': -10,
    'rand_datetime': '2000-05-25T03:20:14.277807',
    'text_array': [
    '01d0e41c06c141fd93dc69f2dd15d58c',
    '68aa565df1b749d596fa78a72a45ab6c',
],
    'words': 'mosquito chicken',
    'nested': {
    'id': 176,
    'rand_digit': 8,
    'array': [
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
],
    'word': 'dog',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cat',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'shark',
    'dragonfly',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'horse',
},
    {
    'id': 177,
    'id_str': [
],
    'text_data': 'a66ee5b6635546d0914579009d0e1825',
    'rand_digit': 6,
    'rand_number': 0.07968,
    'rand_signed_int': 3,
    'rand_datetime': '2000-07-31 01:21:25-1000',
    'text_array': [
    '829eef5c2e854677bed3f086a7fad746',
    '1e501eb351944e9686382ffc25d002ba',
],
    'words': 'hippo bear',
    'nested': {
    'id': 177,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'rabbit',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'gorilla',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'octopus',
    'maybe_null': 'camel',
},
    {
    'id': 178,
    'id_str': [
    '02',
],
    'text_data': 'f255b79ca1334c9bb6c0e20a00f0f95a',
    'rand_digit': 2,
    'rand_number': 0.61677,
    'rand_signed_int': 0,
    'rand_datetime': '2000-06-25 13:10',
    'text_array': [
    '732d6fe0ccf34117ba0556b41db67213',
    'cc5a52deedb74a3fac6180325afa3477',
],
    'words': 'ladybug lion',
    'nested': {
    'id': 178,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'panda',
    'number': 3,
},
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
    'hello',
],
    'word': 'goat',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lobster',
    'mouse',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': [
    93,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': 'shark',
},
    {
    'id': 179,
    'id_str': [
],
    'text_data': 'aa3dc21ba71e4cbcb938a0cdcfeda5e0',
    'rand_digit': 7,
    'rand_number': 0.57561,
    'rand_signed_int': 7,
    'rand_datetime': '2000-07-29T11:00:14.848902',
    'text_array': [
    '9ae9594cd13b4b9bae9e14c10b52d64b',
    '744d3e5caa7046eaa2d6bab4f30a3a6c',
],
    'words': 'bear camel',
    'nested': {
    'id': 179,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 7,
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
    'word': 'giraffe',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'squid',
    'wolf',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': [
    86,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'rabbit',
    'maybe_null': 'mosquito',
},
    {
    'id': 180,
    'id_str': [
    '04',
],
    'text_data': '70d98fc3971d44e8a2d6840a04ff5dc9',
    'rand_digit': 2,
    'rand_number': 0.69351,
    'rand_signed_int': -3,
    'rand_datetime': '2000-02-27T20:53:59.859632',
    'text_array': [
    '1487a66ec6ae404290995520d9403445',
    '3f0f555f8547409ead694eb61baaf5c0',
],
    'words': 'grasshopper fox',
    'nested': {
    'id': 180,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 3,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fish',
    'spider',
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
    'mixed_type': None,
    'maybe': 'cat',
    'maybe_null': 'elephant',
},
    {
    'id': 181,
    'id_str': [
    '01',
],
    'text_data': '7344aa2862c54cac8cb3ad1ff6ef583c',
    'rand_digit': 6,
    'rand_number': 0.30112,
    'rand_signed_int': -4,
    'rand_datetime': '2000-08-04T05:54:14.293861',
    'text_array': [
    '5a7389e1ce06402e86d3d6126178c098',
    'e728be1c1699409ea43bb40fa459b599',
],
    'words': 'gorilla horse',
    'nested': {
    'id': 181,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 1,
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
    'word': 'octopus',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'snake',
    'squid',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': None,
},
    {
    'id': 182,
    'id_str': [
    '28',
    '12',
    '02',
],
    'text_data': 'c986d430a99e4fe991c6b0ce72625d98',
    'rand_digit': 2,
    'rand_number': 0.25124,
    'rand_signed_int': -8,
    'rand_datetime': '2000-07-05T03:08:19+0700',
    'text_array': [
    '188a0fdac17e4a5093ac102eb5891a8e',
    'a8ab4b10a3c34141ae2c5c58e59e0779',
],
    'words': 'ant hyena',
    'nested': {
    'id': 182,
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
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 1,
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
    'rand_tuple': [
    71,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'deer',
},
    {
    'id': 183,
    'id_str': [
    '01',
    '14',
    '06',
    '09',
],
    'text_data': '001e23ba942846ab914e5eb5a417472c',
    'rand_digit': 5,
    'rand_number': 0.97501,
    'rand_signed_int': 8,
    'rand_datetime': '2000-07-07T18:35:52',
    'text_array': [
    '3be9389bbcd849dcba4a78d90303b4d2',
    '7bf4591c3e664d6e9984f77ac2177f5e',
],
    'words': 'wolf horse',
    'nested': {
    'id': 183,
    'rand_digit': 9,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    4,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'panda',
    'dragonfly',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': [
    38,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'sloth',
},
    {
    'id': 184,
    'id_str': [
    '14',
    '23',
    '09',
],
    'text_data': 'd9d61842e2d84de6b59bfc3ef36e5160',
    'rand_digit': 6,
    'rand_number': 0.93285,
    'rand_signed_int': 5,
    'rand_datetime': '2000-11-28',
    'text_array': [
    '114aec581c8d4c0a9889187f799005c6',
    '6d39cb4cc6bf491e969375ce9794becf',
],
    'words': 'deer dolphin',
    'nested': {
    'id': 184,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'horse',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 4,
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
    [
    -9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'spider',
    'panda',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'leopard',
    'maybe_null': None,
},
    {
    'id': 185,
    'id_str': [
    '20',
    '21',
    '04',
    '19',
    '07',
],
    'text_data': '48ba334d225a484e83a8985a1d63d1bf',
    'rand_digit': 4,
    'rand_number': 0.45443,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-23T09:00:11.951387',
    'text_array': [
    '6644f91bb4f9491a913eb53c4af632b4',
    'b4099e2530274b67b308d64aaaddfd52',
],
    'words': 'hyena wolf',
    'nested': {
    'id': 185,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'sheep',
    'hyena',
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
    'mixed_type': 0.47425,
    'maybe_null': 'ladybug',
},
    {
    'id': 186,
    'id_str': [
    '08',
    '18',
],
    'text_data': '7d08c9720a8d4c13a48d192447737672',
    'rand_digit': 8,
    'rand_number': 0.6533,
    'rand_signed_int': -9,
    'rand_datetime': '2000-11-05T21:33:54.643772-1000',
    'text_array': [
    '27c963600d144df787f1c40c616c6fb5',
    '35bdc8a5770e453eb2759387ce463aa7',
],
    'words': 'octopus octopus',
    'nested': {
    'id': 186,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'pig',
    'deer',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'squid',
    'maybe_null': 'lizard',
},
    {
    'id': 187,
    'id_str': [
],
    'text_data': 'da4cf5d540b64a6ea1eb2e145807d388',
    'rand_digit': 7,
    'rand_number': 0.77406,
    'rand_signed_int': -6,
    'rand_datetime': '2000-01-30 06:51',
    'text_array': [
    '0c0baf2b533d4625808db905ec4b8ac8',
    '421ad2bfd11e4eabbb7c78ab4a0a89bb',
],
    'words': 'octopus dog',
    'nested': {
    'id': 187,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'goat',
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
    'frog',
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
    'mixed_type': 'hippo',
    'maybe': 'ape',
},
    {
    'id': 188,
    'id_str': [
],
    'text_data': '0fa9f1287b9040e784d14ca0e1d7eec3',
    'rand_digit': 1,
    'rand_number': 0.20414,
    'rand_signed_int': -3,
    'rand_datetime': '2000-12-16T17:31:48',
    'text_array': [
    '1ff1e18d030f49f0850cce2d68d99272',
    '8c95a8e267444fc0955fb2d6e6c06a4a',
],
    'words': 'spider zebra',
    'nested': {
    'id': 188,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    10,
],
],
    'two_words': [
    'crab',
    'monkey',
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
    'mixed_type': None,
    'maybe_null': 'sheep',
},
    {
    'id': 189,
    'id_str': [
    '06',
    '20',
    '08',
    '01',
    '30',
],
    'text_data': '585252a94217445a8dc9dff5125a3b50',
    'rand_digit': 6,
    'rand_number': 0.18581,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-30T11:16:47.651431',
    'text_array': [
    '95c4efe8d7c448caa18b253aaf8fc09e',
    'fb6e2613b83b48ef8754a6245d7593dd',
],
    'words': 'horse sloth',
    'nested': {
    'id': 189,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cat',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fish',
    'mosquito',
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
    'mixed_type': 0.27661,
    'maybe': 'sloth',
    'maybe_null': None,
},
    {
    'id': 190,
    'id_str': [
    '10',
    '01',
    '23',
    '28',
    '06',
],
    'text_data': '9e30bd242fb4487d80613ec96f24cddf',
    'rand_digit': 3,
    'rand_number': 0.29018,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-30T22:18:54-0100',
    'text_array': [
    '2f1b7e96a894495980bbfc3b59855e44',
    'bbb1b5b9302842d8a1eb9580c32b6d81',
],
    'words': 'spider ladybug',
    'nested': {
    'id': 190,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 1,
},
],
},
    'nested_array': [
    [
    -5,
],
    [
    -3,
],
    [
    -1,
],
],
    'two_words': [
    'leopard',
    'rhino',
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
    'mixed_type': False,
    'maybe': 'dolphin',
},
    {
    'id': 191,
    'id_str': [
    '09',
],
    'text_data': '87077509643641ec984330719ed17fcd',
    'rand_digit': 0,
    'rand_number': 0.17842,
    'rand_signed_int': 2,
    'rand_datetime': '2000-04-13T12:13:05.068546-0800',
    'text_array': [
    '9389223486124fe296a6b05ebc4b200e',
    'd63294ecfb7c40eda6df5fca385dc5fd',
],
    'words': 'tiger rabbit',
    'nested': {
    'id': 191,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'camel',
    'ant',
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
    'maybe_null': 'chicken',
},
    {
    'id': 192,
    'id_str': [
    '16',
    '10',
    '15',
    '17',
],
    'text_data': 'd6ad070569074fa8b2ffaa9970f4fff9',
    'rand_digit': 8,
    'rand_number': 0.43357,
    'rand_signed_int': 5,
    'rand_datetime': '2000-06-02 22:32',
    'text_array': [
    '26eefaa0554d44e79580690440d06752',
    '3c148454e62e4992bfb69ef8c54defc4',
],
    'words': 'ladybug pig',
    'nested': {
    'id': 192,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'elephant',
    'number': 10,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -6,
],
],
    'two_words': [
    'monkey',
    'koala',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'cat',
    'maybe_null': 'bee',
},
    {
    'id': 193,
    'id_str': [
    '24',
    '13',
    '20',
],
    'text_data': 'ef03d2e12ad24a708471d8ee4be6855a',
    'rand_digit': 2,
    'rand_number': 0.63588,
    'rand_signed_int': -2,
    'rand_datetime': '2001-01-16T21:28:44.457180-1000',
    'text_array': [
    '8c73146c711547f5ac8e4e385ab3742c',
    '87f5ea777c6540aba9865e543b517fb8',
],
    'words': 'dog octopus',
    'nested': {
    'id': 193,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
],
    [
    -4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dolphin',
    'fly',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': [
    8,
],
    'rand_bool': False,
    'mixed_type': 0,
    'maybe_null': 'mouse',
},
    {
    'id': 194,
    'id_str': [
    '22',
    '15',
    '25',
    '23',
    '06',
],
    'text_data': 'd46692f53cd74b78b2a4883ac36ab2df',
    'rand_digit': 7,
    'rand_number': 0.89698,
    'rand_signed_int': -4,
    'rand_datetime': '2000-07-17T13:25:19.978390',
    'text_array': [
    '81ab47ba3177411181a23a2548309473',
    '98fcb6c69cba432c8c1c13ec04abf4a3',
],
    'words': 'spider duck',
    'nested': {
    'id': 194,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
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
    'pig',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'butterfly',
    'maybe_null': None,
},
    {
    'id': 195,
    'id_str': [
],
    'text_data': '6ee75ca310d448ecabdbaa78034b460d',
    'rand_digit': 2,
    'rand_number': 0.78452,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-05 18:25:34.742413+1200',
    'text_array': [
    '29617aafeeb842538526556fc89c7510',
    '4806df483ed84550bf299576858b9ac4',
],
    'words': 'mosquito squid',
    'nested': {
    'id': 195,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'cow',
    'goat',
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
},
    {
    'id': 196,
    'id_str': [
    '12',
    '18',
    '21',
    '23',
],
    'text_data': '1e5229c897b84fa8b396917eb260362b',
    'rand_digit': 5,
    'rand_number': 0.86797,
    'rand_signed_int': -7,
    'rand_datetime': '2000-06-30T11:14:51.426063+07:00',
    'text_array': [
    'f47dfa80e79b49868fa323ce07634d32',
    'b07fc8f18bbe4bc5894b9b6067af4bdf',
],
    'words': 'bee monkey',
    'nested': {
    'id': 196,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 3,
},
    {
    'nested_empty': None,
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
    'word': 'monkey',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'fly',
    'whale',
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
    'mixed_type': 'bee',
    'maybe_null': 'lion',
},
    {
    'id': 197,
    'id_str': [
    '04',
],
    'text_data': '6c78fa2cf13249d2a62713f48ad1a3ec',
    'rand_digit': 8,
    'rand_number': 0.47743,
    'rand_signed_int': 1,
    'rand_datetime': '2000-03-03T07:23:25.043149+0200',
    'text_array': [
    '680dfcbb08c44f14b9fbc92649a369e3',
    '0393ce9da95144e6a6a06ad262f8f6b2',
],
    'words': 'fly snail',
    'nested': {
    'id': 197,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ladybug',
    'deer',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': [
    31,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'bear',
    'maybe_null': 'squid',
},
    {
    'id': 198,
    'id_str': [
    '02',
],
    'text_data': '13c9f93eb1b441ae8683f7bccbd862c0',
    'rand_digit': 0,
    'rand_number': 0.72168,
    'rand_signed_int': 7,
    'rand_datetime': '2000-04-23T07:06:51.064428-05:00',
    'text_array': [
    '37b296dd27594fa1bfe6b8838dd1eda1',
    '70d7a2c0cf444ebf97574cf714475bfa',
],
    'words': 'fly snail',
    'nested': {
    'id': 198,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 8,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'mouse',
    'goat',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': [
    2,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'whale',
},
    {
    'id': 199,
    'id_str': [
    '11',
    '15',
    '29',
    '27',
],
    'text_data': 'e9b8b947f144465f8035e6f82e0f2e63',
    'rand_digit': 7,
    'rand_number': 0.58518,
    'rand_signed_int': 2,
    'rand_datetime': '2000-09-26',
    'text_array': [
    '21c2586b39b146238a78ddba2a9d14a3',
    '2f88f6efbc084e158b141763ad074db5',
],
    'words': 'ape frog',
    'nested': {
    'id': 199,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'hyena',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cow',
    'snake',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': [
    80,
],
    'rand_bool': False,
    'mixed_type': 6,
    'maybe_null': None,
},
],
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
        """测试请求 3 - POST http://localhost:6333/collections/congruence_test_collection/points/scroll"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/scroll")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/scroll'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '52',
}
        
        # 原始请求内容
        original_content = {
    'limit': 200,
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



    def test_request_4(self):
        """测试请求 4 - DELETE http://localhost:6333/collections/congruence_test_collection?timeout=60"""
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
    'content-length': '200',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_sparse_updates.test_upload_uuid_in_batches')
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
    test = TestSparseUpdatestestUploadUuidInBatches()
    test.run_tests()
