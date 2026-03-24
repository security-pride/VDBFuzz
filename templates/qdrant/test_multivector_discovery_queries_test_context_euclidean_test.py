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
logger = logging.getLogger('vdb_fuzzer.test.test_multivector_discovery_queries_test_context_euclidean')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_multivector_discovery_queries.test_context_euclidean"
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



class TestMultivectorDiscoveryQueriestestContextEuclidean:
    """自动生成的VDB模糊测试类 - test_multivector_discovery_queries.test_context_euclidean"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_multivector_discovery_queries.test_context_euclidean"
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
    'content-length': '535349',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 100,
    'id_str': [
    '11',
    '20',
    '09',
],
    'text_data': '910e1a183b83455781c12696d81403bc',
    'rand_digit': 2,
    'rand_number': 0.76011,
    'rand_signed_int': -2,
    'rand_datetime': '2000-03-03T16:21:51.202202',
    'text_array': [
    '826f8d2e4c484195abd5993eae9232b7',
    'e45435250c8742bab36f7797dcd5b630',
],
    'words': 'shark jaguar',
    'nested': {
    'id': 100,
    'rand_digit': 6,
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
    'word': 'grasshopper',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'rhino',
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
    'mixed_type': 'ape',
    'maybe_null': None,
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 101,
    'id_str': [
    '26',
    '11',
],
    'text_data': '8eae42f18c0041f7a703bfaade3e4ea3',
    'rand_digit': 1,
    'rand_number': 0.55071,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-28T23:36:09-0800',
    'text_array': [
    '5f3c64d4d22f42d6b448fbbe2ad8c678',
    '9736de6935464760ba5df58a86415b0f',
],
    'words': 'bee pig',
    'nested': {
    'id': 101,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'butterfly',
    'whale',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': [
    22,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'crab',
},
},
    {
    'id': 2,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 102,
    'id_str': [
    '30',
],
    'text_data': '1c77ef548b834fee97c3cbffcb4f8f94',
    'rand_digit': 7,
    'rand_number': 0.91984,
    'rand_signed_int': 3,
    'rand_datetime': '2000-06-21 21:27:19.245424',
    'text_array': [
    'fd9a780d48f14e9fbfe5f2c0800d6b5d',
    'a1a0828e103c4600aa330ff690df244f',
],
    'words': 'tiger wolf',
    'nested': {
    'id': 102,
    'rand_digit': 2,
    'array': [
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
    'hello',
],
    'word': 'dog',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'scorpion',
    'shark',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 103,
    'id_str': [
    '26',
],
    'text_data': 'eac1b1974807497ba19c079573079a21',
    'rand_digit': 8,
    'rand_number': 0.64771,
    'rand_signed_int': 3,
    'rand_datetime': '2000-02-07 13:37:26',
    'text_array': [
    '2cf7686724e44b2293fcf3a5c8982642',
    '880c86cfdd014dd1831766fdb47b9d98',
],
    'words': 'dog duck',
    'nested': {
    'id': 103,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'monkey',
    'camel',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'fox',
    'maybe_null': 'leopard',
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 104,
    'id_str': [
    '23',
    '15',
    '12',
    '14',
],
    'text_data': '70913fc76e4e40dca25a37da822839f4',
    'rand_digit': 8,
    'rand_number': 0.3795,
    'rand_signed_int': -1,
    'rand_datetime': '2000-10-12 16:38:16',
    'text_array': [
    '85fc2a2600584225bd2de691c76821d8',
    '2500330e51194a06a4ad1782574d584d',
],
    'words': 'bird ant',
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
    'word': 'panda',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    [
    -2,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -2,
],
],
    'two_words': [
    'goat',
    'bear',
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
    'mixed_type': 'gorilla',
    'maybe_null': None,
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 105,
    'id_str': [
    '22',
    '15',
    '03',
    '18',
    '19',
],
    'text_data': '0ae87ccaf6474fc89c4ab188c23f56a7',
    'rand_digit': 9,
    'rand_number': 0.35463,
    'rand_signed_int': 7,
    'rand_datetime': '2000-07-05T01:57:06.268835+0500',
    'text_array': [
    '400059fbf2de44f7be94fdcbdfc81db0',
    'f000a33b6076473ebfc372ba09e176b0',
],
    'words': 'rabbit frog',
    'nested': {
    'id': 105,
    'rand_digit': 1,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'chicken',
    'hyena',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.65203,
    'maybe': 'elephant',
    'maybe_null': None,
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 106,
    'id_str': [
    '10',
    '16',
    '03',
    '26',
],
    'text_data': 'dc2ac7b209dd43d5992135ff2837d3fa',
    'rand_digit': 4,
    'rand_number': 0.31793,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-18 20:45:14.656828-1000',
    'text_array': [
    '87b5e6ed00e14ba591c25fe4c936b81b',
    '50cbe194b4094f4ea3c558f6c9738b92',
],
    'words': 'fly mouse',
    'nested': {
    'id': 106,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    10,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    9,
],
],
    'two_words': [
    'cheetah',
    'whale',
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
    'mixed_type': 'spider',
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 107,
    'id_str': [
    '13',
    '12',
    '13',
    '24',
    '19',
],
    'text_data': '3cc6761b2c7c4c468ee0071583547224',
    'rand_digit': 8,
    'rand_number': 0.6591,
    'rand_signed_int': 8,
    'rand_datetime': '2000-08-12 13:24:31.508807+0600',
    'text_array': [
    '59fd6bdb9aac4a09aace0118892ad2d2',
    '0cf57b9677ec4b3290fd9901a3f1d621',
],
    'words': 'elephant dragonfly',
    'nested': {
    'id': 107,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'zebra',
    'butterfly',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 'lizard',
    'maybe_null': 'mosquito',
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 108,
    'id_str': [
    '20',
    '29',
    '03',
    '26',
    '21',
],
    'text_data': '2bd4f53cbe064bfcbbd1cdab40b271ce',
    'rand_digit': 7,
    'rand_number': 0.29331,
    'rand_signed_int': -2,
    'rand_datetime': '2000-10-05 00:55:08+0600',
    'text_array': [
    '698fe07c0c8d44198f9f50203f51efff',
    '68fd09fd6ccd4c7881fed4bb714a9a5b',
],
    'words': 'hyena dolphin',
    'nested': {
    'id': 108,
    'rand_digit': 3,
    'array': [
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
],
    'word': 'hyena',
    'number': 10,
},
],
},
    'nested_array': [
    [
    5,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'octopus',
    'lizard',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': [
    22,
],
    'rand_bool': False,
    'mixed_type': False,
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 109,
    'id_str': [
    '15',
    '17',
    '25',
],
    'text_data': 'ed25ea86c323448ea2ac1ed41cc556e4',
    'rand_digit': 6,
    'rand_number': 0.52247,
    'rand_signed_int': 2,
    'rand_datetime': '2000-03-31T06:50:19+0000',
    'text_array': [
    'c979bd01af874995ad6bd302f4c63fb4',
    '0992e6b58ba44d1cbec7d48dcbb5b842',
],
    'words': 'cheetah deer',
    'nested': {
    'id': 109,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'dragonfly',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 6,
},
],
},
    'nested_array': [
    [
    -6,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'koala',
    'turtle',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': [
    71,
],
    'rand_bool': True,
    'mixed_type': False,
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 110,
    'id_str': [
    '13',
],
    'text_data': '6c423670acb14e1fbd82eea2d85e5d5a',
    'rand_digit': 5,
    'rand_number': 0.96628,
    'rand_signed_int': 6,
    'rand_datetime': '2000-10-18T19:12:15',
    'text_array': [
    '19753d255f854c639cf8e64c5ba8aae4',
    '3ec1e0a0b62b4c378875b015624e73df',
],
    'words': 'chicken dragonfly',
    'nested': {
    'id': 110,
    'rand_digit': 3,
    'array': [
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
],
    'two_words': [
    'gorilla',
    'sheep',
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
    'mixed_type': None,
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 111,
    'id_str': [
    '11',
],
    'text_data': '0216f0bbeaa941e6a52ce1d27d6d5424',
    'rand_digit': 4,
    'rand_number': 0.05738,
    'rand_signed_int': -2,
    'rand_datetime': '2000-09-15T02:41:05.862391-1200',
    'text_array': [
    '0bd897202709457fa4f58e8c61564403',
    'bdbb23350fcd4823bfad71a586e80212',
],
    'words': 'squid snake',
    'nested': {
    'id': 111,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'monkey',
    'number': 9,
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
    'nested_array': '__FLOAT_MULTI_DIM_2,5__',
    'two_words': [
    'rhino',
    'dragonfly',
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
    'mixed_type': False,
    'maybe_null': 'hippo',
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 112,
    'id_str': [
    '27',
    '13',
    '25',
    '19',
    '24',
],
    'text_data': '1834c1e0fd2e4a1b9917b1a1b4f37cfd',
    'rand_digit': 5,
    'rand_number': 0.58106,
    'rand_signed_int': -7,
    'rand_datetime': '2000-09-21 13:27:29.598441',
    'text_array': [
    'ddd3d90119944e229dc12472a8d22bc7',
    '23e60901c0ed4af4a7a83222094f5b9f',
],
    'words': 'pig giraffe',
    'nested': {
    'id': 112,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bee',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 3,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,5__',
    'two_words': [
    'panda',
    'horse',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'goat',
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 113,
    'id_str': [
    '26',
],
    'text_data': 'b4924813890e49bd9c1aac6bb563abc6',
    'rand_digit': 5,
    'rand_number': 0.86641,
    'rand_signed_int': -3,
    'rand_datetime': '2000-09-07 13:24:24',
    'text_array': [
    '93ac9f66e3f5438c825e97e128f5c4f7',
    'f538c21ea2ad4c109e618f5474396d88',
],
    'words': 'fox fox',
    'nested': {
    'id': 113,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'kangaroo',
    'cow',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 114,
    'id_str': [
    '14',
    '15',
    '17',
],
    'text_data': '8e80df50379b4db3922b917f641c2ba4',
    'rand_digit': 9,
    'rand_number': 0.15478,
    'rand_signed_int': 9,
    'rand_datetime': '2001-01-12 23:18',
    'text_array': [
    'f3e4dd6c125349869d4677d811cfdf39',
    '04cf1350b375457e947ff8643609241d',
],
    'words': 'zebra cat',
    'nested': {
    'id': 114,
    'rand_digit': 6,
    'array': [
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
    'hello',
],
    'word': 'dragonfly',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'hyena',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    6,
],
],
    'two_words': [
    'ladybug',
    'scorpion',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': [
    93,
],
    'rand_bool': False,
    'mixed_type': 'cat',
    'maybe': 'bear',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 115,
    'id_str': [
],
    'text_data': '05d17c3f05c441b89a324cfd1d864370',
    'rand_digit': 7,
    'rand_number': 0.97516,
    'rand_signed_int': -4,
    'rand_datetime': '2000-08-28T22:16:58.746117-0900',
    'text_array': [
    '4ea335c5bd0e4f8c8f5b360c8f19b16e',
    '3b83cfadb95348dbb11a3d681c36e74d',
],
    'words': 'monkey kangaroo',
    'nested': {
    'id': 115,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'gorilla',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
    -9,
],
],
    'two_words': [
    'sloth',
    'gorilla',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.81751,
    'maybe_null': None,
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 116,
    'id_str': [
    '28',
    '23',
    '25',
],
    'text_data': '681bbf46f38947119448852edb82a917',
    'rand_digit': 7,
    'rand_number': 0.08098,
    'rand_signed_int': -9,
    'rand_datetime': '2000-07-01T17:25:20.096174+0400',
    'text_array': [
    'ef7d6529472e47e6ba4f44d5266c8090',
    '198d0d42dcb043f6b1b2f37c7c3549a9',
],
    'words': 'snail pig',
    'nested': {
    'id': 116,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'goat',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'goat',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 3,
},
],
},
    'nested_array': [
    [
    3,
],
],
    'two_words': [
    'rabbit',
    'kangaroo',
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
    'mixed_type': 0.70509,
    'maybe': 'panda',
    'maybe_null': 'lobster',
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 117,
    'id_str': [
    '27',
    '27',
    '19',
    '20',
    '03',
],
    'text_data': 'f05e80a8745e4df08b78e916c4623fae',
    'rand_digit': 1,
    'rand_number': 0.87774,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-08 18:53:49.849243+0200',
    'text_array': [
    '123ebf2058c1462fb2d9166d2e81736d',
    '1d500b8285894daca72ff04b0cfd00f1',
],
    'words': 'koala cow',
    'nested': {
    'id': 117,
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
    'number': 8,
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
    'hello',
],
    'word': 'octopus',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'ladybug',
    'dolphin',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cow',
    'maybe_null': 'butterfly',
},
},
    {
    'id': 18,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 118,
    'id_str': [
    '27',
    '21',
],
    'text_data': '0851d9b564b84308b080a832c44eab8f',
    'rand_digit': 1,
    'rand_number': 0.25317,
    'rand_signed_int': 5,
    'rand_datetime': '2000-11-24 12:41:23-0400',
    'text_array': [
    'b36db64cca6f42849be575e2477643d2',
    'b9c5e475d1644b2b8c7a330e78cba30a',
],
    'words': 'grasshopper spider',
    'nested': {
    'id': 118,
    'rand_digit': 2,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
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
    'word': 'wolf',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bee',
    'horse',
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
    'mixed_type': None,
    'maybe': 'giraffe',
    'maybe_null': None,
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
    '02',
    '22',
    '09',
    '25',
    '30',
],
    'text_data': '78d8dfc0e0c444c88a841db31ca16160',
    'rand_digit': 7,
    'rand_number': 0.95917,
    'rand_signed_int': -10,
    'rand_datetime': '2001-01-21 08:24:31',
    'text_array': [
    '7104fcc847544d769cace5f94c046b5e',
    '3b07ac81d1744649b5e1ca4d02e1a3fc',
],
    'words': 'shark bear',
    'nested': {
    'id': 119,
    'rand_digit': 8,
    'array': [
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
    'word': 'fish',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 1,
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
    [
    6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'butterfly',
    'fish',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'whale',
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 120,
    'id_str': [
    '23',
    '22',
    '04',
    '14',
    '10',
],
    'text_data': 'c43198d6ce4b4532bb3d01bb27288a2e',
    'rand_digit': 9,
    'rand_number': 0.71516,
    'rand_signed_int': -8,
    'rand_datetime': '2000-07-16T19:29:17+0400',
    'text_array': [
    'f11b17aa81a64060b41f63a2dc9ac86b',
    'beff270ed1e14bf7ac8d1bc763868ee9',
],
    'words': 'butterfly bear',
    'nested': {
    'id': 120,
    'rand_digit': 1,
    'array': [
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
    'word': 'mouse',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bee',
    'ape',
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
    'mixed_type': 8,
    'maybe': 'cat',
    'maybe_null': 'snail',
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 121,
    'id_str': [
    '16',
    '30',
],
    'text_data': 'a656062f73874e7297239f41b13f496d',
    'rand_digit': 2,
    'rand_number': 0.93996,
    'rand_signed_int': 10,
    'rand_datetime': '2000-07-01 21:12:49.147233+1000',
    'text_array': [
    '99253b343974422caf4af5500fc9043f',
    'd634d2f033e04ebdb2e58fc47726bf16',
],
    'words': 'lion sheep',
    'nested': {
    'id': 121,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lion',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'zebra',
    'camel',
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
    'mixed_type': 'ladybug',
    'maybe_null': None,
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
],
    'text_data': '7e2dba8b0d3e4984bc889ebbdb638a72',
    'rand_digit': 1,
    'rand_number': 0.93275,
    'rand_signed_int': 5,
    'rand_datetime': '2000-08-06 07:01:04-0900',
    'text_array': [
    '7ccb64971839482e96007d8bc964fc54',
    '133e6a87b65b47fc80f81401fe0ca81a',
],
    'words': 'fish scorpion',
    'nested': {
    'id': 122,
    'rand_digit': 3,
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
    'word': 'spider',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'spider',
    'panda',
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
    'mixed_type': 'fly',
    'maybe_null': 'cow',
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 123,
    'id_str': [
    '06',
    '13',
    '03',
    '01',
],
    'text_data': 'ad1381594b9445328dfe4b9ea11834ed',
    'rand_digit': 3,
    'rand_number': 0.31176,
    'rand_signed_int': -7,
    'rand_datetime': '2000-05-06T21:40:24+0700',
    'text_array': [
    '4d7ae466d70a4129bdc7361d086f4142',
    '98b32ada690b4cd79f7af8bde37bf191',
],
    'words': 'butterfly duck',
    'nested': {
    'id': 123,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'octopus',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'koala',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'monkey',
    'cat',
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
    'maybe': 'pig',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 124,
    'id_str': [
    '19',
],
    'text_data': 'dfaa21b5a3af4fbd8bccb7d93e9072ed',
    'rand_digit': 9,
    'rand_number': 0.30542,
    'rand_signed_int': 8,
    'rand_datetime': '2000-05-10T21:10:49.130481',
    'text_array': [
    '5b9213df452f4da3b06d95ef776c15ea',
    '1650590a173c4492b70c541fd7dea0e9',
],
    'words': 'ape giraffe',
    'nested': {
    'id': 124,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 7,
},
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'chicken',
    'cheetah',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'koala',
    'maybe_null': 'lobster',
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
    '27',
    '23',
    '11',
    '04',
    '17',
],
    'text_data': '289ab200fd64489595bc0d7d3c4b586c',
    'rand_digit': 1,
    'rand_number': 0.1344,
    'rand_signed_int': -4,
    'rand_datetime': '2000-07-26T01:02:21.614609',
    'text_array': [
    '8571b669b18340e28a5b8c3885765c05',
    '2025bb50dd024f8482871011964abc14',
],
    'words': 'dragonfly ape',
    'nested': {
    'id': 125,
    'rand_digit': 4,
    'array': [
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -5,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'whale',
    'rhino',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 'butterfly',
    'maybe': 'jaguar',
    'maybe_null': 'butterfly',
},
},
    {
    'id': 26,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 126,
    'id_str': [
    '05',
],
    'text_data': '568989c3aa5742afbc352305314404fa',
    'rand_digit': 5,
    'rand_number': 0.698,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-04 04:57:35.431924',
    'text_array': [
    '00249c0447f844969609cca5477b7ea3',
    'a23f2587716e46ab87c3f6f92aa56034',
],
    'words': 'butterfly spider',
    'nested': {
    'id': 126,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'mosquito',
    'horse',
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
    'mixed_type': 2,
    'maybe': 'ladybug',
    'maybe_null': None,
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 127,
    'id_str': [
],
    'text_data': '23778cee3e6844fd99b90594f644a5b2',
    'rand_digit': 5,
    'rand_number': 0.73458,
    'rand_signed_int': 3,
    'rand_datetime': '2000-01-08T06:52:37.222781',
    'text_array': [
    '77959172d62f47388846ab96b4af97b7',
    '52b956b4fb5549279e3ee78f2016b492',
],
    'words': 'whale bee',
    'nested': {
    'id': 127,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    [
    -1,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'snake',
    'bear',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'tiger',
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 28,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 128,
    'id_str': [
    '06',
],
    'text_data': '445d1711e65f4a10ae8a28eaf7a5c1bb',
    'rand_digit': 4,
    'rand_number': 0.04504,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-09T22:41:56.976514',
    'text_array': [
    'ddae09f1ed474223ae118b285f343c5c',
    '2f6c67354a9043a6880fd69991d9d3e1',
],
    'words': 'tiger ladybug',
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
    'word': 'whale',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 4,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'jaguar',
    'ant',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'sheep',
    'maybe_null': None,
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
    '15',
    '27',
    '02',
],
    'text_data': 'e83c7222372b44a89e48ca57041616d1',
    'rand_digit': 1,
    'rand_number': 0.18533,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-06 18:16:10',
    'text_array': [
    'c515f4b52be942a49ee0403171a1e4b8',
    '8d2bee9f529a4981bd13b76e08d3ac5f',
],
    'words': 'fly scorpion',
    'nested': {
    'id': 129,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    3,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'squid',
    'tiger',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': [
    4,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'koala',
    'maybe_null': None,
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 130,
    'id_str': [
    '14',
],
    'text_data': '64890a44deda4bc982d433f78a3c6168',
    'rand_digit': 8,
    'rand_number': 0.92855,
    'rand_signed_int': -2,
    'rand_datetime': '2000-08-05T08:56:29.300324',
    'text_array': [
    '0ef57c7b6842466587f4198f13b4baf8',
    '1a25eb660858424a897f267e728c08f2',
],
    'words': 'whale chicken',
    'nested': {
    'id': 130,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -1,
],
],
    'two_words': [
    'ape',
    'frog',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': [
    22,
],
    'rand_bool': False,
    'mixed_type': 'ape',
    'maybe': 'goat',
    'maybe_null': None,
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 131,
    'id_str': [
    '24',
    '23',
    '03',
    '09',
    '14',
],
    'text_data': 'a5f7ce32ceb34f6280bbf5f30a4afd50',
    'rand_digit': 3,
    'rand_number': 0.24854,
    'rand_signed_int': -10,
    'rand_datetime': '2000-03-01T00:59:50.428583+0300',
    'text_array': [
    'b475c9f1c5494fc8b203093f98f9f640',
    'a87d87a3b64f4f939016fb08ac4864f9',
],
    'words': 'crab panda',
    'nested': {
    'id': 131,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'lizard',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'bee',
    'camel',
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
    'maybe': 'hippo',
    'maybe_null': 'hyena',
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
    '04',
    '13',
    '17',
],
    'text_data': '742a9b80afd94918978237e248954dbc',
    'rand_digit': 8,
    'rand_number': 0.90168,
    'rand_signed_int': 4,
    'rand_datetime': '2000-11-12T00:49:23.609227',
    'text_array': [
    '776c55ad87c04bd3b4ed55581146f278',
    '01f40405b9374806a0866f6a77bbfded',
],
    'words': 'scorpion turtle',
    'nested': {
    'id': 132,
    'rand_digit': 4,
    'array': [
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
    'word': 'grasshopper',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 8,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'duck',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'elephant',
    'jaguar',
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
    'mixed_type': 8,
    'maybe_null': None,
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 133,
    'id_str': [
    '03',
    '30',
    '14',
],
    'text_data': '6388af2b75e2413293acc8ab018be746',
    'rand_digit': 0,
    'rand_number': 0.69155,
    'rand_signed_int': -1,
    'rand_datetime': '2000-07-23T00:57:16+0600',
    'text_array': [
    'b8ea2213d2e8459095f146d4e8f5d480',
    '84dfeeed070f4523903149470cbaf617',
],
    'words': 'mouse mouse',
    'nested': {
    'id': 133,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
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
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mouse',
    'bird',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': [
    71,
],
    'rand_bool': False,
    'mixed_type': None,
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 134,
    'id_str': [
],
    'text_data': '82c67ce88e464a2dae216d9d3b6653db',
    'rand_digit': 0,
    'rand_number': 0.94888,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-18 16:47',
    'text_array': [
    'ebd748b8555b4c23a2e7b6bf2ab56612',
    '9282446ac47240fbad45fa7e25da68e9',
],
    'words': 'mouse deer',
    'nested': {
    'id': 134,
    'rand_digit': 1,
    'array': [
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
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'panda',
    'shark',
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
    'mixed_type': 0.02921,
    'maybe': 'scorpion',
    'maybe_null': 'sheep',
},
},
    {
    'id': 35,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 135,
    'id_str': [
    '14',
    '21',
    '25',
    '13',
],
    'text_data': '3eaca832499442579be0b1a11bbad89a',
    'rand_digit': 6,
    'rand_number': 0.50973,
    'rand_signed_int': 5,
    'rand_datetime': '2001-01-14',
    'text_array': [
    'a3ee05d4512c4124a67a11eb131f114b',
    'b5c057a80130490fa17b13a51473ec57',
],
    'words': 'shark wolf',
    'nested': {
    'id': 135,
    'rand_digit': 8,
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
    'nested_empty': [
    'hello',
],
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
    'word': 'zebra',
    'number': 2,
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
    'hello',
],
    'word': 'turtle',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'fly',
    'kangaroo',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': [
    40,
],
    'rand_bool': True,
    'mixed_type': 0.38633,
},
},
    {
    'id': 36,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 136,
    'id_str': [
    '25',
],
    'text_data': '72d26700d2914370bb249bdfd0acb598',
    'rand_digit': 6,
    'rand_number': 0.11225,
    'rand_signed_int': -2,
    'rand_datetime': '2000-02-17T13:04:10.677854',
    'text_array': [
    '898f50e22c7d419894c88d58be26a618',
    'ed8c987a25ff471ba4e8e2edd0a351fa',
],
    'words': 'cat dog',
    'nested': {
    'id': 136,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'jaguar',
    'lion',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.28688,
    'maybe': 'bear',
    'maybe_null': 'panda',
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
    '25',
    '17',
    '12',
],
    'text_data': '374504a060e348a3826508ab5de82f2c',
    'rand_digit': 9,
    'rand_number': 0.41826,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-17T12:56:19.767324',
    'text_array': [
    '56b25301d720475892bf3aa9dab51d99',
    'e70a360885cd42e6824ac3b9892e1af5',
],
    'words': 'cheetah shark',
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
    'word': 'chicken',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'zebra',
    'snake',
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
    'maybe': 'ant',
    'maybe_null': 'ape',
},
},
    {
    'id': 38,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 138,
    'id_str': [
],
    'text_data': '30d66b2543604861bbd4e773e66a78d1',
    'rand_digit': 9,
    'rand_number': 0.92438,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-12 03:11:53.564576+0800',
    'text_array': [
    '4b53fa0498204759bb5aa5b301afe274',
    '75146916155f46be8860333257077277',
],
    'words': 'dolphin grasshopper',
    'nested': {
    'id': 138,
    'rand_digit': 5,
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
],
    'word': 'snail',
    'number': 10,
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
],
    'word': 'rabbit',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'camel',
    'panda',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 139,
    'id_str': [
],
    'text_data': 'f02e349b6604477b985cd1e3937c3a59',
    'rand_digit': 8,
    'rand_number': 0.88074,
    'rand_signed_int': -5,
    'rand_datetime': '2000-04-24 20:44:52.076698+1100',
    'text_array': [
    '74a95529eaa94c479de5f24ff8581c5b',
    '2e5f73e3aa794a0da50edce9f1eb7a87',
],
    'words': 'bear chicken',
    'nested': {
    'id': 139,
    'rand_digit': 4,
    'array': [
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
    'word': 'sloth',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 8,
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
    'nested_array': [
    [
],
],
    'two_words': [
    'ape',
    'squid',
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
    'mixed_type': None,
    'maybe_null': 'sheep',
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 140,
    'id_str': [
],
    'text_data': '4b19994825a648bc968b03cfa00bc9fe',
    'rand_digit': 4,
    'rand_number': 0.44656,
    'rand_signed_int': 5,
    'rand_datetime': '2000-04-08 07:08:04-1200',
    'text_array': [
    'ef464781396f40d499eafda1580e2af7',
    '10d2f067bdc746f2b2ebff733e79ab04',
],
    'words': 'lion mouse',
    'nested': {
    'id': 140,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    9,
],
    [
],
],
    'two_words': [
    'shark',
    'rhino',
],
    'city': {
    'name': 'Athens',
    'geo': {
    'lat': 37.98381,
    'lon': 23.727539,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 141,
    'id_str': [
    '29',
],
    'text_data': '04e985a656b3478c960fea77cc7e51af',
    'rand_digit': 7,
    'rand_number': 0.18213,
    'rand_signed_int': 8,
    'rand_datetime': '2000-07-04T13:55:55.735448',
    'text_array': [
    'bd8e394f11544c53bdfda45f97bb62f2',
    'c19bbafd38864a9b83932e1b6b41f8b5',
],
    'words': 'ladybug bear',
    'nested': {
    'id': 141,
    'rand_digit': 7,
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
    'hello',
],
    'word': 'rhino',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 8,
},
],
},
    'nested_array': [
    [
    5,
],
],
    'two_words': [
    'frog',
    'frog',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 142,
    'id_str': [
    '16',
    '24',
],
    'text_data': '439a96c8ba6747398dce196dea373ebb',
    'rand_digit': 7,
    'rand_number': 0.10427,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-08 02:47:24.617938',
    'text_array': [
    'b1afe9f5583546919adda465782c88b1',
    'd59c56ff88ad4c64a71ebecab7d8e03f',
],
    'words': 'hyena horse',
    'nested': {
    'id': 142,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'goat',
    'lion',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'dolphin',
    'maybe_null': 'spider',
},
},
    {
    'id': 43,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 143,
    'id_str': [
    '05',
    '03',
    '27',
    '12',
],
    'text_data': 'c418787cd79245e697d3770972195c43',
    'rand_digit': 2,
    'rand_number': 0.64633,
    'rand_signed_int': -3,
    'rand_datetime': '2000-09-01T14:05:01-0100',
    'text_array': [
    '5e040afe92fa4c7eaaa11765b372ca0e',
    '87aee17116344ba8a97bb61c197cf08b',
],
    'words': 'elephant rhino',
    'nested': {
    'id': 143,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'kangaroo',
    'cheetah',
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
    'mixed_type': False,
    'maybe': 'octopus',
    'maybe_null': 'hippo',
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 144,
    'id_str': [
    '08',
    '07',
    '14',
    '09',
    '14',
],
    'text_data': '87bb19d87262429a882bf2d5e6120a80',
    'rand_digit': 3,
    'rand_number': 0.53855,
    'rand_signed_int': 8,
    'rand_datetime': '2000-05-31 17:08',
    'text_array': [
    'fe39c82c013d48c29f90e414ed9adb24',
    '6ff9205ada4a4eb9aa7b13494a91f4fb',
],
    'words': 'snake wolf',
    'nested': {
    'id': 144,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    0,
],
],
    'two_words': [
    'dolphin',
    'shark',
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
    'mixed_type': False,
    'maybe_null': None,
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 145,
    'id_str': [
    '13',
    '22',
    '21',
],
    'text_data': '2422a32b455e48a29f6605b43c5e4347',
    'rand_digit': 4,
    'rand_number': 0.75722,
    'rand_signed_int': 2,
    'rand_datetime': '2000-10-14 16:33',
    'text_array': [
    'a618ae1759b74f4aaa14dcb430028cf5',
    '825447012a2c48fa9599b5103d4e5599',
],
    'words': 'panda leopard',
    'nested': {
    'id': 145,
    'rand_digit': 9,
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
    'hello',
],
    'word': 'fly',
    'number': 3,
},
],
},
    'nested_array': [
    [
    0,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ant',
    'fish',
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
    'mixed_type': 'duck',
    'maybe': 'crab',
    'maybe_null': None,
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
    '13',
    '02',
],
    'text_data': 'd0fbc8dba2c8446480f504bfb343b4be',
    'rand_digit': 5,
    'rand_number': 0.16666,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-24T19:16:25',
    'text_array': [
    'c5d9f74e59a440be942d3239e19f26b2',
    'aae114e4df3647d6a1b6a8f10b336431',
],
    'words': 'scorpion rhino',
    'nested': {
    'id': 146,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dog',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'wolf',
    'mouse',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
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
    'id': 47,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 147,
    'id_str': [
    '06',
    '24',
    '01',
],
    'text_data': '9960a631be684dcaad76f17f01e88f03',
    'rand_digit': 8,
    'rand_number': 0.85902,
    'rand_signed_int': -9,
    'rand_datetime': '2000-08-08 14:16:49.923506',
    'text_array': [
    '621c3702faf641cf94ce34a01c1c5013',
    '4deb4fe4bc654208b84c00d947aae9e4',
],
    'words': 'giraffe whale',
    'nested': {
    'id': 147,
    'rand_digit': 8,
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
    'word': 'octopus',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'pig',
    'butterfly',
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
    'mixed_type': False,
    'maybe_null': 'bear',
},
},
    {
    'id': 48,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 148,
    'id_str': [
    '22',
],
    'text_data': 'f2191ff7126b443993d75a0e3b1f8467',
    'rand_digit': 5,
    'rand_number': 0.65341,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-09T19:35:19.603740',
    'text_array': [
    '34cad6d527924d1e91d5af0dc21469e7',
    'ccb5fb8d57344574b7d80add24e74cd5',
],
    'words': 'panda dragonfly',
    'nested': {
    'id': 148,
    'rand_digit': 4,
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
    'word': 'hyena',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'sloth',
    'fish',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'dolphin',
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 149,
    'id_str': [
    '24',
    '16',
],
    'text_data': '0434ed317a9e45738ffc42797b8ab50b',
    'rand_digit': 3,
    'rand_number': 0.14054,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-24T04:39:17-0400',
    'text_array': [
    '9aeb47b40a0245a99bffd66565d9b5d1',
    '9312f98dc17747689f9a467a09a2718c',
],
    'words': 'koala shark',
    'nested': {
    'id': 149,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'turtle',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    9,
],
    [
    7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'sheep',
    'wolf',
],
    'city': {
    'name': 'Kharkiv',
    'geo': {
    'lat': 49.980812,
    'lon': 36.25272,
},
},
    'rand_tuple': [
    75,
],
    'rand_bool': False,
    'mixed_type': 9,
    'maybe': 'whale',
    'maybe_null': 'sloth',
},
},
    {
    'id': 50,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 150,
    'id_str': [
    '02',
    '25',
],
    'text_data': '2edefd0e24e94da7bcfc70f23f53777d',
    'rand_digit': 2,
    'rand_number': 0.04869,
    'rand_signed_int': 8,
    'rand_datetime': '2000-05-18T18:21:55.605960+04:00',
    'text_array': [
    'fa7b3cf8bad74952be0defa8b2cd5f46',
    '7ed8a161a8914052bc682101fe8d97e3',
],
    'words': 'butterfly grasshopper',
    'nested': {
    'id': 150,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bird',
    'dolphin',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fly',
    'maybe_null': 'turtle',
},
},
    {
    'id': 51,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 151,
    'id_str': [
    '27',
],
    'text_data': 'ef901a3b45344b7c89e307baaed71db4',
    'rand_digit': 6,
    'rand_number': 0.48158,
    'rand_signed_int': 0,
    'rand_datetime': '2000-03-29T12:22:15.468284+0900',
    'text_array': [
    '21ac987e24b74500b4e8cdb8f56fc2ad',
    'd7bf854a95f54f1daff2c01b43047d26',
],
    'words': 'dog frog',
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
    'word': 'elephant',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 6,
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
    'dolphin',
    'fox',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
},
},
    'rand_tuple': [
    22,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'chicken',
    'maybe_null': 'cheetah',
},
},
    {
    'id': 52,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 152,
    'id_str': [
    '14',
],
    'text_data': '49a126d4a0904362a151c3c836608139',
    'rand_digit': 5,
    'rand_number': 0.71753,
    'rand_signed_int': 0,
    'rand_datetime': '2000-03-24 17:55',
    'text_array': [
    '17a01d8303834661a32fcf482e068bc6',
    '210a85a72a8a4e56b83b61a8d4251fab',
],
    'words': 'cheetah squid',
    'nested': {
    'id': 152,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
],
    [
    -8,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'turtle',
    'shark',
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
    'mixed_type': 8,
},
},
    {
    'id': 53,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 153,
    'id_str': [
    '07',
    '16',
    '29',
],
    'text_data': '2d62d44279b94f2d9e2b8d5ff202f09b',
    'rand_digit': 8,
    'rand_number': 0.58533,
    'rand_signed_int': -8,
    'rand_datetime': '2000-04-30T02:00:31.900223-05:00',
    'text_array': [
    '3ed868a0a2e548f59eb8b8a2ad3d79f7',
    'e921d8c8f78c441c9ecb773c1baf03db',
],
    'words': 'camel shark',
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
    'word': 'hippo',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'grasshopper',
    'rhino',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 8,
    'maybe': 'fox',
    'maybe_null': None,
},
},
    {
    'id': 54,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 154,
    'id_str': [
    '15',
    '24',
    '13',
],
    'text_data': '02a549601d9844219b182fcb3dfc5c5f',
    'rand_digit': 4,
    'rand_number': 0.26676,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-10 03:50',
    'text_array': [
    '65fe35c030c54a38b1e4af7511f6c004',
    'c8aba135c69f4873941584eab1e884ae',
],
    'words': 'giraffe horse',
    'nested': {
    'id': 154,
    'rand_digit': 0,
    'array': [
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
    'hello',
],
    'word': 'horse',
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
],
    'word': 'bee',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'duck',
    'spider',
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
    'mixed_type': 0.47609,
    'maybe': 'giraffe',
    'maybe_null': 'snail',
},
},
    {
    'id': 55,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 155,
    'id_str': [
],
    'text_data': 'b47dda4abe044385940bb1fcff783760',
    'rand_digit': 8,
    'rand_number': 0.34609,
    'rand_signed_int': 8,
    'rand_datetime': '2000-01-31T04:08:37',
    'text_array': [
    '57ae76417fff496cad0ef9047aa75762',
    '4b7e99212aec4fe789795bcb56b5108e',
],
    'words': 'cow jaguar',
    'nested': {
    'id': 155,
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
    'number': 4,
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
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ant',
    'goat',
],
    'city': {
    'name': 'Moscow',
    'geo': {
    'lat': 55.755826,
    'lon': 37.6173,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 3,
    'maybe_null': 'hyena',
},
},
    {
    'id': 56,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 156,
    'id_str': [
    '20',
],
    'text_data': '017522df7e5448279abbbb2f939e0fee',
    'rand_digit': 9,
    'rand_number': 0.67788,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-04T18:18:54',
    'text_array': [
    '3fbfa33009a74fb6ac0a019317f41e38',
    '8fa3b4b158a143ceb480d1c40e4f176c',
],
    'words': 'chicken giraffe',
    'nested': {
    'id': 156,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dog',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    1,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'sheep',
    'fox',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': [
    100,
],
    'rand_bool': False,
    'mixed_type': 'fly',
    'maybe_null': None,
},
},
    {
    'id': 57,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 157,
    'id_str': [
    '10',
    '15',
    '27',
    '22',
    '29',
],
    'text_data': 'dd1cfdef595a4e028c785c3933e7e7ef',
    'rand_digit': 7,
    'rand_number': 0.32913,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-01 06:46:38',
    'text_array': [
    '9bcb3910515548d9ad9a6a14bb605d2e',
    '77c6b6a2f5124e659e1b354c3e69d3a0',
],
    'words': 'bear dog',
    'nested': {
    'id': 157,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'turtle',
    'sloth',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'turtle',
},
},
    {
    'id': 58,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 158,
    'id_str': [
    '21',
    '29',
    '18',
    '30',
],
    'text_data': '62a4aadd063340eb8f1eecd9ccd5dc08',
    'rand_digit': 1,
    'rand_number': 0.34519,
    'rand_signed_int': -5,
    'rand_datetime': '2000-11-21',
    'text_array': [
    'c8b61cabfec543c38675ec135d1baaa2',
    '6b7c56ee3ab04dad865ded7e44a7405c',
],
    'words': 'crab snake',
    'nested': {
    'id': 158,
    'rand_digit': 5,
    'array': [
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
    'nested_empty': [
    'hello',
],
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
    'word': 'lion',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'frog',
    'mosquito',
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
    'maybe_null': 'cat',
},
},
    {
    'id': 59,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 159,
    'id_str': [
    '16',
    '24',
],
    'text_data': '02bf8d5a7a41423b81b13164fc7b3ea2',
    'rand_digit': 7,
    'rand_number': 0.39008,
    'rand_signed_int': -6,
    'rand_datetime': '2000-01-07T19:40:16.024412-0300',
    'text_array': [
    '0b7410e263cc417ebaf0eda1f67cdb09',
    '83c6c2e957da4ea2b53fdc019b369f12',
],
    'words': 'horse sloth',
    'nested': {
    'id': 159,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'frog',
    'fox',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 60,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 160,
    'id_str': [
    '19',
    '09',
],
    'text_data': '9edadd0f5fd9408b9fb51ae8fb8d5719',
    'rand_digit': 2,
    'rand_number': 0.33892,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-20 19:33',
    'text_array': [
    '59c4038082ae4ba5aba2bbfb5eb55293',
    '6b4bca90dfb44bbcade1194ad1b2edd0',
],
    'words': 'panda mosquito',
    'nested': {
    'id': 160,
    'rand_digit': 6,
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
    'word': 'chicken',
    'number': 6,
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
    'hello',
],
    'word': 'scorpion',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -4,
],
],
    'two_words': [
    'sloth',
    'snail',
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
    'maybe': 'wolf',
    'maybe_null': None,
},
},
    {
    'id': 61,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 161,
    'id_str': [
],
    'text_data': '37fc5107da074c5e81d37e7339a1d60c',
    'rand_digit': 2,
    'rand_number': 0.55804,
    'rand_signed_int': -4,
    'rand_datetime': '2000-12-17',
    'text_array': [
    'c37de4bd006841a59cc47a53a2914586',
    'ed384cf6e4604fd094369669eb317c7a',
],
    'words': 'giraffe sheep',
    'nested': {
    'id': 161,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    4,
],
],
    'two_words': [
    'fly',
    'whale',
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
    'mixed_type': 0.43976,
    'maybe_null': 'deer',
},
},
    {
    'id': 62,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 162,
    'id_str': [
    '21',
],
    'text_data': 'f34075b7cc1545faa5d7c68ba0d64220',
    'rand_digit': 2,
    'rand_number': 0.49614,
    'rand_signed_int': 0,
    'rand_datetime': '2000-12-12 20:13:30+1000',
    'text_array': [
    '5a1de68548ee4e40b94a4317f1e18ccd',
    'c215247fe2e54dd79120b339badd7df0',
],
    'words': 'panda jaguar',
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
    'word': 'rabbit',
    'number': 10,
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
    'nested_array': '__FLOAT_MULTI_DIM_3,2__',
    'two_words': [
    'octopus',
    'fox',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bee',
    'maybe_null': 'kangaroo',
},
},
    {
    'id': 63,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 163,
    'id_str': [
    '29',
    '12',
],
    'text_data': 'eced087d2f6f444480cbe62e49f8b80c',
    'rand_digit': 9,
    'rand_number': 0.87266,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-04 12:06:01+0700',
    'text_array': [
    '7b990fd15dde4b3783a192c85b62303c',
    '9df93e5090e846a7834abaa974c1efb5',
],
    'words': 'crab deer',
    'nested': {
    'id': 163,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dragonfly',
    'octopus',
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
    'mixed_type': 'spider',
    'maybe_null': 'butterfly',
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
    'content-length': '410317',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 100,
    'id_str': [
    '28',
    '18',
    '04',
],
    'text_data': 'd4b2c4027d314cbe811408eb08784675',
    'rand_digit': 7,
    'rand_number': 0.01139,
    'rand_signed_int': 7,
    'rand_datetime': '2000-05-10T19:01:55.190722',
    'text_array': [
    'f4a5d68c5dd54bc3a8ad6a20ed2acdf3',
    'ae676929afec491292606c7f3f57fc8c',
],
    'words': 'scorpion snail',
    'nested': {
    'id': 100,
    'rand_digit': 2,
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
    'hello',
],
    'word': 'sloth',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'grasshopper',
    'number': 1,
},
],
},
    'nested_array': [
    [
    6,
],
],
    'two_words': [
    'lobster',
    'tiger',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'chicken',
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 101,
    'id_str': [
    '10',
    '23',
    '22',
    '19',
],
    'text_data': '0b52911576004497b7be0676fa1308f7',
    'rand_digit': 1,
    'rand_number': 0.28957,
    'rand_signed_int': 4,
    'rand_datetime': '2000-05-03T03:41:43.217252',
    'text_array': [
    'fe5db34a5b23469596d0b60650282615',
    '3531982e33dc406fb52f477dac48c102',
],
    'words': 'rabbit dolphin',
    'nested': {
    'id': 101,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    4,
],
],
    'two_words': [
    'scorpion',
    'whale',
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
    'mixed_type': None,
    'maybe': 'jaguar',
    'maybe_null': 'dog',
},
},
    {
    'id': 2,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 102,
    'id_str': [
    '15',
    '15',
    '24',
    '20',
],
    'text_data': '0330eddfd7b549d5b34765dc583c16e2',
    'rand_digit': 3,
    'rand_number': 0.70437,
    'rand_signed_int': 7,
    'rand_datetime': '2000-01-09 10:47',
    'text_array': [
    '93ee77224edd4decb8059b1c08807511',
    '105c02ef83694cabba6242ab9d357786',
],
    'words': 'jaguar hippo',
    'nested': {
    'id': 102,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 3,
},
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
    'hello',
],
    'word': 'fox',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bird',
    'ape',
],
    'city': {
    'name': 'Johannesburg',
    'geo': {
    'lat': -26.204103,
    'lon': 28.047305,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.56823,
    'maybe_null': 'rhino',
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 103,
    'id_str': [
],
    'text_data': '6315e45a44ff4dcabac6be662e96d9ce',
    'rand_digit': 3,
    'rand_number': 0.74286,
    'rand_signed_int': -6,
    'rand_datetime': '2000-03-01T17:41:18.878049+01:00',
    'text_array': [
    '611b3bc601de4be8a1e637ba7533a8dc',
    'd190e8c2dd444c2f878f7ef1f721d1c1',
],
    'words': 'bee fox',
    'nested': {
    'id': 103,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 7,
},
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
    'hello',
],
    'word': 'mouse',
    'number': 1,
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
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'spider',
    'hyena',
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
    'mixed_type': 0.18742,
    'maybe': 'rabbit',
    'maybe_null': 'ant',
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 104,
    'id_str': [
    '17',
    '21',
    '18',
    '26',
],
    'text_data': '2a94b6680751452299b778a92648503c',
    'rand_digit': 5,
    'rand_number': 0.59607,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-02T18:18:38',
    'text_array': [
    '67f3f148694d443189a2e26fa9912b03',
    '25aa9c35f8884405a4397c24e81f1212',
],
    'words': 'horse pig',
    'nested': {
    'id': 104,
    'rand_digit': 8,
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
],
},
    'nested_array': [
],
    'two_words': [
    'bear',
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
    'mixed_type': None,
    'maybe': 'kangaroo',
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 105,
    'id_str': [
    '10',
    '21',
    '13',
],
    'text_data': '6182ed613d22479493d96f09e47a9c43',
    'rand_digit': 8,
    'rand_number': 0.81178,
    'rand_signed_int': 8,
    'rand_datetime': '2000-01-17 04:00:49.619115-0400',
    'text_array': [
    '1d4885bd8da248c6a686a004cbbbb6a4',
    '1bee055d82634f3f8095c59645c80470',
],
    'words': 'jaguar tiger',
    'nested': {
    'id': 105,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fly',
    'pig',
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
    'mixed_type': 'lizard',
    'maybe': 'hyena',
    'maybe_null': None,
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 106,
    'id_str': [
    '04',
    '14',
    '01',
    '04',
],
    'text_data': 'a19d7c970c7744c0a3a4a9515bda3901',
    'rand_digit': 8,
    'rand_number': 0.29319,
    'rand_signed_int': 10,
    'rand_datetime': '2000-09-14T21:27:38',
    'text_array': [
    '89bc047277f24645a8ce679d8ae4b902',
    '9b49f687c9f44345b8b12eaa0dc87921',
],
    'words': 'ladybug sheep',
    'nested': {
    'id': 106,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'snail',
    'bee',
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
    'mixed_type': 0.46987,
    'maybe': 'sheep',
    'maybe_null': 'squid',
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 107,
    'id_str': [
    '21',
],
    'text_data': '179ee5ed059b4f098ee93ba3c3056494',
    'rand_digit': 5,
    'rand_number': 0.79515,
    'rand_signed_int': 7,
    'rand_datetime': '2000-04-07T02:13:43-0400',
    'text_array': [
    '974d3da109ad49628d244c01a3a27a3c',
    '35e231690886483786df405422f667f9',
],
    'words': 'ape bird',
    'nested': {
    'id': 107,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    [
    7,
],
],
    'two_words': [
    'monkey',
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
    25,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'koala',
    'maybe_null': 'ladybug',
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 108,
    'id_str': [
    '23',
    '22',
    '01',
    '13',
    '23',
],
    'text_data': 'b65a457ec11e4f00befe0631185ad714',
    'rand_digit': 1,
    'rand_number': 0.15263,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-24T22:39:03-0100',
    'text_array': [
    '58dadb9cb1fe4439b67b395274dd1436',
    '4921b6f50557498f91cecf10fee335c9',
],
    'words': 'fish duck',
    'nested': {
    'id': 108,
    'rand_digit': 0,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'mosquito',
    'dragonfly',
],
    'city': {
    'name': 'Cardiff',
    'geo': {
    'lat': 51.481581,
    'lon': -3.17909,
},
},
    'rand_tuple': [
    50,
],
    'rand_bool': False,
    'mixed_type': 0.65879,
    'maybe_null': None,
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 109,
    'id_str': [
],
    'text_data': 'b291caab01bf4f698db17ec975b50978',
    'rand_digit': 7,
    'rand_number': 0.62052,
    'rand_signed_int': -4,
    'rand_datetime': '2000-04-21 00:56:25.119732+0900',
    'text_array': [
    '574fb6baac3f4fa2afa5d80e523da294',
    '3ce9af61cbc3429e886ffe0451d0ab15',
],
    'words': 'monkey rabbit',
    'nested': {
    'id': 109,
    'rand_digit': 1,
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
    'word': 'shark',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    [
    2,
],
],
    'two_words': [
    'octopus',
    'dragonfly',
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
    'mixed_type': 0.48476,
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 110,
    'id_str': [
    '03',
    '26',
    '17',
    '20',
    '03',
],
    'text_data': 'ce3921a3d9bb4a2494557e8c4092e808',
    'rand_digit': 1,
    'rand_number': 0.53854,
    'rand_signed_int': 7,
    'rand_datetime': '2000-04-26 12:27:06.622207+1100',
    'text_array': [
    '6d5e131a39ad4708a7d81f4255f25e9b',
    '2879e5a114d54c0eb4ffaeec3cf2ae18',
],
    'words': 'sloth sloth',
    'nested': {
    'id': 110,
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
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'zebra',
    'scorpion',
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
    'mixed_type': 1,
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 111,
    'id_str': [
    '09',
    '29',
],
    'text_data': '4ac16959cc74464c9f407d8270374f2e',
    'rand_digit': 9,
    'rand_number': 0.19196,
    'rand_signed_int': -3,
    'rand_datetime': '2000-12-06T12:10:13.067157-0900',
    'text_array': [
    '009a13085e1a4d31b9908e09b255893c',
    '0da041ba3a4e49b8968b5964b9f3bf6a',
],
    'words': 'chicken cat',
    'nested': {
    'id': 111,
    'rand_digit': 1,
    'array': [
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
    [
    10,
],
],
    'two_words': [
    'ant',
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
    61,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'jaguar',
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 112,
    'id_str': [
    '26',
    '25',
],
    'text_data': 'b33ea073c53a490ab1d8de07fa356d84',
    'rand_digit': 4,
    'rand_number': 0.44532,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-20T17:35:28.606898',
    'text_array': [
    '49ab6fb5b6e44ff79abacb13eadc2f28',
    '8c86331864114858a2e2ec649c56392d',
],
    'words': 'squid zebra',
    'nested': {
    'id': 112,
    'rand_digit': 9,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dolphin',
    'mosquito',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': [
    84,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bird',
    'maybe_null': 'giraffe',
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 113,
    'id_str': [
    '15',
    '08',
],
    'text_data': '3ef9ebc460e54e1f945a99435dbc3dbc',
    'rand_digit': 2,
    'rand_number': 0.11729,
    'rand_signed_int': -8,
    'rand_datetime': '2000-10-02 10:43:24+0700',
    'text_array': [
    '5e9e9ddf1d054adaae07d93237c52fce',
    '5ded3201d9224b3eb82990b64f4d5546',
],
    'words': 'jaguar pig',
    'nested': {
    'id': 113,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    [
    9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'pig',
    'snake',
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
    'mixed_type': None,
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 114,
    'id_str': [
    '12',
    '03',
],
    'text_data': '671e603c2b874aa69a7e5d5dc047839c',
    'rand_digit': 1,
    'rand_number': 0.76871,
    'rand_signed_int': -1,
    'rand_datetime': '2000-10-20T07:33:50.063930',
    'text_array': [
    '96081494b955434eb2a465e15d013aa8',
    '962ddb82b6144aac82c95cc5386db859',
],
    'words': 'spider panda',
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
    'word': 'frog',
    'number': 5,
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
    'shark',
    'spider',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'mosquito',
    'maybe_null': 'butterfly',
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 115,
    'id_str': [
],
    'text_data': '646330622b974d39a35517e258b3aeef',
    'rand_digit': 2,
    'rand_number': 0.31015,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-28 07:56:34.078673+0700',
    'text_array': [
    '246a7302ee694b719a59c1f96fc8717a',
    'b93496c7f9234fd99397c8621ca87bf4',
],
    'words': 'whale camel',
    'nested': {
    'id': 115,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    [
    4,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'butterfly',
    'turtle',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'hippo',
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 116,
    'id_str': [
    '16',
    '21',
    '17',
    '08',
],
    'text_data': '80c5c60e2c624da79b14a854dea95a05',
    'rand_digit': 0,
    'rand_number': 0.08146,
    'rand_signed_int': 8,
    'rand_datetime': '2000-12-27T16:19:42.218920',
    'text_array': [
    '64c1d5027d47465998ac1583bccf117d',
    'c2fcba67b4a04a758e458c5d7814d5e0',
],
    'words': 'cat pig',
    'nested': {
    'id': 116,
    'rand_digit': 4,
    'array': [
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
],
},
    'nested_array': [
],
    'two_words': [
    'goat',
    'sloth',
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
    'mixed_type': 5,
    'maybe_null': None,
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 117,
    'id_str': [
    '14',
    '05',
],
    'text_data': '525506540af44205a8d4e59ce895412a',
    'rand_digit': 1,
    'rand_number': 0.65358,
    'rand_signed_int': -2,
    'rand_datetime': '2000-02-18T00:49:07',
    'text_array': [
    'e909cfaf40704208a14dce3791b57591',
    'cd80a17dc6fa4408b2cba98809841adc',
],
    'words': 'koala lizard',
    'nested': {
    'id': 117,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fly',
    'bear',
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
    'mixed_type': None,
    'maybe': 'butterfly',
    'maybe_null': None,
},
},
    {
    'id': 18,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 118,
    'id_str': [
],
    'text_data': 'f547980f17be4cc383b3fa7807c1996e',
    'rand_digit': 3,
    'rand_number': 0.63403,
    'rand_signed_int': 6,
    'rand_datetime': '2000-03-14 19:29:12-0500',
    'text_array': [
    '180349015e9a4393b0cbb00a944b67fb',
    '34a97f6fc82c4531bec6d9816f24231a',
],
    'words': 'lizard scorpion',
    'nested': {
    'id': 118,
    'rand_digit': 0,
    'array': [
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
    -8,
],
],
    'two_words': [
    'spider',
    'monkey',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.42494,
    'maybe': 'sheep',
    'maybe_null': None,
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
    '04',
    '10',
    '28',
    '04',
    '02',
],
    'text_data': '509a9b806cd5487a83bae91417bba743',
    'rand_digit': 4,
    'rand_number': 0.50264,
    'rand_signed_int': -3,
    'rand_datetime': '2000-12-04T09:31:12',
    'text_array': [
    '5a7e37453b654134a9d0e693781551dd',
    '9d0fcc473d9048e9abe3bb6e7251a9ca',
],
    'words': 'panda octopus',
    'nested': {
    'id': 119,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'pig',
    'wolf',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.40576,
    'maybe': 'lizard',
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 120,
    'id_str': [
],
    'text_data': '72b1771553f7463ebb516b87647ab913',
    'rand_digit': 8,
    'rand_number': 0.68233,
    'rand_signed_int': -9,
    'rand_datetime': '2000-12-14T06:55:24.117683',
    'text_array': [
    '76bf87d3d7fb440eb12e767c52265eaa',
    'f9511a6483ab49f5b05343b5dae20110',
],
    'words': 'scorpion squid',
    'nested': {
    'id': 120,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'snake',
    'monkey',
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
    'mixed_type': 'cow',
    'maybe_null': 'fox',
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 121,
    'id_str': [
    '21',
    '01',
    '14',
    '25',
    '23',
],
    'text_data': '3c973136d94a4013922f55ccd6d45f83',
    'rand_digit': 0,
    'rand_number': 0.51292,
    'rand_signed_int': -10,
    'rand_datetime': '2001-01-25 13:23:44.173755',
    'text_array': [
    '11a2f51ac63c4b14a3fc03f28d82e2bf',
    '5e07cda2771b4609b672f5d9b25c3d85',
],
    'words': 'grasshopper crab',
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
    'word': 'monkey',
    'number': 8,
},
],
},
    'nested_array': [
    [
    8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'bear',
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
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'zebra',
    'maybe_null': None,
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
    '26',
    '29',
    '15',
    '10',
    '09',
],
    'text_data': '839cf7c1b6b94fb6a002a1ddce842dc8',
    'rand_digit': 5,
    'rand_number': 0.84755,
    'rand_signed_int': -10,
    'rand_datetime': '2000-09-06T09:46:41.674815',
    'text_array': [
    'afbb2ae00b14434c9947baaff3284fd2',
    '760727899230481bb09afe820ba77203',
],
    'words': 'koala sheep',
    'nested': {
    'id': 122,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'cheetah',
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
    'lizard',
    'shark',
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
    'maybe': 'elephant',
    'maybe_null': 'giraffe',
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 123,
    'id_str': [
    '16',
    '02',
],
    'text_data': 'ba8ad36f6250495ca753f04b17ae2d85',
    'rand_digit': 6,
    'rand_number': 0.84504,
    'rand_signed_int': 10,
    'rand_datetime': '2000-06-15T22:39:39.532731',
    'text_array': [
    'aaf56b1d5e9341799d7c0ade73088cdc',
    '0069a660cea040ef8e754b1280cd741f',
],
    'words': 'camel pig',
    'nested': {
    'id': 123,
    'rand_digit': 3,
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
],
    'two_words': [
    'snail',
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
    'rand_bool': False,
    'mixed_type': 7,
    'maybe': 'rhino',
    'maybe_null': 'snake',
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 124,
    'id_str': [
],
    'text_data': '2dd7145b05a847b98b78e83bf8d4c5b0',
    'rand_digit': 2,
    'rand_number': 0.85986,
    'rand_signed_int': 1,
    'rand_datetime': '2000-10-14',
    'text_array': [
    '3a4159a9836c4fa4b85cd781b8b1a885',
    'a22fb9a35c7b454abe0196061d6ccd62',
],
    'words': 'lion rhino',
    'nested': {
    'id': 124,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 9,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'pig',
    'kangaroo',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': [
    68,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
    '01',
],
    'text_data': '9fcad54e364649d09a9f3c7a3f47f390',
    'rand_digit': 4,
    'rand_number': 0.55049,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-11 06:56:54-1100',
    'text_array': [
    '9d02684406b944b4ae632bbce6e6f723',
    '187ed34ad3be4a2293fca39d2bb894c1',
],
    'words': 'spider cow',
    'nested': {
    'id': 125,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 4,
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
    'word': 'turtle',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'leopard',
    'dog',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': [
    73,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'camel',
    'maybe_null': 'snail',
},
},
    {
    'id': 26,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 126,
    'id_str': [
    '03',
    '13',
],
    'text_data': 'cc7d9dde71974026a415b9c571071a85',
    'rand_digit': 8,
    'rand_number': 0.08351,
    'rand_signed_int': -4,
    'rand_datetime': '2000-07-31T20:09:48',
    'text_array': [
    '9625a1bcdcbc409389a03137693234f0',
    '8ae53741bb2c42ee84691d513802c51b',
],
    'words': 'giraffe tiger',
    'nested': {
    'id': 126,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'wolf',
    'tiger',
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
    'mixed_type': 1,
    'maybe_null': 'whale',
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 127,
    'id_str': [
    '28',
    '21',
],
    'text_data': 'c0544bff414f43db9c37c0c3e3e131c6',
    'rand_digit': 3,
    'rand_number': 0.25051,
    'rand_signed_int': 6,
    'rand_datetime': '2000-10-10 05:28',
    'text_array': [
    '1277fc35ab9b4727980b47707fe095c3',
    'c3d7f3d21f094b3284ec38ed602f7e19',
],
    'words': 'sheep cow',
    'nested': {
    'id': 127,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 6,
},
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
    -3,
],
],
    'two_words': [
    'mosquito',
    'deer',
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
    'maybe': 'ape',
    'maybe_null': 'cow',
},
},
    {
    'id': 28,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 128,
    'id_str': [
    '27',
    '16',
    '22',
    '20',
],
    'text_data': 'ee573083b8e9409cbb8d2740f4ec1da9',
    'rand_digit': 6,
    'rand_number': 0.10348,
    'rand_signed_int': 9,
    'rand_datetime': '2000-04-17 06:02',
    'text_array': [
    '1c01c099f30e477eb3617b9974ea2b15',
    '829c4adafe9844509224bc49155f3588',
],
    'words': 'shark cat',
    'nested': {
    'id': 128,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
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
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 4,
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
    -3,
],
],
    'two_words': [
    'horse',
    'mouse',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 2,
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
    '03',
    '15',
],
    'text_data': 'fc6afc432f4540d5a47a40c28114bfd5',
    'rand_digit': 3,
    'rand_number': 0.49232,
    'rand_signed_int': 4,
    'rand_datetime': '2000-12-23 06:27',
    'text_array': [
    '35899418bedf474e833d14d560e0d33d',
    '4395355d9fcf4932880e781b9e43c0e0',
],
    'words': 'gorilla rabbit',
    'nested': {
    'id': 129,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    [
],
    [
    -2,
],
],
    'two_words': [
    'gorilla',
    'frog',
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
    'maybe_null': None,
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 130,
    'id_str': [
    '19',
    '05',
    '17',
    '30',
    '10',
],
    'text_data': 'a60cf0c41c58434e9b7fed11b1e37835',
    'rand_digit': 0,
    'rand_number': 0.73037,
    'rand_signed_int': 5,
    'rand_datetime': '2000-05-15',
    'text_array': [
    'a2d4d0d6ae9845afa2a427ea2d422f68',
    '55791b89b27b4a86b3196454418dcb99',
],
    'words': 'sloth hippo',
    'nested': {
    'id': 130,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'leopard',
    'mouse',
],
    'city': {
    'name': 'Rome',
    'geo': {
    'lat': 41.902782,
    'lon': 12.496366,
},
},
    'rand_tuple': [
    56,
],
    'rand_bool': False,
    'mixed_type': 'hyena',
    'maybe_null': 'grasshopper',
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 131,
    'id_str': [
    '11',
],
    'text_data': '9db6ad091d4a439c94766ab991fabc3d',
    'rand_digit': 0,
    'rand_number': 0.91024,
    'rand_signed_int': -1,
    'rand_datetime': '2000-01-02 11:58:51-0200',
    'text_array': [
    '3205f0a91fd64f84a868bc07a0b9b9ff',
    '3f712d5f7c594e7fb3150d44871967b8',
],
    'words': 'frog whale',
    'nested': {
    'id': 131,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
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
    0,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lobster',
    'squid',
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
    'mixed_type': None,
    'maybe_null': 'hippo',
},
},
    {
    'id': 32,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 132,
    'id_str': [
    '19',
    '12',
    '05',
    '15',
    '14',
],
    'text_data': '80f2b35c6c05480981490508711d7eda',
    'rand_digit': 1,
    'rand_number': 0.82118,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-05T12:56:14.903084-11:00',
    'text_array': [
    '5d544447dbfc46b0a4945d2e202e6620',
    '24f5eba45ced49fe842a9b5ccd0d4dc2',
],
    'words': 'lobster leopard',
    'nested': {
    'id': 132,
    'rand_digit': 4,
    'array': [
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    10,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'bee',
    'turtle',
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
    'mixed_type': 0.10822,
    'maybe': 'bee',
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 133,
    'id_str': [
    '12',
],
    'text_data': '2770276cc795416393633a81ec40d2c0',
    'rand_digit': 7,
    'rand_number': 0.91325,
    'rand_signed_int': 7,
    'rand_datetime': '2000-04-07 17:25:41.827301',
    'text_array': [
    '3bc6e086887f42acaf27908be31d2b4d',
    'f0911c146cfd47f6a40835cb3b8ada7b',
],
    'words': 'crab panda',
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
    'word': 'fox',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 3,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'fox',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'fox',
    'mosquito',
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
    'mixed_type': 0.69122,
    'maybe_null': None,
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 134,
    'id_str': [
],
    'text_data': '8f320c47d6a349edafbba9f32aa70291',
    'rand_digit': 1,
    'rand_number': 0.20597,
    'rand_signed_int': -3,
    'rand_datetime': '2000-06-26T04:26:54+0000',
    'text_array': [
    '3c6535b31e404b6fba685e26a0bb97e9',
    '283d0ad46a2946a0a575dae000ed3663',
],
    'words': 'chicken hippo',
    'nested': {
    'id': 134,
    'rand_digit': 1,
    'array': [
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
    'word': 'elephant',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'octopus',
    'giraffe',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': [
    20,
],
    'rand_bool': False,
    'mixed_type': 'hippo',
    'maybe': 'jaguar',
    'maybe_null': 'butterfly',
},
},
    {
    'id': 35,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 135,
    'id_str': [
],
    'text_data': '39404c9613fa4fe4809f2110a5401819',
    'rand_digit': 0,
    'rand_number': 0.9337,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-30 19:04:26-0400',
    'text_array': [
    '238b4478dfa34128b9db66b3c7803399',
    'c98cdad32ccb4d2e8d679ef389879ab4',
],
    'words': 'bear chicken',
    'nested': {
    'id': 135,
    'rand_digit': 8,
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
],
    'word': 'hyena',
    'number': 2,
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
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -3,
],
],
    'two_words': [
    'goat',
    'dolphin',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': 36,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 136,
    'id_str': [
],
    'text_data': 'a6a92fa99d1e42cdb4f2cc225fecec04',
    'rand_digit': 4,
    'rand_number': 0.78023,
    'rand_signed_int': 3,
    'rand_datetime': '2000-12-09 03:47:14-0800',
    'text_array': [
    '2af6a35a50b440c5b815953a58db5641',
    '0669e003782749bd89263355b42ec50a',
],
    'words': 'octopus rhino',
    'nested': {
    'id': 136,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'crab',
    'number': 1,
},
    {
    'nested_empty': None,
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
],
    [
],
    [
    9,
],
],
    'two_words': [
    'dolphin',
    'fish',
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
    'mixed_type': 0.00086,
    'maybe_null': 'octopus',
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
    '15',
    '18',
    '21',
    '04',
    '19',
],
    'text_data': '24b642bdc2f84127984291c01ecfae61',
    'rand_digit': 1,
    'rand_number': 0.97221,
    'rand_signed_int': 10,
    'rand_datetime': '2000-11-03T13:23:58.630898+07:00',
    'text_array': [
    'f82563ce0885497ebb62a04706032f1b',
    'b55f22fa1490439aa948c82eabd26cc7',
],
    'words': 'dog lizard',
    'nested': {
    'id': 137,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'koala',
    'dolphin',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': [
    76,
],
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'kangaroo',
    'maybe_null': None,
},
},
    {
    'id': 38,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 138,
    'id_str': [
    '19',
    '07',
],
    'text_data': '6377341c43594f7e935e037f3cfaa76d',
    'rand_digit': 3,
    'rand_number': 0.21201,
    'rand_signed_int': -9,
    'rand_datetime': '2000-09-25 21:34:19-0200',
    'text_array': [
    '1bc4f3a80ccd448387fb59613ce700b9',
    '39e3762495644f4c9b5ec19c47ce635a',
],
    'words': 'elephant octopus',
    'nested': {
    'id': 138,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 1,
},
],
},
    'nested_array': [
    [
    -7,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'panda',
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
    'rand_bool': False,
    'mixed_type': 1,
    'maybe_null': 'butterfly',
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 139,
    'id_str': [
],
    'text_data': '8ad2a6e9bdbc43f4a34bdc5d48aa3b2b',
    'rand_digit': 4,
    'rand_number': 0.47891,
    'rand_signed_int': -2,
    'rand_datetime': '2000-11-09T01:03:27',
    'text_array': [
    '54a137fa9e8d4e4684a8e1bd71dcd7db',
    '1f498ad3a91e40f8b98c7cb309af6e90',
],
    'words': 'spider fox',
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
    'word': 'giraffe',
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
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'dragonfly',
    'koala',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'wolf',
    'maybe': 'ant',
    'maybe_null': 'cheetah',
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 140,
    'id_str': [
    '23',
    '24',
    '23',
],
    'text_data': '29235848b3bd46bf8af78c0b0f55e2b3',
    'rand_digit': 5,
    'rand_number': 0.5625,
    'rand_signed_int': -1,
    'rand_datetime': '2001-01-14T06:43:21.372100',
    'text_array': [
    'b8d7a8a4f134493e8e7ca57fd65b014d',
    '45eae5ab41f5484cb0c6cf54846625f1',
],
    'words': 'camel whale',
    'nested': {
    'id': 140,
    'rand_digit': 8,
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
    'word': 'kangaroo',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'rhino',
    'mosquito',
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
    'mixed_type': True,
    'maybe': 'fox',
    'maybe_null': 'leopard',
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 141,
    'id_str': [
    '09',
    '23',
    '20',
    '30',
],
    'text_data': '177603e36e7a4e6fa6bd717eb314b22e',
    'rand_digit': 7,
    'rand_number': 0.9962,
    'rand_signed_int': 2,
    'rand_datetime': '2000-01-31 11:53:23.037508-0900',
    'text_array': [
    '173826bf920e4aeaa853b0f53c0dc687',
    '394b9f1116ad4320bf0e52f7cb71d464',
],
    'words': 'bird shark',
    'nested': {
    'id': 141,
    'rand_digit': 7,
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
    'word': 'bear',
    'number': 7,
},
],
},
    'nested_array': [
    [
    4,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'lizard',
    'pig',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'hyena',
    'maybe_null': 'hippo',
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 142,
    'id_str': [
    '18',
    '28',
    '21',
    '25',
    '15',
],
    'text_data': '8b164977ca554d359b770a61ca982d06',
    'rand_digit': 2,
    'rand_number': 0.22062,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-09',
    'text_array': [
    'cb3720665fec420a8d70577a4c3a58d7',
    'b1e8eecd75bf4caea945576fd0dff8bf',
],
    'words': 'jaguar fly',
    'nested': {
    'id': 142,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
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
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'crab',
    'camel',
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
    'maybe_null': 'deer',
},
},
    {
    'id': 43,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 143,
    'id_str': [
    '09',
    '20',
],
    'text_data': '6606abf7a959477f9101895cef1ebdb0',
    'rand_digit': 4,
    'rand_number': 0.73896,
    'rand_signed_int': -7,
    'rand_datetime': '2001-01-28 20:13',
    'text_array': [
    '56585c2197444cd888b30b362bea4fde',
    'fcbc040312ff43ae8371eb197ad27832',
],
    'words': 'tiger fox',
    'nested': {
    'id': 143,
    'rand_digit': 4,
    'array': [
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
    'word': 'ant',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'panda',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -6,
],
    [
    6,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'tiger',
    'wolf',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': [
    54,
],
    'rand_bool': False,
    'mixed_type': 1,
    'maybe': 'mouse',
    'maybe_null': 'whale',
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 144,
    'id_str': [
    '13',
    '19',
    '02',
    '02',
],
    'text_data': 'd9eb44d45cb14d1494876603bdeb55d6',
    'rand_digit': 2,
    'rand_number': 0.55455,
    'rand_signed_int': 0,
    'rand_datetime': '2000-04-24 18:41:25-0800',
    'text_array': [
    '0ae3d395c84b4e5a8fb345914ed6cc5c',
    '67e838ee9b3d4be8b65e35cbbc578f4d',
],
    'words': 'monkey ant',
    'nested': {
    'id': 144,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'koala',
    'kangaroo',
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
    'maybe': 'chicken',
    'maybe_null': 'fly',
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 145,
    'id_str': [
    '02',
    '01',
    '25',
],
    'text_data': 'dddea0755c9e4001908090a8154122f7',
    'rand_digit': 8,
    'rand_number': 0.17097,
    'rand_signed_int': -8,
    'rand_datetime': '2000-06-20 13:23:35+1100',
    'text_array': [
    '38480445b7b94fa78dd594a6b2b4572a',
    '6667a909197a4fe9bd9c1c96b722bdc8',
],
    'words': 'pig ape',
    'nested': {
    'id': 145,
    'rand_digit': 6,
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
    'word': 'bird',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ant',
    'whale',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': [
    31,
],
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
    '20',
],
    'text_data': '341c31ec725b4eed92f760ea5cc034cb',
    'rand_digit': 4,
    'rand_number': 0.7016,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-22 12:46:21',
    'text_array': [
    'b7b49ff4ac7e4aa2ac9816d04e549fbb',
    '38a7757bc53c4211a5ac6b95cc30aaf7',
],
    'words': 'rabbit monkey',
    'nested': {
    'id': 146,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'butterfly',
    'chicken',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'kangaroo',
    'maybe_null': 'bee',
},
},
    {
    'id': 47,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 147,
    'id_str': [
    '28',
],
    'text_data': 'd8b8f0429e91475686949702757adf74',
    'rand_digit': 0,
    'rand_number': 0.5912,
    'rand_signed_int': 8,
    'rand_datetime': '2000-11-14T11:02:37+0000',
    'text_array': [
    'd294e858f42e4d75915888725252c75f',
    'ee89fe5b363345e58d7710ffa254a6bd',
],
    'words': 'gorilla dolphin',
    'nested': {
    'id': 147,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 2,
},
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bee',
    'gorilla',
],
    'city': {
    'name': 'Kuala Lumpur',
    'geo': {
    'lat': 3.139003,
    'lon': 101.686855,
},
},
    'rand_tuple': [
    49,
],
    'rand_bool': False,
    'mixed_type': True,
},
},
    {
    'id': 48,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 148,
    'id_str': [
    '20',
    '28',
    '27',
    '06',
],
    'text_data': '2eed9db7e3a046e2859e592970b3fc9f',
    'rand_digit': 7,
    'rand_number': 0.35863,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-21T18:16:52.058159',
    'text_array': [
    '7f392a3be5574b30ba140fd35af1b277',
    'b75dd693297642288b39c53773576ccc',
],
    'words': 'rabbit dolphin',
    'nested': {
    'id': 148,
    'rand_digit': 9,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -10,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'mouse',
    'monkey',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'monkey',
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 149,
    'id_str': [
    '28',
    '13',
],
    'text_data': '64c973b44fee429281248caa17e988a6',
    'rand_digit': 0,
    'rand_number': 0.25088,
    'rand_signed_int': -6,
    'rand_datetime': '2000-05-12',
    'text_array': [
    '487ec7edc62e4501b2ee55049c6b0d55',
    'c4474d9d0c24473f867274de12193897',
],
    'words': 'whale snake',
    'nested': {
    'id': 149,
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
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'rhino',
    'fish',
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
    'mixed_type': 7,
    'maybe': 'kangaroo',
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



    def test_request_4(self):
        """测试请求 4 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '126',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'context': [
    {
    'positive': 11,
    'negative': 19,
},
],
},
    'using': 'multi-code',
    'limit': 100,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_multivector_discovery_queries.test_context_euclidean')
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
    test = TestMultivectorDiscoveryQueriestestContextEuclidean()
    test.run_tests()
