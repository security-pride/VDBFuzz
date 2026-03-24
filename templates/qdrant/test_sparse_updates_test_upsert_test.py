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
logger = logging.getLogger('vdb_fuzzer.test.test_sparse_updates_test_upsert')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_sparse_updates.test_upsert"
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



class TestSparseUpdatestestUpsert:
    """自动生成的VDB模糊测试类 - test_sparse_updates.test_upsert"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_sparse_updates.test_upsert"
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
    'content-length': '2000442',
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
    '10',
    '15',
    '14',
    '10',
    '20',
],
    'text_data': 'dbcd68d5d5184cf79797a166a9f5320d',
    'rand_digit': 3,
    'rand_number': 0.55551,
    'rand_signed_int': -5,
    'rand_datetime': '2000-07-30 01:52:21.211964',
    'text_array': [
    '38e721ee08d94839a045d51cf1f47295',
    '0e2ae7af95d949769fa68ba31ba6f2cf',
],
    'words': 'bird goat',
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
    'word': 'hyena',
    'number': 6,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'snail',
    'lizard',
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
    'mixed_type': 'koala',
    'maybe': 'hippo',
    'maybe_null': 'bear',
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
    '25',
    '28',
],
    'text_data': '5e3a4db036a649f58c9836e3d2b7a89e',
    'rand_digit': 6,
    'rand_number': 0.5769,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-28',
    'text_array': [
    '8d78cacb201a461ea0e19171fc008c84',
    '529541153a3a42d7a6fe1147cfd2d41a',
],
    'words': 'butterfly giraffe',
    'nested': {
    'id': 101,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
    6,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ape',
    'bear',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'octopus',
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
    '10',
    '17',
    '12',
],
    'text_data': '14e37ad126bf47d489ee58c996ef8701',
    'rand_digit': 9,
    'rand_number': 0.88101,
    'rand_signed_int': -8,
    'rand_datetime': '2000-10-04T04:32:45-0200',
    'text_array': [
    'b028f6022c8e44f0aa246e3dfc29107b',
    'aedc91ba7c9f4e298246bc6796bb4927',
],
    'words': 'mosquito mosquito',
    'nested': {
    'id': 102,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'duck',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'koala',
    'spider',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
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
    '06',
    '15',
    '08',
    '23',
],
    'text_data': '1d10af521a92405c9b8da65fd943bdc6',
    'rand_digit': 8,
    'rand_number': 0.93312,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-20 04:13:47.943670-1200',
    'text_array': [
    'c4e8153303134451bbbf36a581b35649',
    'b9747a7d5fc949999708d2d30edab3f4',
],
    'words': 'rhino lizard',
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
    'word': 'giraffe',
    'number': 6,
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
    9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fox',
    'snake',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'gorilla',
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
    '25',
    '29',
],
    'text_data': '3d8b04f48aa14f24979f9fff2b30e558',
    'rand_digit': 6,
    'rand_number': 0.84658,
    'rand_signed_int': 9,
    'rand_datetime': '2000-02-24',
    'text_array': [
    'd7f8835b2b304c8e88a49f505e84ab82',
    'b7c71f877f22474196b1f1dfaa6ec9f9',
],
    'words': 'snake sheep',
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
    'word': 'leopard',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 3,
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
    'cheetah',
    'cat',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'zebra',
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
    '19',
    '03',
],
    'text_data': '57156df6cb5c43688c1a642c879f0d3a',
    'rand_digit': 2,
    'rand_number': 0.50545,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-16T18:28:45.400479+09:00',
    'text_array': [
    '458032cb2d684356ae40084ecefdc2f8',
    '19a9563774444673b799f6d024b3f705',
],
    'words': 'chicken spider',
    'nested': {
    'id': 105,
    'rand_digit': 4,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 2,
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
    'word': 'camel',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
    2,
],
],
    'two_words': [
    'duck',
    'chicken',
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
    'mixed_type': None,
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
    '21',
],
    'text_data': '7b123b9e1d4443b097326da368fddfd4',
    'rand_digit': 0,
    'rand_number': 0.04129,
    'rand_signed_int': -5,
    'rand_datetime': '2000-01-10 05:44:52.562966+0100',
    'text_array': [
    '3a4b4e1e9d7f4d47bcbbf49974ccaee7',
    '3c8b336444c144e1ac0173cd6cdb79a8',
],
    'words': 'bee rabbit',
    'nested': {
    'id': 106,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    10,
],
],
    'two_words': [
    'turtle',
    'turtle',
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
    'mixed_type': 0,
    'maybe': 'octopus',
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
    '16',
    '10',
],
    'text_data': '5fa50b9bc7934aee96a6049f101225a5',
    'rand_digit': 7,
    'rand_number': 0.37869,
    'rand_signed_int': -1,
    'rand_datetime': '2000-05-29T18:10:39.304939',
    'text_array': [
    '860cebf2a1fa4f7aaec48936332f3478',
    '9924a1ea1cf345fb9cdf184fcab61bea',
],
    'words': 'lizard grasshopper',
    'nested': {
    'id': 107,
    'rand_digit': 5,
    'array': [
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
    'word': 'cow',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 9,
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
    'zebra',
    'butterfly',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': [
    55,
],
    'rand_bool': True,
    'mixed_type': 'butterfly',
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
    '30',
    '10',
    '18',
    '05',
    '07',
],
    'text_data': 'f05d9ad2f09a493eab70dc5c187545cf',
    'rand_digit': 9,
    'rand_number': 0.79995,
    'rand_signed_int': -2,
    'rand_datetime': '2000-06-20T19:33:55.508242',
    'text_array': [
    'ab03d4e8f24d4247826ccbb2c37e1519',
    '714958f29f324feb8e5251098d639826',
],
    'words': 'rabbit mosquito',
    'nested': {
    'id': 108,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'deer',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'crab',
    'monkey',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'grasshopper',
    'maybe_null': None,
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
    '29',
    '19',
    '03',
    '07',
],
    'text_data': '86cb4ec7f7eb4bca98b0c3e16d4cd8b2',
    'rand_digit': 1,
    'rand_number': 0.38173,
    'rand_signed_int': -5,
    'rand_datetime': '2001-01-05T14:23:59.193398+04:00',
    'text_array': [
    '98567d8cd8c44755b18a4bf00d9022fc',
    '268b998109ed42dcbbb6c08d061e180d',
],
    'words': 'lobster fly',
    'nested': {
    'id': 109,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'spider',
    'number': 10,
},
],
},
    'nested_array': [
    [
    5,
],
    [
    0,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'octopus',
    'deer',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': None,
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
    '26',
    '17',
],
    'text_data': 'ae6f783e6f984063891cd0ce8442dcfc',
    'rand_digit': 3,
    'rand_number': 0.48522,
    'rand_signed_int': 9,
    'rand_datetime': '2000-08-08T07:35:07.812007',
    'text_array': [
    '6010b7865f064f9a8dc6e62f17f2fc0c',
    '73717949011a4d00a02d70400ca1cb66',
],
    'words': 'fish butterfly',
    'nested': {
    'id': 110,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'frog',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'fox',
    'mouse',
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
    'maybe': 'dragonfly',
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
    'text_data': 'f12d2b67d5ab4555a3498996c964d7dd',
    'rand_digit': 9,
    'rand_number': 0.2353,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-01T17:03:14.124298-1100',
    'text_array': [
    '42ec1c57ffe94debb871326b58cbab8f',
    '93f84d3b92f74957ba2d80de65ce4425',
],
    'words': 'mouse lizard',
    'nested': {
    'id': 111,
    'rand_digit': 4,
    'array': [
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
],
    'word': 'wolf',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 3,
},
    {
    'nested_empty': None,
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
    'word': 'cow',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'camel',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 6,
    'maybe_null': 'sloth',
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
    '25',
    '17',
    '13',
    '23',
],
    'text_data': '58bbfbf498c94a9e89c0bac53d6824c1',
    'rand_digit': 9,
    'rand_number': 0.19372,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-05T05:41:56.790894',
    'text_array': [
    'cef01e2df82d4f2eb1348131e44a81c4',
    '23b2f011cdd04b159e6d08ade457dda6',
],
    'words': 'zebra jaguar',
    'nested': {
    'id': 112,
    'rand_digit': 5,
    'array': [
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
    'word': 'tiger',
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
    'number': 6,
},
],
},
    'nested_array': [
    [
    6,
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'elephant',
    'dolphin',
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
    'mixed_type': None,
    'maybe_null': 'rabbit',
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
    '27',
    '13',
    '06',
],
    'text_data': '6f0822dd2747419395fe7dab4e8d43e4',
    'rand_digit': 1,
    'rand_number': 0.65147,
    'rand_signed_int': 10,
    'rand_datetime': '2000-06-28 07:22:04.993792',
    'text_array': [
    '4e5409d1ed134eaeb5cc4093225db092',
    '37da2be0cdd844d5825df248878f57ee',
],
    'words': 'bee camel',
    'nested': {
    'id': 113,
    'rand_digit': 5,
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
    'word': 'duck',
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
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dog',
    'duck',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': [
    84,
],
    'rand_bool': False,
    'mixed_type': 4,
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
    '27',
    '10',
    '18',
],
    'text_data': 'a1bc59bce9484d92a0b3530179253f71',
    'rand_digit': 8,
    'rand_number': 0.26463,
    'rand_signed_int': -1,
    'rand_datetime': '2000-04-02T15:25:18',
    'text_array': [
    '2d0c2e80b54c440d8ffc7fe8484ddc4d',
    '6873e91dfd194849bbd1c749499de136',
],
    'words': 'duck fox',
    'nested': {
    'id': 114,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'koala',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 4,
},
],
},
    'nested_array': [
    [
    10,
],
    [
    3,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'deer',
    'pig',
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
    'mixed_type': {
    'key': 'value',
},
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
    '10',
    '11',
    '12',
],
    'text_data': '0e46b40d391347aa847b9e2d6f3f5f26',
    'rand_digit': 0,
    'rand_number': 0.62657,
    'rand_signed_int': 1,
    'rand_datetime': '2001-01-24T01:07:37.972163',
    'text_array': [
    'ee3fa8c4f1894e9da1b03552541e7897',
    'efcaf0641ac24e58bf3d979cfac25bdf',
],
    'words': 'sloth bird',
    'nested': {
    'id': 115,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 6,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_3,2__',
    'two_words': [
    'snail',
    'grasshopper',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'cheetah',
    'maybe_null': 'goat',
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
    '25',
    '13',
    '27',
],
    'text_data': '6682629f03624ab7a767a92b0446f7dc',
    'rand_digit': 7,
    'rand_number': 0.11582,
    'rand_signed_int': -3,
    'rand_datetime': '2000-04-19 07:33:31.797878',
    'text_array': [
    'a48fb200333040a4af4eec61dd753fef',
    '82d1af69b1a74f5b8fc2ad35f9f98448',
],
    'words': 'bird cat',
    'nested': {
    'id': 116,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'elephant',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'hyena',
    'cheetah',
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
    'mixed_type': 7,
    'maybe': 'shark',
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
    '10',
    '17',
    '12',
],
    'text_data': 'cc9a1e0713a74b209d8fec87d5670f8a',
    'rand_digit': 0,
    'rand_number': 0.53469,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-18 22:07:06+0500',
    'text_array': [
    'f3a7e8a046554bdab206ec93c054cde5',
    '6b0bc8e7514243cc80b6a1a16396efde',
],
    'words': 'deer monkey',
    'nested': {
    'id': 117,
    'rand_digit': 1,
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
    'word': 'koala',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'horse',
    'koala',
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
    'maybe_null': 'cow',
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
    '12',
    '22',
    '10',
    '10',
],
    'text_data': 'ea924d9e3fb84e1985c918ffb7fca201',
    'rand_digit': 8,
    'rand_number': 0.26954,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-29T19:55:54.657802+0300',
    'text_array': [
    '2c0a0693da934d95a1848cbd53d88ce6',
    '65683acc812341b69c41337f0db11578',
],
    'words': 'cat squid',
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
    'word': 'hyena',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 3,
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
    'nested_array': [
    [
    2,
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snake',
    'dragonfly',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': [
    26,
],
    'rand_bool': False,
    'mixed_type': 3,
    'maybe_null': 'ladybug',
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
    '03',
    '23',
    '15',
],
    'text_data': 'b53cc4aabda8474c9b5dce872af8e242',
    'rand_digit': 3,
    'rand_number': 0.90521,
    'rand_signed_int': 6,
    'rand_datetime': '2000-10-17T23:46:49',
    'text_array': [
    '6a37517cd01543068ce401ff615a6138',
    'c0c6956aa6fe4f20b480d6f77bef22a4',
],
    'words': 'ant ant',
    'nested': {
    'id': 119,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'squid',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'spider',
    'dog',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'dog',
    'maybe_null': 'ape',
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
    '30',
    '29',
    '21',
],
    'text_data': 'cfb0c428fc024472b105d812ec206420',
    'rand_digit': 6,
    'rand_number': 0.83439,
    'rand_signed_int': 10,
    'rand_datetime': '2000-06-18T06:02:05',
    'text_array': [
    '551398c132de4eb1ab0d9a6ddf52e642',
    'de8c1e010f9f4c2f8b6f85d6cfe1c1f0',
],
    'words': 'leopard butterfly',
    'nested': {
    'id': 120,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
    5,
],
],
    'two_words': [
    'dolphin',
    'fox',
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
    'mixed_type': 0.84127,
    'maybe': 'ape',
    'maybe_null': 'panda',
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
    '03',
],
    'text_data': 'f99c0d4fb972461dadf9b8fd091ae9d3',
    'rand_digit': 7,
    'rand_number': 0.78423,
    'rand_signed_int': 5,
    'rand_datetime': '2000-07-23T02:59:47+0500',
    'text_array': [
    'b3aae5f2ed3e46d78cdcd8104d37604b',
    'e2221555149f457a891067e18e5ce39a',
],
    'words': 'elephant butterfly',
    'nested': {
    'id': 121,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 7,
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
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'gorilla',
    'leopard',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'leopard',
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
    '30',
    '22',
    '23',
    '27',
    '30',
],
    'text_data': 'a5682c51c7d24e77bb2c63d19313cf16',
    'rand_digit': 9,
    'rand_number': 0.40436,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-05 17:04:01.324710-0600',
    'text_array': [
    '45ca5229b3c241a9a7c64ac8371ea323',
    'c24126d71683466b88fcd5a03b17a7cf',
],
    'words': 'butterfly horse',
    'nested': {
    'id': 122,
    'rand_digit': 5,
    'array': [
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
    [
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'wolf',
    'mosquito',
],
    'city': {
    'name': 'Rome',
    'geo': {
    'lat': 41.902782,
    'lon': 12.496366,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'shark',
    'maybe': 'panda',
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
],
    'text_data': 'a3acc15bd1ce41eab8e00e2987feb54f',
    'rand_digit': 2,
    'rand_number': 0.65877,
    'rand_signed_int': -7,
    'rand_datetime': '2000-02-27 19:00:03.590542',
    'text_array': [
    '72b6d852072b435cb40665add96b5142',
    '5c9b849d4016473a97920ee06908c824',
],
    'words': 'squid horse',
    'nested': {
    'id': 123,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'shark',
    'horse',
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
    'mixed_type': 0.95656,
    'maybe': 'mosquito',
    'maybe_null': 'shark',
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
    'text_data': '93a4f6595a284bfdaedbd7843d99b8e3',
    'rand_digit': 9,
    'rand_number': 0.08438,
    'rand_signed_int': -5,
    'rand_datetime': '2000-04-09 17:15:23-0900',
    'text_array': [
    'b0117f43dbc34b3d935c4ba014b5b03f',
    'fc507c38c6bd4864b4ec3e55ed8ecd64',
],
    'words': 'cheetah panda',
    'nested': {
    'id': 124,
    'rand_digit': 0,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'octopus',
    'chicken',
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
    'mixed_type': 5,
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
    '14',
    '11',
    '12',
    '14',
    '06',
],
    'text_data': '5dfd347c5d8b452ea291e5db8c420eb2',
    'rand_digit': 4,
    'rand_number': 0.80157,
    'rand_signed_int': 0,
    'rand_datetime': '2000-10-19T15:16:23.334320',
    'text_array': [
    '40e8498c6fbc4b70b3e8263389c209c3',
    'c455f2f6e49b4f2b995a04d9417649d8',
],
    'words': 'horse wolf',
    'nested': {
    'id': 125,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'fish',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'camel',
    'cat',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': [
    60,
],
    'rand_bool': True,
    'mixed_type': 5,
    'maybe_null': None,
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
    'text_data': 'afce3b6958d34e81b3e3df00ab99d8d6',
    'rand_digit': 7,
    'rand_number': 0.43722,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-07 23:32:33-0100',
    'text_array': [
    '8249c09d0efa4f9bb1247a1423b2c957',
    'f149185e3851455ab84670514aaafa15',
],
    'words': 'crab bee',
    'nested': {
    'id': 126,
    'rand_digit': 6,
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
    'word': 'snail',
    'number': 7,
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
    'nested_array': [
],
    'two_words': [
    'shark',
    'scorpion',
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
    'mixed_type': 3,
    'maybe': 'hyena',
    'maybe_null': 'camel',
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
    '02',
    '04',
    '02',
],
    'text_data': '729e0cc9845c4aee8ade333c0ce124e3',
    'rand_digit': 8,
    'rand_number': 0.76142,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-27 18:04:29',
    'text_array': [
    'aab78c9612c84c45ab91e31ec114e3db',
    'd413f521f1ed46af8ad45e17346c0939',
],
    'words': 'rabbit sloth',
    'nested': {
    'id': 127,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    1,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'hyena',
    'tiger',
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
    'mixed_type': True,
    'maybe': 'shark',
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
    '29',
    '01',
    '23',
    '04',
    '03',
],
    'text_data': '26fa010711de4a9e98fd6c9c719e2d44',
    'rand_digit': 0,
    'rand_number': 0.81741,
    'rand_signed_int': 5,
    'rand_datetime': '2000-03-10 20:56',
    'text_array': [
    '47d9ea905af14aa19c49945525a58dc9',
    '5ea1c7a4cc6b4ef09299f5c319c68a78',
],
    'words': 'lion lizard',
    'nested': {
    'id': 128,
    'rand_digit': 8,
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
    'word': 'horse',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 10,
},
],
},
    'nested_array': [
    [
    2,
],
    [
],
],
    'two_words': [
    'rabbit',
    'dragonfly',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 8,
    'maybe': 'pig',
    'maybe_null': 'deer',
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
    '11',
    '28',
],
    'text_data': '6f395e92f34945b2af4279c4889b7493',
    'rand_digit': 8,
    'rand_number': 0.15655,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-11T19:33:37',
    'text_array': [
    '1c938a8361ab401e9d35877ee2820f3f',
    'b7f4051d65a6495a9a2c498bfc314abf',
],
    'words': 'zebra fly',
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
    'word': 'turtle',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fish',
    'ladybug',
],
    'city': {
    'name': 'Johannesburg',
    'geo': {
    'lat': -26.204103,
    'lon': 28.047305,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'mosquito',
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
    '27',
    '01',
    '06',
],
    'text_data': '8fc12b14c0184ae88916af70b0d3db5a',
    'rand_digit': 6,
    'rand_number': 0.58773,
    'rand_signed_int': 7,
    'rand_datetime': '2000-07-08T11:13:19.001248',
    'text_array': [
    '0b2b3928115b484da12c2c4fb571a7d8',
    'ac5d179cc8824e0c97c77fd3b651ed1b',
],
    'words': 'zebra panda',
    'nested': {
    'id': 130,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
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
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 10,
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
    'ladybug',
    'snail',
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
    'mixed_type': 3,
    'maybe': 'turtle',
    'maybe_null': 'wolf',
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
],
    'text_data': '82f45b7b6755426ba53de30ac6e99c84',
    'rand_digit': 7,
    'rand_number': 0.2251,
    'rand_signed_int': 9,
    'rand_datetime': '2001-01-15T14:03:40',
    'text_array': [
    'c6fdb91a55cd4513b9dc9f3bab1961ef',
    '09ca7ad65b3841998cb5e0d4d0c008d6',
],
    'words': 'sheep cow',
    'nested': {
    'id': 131,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 10,
},
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'lobster',
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
    'mixed_type': 0,
    'maybe_null': 'fox',
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
    '30',
    '01',
],
    'text_data': '9e5398ea6780483a8e4231217796d6de',
    'rand_digit': 6,
    'rand_number': 0.60096,
    'rand_signed_int': -1,
    'rand_datetime': '2000-02-14 02:16',
    'text_array': [
    'b8110d348c504d95964ddf0fad0a9857',
    'cdc8f5f8c18142889c7829346550c309',
],
    'words': 'hyena fox',
    'nested': {
    'id': 132,
    'rand_digit': 4,
    'array': [
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
    'word': 'fish',
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'elephant',
    'deer',
],
    'city': {
    'name': 'Frankfurt',
    'geo': {
    'lat': 50.110922,
    'lon': 8.682127,
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
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
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
    '24',
    '08',
    '11',
    '09',
],
    'text_data': '61da0b75575d450d9f43e9e3ff9ef423',
    'rand_digit': 4,
    'rand_number': 0.49471,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-15 03:15:49',
    'text_array': [
    'b591d680a1584bffad22eb34849126d1',
    '7f4f46b8409f470f8a90b817d48b7852',
],
    'words': 'koala spider',
    'nested': {
    'id': 133,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'sloth',
    'fox',
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
    'mixed_type': 'sloth',
    'maybe': 'tiger',
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
    '29',
    '16',
    '15',
    '21',
    '23',
],
    'text_data': '632b91840cd246b68dfb01a5c53504cc',
    'rand_digit': 6,
    'rand_number': 0.30331,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-04 04:21:21+0800',
    'text_array': [
    '76b234cb7eae422b89cd3316c383d7a5',
    'f2adf9091c5b4ff1ab64915880fe479e',
],
    'words': 'fly fly',
    'nested': {
    'id': 134,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 2,
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
    'word': 'shark',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ladybug',
    'rhino',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'goat',
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
    '27',
    '21',
    '10',
    '17',
],
    'text_data': '599a5315be2545aba9dbbb734c3effac',
    'rand_digit': 2,
    'rand_number': 0.00331,
    'rand_signed_int': -10,
    'rand_datetime': '2000-03-17T14:13:05',
    'text_array': [
    '24a129f07da1414eadc96e8b0556e542',
    '574e44dd89c64872b117a199acc11ac0',
],
    'words': 'fox bird',
    'nested': {
    'id': 135,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 8,
},
],
},
    'nested_array': [
    [
    -5,
],
    [
],
    [
],
],
    'two_words': [
    'goat',
    'koala',
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
    'mixed_type': 'duck',
    'maybe': 'lobster',
    'maybe_null': 'mouse',
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
    '15',
    '08',
    '17',
],
    'text_data': '747f7f2276f04c219c093352cad7409b',
    'rand_digit': 9,
    'rand_number': 0.80899,
    'rand_signed_int': 1,
    'rand_datetime': '2000-04-23 19:15:28+0800',
    'text_array': [
    'af952c353a064393ae448d773c753ff8',
    'b23892625e6d45799a3d0da04d1bc0f5',
],
    'words': 'hippo squid',
    'nested': {
    'id': 136,
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
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'ant',
    'wolf',
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
    'mixed_type': 'fox',
    'maybe': 'sloth',
    'maybe_null': 'spider',
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
    '19',
],
    'text_data': 'af9a64fe8c25476cba34b2953375b286',
    'rand_digit': 1,
    'rand_number': 0.84197,
    'rand_signed_int': -2,
    'rand_datetime': '2001-01-12T14:22:54',
    'text_array': [
    '720709cac25d49e399e3ab12a5fb6060',
    '1173b0a4b12642579954ac64656fd945',
],
    'words': 'jaguar fox',
    'nested': {
    'id': 137,
    'rand_digit': 0,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'spider',
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
    'maybe_null': 'bee',
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
    '09',
],
    'text_data': '23e18169ed4645baa30f9c04b87e8bc9',
    'rand_digit': 3,
    'rand_number': 0.54566,
    'rand_signed_int': -8,
    'rand_datetime': '2000-06-11 01:28',
    'text_array': [
    'd7982b30d5d84bb8ab2a12588c96305f',
    '9a658f0bdf1f4727bbcf9122aa1ae66d',
],
    'words': 'mosquito pig',
    'nested': {
    'id': 138,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 6,
},
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
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
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'crab',
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
    '07',
    '26',
    '20',
],
    'text_data': 'f620d5d8790e4dde846af8524994d675',
    'rand_digit': 7,
    'rand_number': 0.48746,
    'rand_signed_int': 7,
    'rand_datetime': '2000-05-27',
    'text_array': [
    'bcb790b575fa490aab1932fb598a3d8c',
    '8307b88a68c249628ac6a8688f2ddb9a',
],
    'words': 'sheep ant',
    'nested': {
    'id': 139,
    'rand_digit': 5,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dog',
    'spider',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bird',
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
    '25',
    '27',
    '02',
],
    'text_data': 'ec8213f63ecc4e9982bbd51b30ebe917',
    'rand_digit': 5,
    'rand_number': 0.15294,
    'rand_signed_int': 9,
    'rand_datetime': '2000-12-23T21:24:07+0800',
    'text_array': [
    '309b08dbed294bcfbc74884416ba2ac3',
    '2c2f67a59d0647a893357e921ad3bd5e',
],
    'words': 'lobster grasshopper',
    'nested': {
    'id': 140,
    'rand_digit': 4,
    'array': [
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 7,
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
    'hello',
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
    'word': 'dragonfly',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -4,
],
    [
],
    [
    4,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'monkey',
    'octopus',
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
    'mixed_type': 0.2873,
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
    '18',
    '21',
    '19',
    '01',
],
    'text_data': 'd4179423a6cc4a659a4730115e0f8256',
    'rand_digit': 9,
    'rand_number': 0.82021,
    'rand_signed_int': -4,
    'rand_datetime': '2000-09-07 17:21',
    'text_array': [
    '992e58263a5c4e71ab9469c3289696c9',
    '8d02dd16a78c4929bcfe7aa4b51092fd',
],
    'words': 'cheetah panda',
    'nested': {
    'id': 141,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 9,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 5,
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
    'word': 'duck',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -1,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'elephant',
    'fox',
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
    'mixed_type': 0.4709,
    'maybe': 'lobster',
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
    '02',
],
    'text_data': 'dce8e57b2198488aa76e46bb8149dc04',
    'rand_digit': 2,
    'rand_number': 0.30369,
    'rand_signed_int': -1,
    'rand_datetime': '2001-01-03T23:17:22.629115-1200',
    'text_array': [
    'eff0002064d848e881a2a37c84e39f13',
    'a2957d8571e84f3ca0b22fb9f081720b',
],
    'words': 'hippo squid',
    'nested': {
    'id': 142,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'giraffe',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 9,
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
    'word': 'giraffe',
    'number': 6,
},
],
},
    'nested_array': [
    [
    -9,
],
],
    'two_words': [
    'rabbit',
    'frog',
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
    'maybe': 'fly',
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
    '29',
    '06',
],
    'text_data': '8cd456c4402f41d4aecdc93a44ba53cd',
    'rand_digit': 7,
    'rand_number': 0.83498,
    'rand_signed_int': -7,
    'rand_datetime': '2001-01-08 15:17:31+0700',
    'text_array': [
    '8e757660041448e1983516bdd9e18280',
    'eb7011dfea0049c68dcb26042530e29c',
],
    'words': 'zebra kangaroo',
    'nested': {
    'id': 143,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'gorilla',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'chicken',
    'butterfly',
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
    'mixed_type': 0.33521,
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
],
    'text_data': 'a8c8f42b0788493ab5e594d3eddf85c4',
    'rand_digit': 1,
    'rand_number': 0.21713,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-18',
    'text_array': [
    'ef3ebb99613249568b8f7a5251c7944f',
    'a7195baabef44fdb96ca20fcab319749',
],
    'words': 'scorpion dragonfly',
    'nested': {
    'id': 144,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    8,
],
    [
],
],
    'two_words': [
    'dog',
    'fox',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'elephant',
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
    '28',
    '26',
    '05',
],
    'text_data': 'e6812585de8447c3b8029723cefa8338',
    'rand_digit': 3,
    'rand_number': 0.4925,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-30T21:50:39.279982',
    'text_array': [
    '271c3acf874747f7bc46be158a74c39e',
    'a3f9b229f58f4f57a617428c839be6ce',
],
    'words': 'mosquito lion',
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bird',
    'camel',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
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
    '20',
],
    'text_data': '889f362223da429b8cdc34c37206adaf',
    'rand_digit': 9,
    'rand_number': 0.61181,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-01T16:41:11-0800',
    'text_array': [
    '92319feae07646b48efd42a6b8f79a94',
    '49e9b02f56e44108a4d77b33895bee0e',
],
    'words': 'hippo duck',
    'nested': {
    'id': 146,
    'rand_digit': 6,
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
    'word': 'wolf',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'rabbit',
    'camel',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': [
    11,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'monkey',
    'maybe_null': None,
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
    '16',
],
    'text_data': '284810c5e645472ea73dee2a2c3c0a7c',
    'rand_digit': 2,
    'rand_number': 0.35068,
    'rand_signed_int': 2,
    'rand_datetime': '2000-02-11T11:52:18.981970+0700',
    'text_array': [
    '0169369acadf4edf8ed8001d8861e110',
    '7418e58b91714f0d980f88295032c299',
],
    'words': 'hyena dragonfly',
    'nested': {
    'id': 147,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'elephant',
    'number': 4,
},
],
},
    'nested_array': [
    [
    6,
],
],
    'two_words': [
    'gorilla',
    'dragonfly',
],
    'city': {
    'name': 'Frankfurt',
    'geo': {
    'lat': 50.110922,
    'lon': 8.682127,
},
},
    'rand_tuple': [
    21,
],
    'rand_bool': False,
    'mixed_type': True,
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
    '13',
    '07',
    '25',
    '01',
],
    'text_data': '7891faa776404376808e7e09cb42e0ac',
    'rand_digit': 7,
    'rand_number': 0.37754,
    'rand_signed_int': -1,
    'rand_datetime': '2000-02-24',
    'text_array': [
    'ee438bfabf864276936c1bb98b194088',
    'eaf1169f9e1b4472bc866dde97172423',
],
    'words': 'bear rabbit',
    'nested': {
    'id': 148,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'wolf',
    'ladybug',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': [
    62,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'horse',
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
    '04',
    '27',
    '27',
    '05',
],
    'text_data': '0e8042f5644c4033b3e7e2ad39704ef3',
    'rand_digit': 5,
    'rand_number': 0.32284,
    'rand_signed_int': -9,
    'rand_datetime': '2000-09-16 10:10:18+0700',
    'text_array': [
    '7ccf88991b9b41e7b391e63642c92aca',
    '58ea51a340eb4f2cb1919e428c0b2a9a',
],
    'words': 'jaguar lizard',
    'nested': {
    'id': 149,
    'rand_digit': 3,
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
    'hello',
],
    'word': 'mosquito',
    'number': 10,
},
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
    'hello',
],
    'word': 'deer',
    'number': 10,
},
],
},
    'nested_array': [
    [
    6,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hippo',
    'mosquito',
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
    'mixed_type': 3,
    'maybe': 'grasshopper',
    'maybe_null': 'horse',
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
    'text_data': 'e05a6559139d4b85b331a1cd133492b2',
    'rand_digit': 4,
    'rand_number': 0.37875,
    'rand_signed_int': 10,
    'rand_datetime': '2000-12-10T02:57:02.366297+0100',
    'text_array': [
    '73889d73b8a2458bb826182c9e70fac1',
    '66c2f03b0fac444ea7e3782c19baa601',
],
    'words': 'elephant gorilla',
    'nested': {
    'id': 150,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'squid',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'mosquito',
    'hyena',
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
    'mixed_type': 'wolf',
    'maybe': 'monkey',
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
    '09',
    '12',
],
    'text_data': '9264a70e28594263ae4f9e5836cbf3b2',
    'rand_digit': 7,
    'rand_number': 0.85813,
    'rand_signed_int': -1,
    'rand_datetime': '2000-05-27 16:14:30',
    'text_array': [
    '876d632ce0494ec3a85be34d24fd44b9',
    '84ca8249c6df4109b85ef9d37c2b1a2a',
],
    'words': 'grasshopper panda',
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
    'word': 'koala',
    'number': 7,
},
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
],
    'word': 'fish',
    'number': 9,
},
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
    'word': 'spider',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bee',
    'kangaroo',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 'koala',
    'maybe_null': 'lizard',
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
    'text_data': '24f23b198fba42a8ad036fa40f7daec0',
    'rand_digit': 3,
    'rand_number': 0.70971,
    'rand_signed_int': 9,
    'rand_datetime': '2000-02-06 22:47:14',
    'text_array': [
    '0924631d78df42af8f7e49bbb45064f5',
    '88923107af6f4ce1bd695a546bed185d',
],
    'words': 'leopard mosquito',
    'nested': {
    'id': 152,
    'rand_digit': 4,
    'array': [
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
],
    'word': 'dog',
    'number': 5,
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
    'hello',
],
    'word': 'dolphin',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    2,
],
],
    'two_words': [
    'turtle',
    'mosquito',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
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
    '02',
],
    'text_data': 'a53f49ac66894daabb964c3447b94570',
    'rand_digit': 3,
    'rand_number': 0.98101,
    'rand_signed_int': 1,
    'rand_datetime': '2000-05-29 00:09:20-0900',
    'text_array': [
    '91d09dfbc1e04ee89d29c87fe556c2ae',
    '1c29d05d4e7c433b8336a9d9752299c4',
],
    'words': 'kangaroo elephant',
    'nested': {
    'id': 153,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lion',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mosquito',
    'fish',
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
    'mixed_type': None,
    'maybe_null': 'ant',
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
    '26',
    '06',
],
    'text_data': 'e4cd00b92bff46e3822df93c1ab88e18',
    'rand_digit': 4,
    'rand_number': 0.88282,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-21T05:24:18-0500',
    'text_array': [
    '639301dbefe8474696a99621534df247',
    '83cb3887cdc44e7dac170d1943679e4a',
],
    'words': 'cheetah leopard',
    'nested': {
    'id': 154,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 10,
},
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
    'word': 'goat',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 1,
},
],
},
    'nested_array': [
    [
    5,
],
],
    'two_words': [
    'octopus',
    'lobster',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'dog',
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
    '08',
    '02',
    '25',
    '01',
    '10',
],
    'text_data': '49c1faa34bf6455d90694f378bc84ba4',
    'rand_digit': 7,
    'rand_number': 0.21121,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-04T11:29:52-0700',
    'text_array': [
    'a272e7da88a944f581f9d8c13ec92580',
    '33b731c4536945279c058f30dd589899',
],
    'words': 'bee bird',
    'nested': {
    'id': 155,
    'rand_digit': 8,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 1,
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
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'shark',
    'turtle',
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
    'mixed_type': 6,
    'maybe': 'sloth',
    'maybe_null': 'lobster',
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
    '11',
    '12',
    '16',
    '30',
],
    'text_data': '84723d2058164d2cb48a1f923513944a',
    'rand_digit': 7,
    'rand_number': 0.86285,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-15T01:11:12.630459',
    'text_array': [
    'e4e94923fcea4a9083b4e05c89a073a9',
    '8d75d0826e024c3da60eda3244039a61',
],
    'words': 'dog pig',
    'nested': {
    'id': 156,
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
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'sloth',
    'lizard',
],
    'city': {
    'name': 'Dubai',
    'geo': {
    'lat': 25.204849,
    'lon': 55.270783,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'monkey',
    'maybe_null': 'lion',
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
    '29',
    '04',
    '20',
],
    'text_data': '6b5f2122b640461696bb9521631e4709',
    'rand_digit': 2,
    'rand_number': 0.8212,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-30 01:01:52+0100',
    'text_array': [
    '6dc87596b7d647339a630f5adf1ea19a',
    'e6f9baf1b2a14051886b4a1bbe0db6a0',
],
    'words': 'lion scorpion',
    'nested': {
    'id': 157,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 1,
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
    [
    9,
],
],
    'two_words': [
    'goat',
    'grasshopper',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': [
    42,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'gorilla',
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
    'text_data': 'e67aa3ef5ed848e693e88247c3e00231',
    'rand_digit': 1,
    'rand_number': 0.38197,
    'rand_signed_int': -6,
    'rand_datetime': '2000-05-24T15:05:25-0600',
    'text_array': [
    '75aebbd150af4d26921ce2ccc83492e2',
    'ee414dd6be604c369bc546c5f8857ae4',
],
    'words': 'rabbit fly',
    'nested': {
    'id': 158,
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
    'number': 2,
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
],
    'word': 'crab',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'chicken',
    'leopard',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0,
    'maybe_null': 'bear',
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
],
    'text_data': '7d5d108eb0e94569bb20b58d2c8e8ed0',
    'rand_digit': 5,
    'rand_number': 0.4501,
    'rand_signed_int': 5,
    'rand_datetime': '2000-08-18T23:17:08.216610',
    'text_array': [
    'f9916fe0aeca471592c59faeceff40b7',
    '893a7f6b7fd74259924e142f8c987fb3',
],
    'words': 'lion kangaroo',
    'nested': {
    'id': 159,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ant',
    'number': 9,
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
    0,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lion',
    'snail',
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
    'mixed_type': None,
    'maybe': 'wolf',
    'maybe_null': 'dragonfly',
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
    '03',
],
    'text_data': 'a1ec8f81c2d2404cbb2e9a0069a40401',
    'rand_digit': 4,
    'rand_number': 0.0427,
    'rand_signed_int': 5,
    'rand_datetime': '2000-01-30T22:52:15.652707',
    'text_array': [
    '73b4330819f34e15ac34ec0d6169d19e',
    'f8b74918714743b69e0df41c46ce568d',
],
    'words': 'kangaroo bear',
    'nested': {
    'id': 160,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -9,
],
],
    'two_words': [
    'shark',
    'elephant',
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
    'mixed_type': 'squid',
    'maybe_null': 'koala',
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
    '07',
    '22',
    '08',
    '03',
],
    'text_data': 'b965c34be61444e69a4048f6e9028d90',
    'rand_digit': 9,
    'rand_number': 0.16533,
    'rand_signed_int': 1,
    'rand_datetime': '2000-12-08T22:06:37.802299',
    'text_array': [
    'be49dcf4e49a443c9b92c916118f9df2',
    'eb924fa2e8da47cdb3f30115e335d5ac',
],
    'words': 'rabbit squid',
    'nested': {
    'id': 161,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'tiger',
    'number': 1,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dog',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bear',
    'dolphin',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.55531,
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
    'text_data': 'ea0d1cd51ac04bba9fa1aac73363cbe6',
    'rand_digit': 5,
    'rand_number': 0.5004,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-18 11:09',
    'text_array': [
    'f790435075e444b48fdd6f6f7c9eb1d6',
    'e31072069f6c4072b980a27204acf3c3',
],
    'words': 'snail fly',
    'nested': {
    'id': 162,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'octopus',
    'panda',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.47443,
    'maybe': 'snail',
    'maybe_null': 'pig',
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
    '21',
    '23',
    '14',
],
    'text_data': '19d580d0643e476c9dfc581648dca2ef',
    'rand_digit': 9,
    'rand_number': 0.42002,
    'rand_signed_int': -9,
    'rand_datetime': '2000-09-09T12:33:30.155920',
    'text_array': [
    'c6e80f7c0af647cfb8eaf39b2c5ab293',
    'd67781d4f86b4737b9e0fec46263d11b',
],
    'words': 'bear hyena',
    'nested': {
    'id': 163,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 3,
},
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
    'word': 'whale',
    'number': 1,
},
    {
    'nested_empty': None,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lizard',
    'monkey',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'wolf',
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
    'content-length': '3117508',
}
        
        # 原始请求内容
        original_content = {
    'batch': {
    'ids': self.mutator.generate_float_array(dimension=100, normalized=True),
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
    '10',
    '15',
    '14',
    '10',
    '20',
],
    'text_data': 'dbcd68d5d5184cf79797a166a9f5320d',
    'rand_digit': 3,
    'rand_number': 0.55551,
    'rand_signed_int': -5,
    'rand_datetime': '2000-07-30 01:52:21.211964',
    'text_array': [
    '38e721ee08d94839a045d51cf1f47295',
    '0e2ae7af95d949769fa68ba31ba6f2cf',
],
    'words': 'bird goat',
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
    'word': 'hyena',
    'number': 6,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'snail',
    'lizard',
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
    'mixed_type': 'koala',
    'maybe': 'hippo',
    'maybe_null': 'bear',
},
    {
    'id': 101,
    'id_str': [
    '25',
    '28',
],
    'text_data': '5e3a4db036a649f58c9836e3d2b7a89e',
    'rand_digit': 6,
    'rand_number': 0.5769,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-28',
    'text_array': [
    '8d78cacb201a461ea0e19171fc008c84',
    '529541153a3a42d7a6fe1147cfd2d41a',
],
    'words': 'butterfly giraffe',
    'nested': {
    'id': 101,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
    6,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ape',
    'bear',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'octopus',
},
    {
    'id': 102,
    'id_str': [
    '10',
    '17',
    '12',
],
    'text_data': '14e37ad126bf47d489ee58c996ef8701',
    'rand_digit': 9,
    'rand_number': 0.88101,
    'rand_signed_int': -8,
    'rand_datetime': '2000-10-04T04:32:45-0200',
    'text_array': [
    'b028f6022c8e44f0aa246e3dfc29107b',
    'aedc91ba7c9f4e298246bc6796bb4927',
],
    'words': 'mosquito mosquito',
    'nested': {
    'id': 102,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'duck',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'koala',
    'spider',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
},
    {
    'id': 103,
    'id_str': [
    '06',
    '15',
    '08',
    '23',
],
    'text_data': '1d10af521a92405c9b8da65fd943bdc6',
    'rand_digit': 8,
    'rand_number': 0.93312,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-20 04:13:47.943670-1200',
    'text_array': [
    'c4e8153303134451bbbf36a581b35649',
    'b9747a7d5fc949999708d2d30edab3f4',
],
    'words': 'rhino lizard',
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
    'word': 'giraffe',
    'number': 6,
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
    9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fox',
    'snake',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'gorilla',
},
    {
    'id': 104,
    'id_str': [
    '09',
    '25',
    '29',
],
    'text_data': '3d8b04f48aa14f24979f9fff2b30e558',
    'rand_digit': 6,
    'rand_number': 0.84658,
    'rand_signed_int': 9,
    'rand_datetime': '2000-02-24',
    'text_array': [
    'd7f8835b2b304c8e88a49f505e84ab82',
    'b7c71f877f22474196b1f1dfaa6ec9f9',
],
    'words': 'snake sheep',
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
    'word': 'leopard',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 3,
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
    'cheetah',
    'cat',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'zebra',
},
    {
    'id': 105,
    'id_str': [
    '01',
    '19',
    '03',
],
    'text_data': '57156df6cb5c43688c1a642c879f0d3a',
    'rand_digit': 2,
    'rand_number': 0.50545,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-16T18:28:45.400479+09:00',
    'text_array': [
    '458032cb2d684356ae40084ecefdc2f8',
    '19a9563774444673b799f6d024b3f705',
],
    'words': 'chicken spider',
    'nested': {
    'id': 105,
    'rand_digit': 4,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 2,
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
    'word': 'camel',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
    2,
],
],
    'two_words': [
    'duck',
    'chicken',
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
    'mixed_type': None,
    'maybe_null': None,
},
    {
    'id': 106,
    'id_str': [
    '21',
],
    'text_data': '7b123b9e1d4443b097326da368fddfd4',
    'rand_digit': 0,
    'rand_number': 0.04129,
    'rand_signed_int': -5,
    'rand_datetime': '2000-01-10 05:44:52.562966+0100',
    'text_array': [
    '3a4b4e1e9d7f4d47bcbbf49974ccaee7',
    '3c8b336444c144e1ac0173cd6cdb79a8',
],
    'words': 'bee rabbit',
    'nested': {
    'id': 106,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    10,
],
],
    'two_words': [
    'turtle',
    'turtle',
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
    'mixed_type': 0,
    'maybe': 'octopus',
},
    {
    'id': 107,
    'id_str': [
    '16',
    '10',
],
    'text_data': '5fa50b9bc7934aee96a6049f101225a5',
    'rand_digit': 7,
    'rand_number': 0.37869,
    'rand_signed_int': -1,
    'rand_datetime': '2000-05-29T18:10:39.304939',
    'text_array': [
    '860cebf2a1fa4f7aaec48936332f3478',
    '9924a1ea1cf345fb9cdf184fcab61bea',
],
    'words': 'lizard grasshopper',
    'nested': {
    'id': 107,
    'rand_digit': 5,
    'array': [
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
    'word': 'cow',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 9,
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
    'zebra',
    'butterfly',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': [
    55,
],
    'rand_bool': True,
    'mixed_type': 'butterfly',
},
    {
    'id': 108,
    'id_str': [
    '30',
    '10',
    '18',
    '05',
    '07',
],
    'text_data': 'f05d9ad2f09a493eab70dc5c187545cf',
    'rand_digit': 9,
    'rand_number': 0.79995,
    'rand_signed_int': -2,
    'rand_datetime': '2000-06-20T19:33:55.508242',
    'text_array': [
    'ab03d4e8f24d4247826ccbb2c37e1519',
    '714958f29f324feb8e5251098d639826',
],
    'words': 'rabbit mosquito',
    'nested': {
    'id': 108,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'deer',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'crab',
    'monkey',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'grasshopper',
    'maybe_null': None,
},
    {
    'id': 109,
    'id_str': [
    '29',
    '19',
    '03',
    '07',
],
    'text_data': '86cb4ec7f7eb4bca98b0c3e16d4cd8b2',
    'rand_digit': 1,
    'rand_number': 0.38173,
    'rand_signed_int': -5,
    'rand_datetime': '2001-01-05T14:23:59.193398+04:00',
    'text_array': [
    '98567d8cd8c44755b18a4bf00d9022fc',
    '268b998109ed42dcbbb6c08d061e180d',
],
    'words': 'lobster fly',
    'nested': {
    'id': 109,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'spider',
    'number': 10,
},
],
},
    'nested_array': [
    [
    5,
],
    [
    0,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'octopus',
    'deer',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': None,
},
    {
    'id': 110,
    'id_str': [
    '16',
    '26',
    '17',
],
    'text_data': 'ae6f783e6f984063891cd0ce8442dcfc',
    'rand_digit': 3,
    'rand_number': 0.48522,
    'rand_signed_int': 9,
    'rand_datetime': '2000-08-08T07:35:07.812007',
    'text_array': [
    '6010b7865f064f9a8dc6e62f17f2fc0c',
    '73717949011a4d00a02d70400ca1cb66',
],
    'words': 'fish butterfly',
    'nested': {
    'id': 110,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'frog',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'fox',
    'mouse',
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
    'maybe': 'dragonfly',
},
    {
    'id': 111,
    'id_str': [
],
    'text_data': 'f12d2b67d5ab4555a3498996c964d7dd',
    'rand_digit': 9,
    'rand_number': 0.2353,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-01T17:03:14.124298-1100',
    'text_array': [
    '42ec1c57ffe94debb871326b58cbab8f',
    '93f84d3b92f74957ba2d80de65ce4425',
],
    'words': 'mouse lizard',
    'nested': {
    'id': 111,
    'rand_digit': 4,
    'array': [
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
],
    'word': 'wolf',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 3,
},
    {
    'nested_empty': None,
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
    'word': 'cow',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'camel',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 6,
    'maybe_null': 'sloth',
},
    {
    'id': 112,
    'id_str': [
    '25',
    '17',
    '13',
    '23',
],
    'text_data': '58bbfbf498c94a9e89c0bac53d6824c1',
    'rand_digit': 9,
    'rand_number': 0.19372,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-05T05:41:56.790894',
    'text_array': [
    'cef01e2df82d4f2eb1348131e44a81c4',
    '23b2f011cdd04b159e6d08ade457dda6',
],
    'words': 'zebra jaguar',
    'nested': {
    'id': 112,
    'rand_digit': 5,
    'array': [
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
    'word': 'tiger',
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
    'number': 6,
},
],
},
    'nested_array': [
    [
    6,
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'elephant',
    'dolphin',
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
    'mixed_type': None,
    'maybe_null': 'rabbit',
},
    {
    'id': 113,
    'id_str': [
    '01',
    '27',
    '13',
    '06',
],
    'text_data': '6f0822dd2747419395fe7dab4e8d43e4',
    'rand_digit': 1,
    'rand_number': 0.65147,
    'rand_signed_int': 10,
    'rand_datetime': '2000-06-28 07:22:04.993792',
    'text_array': [
    '4e5409d1ed134eaeb5cc4093225db092',
    '37da2be0cdd844d5825df248878f57ee',
],
    'words': 'bee camel',
    'nested': {
    'id': 113,
    'rand_digit': 5,
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
    'word': 'duck',
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
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dog',
    'duck',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': [
    84,
],
    'rand_bool': False,
    'mixed_type': 4,
},
    {
    'id': 114,
    'id_str': [
    '27',
    '10',
    '18',
],
    'text_data': 'a1bc59bce9484d92a0b3530179253f71',
    'rand_digit': 8,
    'rand_number': 0.26463,
    'rand_signed_int': -1,
    'rand_datetime': '2000-04-02T15:25:18',
    'text_array': [
    '2d0c2e80b54c440d8ffc7fe8484ddc4d',
    '6873e91dfd194849bbd1c749499de136',
],
    'words': 'duck fox',
    'nested': {
    'id': 114,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'koala',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 4,
},
],
},
    'nested_array': [
    [
    10,
],
    [
    3,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'deer',
    'pig',
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
    'mixed_type': {
    'key': 'value',
},
},
    {
    'id': 115,
    'id_str': [
    '10',
    '11',
    '12',
],
    'text_data': '0e46b40d391347aa847b9e2d6f3f5f26',
    'rand_digit': 0,
    'rand_number': 0.62657,
    'rand_signed_int': 1,
    'rand_datetime': '2001-01-24T01:07:37.972163',
    'text_array': [
    'ee3fa8c4f1894e9da1b03552541e7897',
    'efcaf0641ac24e58bf3d979cfac25bdf',
],
    'words': 'sloth bird',
    'nested': {
    'id': 115,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 6,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_3,2__',
    'two_words': [
    'snail',
    'grasshopper',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'cheetah',
    'maybe_null': 'goat',
},
    {
    'id': 116,
    'id_str': [
    '06',
    '25',
    '13',
    '27',
],
    'text_data': '6682629f03624ab7a767a92b0446f7dc',
    'rand_digit': 7,
    'rand_number': 0.11582,
    'rand_signed_int': -3,
    'rand_datetime': '2000-04-19 07:33:31.797878',
    'text_array': [
    'a48fb200333040a4af4eec61dd753fef',
    '82d1af69b1a74f5b8fc2ad35f9f98448',
],
    'words': 'bird cat',
    'nested': {
    'id': 116,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'elephant',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'hyena',
    'cheetah',
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
    'mixed_type': 7,
    'maybe': 'shark',
    'maybe_null': 'jaguar',
},
    {
    'id': 117,
    'id_str': [
    '10',
    '17',
    '12',
],
    'text_data': 'cc9a1e0713a74b209d8fec87d5670f8a',
    'rand_digit': 0,
    'rand_number': 0.53469,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-18 22:07:06+0500',
    'text_array': [
    'f3a7e8a046554bdab206ec93c054cde5',
    '6b0bc8e7514243cc80b6a1a16396efde',
],
    'words': 'deer monkey',
    'nested': {
    'id': 117,
    'rand_digit': 1,
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
    'word': 'koala',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'horse',
    'koala',
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
    'maybe_null': 'cow',
},
    {
    'id': 118,
    'id_str': [
    '12',
    '22',
    '10',
    '10',
],
    'text_data': 'ea924d9e3fb84e1985c918ffb7fca201',
    'rand_digit': 8,
    'rand_number': 0.26954,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-29T19:55:54.657802+0300',
    'text_array': [
    '2c0a0693da934d95a1848cbd53d88ce6',
    '65683acc812341b69c41337f0db11578',
],
    'words': 'cat squid',
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
    'word': 'hyena',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 3,
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
    'nested_array': [
    [
    2,
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snake',
    'dragonfly',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': [
    26,
],
    'rand_bool': False,
    'mixed_type': 3,
    'maybe_null': 'ladybug',
},
    {
    'id': 119,
    'id_str': [
    '03',
    '23',
    '15',
],
    'text_data': 'b53cc4aabda8474c9b5dce872af8e242',
    'rand_digit': 3,
    'rand_number': 0.90521,
    'rand_signed_int': 6,
    'rand_datetime': '2000-10-17T23:46:49',
    'text_array': [
    '6a37517cd01543068ce401ff615a6138',
    'c0c6956aa6fe4f20b480d6f77bef22a4',
],
    'words': 'ant ant',
    'nested': {
    'id': 119,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'squid',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'spider',
    'dog',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'dog',
    'maybe_null': 'ape',
},
    {
    'id': 120,
    'id_str': [
    '30',
    '29',
    '21',
],
    'text_data': 'cfb0c428fc024472b105d812ec206420',
    'rand_digit': 6,
    'rand_number': 0.83439,
    'rand_signed_int': 10,
    'rand_datetime': '2000-06-18T06:02:05',
    'text_array': [
    '551398c132de4eb1ab0d9a6ddf52e642',
    'de8c1e010f9f4c2f8b6f85d6cfe1c1f0',
],
    'words': 'leopard butterfly',
    'nested': {
    'id': 120,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
    5,
],
],
    'two_words': [
    'dolphin',
    'fox',
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
    'mixed_type': 0.84127,
    'maybe': 'ape',
    'maybe_null': 'panda',
},
    {
    'id': 121,
    'id_str': [
    '03',
],
    'text_data': 'f99c0d4fb972461dadf9b8fd091ae9d3',
    'rand_digit': 7,
    'rand_number': 0.78423,
    'rand_signed_int': 5,
    'rand_datetime': '2000-07-23T02:59:47+0500',
    'text_array': [
    'b3aae5f2ed3e46d78cdcd8104d37604b',
    'e2221555149f457a891067e18e5ce39a',
],
    'words': 'elephant butterfly',
    'nested': {
    'id': 121,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 7,
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
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'gorilla',
    'leopard',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'leopard',
    'maybe_null': None,
},
    {
    'id': 122,
    'id_str': [
    '30',
    '22',
    '23',
    '27',
    '30',
],
    'text_data': 'a5682c51c7d24e77bb2c63d19313cf16',
    'rand_digit': 9,
    'rand_number': 0.40436,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-05 17:04:01.324710-0600',
    'text_array': [
    '45ca5229b3c241a9a7c64ac8371ea323',
    'c24126d71683466b88fcd5a03b17a7cf',
],
    'words': 'butterfly horse',
    'nested': {
    'id': 122,
    'rand_digit': 5,
    'array': [
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
    [
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'wolf',
    'mosquito',
],
    'city': {
    'name': 'Rome',
    'geo': {
    'lat': 41.902782,
    'lon': 12.496366,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'shark',
    'maybe': 'panda',
},
    {
    'id': 123,
    'id_str': [
],
    'text_data': 'a3acc15bd1ce41eab8e00e2987feb54f',
    'rand_digit': 2,
    'rand_number': 0.65877,
    'rand_signed_int': -7,
    'rand_datetime': '2000-02-27 19:00:03.590542',
    'text_array': [
    '72b6d852072b435cb40665add96b5142',
    '5c9b849d4016473a97920ee06908c824',
],
    'words': 'squid horse',
    'nested': {
    'id': 123,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'shark',
    'horse',
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
    'mixed_type': 0.95656,
    'maybe': 'mosquito',
    'maybe_null': 'shark',
},
    {
    'id': 124,
    'id_str': [
],
    'text_data': '93a4f6595a284bfdaedbd7843d99b8e3',
    'rand_digit': 9,
    'rand_number': 0.08438,
    'rand_signed_int': -5,
    'rand_datetime': '2000-04-09 17:15:23-0900',
    'text_array': [
    'b0117f43dbc34b3d935c4ba014b5b03f',
    'fc507c38c6bd4864b4ec3e55ed8ecd64',
],
    'words': 'cheetah panda',
    'nested': {
    'id': 124,
    'rand_digit': 0,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'octopus',
    'chicken',
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
    'mixed_type': 5,
    'maybe_null': 'crab',
},
    {
    'id': 125,
    'id_str': [
    '14',
    '11',
    '12',
    '14',
    '06',
],
    'text_data': '5dfd347c5d8b452ea291e5db8c420eb2',
    'rand_digit': 4,
    'rand_number': 0.80157,
    'rand_signed_int': 0,
    'rand_datetime': '2000-10-19T15:16:23.334320',
    'text_array': [
    '40e8498c6fbc4b70b3e8263389c209c3',
    'c455f2f6e49b4f2b995a04d9417649d8',
],
    'words': 'horse wolf',
    'nested': {
    'id': 125,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'fish',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'camel',
    'cat',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': [
    60,
],
    'rand_bool': True,
    'mixed_type': 5,
    'maybe_null': None,
},
    {
    'id': 126,
    'id_str': [
],
    'text_data': 'afce3b6958d34e81b3e3df00ab99d8d6',
    'rand_digit': 7,
    'rand_number': 0.43722,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-07 23:32:33-0100',
    'text_array': [
    '8249c09d0efa4f9bb1247a1423b2c957',
    'f149185e3851455ab84670514aaafa15',
],
    'words': 'crab bee',
    'nested': {
    'id': 126,
    'rand_digit': 6,
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
    'word': 'snail',
    'number': 7,
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
    'nested_array': [
],
    'two_words': [
    'shark',
    'scorpion',
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
    'mixed_type': 3,
    'maybe': 'hyena',
    'maybe_null': 'camel',
},
    {
    'id': 127,
    'id_str': [
    '02',
    '04',
    '02',
],
    'text_data': '729e0cc9845c4aee8ade333c0ce124e3',
    'rand_digit': 8,
    'rand_number': 0.76142,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-27 18:04:29',
    'text_array': [
    'aab78c9612c84c45ab91e31ec114e3db',
    'd413f521f1ed46af8ad45e17346c0939',
],
    'words': 'rabbit sloth',
    'nested': {
    'id': 127,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    1,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'hyena',
    'tiger',
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
    'mixed_type': True,
    'maybe': 'shark',
},
    {
    'id': 128,
    'id_str': [
    '29',
    '01',
    '23',
    '04',
    '03',
],
    'text_data': '26fa010711de4a9e98fd6c9c719e2d44',
    'rand_digit': 0,
    'rand_number': 0.81741,
    'rand_signed_int': 5,
    'rand_datetime': '2000-03-10 20:56',
    'text_array': [
    '47d9ea905af14aa19c49945525a58dc9',
    '5ea1c7a4cc6b4ef09299f5c319c68a78',
],
    'words': 'lion lizard',
    'nested': {
    'id': 128,
    'rand_digit': 8,
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
    'word': 'horse',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 10,
},
],
},
    'nested_array': [
    [
    2,
],
    [
],
],
    'two_words': [
    'rabbit',
    'dragonfly',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 8,
    'maybe': 'pig',
    'maybe_null': 'deer',
},
    {
    'id': 129,
    'id_str': [
    '11',
    '28',
],
    'text_data': '6f395e92f34945b2af4279c4889b7493',
    'rand_digit': 8,
    'rand_number': 0.15655,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-11T19:33:37',
    'text_array': [
    '1c938a8361ab401e9d35877ee2820f3f',
    'b7f4051d65a6495a9a2c498bfc314abf',
],
    'words': 'zebra fly',
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
    'word': 'turtle',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fish',
    'ladybug',
],
    'city': {
    'name': 'Johannesburg',
    'geo': {
    'lat': -26.204103,
    'lon': 28.047305,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'mosquito',
},
    {
    'id': 130,
    'id_str': [
    '27',
    '01',
    '06',
],
    'text_data': '8fc12b14c0184ae88916af70b0d3db5a',
    'rand_digit': 6,
    'rand_number': 0.58773,
    'rand_signed_int': 7,
    'rand_datetime': '2000-07-08T11:13:19.001248',
    'text_array': [
    '0b2b3928115b484da12c2c4fb571a7d8',
    'ac5d179cc8824e0c97c77fd3b651ed1b',
],
    'words': 'zebra panda',
    'nested': {
    'id': 130,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
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
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 10,
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
    'ladybug',
    'snail',
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
    'mixed_type': 3,
    'maybe': 'turtle',
    'maybe_null': 'wolf',
},
    {
    'id': 131,
    'id_str': [
],
    'text_data': '82f45b7b6755426ba53de30ac6e99c84',
    'rand_digit': 7,
    'rand_number': 0.2251,
    'rand_signed_int': 9,
    'rand_datetime': '2001-01-15T14:03:40',
    'text_array': [
    'c6fdb91a55cd4513b9dc9f3bab1961ef',
    '09ca7ad65b3841998cb5e0d4d0c008d6',
],
    'words': 'sheep cow',
    'nested': {
    'id': 131,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 10,
},
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'lobster',
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
    'mixed_type': 0,
    'maybe_null': 'fox',
},
    {
    'id': 132,
    'id_str': [
    '30',
    '01',
],
    'text_data': '9e5398ea6780483a8e4231217796d6de',
    'rand_digit': 6,
    'rand_number': 0.60096,
    'rand_signed_int': -1,
    'rand_datetime': '2000-02-14 02:16',
    'text_array': [
    'b8110d348c504d95964ddf0fad0a9857',
    'cdc8f5f8c18142889c7829346550c309',
],
    'words': 'hyena fox',
    'nested': {
    'id': 132,
    'rand_digit': 4,
    'array': [
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
    'word': 'fish',
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'elephant',
    'deer',
],
    'city': {
    'name': 'Frankfurt',
    'geo': {
    'lat': 50.110922,
    'lon': 8.682127,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
    {
    'id': 133,
    'id_str': [
    '24',
    '08',
    '11',
    '09',
],
    'text_data': '61da0b75575d450d9f43e9e3ff9ef423',
    'rand_digit': 4,
    'rand_number': 0.49471,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-15 03:15:49',
    'text_array': [
    'b591d680a1584bffad22eb34849126d1',
    '7f4f46b8409f470f8a90b817d48b7852',
],
    'words': 'koala spider',
    'nested': {
    'id': 133,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'sloth',
    'fox',
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
    'mixed_type': 'sloth',
    'maybe': 'tiger',
},
    {
    'id': 134,
    'id_str': [
    '29',
    '16',
    '15',
    '21',
    '23',
],
    'text_data': '632b91840cd246b68dfb01a5c53504cc',
    'rand_digit': 6,
    'rand_number': 0.30331,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-04 04:21:21+0800',
    'text_array': [
    '76b234cb7eae422b89cd3316c383d7a5',
    'f2adf9091c5b4ff1ab64915880fe479e',
],
    'words': 'fly fly',
    'nested': {
    'id': 134,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 2,
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
    'word': 'shark',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ladybug',
    'rhino',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'goat',
},
    {
    'id': 135,
    'id_str': [
    '27',
    '21',
    '10',
    '17',
],
    'text_data': '599a5315be2545aba9dbbb734c3effac',
    'rand_digit': 2,
    'rand_number': 0.00331,
    'rand_signed_int': -10,
    'rand_datetime': '2000-03-17T14:13:05',
    'text_array': [
    '24a129f07da1414eadc96e8b0556e542',
    '574e44dd89c64872b117a199acc11ac0',
],
    'words': 'fox bird',
    'nested': {
    'id': 135,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 8,
},
],
},
    'nested_array': [
    [
    -5,
],
    [
],
    [
],
],
    'two_words': [
    'goat',
    'koala',
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
    'mixed_type': 'duck',
    'maybe': 'lobster',
    'maybe_null': 'mouse',
},
    {
    'id': 136,
    'id_str': [
    '15',
    '08',
    '17',
],
    'text_data': '747f7f2276f04c219c093352cad7409b',
    'rand_digit': 9,
    'rand_number': 0.80899,
    'rand_signed_int': 1,
    'rand_datetime': '2000-04-23 19:15:28+0800',
    'text_array': [
    'af952c353a064393ae448d773c753ff8',
    'b23892625e6d45799a3d0da04d1bc0f5',
],
    'words': 'hippo squid',
    'nested': {
    'id': 136,
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
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'ant',
    'wolf',
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
    'mixed_type': 'fox',
    'maybe': 'sloth',
    'maybe_null': 'spider',
},
    {
    'id': 137,
    'id_str': [
    '19',
],
    'text_data': 'af9a64fe8c25476cba34b2953375b286',
    'rand_digit': 1,
    'rand_number': 0.84197,
    'rand_signed_int': -2,
    'rand_datetime': '2001-01-12T14:22:54',
    'text_array': [
    '720709cac25d49e399e3ab12a5fb6060',
    '1173b0a4b12642579954ac64656fd945',
],
    'words': 'jaguar fox',
    'nested': {
    'id': 137,
    'rand_digit': 0,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'spider',
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
    'maybe_null': 'bee',
},
    {
    'id': 138,
    'id_str': [
    '09',
],
    'text_data': '23e18169ed4645baa30f9c04b87e8bc9',
    'rand_digit': 3,
    'rand_number': 0.54566,
    'rand_signed_int': -8,
    'rand_datetime': '2000-06-11 01:28',
    'text_array': [
    'd7982b30d5d84bb8ab2a12588c96305f',
    '9a658f0bdf1f4727bbcf9122aa1ae66d',
],
    'words': 'mosquito pig',
    'nested': {
    'id': 138,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 6,
},
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
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
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'crab',
},
    {
    'id': 139,
    'id_str': [
    '07',
    '26',
    '20',
],
    'text_data': 'f620d5d8790e4dde846af8524994d675',
    'rand_digit': 7,
    'rand_number': 0.48746,
    'rand_signed_int': 7,
    'rand_datetime': '2000-05-27',
    'text_array': [
    'bcb790b575fa490aab1932fb598a3d8c',
    '8307b88a68c249628ac6a8688f2ddb9a',
],
    'words': 'sheep ant',
    'nested': {
    'id': 139,
    'rand_digit': 5,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dog',
    'spider',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bird',
    'maybe_null': None,
},
    {
    'id': 140,
    'id_str': [
    '26',
    '25',
    '27',
    '02',
],
    'text_data': 'ec8213f63ecc4e9982bbd51b30ebe917',
    'rand_digit': 5,
    'rand_number': 0.15294,
    'rand_signed_int': 9,
    'rand_datetime': '2000-12-23T21:24:07+0800',
    'text_array': [
    '309b08dbed294bcfbc74884416ba2ac3',
    '2c2f67a59d0647a893357e921ad3bd5e',
],
    'words': 'lobster grasshopper',
    'nested': {
    'id': 140,
    'rand_digit': 4,
    'array': [
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 7,
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
    'hello',
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
    'word': 'dragonfly',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -4,
],
    [
],
    [
    4,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'monkey',
    'octopus',
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
    'mixed_type': 0.2873,
    'maybe_null': None,
},
    {
    'id': 141,
    'id_str': [
    '18',
    '21',
    '19',
    '01',
],
    'text_data': 'd4179423a6cc4a659a4730115e0f8256',
    'rand_digit': 9,
    'rand_number': 0.82021,
    'rand_signed_int': -4,
    'rand_datetime': '2000-09-07 17:21',
    'text_array': [
    '992e58263a5c4e71ab9469c3289696c9',
    '8d02dd16a78c4929bcfe7aa4b51092fd',
],
    'words': 'cheetah panda',
    'nested': {
    'id': 141,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 9,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 5,
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
    'word': 'duck',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -1,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'elephant',
    'fox',
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
    'mixed_type': 0.4709,
    'maybe': 'lobster',
},
    {
    'id': 142,
    'id_str': [
    '02',
],
    'text_data': 'dce8e57b2198488aa76e46bb8149dc04',
    'rand_digit': 2,
    'rand_number': 0.30369,
    'rand_signed_int': -1,
    'rand_datetime': '2001-01-03T23:17:22.629115-1200',
    'text_array': [
    'eff0002064d848e881a2a37c84e39f13',
    'a2957d8571e84f3ca0b22fb9f081720b',
],
    'words': 'hippo squid',
    'nested': {
    'id': 142,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'giraffe',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 9,
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
    'word': 'giraffe',
    'number': 6,
},
],
},
    'nested_array': [
    [
    -9,
],
],
    'two_words': [
    'rabbit',
    'frog',
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
    'maybe': 'fly',
    'maybe_null': None,
},
    {
    'id': 143,
    'id_str': [
    '29',
    '06',
],
    'text_data': '8cd456c4402f41d4aecdc93a44ba53cd',
    'rand_digit': 7,
    'rand_number': 0.83498,
    'rand_signed_int': -7,
    'rand_datetime': '2001-01-08 15:17:31+0700',
    'text_array': [
    '8e757660041448e1983516bdd9e18280',
    'eb7011dfea0049c68dcb26042530e29c',
],
    'words': 'zebra kangaroo',
    'nested': {
    'id': 143,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'gorilla',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'chicken',
    'butterfly',
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
    'mixed_type': 0.33521,
    'maybe_null': None,
},
    {
    'id': 144,
    'id_str': [
],
    'text_data': 'a8c8f42b0788493ab5e594d3eddf85c4',
    'rand_digit': 1,
    'rand_number': 0.21713,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-18',
    'text_array': [
    'ef3ebb99613249568b8f7a5251c7944f',
    'a7195baabef44fdb96ca20fcab319749',
],
    'words': 'scorpion dragonfly',
    'nested': {
    'id': 144,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    8,
],
    [
],
],
    'two_words': [
    'dog',
    'fox',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'elephant',
},
    {
    'id': 145,
    'id_str': [
    '28',
    '26',
    '05',
],
    'text_data': 'e6812585de8447c3b8029723cefa8338',
    'rand_digit': 3,
    'rand_number': 0.4925,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-30T21:50:39.279982',
    'text_array': [
    '271c3acf874747f7bc46be158a74c39e',
    'a3f9b229f58f4f57a617428c839be6ce',
],
    'words': 'mosquito lion',
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bird',
    'camel',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
},
    {
    'id': 146,
    'id_str': [
    '20',
],
    'text_data': '889f362223da429b8cdc34c37206adaf',
    'rand_digit': 9,
    'rand_number': 0.61181,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-01T16:41:11-0800',
    'text_array': [
    '92319feae07646b48efd42a6b8f79a94',
    '49e9b02f56e44108a4d77b33895bee0e',
],
    'words': 'hippo duck',
    'nested': {
    'id': 146,
    'rand_digit': 6,
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
    'word': 'wolf',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'rabbit',
    'camel',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': [
    11,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'monkey',
    'maybe_null': None,
},
    {
    'id': 147,
    'id_str': [
    '16',
],
    'text_data': '284810c5e645472ea73dee2a2c3c0a7c',
    'rand_digit': 2,
    'rand_number': 0.35068,
    'rand_signed_int': 2,
    'rand_datetime': '2000-02-11T11:52:18.981970+0700',
    'text_array': [
    '0169369acadf4edf8ed8001d8861e110',
    '7418e58b91714f0d980f88295032c299',
],
    'words': 'hyena dragonfly',
    'nested': {
    'id': 147,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'elephant',
    'number': 4,
},
],
},
    'nested_array': [
    [
    6,
],
],
    'two_words': [
    'gorilla',
    'dragonfly',
],
    'city': {
    'name': 'Frankfurt',
    'geo': {
    'lat': 50.110922,
    'lon': 8.682127,
},
},
    'rand_tuple': [
    21,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': None,
},
    {
    'id': 148,
    'id_str': [
    '13',
    '07',
    '25',
    '01',
],
    'text_data': '7891faa776404376808e7e09cb42e0ac',
    'rand_digit': 7,
    'rand_number': 0.37754,
    'rand_signed_int': -1,
    'rand_datetime': '2000-02-24',
    'text_array': [
    'ee438bfabf864276936c1bb98b194088',
    'eaf1169f9e1b4472bc866dde97172423',
],
    'words': 'bear rabbit',
    'nested': {
    'id': 148,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'wolf',
    'ladybug',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': [
    62,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'horse',
},
    {
    'id': 149,
    'id_str': [
    '04',
    '27',
    '27',
    '05',
],
    'text_data': '0e8042f5644c4033b3e7e2ad39704ef3',
    'rand_digit': 5,
    'rand_number': 0.32284,
    'rand_signed_int': -9,
    'rand_datetime': '2000-09-16 10:10:18+0700',
    'text_array': [
    '7ccf88991b9b41e7b391e63642c92aca',
    '58ea51a340eb4f2cb1919e428c0b2a9a',
],
    'words': 'jaguar lizard',
    'nested': {
    'id': 149,
    'rand_digit': 3,
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
    'hello',
],
    'word': 'mosquito',
    'number': 10,
},
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
    'hello',
],
    'word': 'deer',
    'number': 10,
},
],
},
    'nested_array': [
    [
    6,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hippo',
    'mosquito',
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
    'mixed_type': 3,
    'maybe': 'grasshopper',
    'maybe_null': 'horse',
},
    {
    'id': 150,
    'id_str': [
],
    'text_data': 'e05a6559139d4b85b331a1cd133492b2',
    'rand_digit': 4,
    'rand_number': 0.37875,
    'rand_signed_int': 10,
    'rand_datetime': '2000-12-10T02:57:02.366297+0100',
    'text_array': [
    '73889d73b8a2458bb826182c9e70fac1',
    '66c2f03b0fac444ea7e3782c19baa601',
],
    'words': 'elephant gorilla',
    'nested': {
    'id': 150,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'squid',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'mosquito',
    'hyena',
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
    'mixed_type': 'wolf',
    'maybe': 'monkey',
},
    {
    'id': 151,
    'id_str': [
    '09',
    '12',
],
    'text_data': '9264a70e28594263ae4f9e5836cbf3b2',
    'rand_digit': 7,
    'rand_number': 0.85813,
    'rand_signed_int': -1,
    'rand_datetime': '2000-05-27 16:14:30',
    'text_array': [
    '876d632ce0494ec3a85be34d24fd44b9',
    '84ca8249c6df4109b85ef9d37c2b1a2a',
],
    'words': 'grasshopper panda',
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
    'word': 'koala',
    'number': 7,
},
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
],
    'word': 'fish',
    'number': 9,
},
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
    'word': 'spider',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bee',
    'kangaroo',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 'koala',
    'maybe_null': 'lizard',
},
    {
    'id': 152,
    'id_str': [
],
    'text_data': '24f23b198fba42a8ad036fa40f7daec0',
    'rand_digit': 3,
    'rand_number': 0.70971,
    'rand_signed_int': 9,
    'rand_datetime': '2000-02-06 22:47:14',
    'text_array': [
    '0924631d78df42af8f7e49bbb45064f5',
    '88923107af6f4ce1bd695a546bed185d',
],
    'words': 'leopard mosquito',
    'nested': {
    'id': 152,
    'rand_digit': 4,
    'array': [
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
],
    'word': 'dog',
    'number': 5,
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
    'hello',
],
    'word': 'dolphin',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    2,
],
],
    'two_words': [
    'turtle',
    'mosquito',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': None,
},
    {
    'id': 153,
    'id_str': [
    '02',
],
    'text_data': 'a53f49ac66894daabb964c3447b94570',
    'rand_digit': 3,
    'rand_number': 0.98101,
    'rand_signed_int': 1,
    'rand_datetime': '2000-05-29 00:09:20-0900',
    'text_array': [
    '91d09dfbc1e04ee89d29c87fe556c2ae',
    '1c29d05d4e7c433b8336a9d9752299c4',
],
    'words': 'kangaroo elephant',
    'nested': {
    'id': 153,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lion',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mosquito',
    'fish',
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
    'mixed_type': None,
    'maybe_null': 'ant',
},
    {
    'id': 154,
    'id_str': [
    '26',
    '06',
],
    'text_data': 'e4cd00b92bff46e3822df93c1ab88e18',
    'rand_digit': 4,
    'rand_number': 0.88282,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-21T05:24:18-0500',
    'text_array': [
    '639301dbefe8474696a99621534df247',
    '83cb3887cdc44e7dac170d1943679e4a',
],
    'words': 'cheetah leopard',
    'nested': {
    'id': 154,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 10,
},
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
    'word': 'goat',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 1,
},
],
},
    'nested_array': [
    [
    5,
],
],
    'two_words': [
    'octopus',
    'lobster',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'dog',
},
    {
    'id': 155,
    'id_str': [
    '08',
    '02',
    '25',
    '01',
    '10',
],
    'text_data': '49c1faa34bf6455d90694f378bc84ba4',
    'rand_digit': 7,
    'rand_number': 0.21121,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-04T11:29:52-0700',
    'text_array': [
    'a272e7da88a944f581f9d8c13ec92580',
    '33b731c4536945279c058f30dd589899',
],
    'words': 'bee bird',
    'nested': {
    'id': 155,
    'rand_digit': 8,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 1,
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
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'shark',
    'turtle',
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
    'mixed_type': 6,
    'maybe': 'sloth',
    'maybe_null': 'lobster',
},
    {
    'id': 156,
    'id_str': [
    '11',
    '12',
    '16',
    '30',
],
    'text_data': '84723d2058164d2cb48a1f923513944a',
    'rand_digit': 7,
    'rand_number': 0.86285,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-15T01:11:12.630459',
    'text_array': [
    'e4e94923fcea4a9083b4e05c89a073a9',
    '8d75d0826e024c3da60eda3244039a61',
],
    'words': 'dog pig',
    'nested': {
    'id': 156,
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
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'sloth',
    'lizard',
],
    'city': {
    'name': 'Dubai',
    'geo': {
    'lat': 25.204849,
    'lon': 55.270783,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'monkey',
    'maybe_null': 'lion',
},
    {
    'id': 157,
    'id_str': [
    '29',
    '04',
    '20',
],
    'text_data': '6b5f2122b640461696bb9521631e4709',
    'rand_digit': 2,
    'rand_number': 0.8212,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-30 01:01:52+0100',
    'text_array': [
    '6dc87596b7d647339a630f5adf1ea19a',
    'e6f9baf1b2a14051886b4a1bbe0db6a0',
],
    'words': 'lion scorpion',
    'nested': {
    'id': 157,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 1,
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
    [
    9,
],
],
    'two_words': [
    'goat',
    'grasshopper',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': [
    42,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'gorilla',
},
    {
    'id': 158,
    'id_str': [
],
    'text_data': 'e67aa3ef5ed848e693e88247c3e00231',
    'rand_digit': 1,
    'rand_number': 0.38197,
    'rand_signed_int': -6,
    'rand_datetime': '2000-05-24T15:05:25-0600',
    'text_array': [
    '75aebbd150af4d26921ce2ccc83492e2',
    'ee414dd6be604c369bc546c5f8857ae4',
],
    'words': 'rabbit fly',
    'nested': {
    'id': 158,
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
    'number': 2,
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
],
    'word': 'crab',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'chicken',
    'leopard',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0,
    'maybe_null': 'bear',
},
    {
    'id': 159,
    'id_str': [
],
    'text_data': '7d5d108eb0e94569bb20b58d2c8e8ed0',
    'rand_digit': 5,
    'rand_number': 0.4501,
    'rand_signed_int': 5,
    'rand_datetime': '2000-08-18T23:17:08.216610',
    'text_array': [
    'f9916fe0aeca471592c59faeceff40b7',
    '893a7f6b7fd74259924e142f8c987fb3',
],
    'words': 'lion kangaroo',
    'nested': {
    'id': 159,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ant',
    'number': 9,
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
    0,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lion',
    'snail',
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
    'mixed_type': None,
    'maybe': 'wolf',
    'maybe_null': 'dragonfly',
},
    {
    'id': 160,
    'id_str': [
    '03',
],
    'text_data': 'a1ec8f81c2d2404cbb2e9a0069a40401',
    'rand_digit': 4,
    'rand_number': 0.0427,
    'rand_signed_int': 5,
    'rand_datetime': '2000-01-30T22:52:15.652707',
    'text_array': [
    '73b4330819f34e15ac34ec0d6169d19e',
    'f8b74918714743b69e0df41c46ce568d',
],
    'words': 'kangaroo bear',
    'nested': {
    'id': 160,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -9,
],
],
    'two_words': [
    'shark',
    'elephant',
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
    'mixed_type': 'squid',
    'maybe_null': 'koala',
},
    {
    'id': 161,
    'id_str': [
    '07',
    '22',
    '08',
    '03',
],
    'text_data': 'b965c34be61444e69a4048f6e9028d90',
    'rand_digit': 9,
    'rand_number': 0.16533,
    'rand_signed_int': 1,
    'rand_datetime': '2000-12-08T22:06:37.802299',
    'text_array': [
    'be49dcf4e49a443c9b92c916118f9df2',
    'eb924fa2e8da47cdb3f30115e335d5ac',
],
    'words': 'rabbit squid',
    'nested': {
    'id': 161,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'tiger',
    'number': 1,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dog',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bear',
    'dolphin',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.55531,
},
    {
    'id': 162,
    'id_str': [
],
    'text_data': 'ea0d1cd51ac04bba9fa1aac73363cbe6',
    'rand_digit': 5,
    'rand_number': 0.5004,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-18 11:09',
    'text_array': [
    'f790435075e444b48fdd6f6f7c9eb1d6',
    'e31072069f6c4072b980a27204acf3c3',
],
    'words': 'snail fly',
    'nested': {
    'id': 162,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'octopus',
    'panda',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.47443,
    'maybe': 'snail',
    'maybe_null': 'pig',
},
    {
    'id': 163,
    'id_str': [
    '21',
    '23',
    '14',
],
    'text_data': '19d580d0643e476c9dfc581648dca2ef',
    'rand_digit': 9,
    'rand_number': 0.42002,
    'rand_signed_int': -9,
    'rand_datetime': '2000-09-09T12:33:30.155920',
    'text_array': [
    'c6e80f7c0af647cfb8eaf39b2c5ab293',
    'd67781d4f86b4737b9e0fec46263d11b',
],
    'words': 'bear hyena',
    'nested': {
    'id': 163,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 3,
},
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
    'word': 'whale',
    'number': 1,
},
    {
    'nested_empty': None,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lizard',
    'monkey',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'wolf',
},
    {
    'id': 164,
    'id_str': [
    '26',
    '06',
],
    'text_data': '8d99cf4b9ed14b619294bb9fd5e513b8',
    'rand_digit': 4,
    'rand_number': 0.31153,
    'rand_signed_int': -6,
    'rand_datetime': '2000-05-09',
    'text_array': [
    'edee4659e6cb41bd89e3c6a4d11bf563',
    'e01a81656b1a40b889c1d34fa250f351',
],
    'words': 'kangaroo ladybug',
    'nested': {
    'id': 164,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'deer',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -2,
],
],
    'two_words': [
    'mosquito',
    'bee',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': [
    69,
],
    'rand_bool': True,
    'mixed_type': 0.40139,
},
    {
    'id': 165,
    'id_str': [
],
    'text_data': '86340c99c6184ec081523a7e54176e0d',
    'rand_digit': 9,
    'rand_number': 0.46016,
    'rand_signed_int': 0,
    'rand_datetime': '2000-10-18T10:02:30-0200',
    'text_array': [
    '1f46b7fb8e1448988a746712dfd3816d',
    '326bb03b14134851949b164b68e8a4b6',
],
    'words': 'hippo tiger',
    'nested': {
    'id': 165,
    'rand_digit': 0,
    'array': [
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
    'squid',
    'panda',
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
    'mixed_type': 'fox',
    'maybe_null': 'tiger',
},
    {
    'id': 166,
    'id_str': [
    '02',
    '08',
    '24',
    '06',
],
    'text_data': 'd7a359c23fb0472391cc2f52d57b98db',
    'rand_digit': 2,
    'rand_number': 0.06094,
    'rand_signed_int': -9,
    'rand_datetime': '2000-08-22 16:05',
    'text_array': [
    '941eb0a65da5416d9d1534c51a5a5ebd',
    '171aec256f1342d6990cb6a4703f5b4a',
],
    'words': 'butterfly jaguar',
    'nested': {
    'id': 166,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
    -6,
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'goat',
    'butterfly',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'bear',
},
    {
    'id': 167,
    'id_str': [
    '22',
],
    'text_data': '94a08c6ba6cd435790f4f92863144ece',
    'rand_digit': 8,
    'rand_number': 0.98621,
    'rand_signed_int': -6,
    'rand_datetime': '2000-11-29 14:49',
    'text_array': [
    '07a2efcd5e234fb1907c4266dac01bfb',
    '2fdf549e963b441e94fbe6e263f5b58f',
],
    'words': 'dog shark',
    'nested': {
    'id': 167,
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
    'number': 5,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 2,
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
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dog',
    'lion',
],
    'city': {
    'name': 'London',
    'geo': {
    'lat': 51.507351,
    'lon': -0.127758,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'camel',
    'maybe_null': 'kangaroo',
},
    {
    'id': 168,
    'id_str': [
    '22',
    '06',
    '18',
],
    'text_data': '666bed31a0784c59a7a10d6c32d50325',
    'rand_digit': 6,
    'rand_number': 0.54317,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-17T17:06:48.252673-1000',
    'text_array': [
    '24997667b8eb4f94a6b1ac8e2018849d',
    'a207cfb2742e4b85acce6afa9fa52384',
],
    'words': 'butterfly mosquito',
    'nested': {
    'id': 168,
    'rand_digit': 0,
    'array': [
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
    'word': 'snake',
    'number': 5,
},
    {
    'nested_empty': None,
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
    'word': 'spider',
    'number': 1,
},
],
},
    'nested_array': [
    [
    8,
],
],
    'two_words': [
    'dragonfly',
    'squid',
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
    'mixed_type': 0.51604,
    'maybe': 'spider',
},
    {
    'id': 169,
    'id_str': [
    '13',
    '21',
    '25',
    '06',
],
    'text_data': 'd1867e731f52422594f6ec1500d893ee',
    'rand_digit': 9,
    'rand_number': 0.93209,
    'rand_signed_int': 8,
    'rand_datetime': '2000-06-10T00:49:15.754080-1100',
    'text_array': [
    '6223915725604cff9f3d43c83dd31f75',
    'a1c45823620e4dd6b9165b7ec1945813',
],
    'words': 'kangaroo wolf',
    'nested': {
    'id': 169,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 3,
},
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lion',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ape',
    'elephant',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': [
    75,
],
    'rand_bool': False,
    'mixed_type': None,
},
    {
    'id': 170,
    'id_str': [
    '12',
    '04',
    '07',
],
    'text_data': '74a0a5230905439ab3931ad5b1588942',
    'rand_digit': 9,
    'rand_number': 0.7858,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-25T00:38:25',
    'text_array': [
    'b15ea2d174464b03a1bfe552ab08334a',
    '0e8f72245401417cbca1f098e2e2d97d',
],
    'words': 'cow ladybug',
    'nested': {
    'id': 170,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'fox',
    'kangaroo',
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
    'maybe': 'hippo',
},
    {
    'id': 171,
    'id_str': [
],
    'text_data': 'ed603d9d62664236a1688900bcb26fd7',
    'rand_digit': 1,
    'rand_number': 0.10048,
    'rand_signed_int': -9,
    'rand_datetime': '2000-07-30',
    'text_array': [
    '32b0f74a1601454a85596339b51df1cd',
    'b23d741c974342a48875d570c4c88bb3',
],
    'words': 'wolf bee',
    'nested': {
    'id': 171,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'bear',
    'butterfly',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'horse',
},
    {
    'id': 172,
    'id_str': [
    '25',
    '26',
    '04',
    '05',
],
    'text_data': '90f14da2d7484465b609f38175219f7e',
    'rand_digit': 7,
    'rand_number': 0.16816,
    'rand_signed_int': -3,
    'rand_datetime': '2000-08-09 01:12:00.765853-0600',
    'text_array': [
    '451c9d9bb4584a25a1dae21a6433980f',
    'b4b217a69f174519aadf4ad141aa637b',
],
    'words': 'scorpion frog',
    'nested': {
    'id': 172,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'whale',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ant',
    'snail',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': [
    59,
],
    'rand_bool': True,
    'mixed_type': 2,
    'maybe': 'whale',
    'maybe_null': 'pig',
},
    {
    'id': 173,
    'id_str': [
    '01',
    '04',
],
    'text_data': '8f5c70ff80b4431e99c5eef1bea00827',
    'rand_digit': 0,
    'rand_number': 0.48902,
    'rand_signed_int': -9,
    'rand_datetime': '2000-03-04 04:09:16.646214-0800',
    'text_array': [
    'c8433d00df054f0daa65f01b83cc95e6',
    '144491788f174276a92f62cac0021a9d',
],
    'words': 'hyena grasshopper',
    'nested': {
    'id': 173,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'tiger',
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
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'elephant',
    'number': 9,
},
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
    [
    9,
],
],
    'two_words': [
    'jaguar',
    'whale',
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
    'mixed_type': None,
    'maybe': 'frog',
},
    {
    'id': 174,
    'id_str': [
    '13',
    '24',
],
    'text_data': '0207471c131c4b32a7a23b4df32124f6',
    'rand_digit': 1,
    'rand_number': 0.48712,
    'rand_signed_int': 3,
    'rand_datetime': '2000-12-02T13:51:14.453286',
    'text_array': [
    'd5635a1f4e24436dbdc8d7079d6c945a',
    '6daa2d5d7c304da1bfbb5064bd2df0ff',
],
    'words': 'horse chicken',
    'nested': {
    'id': 174,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'rabbit',
    'cheetah',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': [
    83,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'rhino',
},
    {
    'id': 175,
    'id_str': [
    '02',
    '23',
    '03',
],
    'text_data': '571bb62fc5fc4177a53b17f1423cd067',
    'rand_digit': 8,
    'rand_number': 0.69316,
    'rand_signed_int': 8,
    'rand_datetime': '2000-04-20T22:17:28.949614+0900',
    'text_array': [
    '15c16f8de81e43cba72d5bc9d6bb80fa',
    '7058eb0124e64a19ba19f89b501ca669',
],
    'words': 'grasshopper ant',
    'nested': {
    'id': 175,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'ant',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'jaguar',
    'ladybug',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': [
    95,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': None,
},
    {
    'id': 176,
    'id_str': [
    '02',
    '19',
    '03',
],
    'text_data': 'e39946f24372416a9c31e3baa60738ca',
    'rand_digit': 2,
    'rand_number': 0.53493,
    'rand_signed_int': -10,
    'rand_datetime': '2000-05-20 11:23:31-0700',
    'text_array': [
    'bb1361a584a0488b961213bef255c70f',
    'd6cc6039b5594f92bd42b8dd8f3ac5d1',
],
    'words': 'hippo squid',
    'nested': {
    'id': 176,
    'rand_digit': 3,
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
    'word': 'gorilla',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'scorpion',
    'grasshopper',
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
    'mixed_type': 0.01548,
    'maybe_null': 'chicken',
},
    {
    'id': 177,
    'id_str': [
],
    'text_data': 'e77ac8c11fb14a0e80fb9b158e4f0401',
    'rand_digit': 6,
    'rand_number': 0.2452,
    'rand_signed_int': -3,
    'rand_datetime': '2000-05-19',
    'text_array': [
    'f44e5f532e974537884526fc18cf70a8',
    '23c3ba0ad09342608ae76ea0dc03639e',
],
    'words': 'zebra cow',
    'nested': {
    'id': 177,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'turtle',
    'turtle',
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
    'mixed_type': None,
    'maybe': 'crab',
    'maybe_null': None,
},
    {
    'id': 178,
    'id_str': [
    '30',
],
    'text_data': '4c62877192bc46c699cdc1400838464e',
    'rand_digit': 9,
    'rand_number': 0.54082,
    'rand_signed_int': -1,
    'rand_datetime': '2000-01-31T17:20:13.802965',
    'text_array': [
    'cad82365b55e4ef680244a18fada4e54',
    '6ed172ab63094f1e966b870a277bbaf4',
],
    'words': 'shark shark',
    'nested': {
    'id': 178,
    'rand_digit': 4,
    'array': [
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
    'word': 'elephant',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 10,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'deer',
    'ape',
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
    'mixed_type': 7,
    'maybe_null': None,
},
    {
    'id': 179,
    'id_str': [
    '20',
    '20',
    '08',
    '23',
],
    'text_data': 'fa749a4567af4b078cd470b13fba4ceb',
    'rand_digit': 1,
    'rand_number': 0.71463,
    'rand_signed_int': -9,
    'rand_datetime': '2000-03-20T07:18:05',
    'text_array': [
    '8fb35cfca81248f28eae329fc0abdc87',
    '2c0e2ecd5e5f474388083920f51f4a28',
],
    'words': 'giraffe pig',
    'nested': {
    'id': 179,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lizard',
    'camel',
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
    'mixed_type': 0.08487,
    'maybe_null': None,
},
    {
    'id': 180,
    'id_str': [
    '08',
    '11',
    '19',
],
    'text_data': '9d3969e9a3f34178b564f99758b49cd3',
    'rand_digit': 2,
    'rand_number': 0.32705,
    'rand_signed_int': 9,
    'rand_datetime': '2000-12-13T23:33:27-0500',
    'text_array': [
    '84938f6945d44889a2fa2cbfdae932c5',
    '00ba575ab7ae4e47b15a88c01663f52c',
],
    'words': 'squid kangaroo',
    'nested': {
    'id': 180,
    'rand_digit': 8,
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
    'nested_empty': [
    'hello',
],
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
],
    'word': 'fish',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'frog',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'giraffe',
    'lion',
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
    'mixed_type': 'cheetah',
    'maybe': 'elephant',
    'maybe_null': 'goat',
},
    {
    'id': 181,
    'id_str': [
    '02',
    '24',
],
    'text_data': '11db88372d234a1288b67e10852d9023',
    'rand_digit': 4,
    'rand_number': 0.43444,
    'rand_signed_int': 0,
    'rand_datetime': '2000-05-12T21:47:58',
    'text_array': [
    '87a3058cbb924dd49c6dc4251e5a8d30',
    '31402788aaf64469a9739553d03f7eea',
],
    'words': 'dog kangaroo',
    'nested': {
    'id': 181,
    'rand_digit': 8,
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
],
    'word': 'giraffe',
    'number': 1,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'octopus',
    'zebra',
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
    'mixed_type': 0.76854,
    'maybe': 'dragonfly',
},
    {
    'id': 182,
    'id_str': [
    '20',
],
    'text_data': 'a9d7f25e12964882821338b97678ebe4',
    'rand_digit': 8,
    'rand_number': 0.70798,
    'rand_signed_int': 2,
    'rand_datetime': '2000-06-01 21:08',
    'text_array': [
    '9b719343356a4fcdafbb3dd1aa97c4eb',
    '1689ad077980405796e546f9f53cd88f',
],
    'words': 'snail elephant',
    'nested': {
    'id': 182,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    [
    -2,
],
    [
],
    [
    -5,
],
    [
],
],
    'two_words': [
    'sheep',
    'lobster',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
    {
    'id': 183,
    'id_str': [
    '28',
    '07',
],
    'text_data': 'd7843b40db4a42858b6a531f43687bcc',
    'rand_digit': 1,
    'rand_number': 0.52557,
    'rand_signed_int': -10,
    'rand_datetime': '2000-07-28T06:59:37.983658',
    'text_array': [
    'f38a26198b50463b8a8c7d676d427ec1',
    'fd00a991a90e4e2f893fc98b9781454d',
],
    'words': 'panda panda',
    'nested': {
    'id': 183,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'deer',
    'giraffe',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 4,
    'maybe': 'mosquito',
    'maybe_null': 'gorilla',
},
    {
    'id': 184,
    'id_str': [
    '04',
],
    'text_data': '112361c883fd436ebbdd237219192c60',
    'rand_digit': 7,
    'rand_number': 0.90613,
    'rand_signed_int': -2,
    'rand_datetime': '2000-04-12T13:38:34+1000',
    'text_array': [
    'ab44c88deb9d49c0bc001d3067450704',
    '7f7f319559e7485783272bca462a3b15',
],
    'words': 'lobster leopard',
    'nested': {
    'id': 184,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'shark',
    'dolphin',
],
    'city': {
    'name': 'Barcelona',
    'geo': {
    'lat': 41.385064,
    'lon': 2.173403,
},
},
    'rand_tuple': [
    60,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'bird',
},
    {
    'id': 185,
    'id_str': [
],
    'text_data': '50061e54ada948eb83a061091bb563a3',
    'rand_digit': 7,
    'rand_number': 0.48707,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-04T17:18:16-0300',
    'text_array': [
    'cb218e261f614a469e04470874ed3062',
    '76e972c086b34e12bbd3051d2e05e187',
],
    'words': 'panda duck',
    'nested': {
    'id': 185,
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
    'nested_empty': None,
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
],
    'word': 'panda',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'bee',
    'koala',
],
    'city': {
    'name': 'Cardiff',
    'geo': {
    'lat': 51.481581,
    'lon': -3.17909,
},
},
    'rand_tuple': [
    48,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': None,
},
    {
    'id': 186,
    'id_str': [
    '09',
    '01',
    '13',
    '27',
],
    'text_data': '8d74a3c0bbcd44bda70c85b00b7ea4c3',
    'rand_digit': 5,
    'rand_number': 0.7944,
    'rand_signed_int': -4,
    'rand_datetime': '2000-08-30 11:50:30.622480',
    'text_array': [
    'ad83962b33094094946ef91e52ee9f82',
    'ff4b89d3b25045668b556641952a70e6',
],
    'words': 'chicken fox',
    'nested': {
    'id': 186,
    'rand_digit': 9,
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
    'word': 'pig',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'duck',
    'squid',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.65185,
    'maybe': 'monkey',
    'maybe_null': 'deer',
},
    {
    'id': 187,
    'id_str': [
    '21',
],
    'text_data': 'f646b90e849741e98e3a603ade676bca',
    'rand_digit': 6,
    'rand_number': 0.03835,
    'rand_signed_int': 3,
    'rand_datetime': '2000-03-26T01:22:00',
    'text_array': [
    '97b41f7f6f6f45ebbe81956955ee005f',
    '4cc86b9c3b7e44fd9c499ed3ef08c792',
],
    'words': 'wolf horse',
    'nested': {
    'id': 187,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'camel',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 9,
},
],
},
    'nested_array': [
    [
    10,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snake',
    'fish',
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
    'maybe': 'jaguar',
    'maybe_null': 'cat',
},
    {
    'id': 188,
    'id_str': [
    '21',
],
    'text_data': 'ceda53b069bb4557b750da4ce324128f',
    'rand_digit': 4,
    'rand_number': 0.38506,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-15T06:48:22.127548-11:00',
    'text_array': [
    '74ce4f71943c408fb138b81e1ec5c0c9',
    '214c2e5a9a0f43b0ba6cde93f8552702',
],
    'words': 'rhino pig',
    'nested': {
    'id': 188,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    10,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'elephant',
    'bird',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': [
    89,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'fish',
    'maybe_null': 'duck',
},
    {
    'id': 189,
    'id_str': [
    '30',
    '25',
],
    'text_data': 'ed28198db0544c2c99654ef3b238e961',
    'rand_digit': 3,
    'rand_number': 0.37395,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-30 05:27:46',
    'text_array': [
    '5a1765e1f2c2420b821758e9aca4cce5',
    'd536d112e09c4f2abd68e262f2175d27',
],
    'words': 'lobster deer',
    'nested': {
    'id': 189,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'lobster',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 9,
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
    [
    9,
],
],
    'two_words': [
    'cat',
    'mosquito',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': [
    38,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'lizard',
},
    {
    'id': 190,
    'id_str': [
    '25',
    '25',
    '02',
    '09',
],
    'text_data': 'c521dc019c2a49388abefc4e69c4773a',
    'rand_digit': 4,
    'rand_number': 0.15289,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-04 11:57:07.476432+0300',
    'text_array': [
    '530d5236903b42969f55bd186d583918',
    '0fef3417324b4ba18c86ca22b4264974',
],
    'words': 'chicken fly',
    'nested': {
    'id': 190,
    'rand_digit': 1,
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
    'word': 'dog',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'frog',
    'mosquito',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': [
    88,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
},
    {
    'id': 191,
    'id_str': [
    '21',
    '07',
    '19',
],
    'text_data': '15704710636a498b89d58e9a932203cb',
    'rand_digit': 6,
    'rand_number': 0.20622,
    'rand_signed_int': 5,
    'rand_datetime': '2000-01-05 14:26:56',
    'text_array': [
    '19516c339edd4662b265e0eecf0bd437',
    'ec5a253e80434ded93f176890ce30b2f',
],
    'words': 'duck ape',
    'nested': {
    'id': 191,
    'rand_digit': 0,
    'array': [
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
    'word': 'tiger',
    'number': 1,
},
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    6,
],
],
    'two_words': [
    'giraffe',
    'elephant',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': [
    54,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
    {
    'id': 192,
    'id_str': [
    '10',
    '23',
],
    'text_data': '00115758d9eb4d9f80715bce5d88b23c',
    'rand_digit': 1,
    'rand_number': 0.69299,
    'rand_signed_int': -7,
    'rand_datetime': '2001-01-24 14:05',
    'text_array': [
    '5997403f16e6425db47d2047387ad19c',
    'c0c1f00f792f40379b8a12cb1f17e658',
],
    'words': 'crab ape',
    'nested': {
    'id': 192,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'lobster',
    'frog',
],
    'city': {
    'name': 'Seoul',
    'geo': {
    'lat': 37.566535,
    'lon': 126.977969,
},
},
    'rand_tuple': [
    0,
],
    'rand_bool': False,
    'mixed_type': 0,
    'maybe_null': None,
},
    {
    'id': 193,
    'id_str': [
],
    'text_data': '6b6c736ffe8b4e72b8d225a0afde44dd',
    'rand_digit': 1,
    'rand_number': 0.4248,
    'rand_signed_int': 7,
    'rand_datetime': '2000-02-02 11:27:42',
    'text_array': [
    '5bc58cab8e1f41fda6d3bad3926b5dc7',
    '6c075b3f0feb4a7784a3a00159fe6386',
],
    'words': 'crab horse',
    'nested': {
    'id': 193,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'sheep',
    'dolphin',
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
    'mixed_type': True,
    'maybe_null': None,
},
    {
    'id': 194,
    'id_str': [
    '12',
    '15',
    '10',
    '08',
],
    'text_data': '379c7cda07a44354a88d819602b8fe6d',
    'rand_digit': 6,
    'rand_number': 0.11482,
    'rand_signed_int': 1,
    'rand_datetime': '2000-08-25T07:59:39.662805',
    'text_array': [
    'fcce3f5f361a4eb5921831f86638408c',
    'a7a08794404244008b6bb0558af9c1e0',
],
    'words': 'deer scorpion',
    'nested': {
    'id': 194,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'leopard',
    'mouse',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'chicken',
    'maybe_null': 'sheep',
},
    {
    'id': 195,
    'id_str': [
    '03',
],
    'text_data': '10e46a0011934459af0f47edc922d24d',
    'rand_digit': 4,
    'rand_number': 0.63479,
    'rand_signed_int': 3,
    'rand_datetime': '2000-05-30 10:04:33.847111-1000',
    'text_array': [
    '477c799578c54cff847f09172743ceb8',
    '57f89de7702944f0b5caf007ec129abb',
],
    'words': 'leopard hyena',
    'nested': {
    'id': 195,
    'rand_digit': 1,
    'array': [
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
    'nested_array': [
],
    'two_words': [
    'camel',
    'giraffe',
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
    'mixed_type': True,
},
    {
    'id': 196,
    'id_str': [
    '17',
],
    'text_data': '16c76b5dc01b4736896ea1b77323d9cd',
    'rand_digit': 3,
    'rand_number': 0.11332,
    'rand_signed_int': 7,
    'rand_datetime': '2000-02-28 06:40:13.783168',
    'text_array': [
    'a597a8fbf86d41c29a574ab654b8c7de',
    'aee1bf52149e491f8123155ab7e7e101',
],
    'words': 'wolf hippo',
    'nested': {
    'id': 196,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'lion',
    'snail',
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
    'mixed_type': None,
    'maybe_null': None,
},
    {
    'id': 197,
    'id_str': [
    '08',
],
    'text_data': '71e0ea372bd642ecb38fba683bf1aec0',
    'rand_digit': 4,
    'rand_number': 0.87243,
    'rand_signed_int': 9,
    'rand_datetime': '2000-07-09 14:25:09',
    'text_array': [
    '0fb4333aabfc4edc9eb54ee3512427c9',
    '9d824879839b4bbd99676611729e0994',
],
    'words': 'tiger chicken',
    'nested': {
    'id': 197,
    'rand_digit': 2,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 2,
},
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
],
    'word': 'ape',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
    1,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'giraffe',
    'dog',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
},
    {
    'id': 198,
    'id_str': [
    '14',
    '07',
    '01',
],
    'text_data': '4e409f6a0f96489b8d6b4084834c3899',
    'rand_digit': 2,
    'rand_number': 0.24129,
    'rand_signed_int': -10,
    'rand_datetime': '2000-01-29 00:10',
    'text_array': [
    '44ddbd70eac945acb2ec62ce949383e7',
    '53a84cd49e7f41f09ec90822f663e840',
],
    'words': 'rabbit grasshopper',
    'nested': {
    'id': 198,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -5,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ape',
    'bee',
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
    'mixed_type': 'rabbit',
    'maybe': 'octopus',
    'maybe_null': 'mosquito',
},
    {
    'id': 199,
    'id_str': [
    '28',
    '28',
    '11',
    '08',
],
    'text_data': '63454daa108c4eed8b43a7712117b611',
    'rand_digit': 3,
    'rand_number': 0.4628,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-15T20:28:25+0700',
    'text_array': [
    '6a2000ac7c78444d8ab8ffec89a2fe7e',
    '175521e8abc84d268cba5b2c857d3445',
],
    'words': 'goat lizard',
    'nested': {
    'id': 199,
    'rand_digit': 0,
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
],
    'word': 'frog',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'rabbit',
    'snake',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.37145,
    'maybe_null': 'pig',
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
    'content-length': '86',
}
        
        # 原始请求内容
        original_content = {
    'limit': 1,
    'filter': {
    'must': [
    {
    'has_id': [
    0,
],
},
],
},
    'with_payload': True,
    'with_vector': False,
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
        """测试请求 4 - POST http://localhost:6333/collections/congruence_test_collection/points/scroll"""
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_sparse_updates.test_upsert')
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
    test = TestSparseUpdatestestUpsert()
    test.run_tests()
