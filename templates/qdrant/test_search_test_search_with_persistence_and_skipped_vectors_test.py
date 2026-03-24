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
logger = logging.getLogger('vdb_fuzzer.test.test_search_test_search_with_persistence_and_skipped_vectors')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_search.test_search_with_persistence_and_skipped_vectors"
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



class TestSearchtestSearchWithPersistenceAndSkippedVectors:
    """自动生成的VDB模糊测试类 - test_search.test_search_with_persistence_and_skipped_vectors"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_search.test_search_with_persistence_and_skipped_vectors"
        self.test_count = 12  # 测试方法数量
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
    'content-length': '132756',
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
],
    'text_data': '71cd8841ac474c1cbc76c62b760dfd36',
    'rand_digit': 0,
    'rand_number': 0.84513,
    'rand_signed_int': 9,
    'rand_datetime': '2000-12-30 07:42:11.985325',
    'text_array': [
    '60e85e212f5341e986503703180f344d',
    'dda1412aeb794c86a609cf2d3dcc6d82',
],
    'words': 'giraffe dolphin',
    'nested': {
    'id': 100,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 1,
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
    'octopus',
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
    'mixed_type': 3,
    'maybe': 'fish',
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
],
    'text_data': '1112bd13eb4745ff91387b1a96dc3ed2',
    'rand_digit': 8,
    'rand_number': 0.73572,
    'rand_signed_int': -6,
    'rand_datetime': '2000-05-07T13:23:19.875039Z',
    'text_array': [
    '58b733b58f3d489fb2f4bdf0937fc21d',
    '0439d453553d4ba8a63ee0286bfbf032',
],
    'words': 'spider butterfly',
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
    'word': 'cat',
    'number': 5,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'mosquito',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'duck',
    'wolf',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': [
    63,
],
    'rand_bool': False,
    'mixed_type': 0.97043,
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
    '18',
    '23',
    '10',
    '28',
    '27',
],
    'text_data': '6988775fd5644c5497ebd2656e9c4818',
    'rand_digit': 3,
    'rand_number': 0.00474,
    'rand_signed_int': -3,
    'rand_datetime': '2000-05-15 17:16:11.228996',
    'text_array': [
    '7e8d1531bcc54954b6bb968a301c6d6a',
    'e0e644f9d9b342bfa00d688cf0cde8da',
],
    'words': 'kangaroo zebra',
    'nested': {
    'id': 102,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'giraffe',
    'duck',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': [
    82,
],
    'rand_bool': False,
    'mixed_type': 0.33459,
    'maybe_null': 'scorpion',
},
},
    {
    'id': 3,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 103,
    'id_str': [
    '06',
    '15',
],
    'text_data': '3d9c51db674b4936a25c9f9a759915b4',
    'rand_digit': 4,
    'rand_number': 0.53555,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-27 19:55:03',
    'text_array': [
    '1743e1556bdf4d0db4b53fcfe6e4483b',
    'adce8824831d4cf4885cc3c4647e1b1c',
],
    'words': 'jaguar sloth',
    'nested': {
    'id': 103,
    'rand_digit': 6,
    'array': [
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
    'word': 'dragonfly',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'wolf',
    'spider',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 8,
    'maybe': 'spider',
    'maybe_null': None,
},
},
    {
    'id': 4,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 104,
    'id_str': [
],
    'text_data': '5987ce8a92104456b5ac06cdd76346d5',
    'rand_digit': 3,
    'rand_number': 0.86517,
    'rand_signed_int': -2,
    'rand_datetime': '2000-01-23T16:37:56',
    'text_array': [
    '6bac678bc5ae4a8db653fcf66be06ea4',
    '4a4b95ae6dbd416eb038ec1663c0abbd',
],
    'words': 'ape jaguar',
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
    'word': 'shark',
    'number': 2,
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
    'sheep',
    'hippo',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': [
    7,
],
    'rand_bool': True,
    'mixed_type': 'lion',
    'maybe': 'hippo',
    'maybe_null': 'deer',
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
    '03',
    '04',
    '15',
    '15',
    '14',
],
    'text_data': 'c52798fcb7ed42fdb4d697d00dc9b7ea',
    'rand_digit': 8,
    'rand_number': 0.44901,
    'rand_signed_int': 7,
    'rand_datetime': '2000-11-10T02:58:26',
    'text_array': [
    'ded07d7dcbcd435ebd2da4f103ddd280',
    'c3373cb9e7b6473082cf7224e4ed611a',
],
    'words': 'bear pig',
    'nested': {
    'id': 105,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 5,
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
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'giraffe',
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
    '17',
    '05',
    '04',
    '10',
],
    'text_data': '1cf179494f734776be458a2fcc3b346a',
    'rand_digit': 1,
    'rand_number': 0.17107,
    'rand_signed_int': 9,
    'rand_datetime': '2000-04-23T00:05:28.000198',
    'text_array': [
    '07c3dc72d26f49329b17fd5ec9f2d41b',
    'a042d21823f04424b49110acd9575d50',
],
    'words': 'bee shark',
    'nested': {
    'id': 106,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 10,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'butterfly',
    'lion',
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
    'mixed_type': 'ant',
    'maybe': 'mosquito',
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
    '30',
    '26',
],
    'text_data': '30267b6d642f406bb4746eadf55d92ae',
    'rand_digit': 7,
    'rand_number': 0.01129,
    'rand_signed_int': 3,
    'rand_datetime': '2000-02-20T13:08:18.890323',
    'text_array': [
    'c3824228f24b404cb002170f7d1fde6b',
    '74c330c3e10f4abca019ecb1ac215ee6',
],
    'words': 'snail cat',
    'nested': {
    'id': 107,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    [
    8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -2,
],
    [
],
    [
],
],
    'two_words': [
    'dog',
    'pig',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'hyena',
},
},
    {
    'id': 8,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 108,
    'id_str': [
    '13',
    '29',
    '24',
    '19',
],
    'text_data': '9d7cd1146efe43718f6891725d763e5a',
    'rand_digit': 1,
    'rand_number': 0.68467,
    'rand_signed_int': -4,
    'rand_datetime': '2000-09-13 17:49:33-0700',
    'text_array': [
    'cf4ea4011e6149c48ef68a7055763bd9',
    '81efb20ad8f946beafaa34a4bbbdf683',
],
    'words': 'kangaroo fish',
    'nested': {
    'id': 108,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
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
    'rhino',
    'horse',
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
    'mixed_type': True,
    'maybe': 'wolf',
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
    '08',
    '11',
    '25',
],
    'text_data': '8e9847ef5c014e79954c8fc925332a67',
    'rand_digit': 8,
    'rand_number': 0.18776,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-23T05:56:03.610412',
    'text_array': [
    'd1d7c6a236ec452da83b5764b390ac2e',
    '14bb044438ac45cca1f1cfd8302435dd',
],
    'words': 'whale gorilla',
    'nested': {
    'id': 109,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
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
    'number': 1,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 4,
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
    'turtle',
    'ape',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': [
    91,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'mosquito',
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
    '22',
    '21',
    '29',
],
    'text_data': 'e624cdea3ab843e697b65620ded26470',
    'rand_digit': 7,
    'rand_number': 0.67775,
    'rand_signed_int': -9,
    'rand_datetime': '2000-03-07 02:04:43.160494-0500',
    'text_array': [
    'b8a5c53c6e234c70b956d068652176ec',
    '5397538f396f431c8aede7b2db4c9479',
],
    'words': 'grasshopper fly',
    'nested': {
    'id': 110,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 2,
},
],
},
    'nested_array': [
    [
    10,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'mosquito',
    'tiger',
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
    'mixed_type': None,
    'maybe': 'bee',
},
},
    {
    'id': 11,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 111,
    'id_str': [
    '30',
    '05',
    '08',
    '22',
],
    'text_data': '4da41bc84fd647bda992bf635ece466c',
    'rand_digit': 4,
    'rand_number': 0.40783,
    'rand_signed_int': 7,
    'rand_datetime': '2000-10-26T02:43:40.768012',
    'text_array': [
    '2f479b68006e48448ee3c0a935292da1',
    '7dd8101f1e67481a8aa68a18ac940145',
],
    'words': 'dragonfly mouse',
    'nested': {
    'id': 111,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'giraffe',
    'camel',
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
    'mixed_type': 'mouse',
    'maybe_null': 'ape',
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
],
    'text_data': '60ecdc309a634f59849ae5ddbdb6080e',
    'rand_digit': 7,
    'rand_number': 0.04189,
    'rand_signed_int': -7,
    'rand_datetime': '2000-04-07T01:15:30.932918',
    'text_array': [
    'd0e32edce60d4dd5bfb4d5e8ebc1170b',
    '60800fba41524a0eb8b261e569188eec',
],
    'words': 'snake dragonfly',
    'nested': {
    'id': 112,
    'rand_digit': 3,
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
    'word': 'dolphin',
    'number': 6,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 3,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'horse',
    'rabbit',
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
    'mixed_type': 0.01139,
    'maybe': 'spider',
},
},
    {
    'id': 13,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    'payload': {
    'id': 113,
    'id_str': [
    '29',
],
    'text_data': '74ced15e7dae489d9742880c4199fa4a',
    'rand_digit': 9,
    'rand_number': 0.20823,
    'rand_signed_int': 7,
    'rand_datetime': '2000-08-04 11:45:35-1200',
    'text_array': [
    '8c548919e646436ca379c3e2fea724d9',
    '59320b358e9743c4a648ac686bb1e944',
],
    'words': 'ant bird',
    'nested': {
    'id': 113,
    'rand_digit': 8,
    'array': [
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
],
    'word': 'snail',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'cat',
    'cow',
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
    'mixed_type': 7,
    'maybe': 'elephant',
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
    'text_data': 'e2e03b8af9984171a66197d0c182d77c',
    'rand_digit': 7,
    'rand_number': 0.21998,
    'rand_signed_int': 1,
    'rand_datetime': '2000-12-07 00:22:28.339606-0700',
    'text_array': [
    '3dff0d5e697344fba16af18cb89f37d1',
    'cf889c9700bd45ea8ed3acd28744d1bb',
],
    'words': 'butterfly butterfly',
    'nested': {
    'id': 114,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 4,
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
    'nested_empty': None,
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
    'word': 'fly',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'shark',
    'leopard',
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
    'mixed_type': 'lizard',
    'maybe_null': 'pig',
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
    '29',
    '07',
],
    'text_data': '49dc0e0600fd44e0883cef038a3ff882',
    'rand_digit': 3,
    'rand_number': 0.40334,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-02 03:14:56.518632+0300',
    'text_array': [
    '7e6b1b89f2ae47438a42f5e64ab750bf',
    'e5086bdd1e7f4678800ccc7e6663958d',
],
    'words': 'cat lion',
    'nested': {
    'id': 115,
    'rand_digit': 7,
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
    {
    'nested_empty': None,
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
    'word': 'hippo',
    'number': 10,
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
    'word': 'ape',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'jaguar',
    'ant',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': [
    86,
],
    'rand_bool': True,
    'mixed_type': 5,
    'maybe': 'monkey',
    'maybe_null': None,
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
    '30',
],
    'text_data': 'a19fb94dde084f5c85fb54f14629fdda',
    'rand_digit': 0,
    'rand_number': 0.95552,
    'rand_signed_int': 8,
    'rand_datetime': '2000-07-12T01:54:32',
    'text_array': [
    'faf133d0e86f43ec84cdd7a8755cbd2a',
    '7e41ad0b819f4cf896d219abe8f75932',
],
    'words': 'duck wolf',
    'nested': {
    'id': 116,
    'rand_digit': 2,
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
],
},
    'nested_array': [
    [
    3,
],
    [
],
    [
    -3,
],
    [
    1,
],
    [
],
],
    'two_words': [
    'cat',
    'fox',
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
    'maybe': 'sloth',
    'maybe_null': 'tiger',
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
    '21',
    '14',
    '17',
    '13',
],
    'text_data': '58fee16665874630acb2fa436d39197f',
    'rand_digit': 2,
    'rand_number': 0.69466,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-13 06:28:43',
    'text_array': [
    'f971b1932441415b97bedeee718520a4',
    '079a631867234d00ac4df1e05f387841',
],
    'words': 'monkey goat',
    'nested': {
    'id': 117,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -9,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'cow',
    'lizard',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'crab',
    'maybe_null': 'sloth',
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
    '14',
],
    'text_data': '543c8f401f8e4d37b3e6302980dbdd53',
    'rand_digit': 6,
    'rand_number': 0.96316,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-20T18:55:41.551219+0400',
    'text_array': [
    'ae977da5a0aa4a119e7d6983ac0cf83f',
    '848a556f3d254efea591094a0a6b5954',
],
    'words': 'dog panda',
    'nested': {
    'id': 118,
    'rand_digit': 7,
    'array': [
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
    'word': 'sheep',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'frog',
    'sloth',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '29',
    '16',
    '17',
    '29',
    '01',
],
    'text_data': 'a6ae124fe157451ea053bcd479c40559',
    'rand_digit': 1,
    'rand_number': 0.44899,
    'rand_signed_int': -7,
    'rand_datetime': '2000-02-12T05:47:51',
    'text_array': [
    '25eeee5897f945d2a797d15b954a9c24',
    'e3e46b44c9b6472591f3c9c0b612192e',
],
    'words': 'cat tiger',
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
    'word': 'lion',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'goat',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'snail',
    'rabbit',
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
    'mixed_type': 0.89003,
    'maybe': 'hyena',
    'maybe_null': 'sloth',
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
    '19',
],
    'text_data': 'f9da1350c68442f9b79bf1f6ccbdc15b',
    'rand_digit': 3,
    'rand_number': 0.92254,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-26 08:12:24',
    'text_array': [
    '3810a07a8f154ccf958b271d8fe78b7b',
    '869b0418806a43b999f2b4549c48ad4b',
],
    'words': 'frog bee',
    'nested': {
    'id': 120,
    'rand_digit': 8,
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
],
    'word': 'gorilla',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dragonfly',
    'mouse',
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
    'mixed_type': 1,
    'maybe': 'dragonfly',
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
],
    'text_data': 'f8ab1d59044f4407a818ea8b2864060b',
    'rand_digit': 4,
    'rand_number': 0.07453,
    'rand_signed_int': -7,
    'rand_datetime': '2000-05-20T07:42:04.369332-0800',
    'text_array': [
    'f8c4270b883045f5a4689f086aefdb30',
    '6f2008e852f24dbd9fb47af3045f477f',
],
    'words': 'turtle monkey',
    'nested': {
    'id': 121,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 3,
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
    'hello',
],
    'word': 'sheep',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'monkey',
    'shark',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe_null': 'dolphin',
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
    '04',
    '24',
],
    'text_data': '942e07fd413343f38180017f71c37f40',
    'rand_digit': 6,
    'rand_number': 0.29056,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-22 11:57:52.751725+0000',
    'text_array': [
    '89620a1c14c045bb9e4ba2df01ae9698',
    '62701f657c3342d7bdc3cb3b76e03536',
],
    'words': 'bee jaguar',
    'nested': {
    'id': 122,
    'rand_digit': 4,
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
],
    'word': 'panda',
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
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'fox',
    'cow',
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
    'mixed_type': None,
    'maybe_null': 'lion',
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
    '23',
    '29',
    '24',
    '02',
    '28',
],
    'text_data': '39fe6493add6411192b59261f10b3e30',
    'rand_digit': 9,
    'rand_number': 0.44723,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-16 22:06:50.583144-0600',
    'text_array': [
    'a1243c78097c436d92863282829d798c',
    'e225f26cd6744f7da251783184ef9f03',
],
    'words': 'fish snake',
    'nested': {
    'id': 123,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'deer',
    'number': 9,
},
],
},
    'nested_array': [
    [
    4,
],
    [
    -5,
],
    [
    10,
],
    [
    3,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'mouse',
    'lobster',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': [
    66,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'lion',
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
    '25',
    '01',
],
    'text_data': 'b253c3a88aa346a7beddd0e40953c2a6',
    'rand_digit': 2,
    'rand_number': 0.10431,
    'rand_signed_int': 7,
    'rand_datetime': '2000-10-10T09:48:35.069288-0700',
    'text_array': [
    'ed92aae937474e539afa06945547f328',
    '2d929bf132d84368a7847dff3d90575b',
],
    'words': 'bee ape',
    'nested': {
    'id': 124,
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
    'nested_empty': None,
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
    'word': 'bear',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'butterfly',
    'mouse',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'sheep',
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
    '02',
    '15',
    '24',
    '22',
],
    'text_data': 'ca07b0c52d8d4a338fa76a7e2e0348ac',
    'rand_digit': 7,
    'rand_number': 0.7889,
    'rand_signed_int': 7,
    'rand_datetime': '2000-06-07 18:11:10.666732',
    'text_array': [
    '62ecda8dc32b44d8b8fcbb29d6ec9f90',
    '5b824a699b9841d69ef8499991324057',
],
    'words': 'octopus ant',
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
    'word': 'chicken',
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
    'word': 'dog',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'elephant',
    'gorilla',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': [
    37,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bear',
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
    '16',
],
    'text_data': '537c5ac12eba4802a7c80b539a52f165',
    'rand_digit': 7,
    'rand_number': 0.74825,
    'rand_signed_int': 3,
    'rand_datetime': '2000-06-17T14:43:02',
    'text_array': [
    'f921e5880d7e4d0cba4b777eff3cbe1d',
    '5cb68042ce1245bf9ffe435a783f463a',
],
    'words': 'pig zebra',
    'nested': {
    'id': 126,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 6,
},
],
},
    'nested_array': [
    [
    -5,
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'mouse',
    'dolphin',
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
    'mixed_type': True,
    'maybe': 'sloth',
    'maybe_null': None,
},
},
    {
    'id': 27,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 127,
    'id_str': [
    '25',
    '12',
    '24',
],
    'text_data': '4175eda66a95494cb96a8c8001e57491',
    'rand_digit': 1,
    'rand_number': 0.71718,
    'rand_signed_int': -2,
    'rand_datetime': '2000-11-30T17:58:47.614807-11:00',
    'text_array': [
    'a723f070f0b64396bd0d166aad55a68e',
    '9fef497fe500428d82737e5ffb8c99f1',
],
    'words': 'butterfly fox',
    'nested': {
    'id': 127,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'sloth',
    'number': 3,
},
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
    'bird',
    'chicken',
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
    'maybe_null': 'fish',
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
    '03',
    '06',
    '02',
],
    'text_data': '9eab0a81ac884be99c981e0b041c0375',
    'rand_digit': 3,
    'rand_number': 0.88238,
    'rand_signed_int': 9,
    'rand_datetime': '2000-05-23T22:11:24.914861',
    'text_array': [
    'c5e1652908e54dfab3e11a19706d62b7',
    '9fbb796aa95f42a6b710c8294c9eff08',
],
    'words': 'wolf gorilla',
    'nested': {
    'id': 128,
    'rand_digit': 8,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 6,
},
],
},
    'nested_array': [
    [
    6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fly',
    'bee',
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
    'mixed_type': 0.76198,
    'maybe': 'dolphin',
    'maybe_null': None,
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
    '15',
    '18',
],
    'text_data': '97aadc60d3534fbf81e047d2e01d4519',
    'rand_digit': 4,
    'rand_number': 0.36055,
    'rand_signed_int': -7,
    'rand_datetime': '2000-04-23 18:43:17',
    'text_array': [
    '096c9522118b4d93af9bc3baf5209bd2',
    'ef556ca61b7a4619a2c745eeb93fbbe2',
],
    'words': 'dog cow',
    'nested': {
    'id': 129,
    'rand_digit': 1,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    6,
],
],
    'two_words': [
    'dolphin',
    'rabbit',
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
    'mixed_type': True,
    'maybe': 'monkey',
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
    '11',
    '28',
    '20',
],
    'text_data': '840fdd7d8218424aa84c0d0a2d77a904',
    'rand_digit': 9,
    'rand_number': 0.39302,
    'rand_signed_int': 3,
    'rand_datetime': '2000-04-20T19:26:07',
    'text_array': [
    '595991f11fe24703aa85a6b76c36734a',
    '173f7f7399584dbebc51ce57260643d7',
],
    'words': 'fly leopard',
    'nested': {
    'id': 130,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'duck',
    'number': 9,
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
    'word': 'deer',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'goat',
    'rhino',
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
    'mixed_type': None,
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
    '30',
    '26',
    '21',
],
    'text_data': '702c954f9118428ea7a23a66630d381b',
    'rand_digit': 4,
    'rand_number': 0.57654,
    'rand_signed_int': 6,
    'rand_datetime': '2000-08-29T13:12:26.270526+01:00',
    'text_array': [
    '389d6d2f94a4400db9cd852d5969d1ff',
    '75f6204bec2c4a2d8f810a96c9fe6382',
],
    'words': 'spider lion',
    'nested': {
    'id': 131,
    'rand_digit': 8,
    'array': [
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
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'cheetah',
    'sheep',
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
    'mixed_type': 5,
    'maybe': 'panda',
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
    '09',
    '30',
    '29',
    '30',
    '08',
],
    'text_data': '94ce523cdcb34667b9ad2dcb5e776345',
    'rand_digit': 3,
    'rand_number': 0.66929,
    'rand_signed_int': -3,
    'rand_datetime': '2000-05-19 22:05:25-0900',
    'text_array': [
    'f83c6b0438984eaab36f93a3eb68c245',
    'cd1a0816a3414f80865334ea016e661c',
],
    'words': 'butterfly fish',
    'nested': {
    'id': 132,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 7,
},
    {
    'nested_empty': None,
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
    'word': 'fish',
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -9,
],
],
    'two_words': [
    'gorilla',
    'jaguar',
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
    'mixed_type': 0.11264,
    'maybe': 'ape',
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
    '10',
    '25',
    '21',
],
    'text_data': '7cc672f3b5934106953662281c96b8b3',
    'rand_digit': 9,
    'rand_number': 0.738,
    'rand_signed_int': 5,
    'rand_datetime': '2000-06-11T05:20:54',
    'text_array': [
    '072e3294106f4ae4b72d50a0dee4dd1a',
    '11584d13f33f4b0fa14ba6be0064f72b',
],
    'words': 'monkey bee',
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
    'word': 'bird',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'cheetah',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'mouse',
},
},
    {
    'id': 34,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 134,
    'id_str': [
    '29',
],
    'text_data': '477b3012c4e94f60988e915367b354de',
    'rand_digit': 0,
    'rand_number': 0.80448,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-15T16:36:03',
    'text_array': [
    'be07404b396c4f4693835ff8cba7e920',
    '1c8ddbb9e217483592037ade3152e06b',
],
    'words': 'whale chicken',
    'nested': {
    'id': 134,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
    -2,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'crab',
    'sheep',
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
    'mixed_type': 0.91651,
    'maybe': 'panda',
    'maybe_null': 'koala',
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
    'text_data': '0d9505741ace47c9bd9847fa0f6794fa',
    'rand_digit': 6,
    'rand_number': 0.38407,
    'rand_signed_int': 0,
    'rand_datetime': '2000-05-16 00:16:31.267812+1200',
    'text_array': [
    'ebd04fd7a04e4013a810b7d83550c9c7',
    '0cb764f939b143af8c7a65675cea17e4',
],
    'words': 'sloth snail',
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
    'word': 'sloth',
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
    'number': 7,
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
    'hello',
],
    'word': 'ape',
    'number': 9,
},
],
},
    'nested_array': [
    [
    1,
],
    [
    -5,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'koala',
    'elephant',
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
    'maybe_null': 'jaguar',
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
    '17',
    '07',
    '15',
    '21',
    '04',
],
    'text_data': '96b0324a037e4ffdbeb183f7c656a7ef',
    'rand_digit': 6,
    'rand_number': 0.98741,
    'rand_signed_int': 5,
    'rand_datetime': '2000-04-27 10:49:29-0400',
    'text_array': [
    'cc6858eebecd40c994581092c8846c2d',
    '4f865f68f2a4459ababe0ca77ea74be5',
],
    'words': 'spider scorpion',
    'nested': {
    'id': 136,
    'rand_digit': 5,
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
],
},
    'nested_array': [
    [
    -8,
],
],
    'two_words': [
    'dolphin',
    'spider',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'lion',
    'maybe_null': 'lion',
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
],
    'text_data': '9502a27405a5453ea882165eb517d663',
    'rand_digit': 6,
    'rand_number': 0.55297,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-09T21:36:13.646090-0600',
    'text_array': [
    '3f424e6011344038992932eefbececf3',
    '82d1a8c655864418807797cce818ded4',
],
    'words': 'goat frog',
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
    'word': 'ape',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -8,
],
],
    'two_words': [
    'snail',
    'panda',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': [
    90,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'snake',
},
},
    {
    'id': 38,
    'vector': {
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 138,
    'id_str': [
    '13',
    '07',
    '05',
    '08',
],
    'text_data': 'af28440a18664e7fb85340b3ad13bb88',
    'rand_digit': 3,
    'rand_number': 0.39441,
    'rand_signed_int': -5,
    'rand_datetime': '2000-07-31 11:42:38.681951+0500',
    'text_array': [
    '458ff36d508440fd99763a1253a88b24',
    '0d5b56eed227463f8e7905046b5a1ec9',
],
    'words': 'rabbit tiger',
    'nested': {
    'id': 138,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    [
],
    [
    -8,
],
],
    'two_words': [
    'zebra',
    'shark',
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
    '12',
    '06',
    '16',
],
    'text_data': '1e7cb8c017984dd6a515b9acf7c6dd2b',
    'rand_digit': 1,
    'rand_number': 0.22476,
    'rand_signed_int': 7,
    'rand_datetime': '2000-01-28 13:01:22',
    'text_array': [
    '16f4849ee703438190da6edc62b65dce',
    'c48305a0d4444457ab04c413407b5206',
],
    'words': 'ant bear',
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
    'word': 'grasshopper',
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
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 4,
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
    'word': 'spider',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'hippo',
    'leopard',
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
    'mixed_type': None,
    'maybe': 'turtle',
    'maybe_null': 'crab',
},
},
    {
    'id': 40,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    'payload': {
    'id': 140,
    'id_str': [
    '13',
    '03',
    '29',
    '15',
],
    'text_data': '42ae9c3b81934724b2467007bd9e8171',
    'rand_digit': 7,
    'rand_number': 0.80959,
    'rand_signed_int': 1,
    'rand_datetime': '2000-08-28 21:51:06.771227',
    'text_array': [
    'e5e7018c46724fae913f262a22844de3',
    '72dc9724934f4a68a94ea75a11ea668f',
],
    'words': 'dragonfly grasshopper',
    'nested': {
    'id': 140,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 6,
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
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'sheep',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'pig',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    [
    -3,
],
    [
],
    [
    10,
],
    [
    2,
],
],
    'two_words': [
    'koala',
    'dog',
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
    'mixed_type': False,
    'maybe': 'tiger',
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
    '06',
    '09',
    '20',
    '19',
],
    'text_data': '7fc7fbcfd34e4a3c96e71018d288914d',
    'rand_digit': 4,
    'rand_number': 0.25169,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-26 10:47:51.253461+0100',
    'text_array': [
    '6d826816387541a283f3f004d26e1456',
    '6ef840c5945f4843b8e3470236b558f0',
],
    'words': 'duck wolf',
    'nested': {
    'id': 141,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'tiger',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'mouse',
    'koala',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'lizard',
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
    '15',
    '02',
    '18',
    '29',
    '02',
],
    'text_data': 'ece761b38fdb43159c9adea9306c8a8d',
    'rand_digit': 1,
    'rand_number': 0.04527,
    'rand_signed_int': -7,
    'rand_datetime': '2000-09-23T12:01:02.094123',
    'text_array': [
    '695f715f3fe14a13bb2aad61e4070fb4',
    'e626ea58c5c74c9c9ef4c706440436a1',
],
    'words': 'dog snake',
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
    'word': 'gorilla',
    'number': 6,
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
    'word': 'koala',
    'number': 2,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -9,
],
],
    'two_words': [
    'cheetah',
    'octopus',
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
    'mixed_type': None,
    'maybe': 'butterfly',
    'maybe_null': 'chicken',
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
    '17',
    '28',
    '10',
    '23',
],
    'text_data': '73cd9d969459476abaf83598e0bff8b5',
    'rand_digit': 0,
    'rand_number': 0.70923,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-08',
    'text_array': [
    'bb13072f8ebb4134a1f399aa5828b15e',
    '063e507275ce496ca32dea3600ef455e',
],
    'words': 'tiger squid',
    'nested': {
    'id': 143,
    'rand_digit': 8,
    'array': [
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
    'hello',
],
    'word': 'wolf',
    'number': 10,
},
    {
    'nested_empty': None,
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
    'word': 'duck',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'chicken',
    'camel',
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
    'mixed_type': 'leopard',
    'maybe': 'monkey',
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
],
    'text_data': '257f19aca8cd49368679eddb59b65fd4',
    'rand_digit': 7,
    'rand_number': 0.60454,
    'rand_signed_int': -4,
    'rand_datetime': '2000-07-13 11:06:15.806996',
    'text_array': [
    '5296829f6c014024a90ddea5312de4ab',
    '11965312088b4c8c9b1e7b6af1db3fa4',
],
    'words': 'sheep scorpion',
    'nested': {
    'id': 144,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'wolf',
    'number': 3,
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
    'crab',
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
    'mixed_type': False,
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
    '12',
    '01',
    '09',
],
    'text_data': '153551996c2d4eebba065e23c715f633',
    'rand_digit': 4,
    'rand_number': 0.49284,
    'rand_signed_int': -4,
    'rand_datetime': '2000-12-21 01:45:48.611365',
    'text_array': [
    'bce32ad5da584e07899c1693168f5a58',
    '89ec810959c24a7097d110939580c87c',
],
    'words': 'zebra butterfly',
    'nested': {
    'id': 145,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'sheep',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'bird',
    'pig',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'sheep',
},
},
    {
    'id': 46,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 146,
    'id_str': [
    '01',
    '29',
    '02',
    '18',
],
    'text_data': '9ca6b02175e24cd284995288ee79af78',
    'rand_digit': 6,
    'rand_number': 0.26763,
    'rand_signed_int': 10,
    'rand_datetime': '2000-08-28 13:51:20+0100',
    'text_array': [
    '5eb3764055f741fe833f53022d849034',
    'd987e69432cb4cc4a8732ec4ffe5b253',
],
    'words': 'camel koala',
    'nested': {
    'id': 146,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 7,
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
],
    'word': 'spider',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'hippo',
    'rabbit',
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
    'maybe': 'horse',
    'maybe_null': None,
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
    '07',
    '21',
    '16',
    '17',
],
    'text_data': '016a03c590694e02a26b851055c89900',
    'rand_digit': 2,
    'rand_number': 0.31528,
    'rand_signed_int': 2,
    'rand_datetime': '2000-02-03T09:05:20.478768-1200',
    'text_array': [
    'ef2c7a0800274178a970dd6b05ea94b9',
    '7eb2f97ffc3843efaeaae23e0bcb16d7',
],
    'words': 'bee duck',
    'nested': {
    'id': 147,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'camel',
    'turtle',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'lion',
    'maybe_null': 'fly',
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
    '11',
    '11',
],
    'text_data': '8716b582104e4283bc2bdeb787446c5d',
    'rand_digit': 1,
    'rand_number': 0.32404,
    'rand_signed_int': 0,
    'rand_datetime': '2000-06-23T19:20:14.701637',
    'text_array': [
    '4e350abd55664fd5b35f21c45389f0ec',
    'f408fc5ac5a9425e9d179d9d1c22b35a',
],
    'words': 'snake shark',
    'nested': {
    'id': 148,
    'rand_digit': 7,
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
    'word': 'ant',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'whale',
    'hyena',
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
    'mixed_type': 3,
    'maybe': 'turtle',
    'maybe_null': 'deer',
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
    '07',
    '09',
    '01',
    '05',
    '30',
],
    'text_data': '74967c2e29df4950912eaac500257111',
    'rand_digit': 5,
    'rand_number': 0.83097,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-16 11:16:46',
    'text_array': [
    'c82d60873ccf4fc6b1fabe1c118d1ac9',
    'a7e10f91ede64e1a80e076061a8e0b98',
],
    'words': 'whale monkey',
    'nested': {
    'id': 149,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 8,
},
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
],
    'two_words': [
    'hyena',
    'bird',
],
    'city': {
    'name': 'Frankfurt',
    'geo': {
    'lat': 50.110922,
    'lon': 8.682127,
},
},
    'rand_tuple': [
    96,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': 'dragonfly',
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
    '28',
],
    'text_data': 'eb31659674604713b661e6427a4dade7',
    'rand_digit': 0,
    'rand_number': 0.30447,
    'rand_signed_int': 5,
    'rand_datetime': '2001-01-08 17:07',
    'text_array': [
    'e50a0f19b0e34d70ad5655c19ebbe7ac',
    '1a996bf1c59644e48be842faee8ebea2',
],
    'words': 'bear jaguar',
    'nested': {
    'id': 150,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dragonfly',
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
    'rand_bool': False,
    'mixed_type': 'butterfly',
    'maybe_null': 'mouse',
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
],
    'text_data': '57dd946cc98c4414b230b0f5ffa43821',
    'rand_digit': 0,
    'rand_number': 0.31706,
    'rand_signed_int': -10,
    'rand_datetime': '2000-10-04 06:48',
    'text_array': [
    'a8376de1d9644da6b7c6c6bcecf1fdd5',
    '55147240856f4348a413e9109604fc9a',
],
    'words': 'lobster deer',
    'nested': {
    'id': 151,
    'rand_digit': 8,
    'array': [
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
    'hello',
],
    'word': 'frog',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 7,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,2__',
    'two_words': [
    'lobster',
    'fox',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': [
    48,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'bird',
    'maybe_null': None,
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
    '11',
    '22',
],
    'text_data': '1320d44494954d52bb89d519039a46a7',
    'rand_digit': 3,
    'rand_number': 0.36286,
    'rand_signed_int': 0,
    'rand_datetime': '2000-10-08',
    'text_array': [
    '0411f33ecefe49638867a34d2981e8a8',
    '84fb3d251ac940a48255e674e1ee9ef2',
],
    'words': 'mosquito panda',
    'nested': {
    'id': 152,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'fly',
    'fox',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'bear',
    'maybe_null': 'sloth',
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
    '01',
    '01',
    '25',
    '20',
],
    'text_data': '4d6eb8f20ecc438a894ea888be959235',
    'rand_digit': 7,
    'rand_number': 0.54649,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-27 09:04',
    'text_array': [
    'f282634fac5340ca9dd825fb07f8c501',
    '8bfa7bc1eaf14078bf53a0140cedbe0a',
],
    'words': 'bear horse',
    'nested': {
    'id': 153,
    'rand_digit': 4,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -5,
],
],
    'two_words': [
    'giraffe',
    'sloth',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'lion',
    'maybe_null': None,
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
    '02',
    '08',
    '20',
    '12',
    '21',
],
    'text_data': '6664122900954b9b8fb1ccab47de2c5d',
    'rand_digit': 9,
    'rand_number': 0.52433,
    'rand_signed_int': -7,
    'rand_datetime': '2000-11-17T09:36:56.142094',
    'text_array': [
    '3454aba1e1e34158922b2ef08562c491',
    '43efdea92a984ef6b7fc1db1dd3fb1e8',
],
    'words': 'lion monkey',
    'nested': {
    'id': 154,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'sloth',
    'dolphin',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': [
    40,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cheetah',
    'maybe_null': 'lobster',
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
    '02',
    '06',
],
    'text_data': '8cc9f9fad98443deafd7d8096b1163e5',
    'rand_digit': 7,
    'rand_number': 0.99317,
    'rand_signed_int': -7,
    'rand_datetime': '2000-07-21 21:14:31.784469+0600',
    'text_array': [
    '5353716e9e45428c93b016982e9a4979',
    '624eabb1dbc34800bd399bf770abc59a',
],
    'words': 'dragonfly snail',
    'nested': {
    'id': 155,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dragonfly',
    'scorpion',
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
    'mixed_type': None,
    'maybe': 'cheetah',
},
},
    {
    'id': 56,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    'payload': {
    'id': 156,
    'id_str': [
    '11',
    '11',
],
    'text_data': '8a3d75eb371a44f0b5f96d2f17fd548f',
    'rand_digit': 3,
    'rand_number': 0.29043,
    'rand_signed_int': -8,
    'rand_datetime': '2000-05-11 01:37:53-0500',
    'text_array': [
    'b137452c3696405a8f6e3a6551200233',
    'a4dbd7ccca2b48fa9ba62c1bc4bb1f83',
],
    'words': 'pig chicken',
    'nested': {
    'id': 156,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 8,
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
    'word': 'cat',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -4,
],
],
    'two_words': [
    'sloth',
    'lion',
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
    'mixed_type': None,
    'maybe': 'squid',
    'maybe_null': 'sheep',
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
    '13',
],
    'text_data': '8f4deb812b0b411f9d7b55147bbba1c5',
    'rand_digit': 6,
    'rand_number': 0.08694,
    'rand_signed_int': -8,
    'rand_datetime': '2000-10-18',
    'text_array': [
    'c3ac091c1d1944e585681e098d4ae92b',
    'e363360c1a8648b8a545f0a87bd56e25',
],
    'words': 'rabbit spider',
    'nested': {
    'id': 157,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'rabbit',
    'cat',
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
    'mixed_type': 0.3682,
    'maybe': 'octopus',
    'maybe_null': 'duck',
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
    '09',
    '17',
    '03',
    '17',
],
    'text_data': '1687d04078f54c59b9c2b7a69542249c',
    'rand_digit': 5,
    'rand_number': 0.982,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-06T20:17:09.506640+0300',
    'text_array': [
    '16bb382ff4e24e0b911d261484b9ccfc',
    '2c58998e3b154fddb2f92f688f9d20f7',
],
    'words': 'crab fox',
    'nested': {
    'id': 158,
    'rand_digit': 2,
    'array': [
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'monkey',
    'sheep',
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
    'mixed_type': 0.6467,
    'maybe': 'mosquito',
    'maybe_null': None,
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
    '06',
    '30',
    '27',
],
    'text_data': 'be13cf873a9f44ad8dd14154f0463267',
    'rand_digit': 1,
    'rand_number': 0.59155,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-01 16:58',
    'text_array': [
    'b030d012aafa4d8da831f8df092048f8',
    'f552382610164bb8849e63e5a94dc6c3',
],
    'words': 'zebra elephant',
    'nested': {
    'id': 159,
    'rand_digit': 3,
    'array': [
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
    'word': 'mouse',
    'number': 4,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    2,
],
    [
    1,
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'scorpion',
    'panda',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'lion',
    'maybe_null': None,
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
    '15',
    '18',
    '15',
    '20',
],
    'text_data': '292fac7f316b404d8f54f5f3f2f97756',
    'rand_digit': 9,
    'rand_number': 0.39368,
    'rand_signed_int': 7,
    'rand_datetime': '2000-02-16T15:05:08.940895+01:00',
    'text_array': [
    '39bcb69b1f9248d28a7035136279b848',
    '8be02786579149d4b0ed267e2c6702b6',
],
    'words': 'bear cow',
    'nested': {
    'id': 160,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snake',
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    5,
],
    [
],
    [
],
    [
],
],
    'two_words': [
    'koala',
    'dog',
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
    'mixed_type': True,
    'maybe': 'cheetah',
    'maybe_null': 'ape',
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
    '03',
    '02',
    '17',
    '10',
    '27',
],
    'text_data': '00888352ad5a4a27b495c9544a6ecbef',
    'rand_digit': 8,
    'rand_number': 0.14714,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-17 03:38:18.335161+0700',
    'text_array': [
    '00f40a79101b4c1b9c3c88af7d0cf78a',
    '1410cc062250463e9ef71df1d3086107',
],
    'words': 'chicken snail',
    'nested': {
    'id': 161,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'koala',
    'hippo',
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
    'mixed_type': 'pig',
    'maybe': 'wolf',
},
},
    {
    'id': 62,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 162,
    'id_str': [
    '06',
    '23',
    '19',
    '15',
],
    'text_data': 'd42ab0e26b7a4cb0b20a0a31b1ab9a82',
    'rand_digit': 7,
    'rand_number': 0.32396,
    'rand_signed_int': -6,
    'rand_datetime': '2000-09-10 16:53:48.751842+0300',
    'text_array': [
    '8e72447a66f24673bb13dfa788d88d2e',
    'a2a78ae0d446440c8b50b4ed63a4f955',
],
    'words': 'bear cheetah',
    'nested': {
    'id': 162,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dolphin',
    'jaguar',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'deer',
    'maybe_null': 'horse',
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
    '16',
],
    'text_data': '547b15e8f114443dac55768f81bbcf9d',
    'rand_digit': 8,
    'rand_number': 0.08752,
    'rand_signed_int': 4,
    'rand_datetime': '2000-04-05 01:37:33.118749',
    'text_array': [
    'eb4585ced9944c8babead2084abd6ef7',
    '597d8616f06746b48c8eb720e2237de2',
],
    'words': 'octopus camel',
    'nested': {
    'id': 163,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'camel',
    'dog',
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
    'mixed_type': None,
    'maybe_null': 'spider',
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
        """测试请求 2 - POST http://localhost:6333/collections/congruence_test_collection/points/payload?wait=true"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/payload?wait=true")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/payload?wait=true'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '384',
}
        
        # 原始请求内容
        original_content = {
    'payload': {
    'test': 'test',
},
    'filter': {
    'should': {
    'key': 'id_str',
    'match': {
    'value': '26',
},
},
    'must': [
    {
    'must_not': [
    {
    'key': 'city.geo',
    'geo_radius': {
    'center': {
    'lon': 2.173403,
    'lat': 41.385064,
},
    'radius': 894914.3712588341,
},
},
    {
    'key': 'city.geo',
    'geo_bounding_box': {
    'top_left': {
    'lon': 114.44052117422956,
    'lat': 3.6144146985590027,
},
    'bottom_right': {
    'lon': 48.650639835805435,
    'lat': -39.92972792701668,
},
},
},
],
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
        """测试请求 3 - POST http://localhost:6333/collections/congruence_test_collection/points/payload?wait=true"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/payload?wait=true")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/payload?wait=true'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '162',
}
        
        # 原始请求内容
        original_content = {
    'payload': {
    'test': 'test2',
},
    'filter': {
    'must': [
    {
    'key': 'rand_datetime',
    'range': {
    'lt': '2000-11-22T14:05:39.861765-05:00',
    'gt': '2000-10-08T02:28:36.365945-03:00',
},
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



    def test_request_4(self):
        """测试请求 4 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1117',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
},
    'limit': 10,
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



    def test_request_5(self):
        """测试请求 5 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1211',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': [
    {
    'key': 'two_words',
    'match': {
    'except': [
    '10',
    '02',
    '21',
    '09',
    '29',
    '07',
    '07',
    '12',
    '28',
    '29',
],
},
},
    {
    'key': 'rand_datetime',
    'range': {
    'gt': '2000-06-21',
},
},
],
},
    'limit': 10,
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



    def test_request_6(self):
        """测试请求 6 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1171',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must_not': {
    'key': 'city.geo',
    'geo_radius': {
    'center': {
    'lon': -6.26031,
    'lat': 53.349805,
},
    'radius': 1345972.911952188,
},
},
},
    'limit': 10,
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



    def test_request_7(self):
        """测试请求 7 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1108',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must_not': {
    'key': 'words',
    'match': {
    'text': 'lion',
},
},
},
    'limit': 10,
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



    def test_request_8(self):
        """测试请求 8 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1209',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must': {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'turtle',
},
},
],
    'must_not': [
    {
    'key': 'number',
    'range': {
    'lt': 9.0,
},
},
],
},
},
},
},
    'limit': 10,
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



    def test_request_9(self):
        """测试请求 9 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1274',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must': [
    {
    'key': 'city.geo',
    'geo_bounding_box': {
    'top_left': {
    'lon': 98.78238985500451,
    'lat': 44.53297663245027,
},
    'bottom_right': {
    'lon': -172.39106991775398,
    'lat': 20.84378450620673,
},
},
},
    {
    'key': 'id_str',
    'match': {
    'value': '08',
},
},
],
},
    'limit': 10,
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



    def test_request_10(self):
        """测试请求 10 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1095',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': {
    'is_empty': {
    'key': 'maybe',
},
},
},
    'limit': 10,
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



    def test_request_11(self):
        """测试请求 11 - DELETE http://localhost:6333/collections/congruence_test_collection?timeout=60"""
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_search.test_search_with_persistence_and_skipped_vectors')
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
    test = TestSearchtestSearchWithPersistenceAndSkippedVectors()
    test.run_tests()
