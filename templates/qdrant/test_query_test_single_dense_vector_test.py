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
logger = logging.getLogger('vdb_fuzzer.test.test_query_test_single_dense_vector')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_query.test_single_dense_vector"
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



class TestQuerytestSingleDenseVector:
    """自动生成的VDB模糊测试类 - test_query.test_single_dense_vector"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_query.test_single_dense_vector"
        self.test_count = 30  # 测试方法数量
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
    'content-length': '40',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'size': 50,
    'distance': 'Dot',
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
    'content-length': '68932',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 100,
    'id_str': [
    '21',
],
    'text_data': '4b1f61d61a784e5c86b7d307ac8931fc',
    'rand_digit': 3,
    'rand_number': 0.89348,
    'rand_signed_int': -6,
    'rand_datetime': '2000-08-01T07:09:04.132297',
    'text_array': [
    '8d8e279a0772412d9dafbc829b5b8498',
    '8f3d95b474604039be3aa86dd1de1e2c',
],
    'words': 'bear dog',
    'nested': {
    'id': 100,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'lion',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 4,
},
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'wolf',
    'snake',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': [
    89,
],
    'rand_bool': False,
    'mixed_type': 4,
    'maybe_null': 'frog',
},
},
    {
    'id': 1,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 101,
    'id_str': [
],
    'text_data': 'c0da8a24a7bc436e8641db0bc02589c3',
    'rand_digit': 9,
    'rand_number': 0.64549,
    'rand_signed_int': 10,
    'rand_datetime': '2000-11-29T02:59:34.353789',
    'text_array': [
    '838767e31a49439daf7492e931745126',
    '7360bdbb12c2490bb630f1e0eb9d3072',
],
    'words': 'monkey grasshopper',
    'nested': {
    'id': 101,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
    0,
],
    [
],
],
    'two_words': [
    'spider',
    'sloth',
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
    'maybe': 'octopus',
},
},
    {
    'id': 2,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 102,
    'id_str': [
],
    'text_data': 'a4df62d3f4024402987492fa3946458b',
    'rand_digit': 6,
    'rand_number': 0.62154,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-21T13:59:05.178150',
    'text_array': [
    '6c15aedd5d2641249a6187a0d3350b51',
    'ef5837e30acc4cdfbed03b6731b3a7d6',
],
    'words': 'fly bird',
    'nested': {
    'id': 102,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'squid',
    'bear',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'dog',
},
},
    {
    'id': 3,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 103,
    'id_str': [
    '30',
],
    'text_data': '8e6432be2c4f457db5aecb11a61b13bf',
    'rand_digit': 1,
    'rand_number': 0.73515,
    'rand_signed_int': -5,
    'rand_datetime': '2000-11-09T03:05:26.842344-01:00',
    'text_array': [
    '1287be71c74b4ce0854e60e1160193c4',
    '859f34b3f8124c46817d8b013cf8e46f',
],
    'words': 'giraffe chicken',
    'nested': {
    'id': 103,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'grasshopper',
    'lizard',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'gorilla',
},
},
    {
    'id': 4,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 104,
    'id_str': [
    '30',
    '10',
],
    'text_data': '7a0715215b97462d869498ababc5dfea',
    'rand_digit': 5,
    'rand_number': 0.45058,
    'rand_signed_int': -2,
    'rand_datetime': '2000-01-21',
    'text_array': [
    '9f25b8ff8544461494ea9b3cd4d5da86',
    'df6d43edc75242aca47b24a9882a0aed',
],
    'words': 'monkey panda',
    'nested': {
    'id': 104,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'panda',
    'horse',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'snake',
},
},
    {
    'id': 5,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 105,
    'id_str': [
    '27',
    '13',
    '22',
],
    'text_data': 'c4af724b4f374b4f99a443f2936c2c0f',
    'rand_digit': 8,
    'rand_number': 0.36687,
    'rand_signed_int': 4,
    'rand_datetime': '2000-02-06T23:51:12.887757+01:00',
    'text_array': [
    'da3794461f9847f8a893b54894073d79',
    'acc5ea223e884d55b78c43e53b4505a3',
],
    'words': 'jaguar scorpion',
    'nested': {
    'id': 105,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    [
    -4,
],
    [
],
],
    'two_words': [
    'frog',
    'fly',
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
    'mixed_type': 0.2699,
    'maybe_null': None,
},
},
    {
    'id': 6,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 106,
    'id_str': [
    '26',
    '17',
],
    'text_data': '5c674e3f1406400380c033ef5a21a22b',
    'rand_digit': 9,
    'rand_number': 0.24063,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-16 04:40:35',
    'text_array': [
    '8e0c1785b37144cf8360610914dedb9c',
    'fdf53c7955f34ac090b8d137332ef099',
],
    'words': 'ape kangaroo',
    'nested': {
    'id': 106,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'rabbit',
    'rhino',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'dragonfly',
    'maybe_null': 'fish',
},
},
    {
    'id': 7,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 107,
    'id_str': [
],
    'text_data': '9feffaabce3a4cf98f461d4904287375',
    'rand_digit': 1,
    'rand_number': 0.84303,
    'rand_signed_int': -2,
    'rand_datetime': '2000-06-26 20:19',
    'text_array': [
    'ea9ab482b2fa4644aa317c1e50bf1524',
    '6be64832f36845d5a0a1291754a1f733',
],
    'words': 'jaguar camel',
    'nested': {
    'id': 107,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'rhino',
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
    22,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'snail',
    'maybe_null': 'tiger',
},
},
    {
    'id': 8,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 108,
    'id_str': [
],
    'text_data': '2b49e5684341442a807e249f7ad86aeb',
    'rand_digit': 7,
    'rand_number': 0.57115,
    'rand_signed_int': -10,
    'rand_datetime': '2001-01-06T23:50:10+0100',
    'text_array': [
    'b6eee6326a0249bd9ad3ce0a4f674817',
    '4fbb9c2d239a4324b48002daae774f3e',
],
    'words': 'ladybug pig',
    'nested': {
    'id': 108,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'shark',
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
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
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'cheetah',
    'zebra',
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
    'mixed_type': None,
    'maybe': 'spider',
    'maybe_null': 'ladybug',
},
},
    {
    'id': 9,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 109,
    'id_str': [
    '28',
    '09',
],
    'text_data': '97a80cde2eba4d278a27aa129829f13d',
    'rand_digit': 7,
    'rand_number': 0.24116,
    'rand_signed_int': -4,
    'rand_datetime': '2000-01-16T19:54:13-0600',
    'text_array': [
    'c610cb69c5e94ff68157d0be44803c27',
    '6e4fccc745774658930dc95285d05839',
],
    'words': 'giraffe ant',
    'nested': {
    'id': 109,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -8,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    6,
],
],
    'two_words': [
    'mosquito',
    'mouse',
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
    'mixed_type': False,
    'maybe': 'zebra',
    'maybe_null': 'turtle',
},
},
    {
    'id': 10,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 110,
    'id_str': [
    '20',
    '19',
    '09',
],
    'text_data': 'e78ae974333c4334bb5268521cfe4413',
    'rand_digit': 4,
    'rand_number': 0.48973,
    'rand_signed_int': 1,
    'rand_datetime': '2000-05-19T01:34:10.132687-02:00',
    'text_array': [
    '3abc9f31d3644c19b0d4ad30976a8798',
    '34674801681449ff8909bd75adbd0ff7',
],
    'words': 'bird octopus',
    'nested': {
    'id': 110,
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
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 3,
},
    {
    'nested_empty': None,
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
    'hello',
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
    'word': 'spider',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'whale',
    'rabbit',
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
    'mixed_type': None,
    'maybe': 'shark',
    'maybe_null': None,
},
},
    {
    'id': 11,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 111,
    'id_str': [
    '30',
    '25',
    '19',
    '12',
    '21',
],
    'text_data': '67ed26a3948b4c37a241f95346c96ddc',
    'rand_digit': 4,
    'rand_number': 0.83949,
    'rand_signed_int': 5,
    'rand_datetime': '2000-11-30 12:51:44-1000',
    'text_array': [
    'e00438afad9241fea4f705090489494b',
    '735ad688cbef4d399082243ac50b9529',
],
    'words': 'rabbit duck',
    'nested': {
    'id': 111,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
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
],
    'word': 'pig',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'whale',
    'sloth',
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
    'maybe': 'bee',
},
},
    {
    'id': 12,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 112,
    'id_str': [
    '16',
],
    'text_data': '5d01199b99ec49e589158c9e68f57b8a',
    'rand_digit': 8,
    'rand_number': 0.75031,
    'rand_signed_int': 9,
    'rand_datetime': '2000-06-29T15:24:44.312420',
    'text_array': [
    'd9bd5975ee3a43fcbf423b2cd8be6f50',
    '51886716b865408d95654ecb6737a130',
],
    'words': 'deer hyena',
    'nested': {
    'id': 112,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ladybug',
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
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
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
    'jaguar',
    'koala',
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
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': 13,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 113,
    'id_str': [
    '04',
    '26',
    '25',
    '12',
],
    'text_data': '0a95568a20884205b0d71fb1e21e97b2',
    'rand_digit': 8,
    'rand_number': 0.13766,
    'rand_signed_int': 2,
    'rand_datetime': '2000-03-14T03:21:09+1100',
    'text_array': [
    '32e0a4fc501a41d08ab7e8157c8d4048',
    '7337443a61c34017bee61514397708c8',
],
    'words': 'snail spider',
    'nested': {
    'id': 113,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
    -9,
],
],
    'two_words': [
    'bear',
    'snake',
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
    'mixed_type': 0.86967,
    'maybe_null': 'lobster',
},
},
    {
    'id': 14,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 114,
    'id_str': [
    '16',
],
    'text_data': 'cfc1f287b281490983dd9f089b6b6c21',
    'rand_digit': 4,
    'rand_number': 0.45339,
    'rand_signed_int': -6,
    'rand_datetime': '2000-12-14 08:03:52-0600',
    'text_array': [
    'f1de52b1283b4bc9a29569246031e637',
    'c2a85d4c783b4013b0710d86097ec964',
],
    'words': 'mouse ladybug',
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
    'word': 'duck',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ape',
    'frog',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': [
    75,
],
    'rand_bool': False,
    'mixed_type': 7,
},
},
    {
    'id': 15,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 115,
    'id_str': [
    '27',
    '21',
    '23',
    '25',
],
    'text_data': 'a12b7dbca9ce460cae3dcba432df037a',
    'rand_digit': 6,
    'rand_number': 0.69797,
    'rand_signed_int': 4,
    'rand_datetime': '2000-02-14 00:37:33.974542-1200',
    'text_array': [
    '2af2ac17eac740668bedbdfb460ff7ef',
    'de1f8718a7cd4892b3a0f0859947b22f',
],
    'words': 'snail bear',
    'nested': {
    'id': 115,
    'rand_digit': 7,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
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
],
},
    'nested_array': [
],
    'two_words': [
    'hippo',
    'dolphin',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': [
    18,
],
    'rand_bool': False,
    'mixed_type': 0.77338,
    'maybe': 'zebra',
    'maybe_null': 'jaguar',
},
},
    {
    'id': 16,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 116,
    'id_str': [
    '27',
    '10',
    '09',
    '18',
],
    'text_data': '9e96941ac6004a8b8993a3b107f19865',
    'rand_digit': 3,
    'rand_number': 0.06263,
    'rand_signed_int': 3,
    'rand_datetime': '2000-06-23 18:37:38-0900',
    'text_array': [
    '60d3b715c36846d3836210f584627095',
    '6dbb542780784a2ea7883de1745a89f7',
],
    'words': 'fox ant',
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
    'word': 'wolf',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cow',
    'jaguar',
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
    'mixed_type': 'sheep',
    'maybe': 'snake',
    'maybe_null': 'grasshopper',
},
},
    {
    'id': 17,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 117,
    'id_str': [
    '20',
    '30',
    '30',
],
    'text_data': 'bfa1812767dd46d2884910fa07593e8b',
    'rand_digit': 6,
    'rand_number': 0.72828,
    'rand_signed_int': -7,
    'rand_datetime': '2000-02-19T03:40:57.828932-01:00',
    'text_array': [
    'a1318da2ddd84cd0936d7fba29b344ea',
    'a047b8f19d8847d5bac161e9b3326b07',
],
    'words': 'dragonfly mouse',
    'nested': {
    'id': 117,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
    [
    -1,
],
],
    'two_words': [
    'frog',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'chicken',
},
},
    {
    'id': 18,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 118,
    'id_str': [
],
    'text_data': '127e1fcbdadd4b4387edbff335d2026b',
    'rand_digit': 7,
    'rand_number': 0.01584,
    'rand_signed_int': -1,
    'rand_datetime': '2000-03-27 17:00:24',
    'text_array': [
    '28ed946d21934841bb0bdb64b8f3035f',
    '783ea8c2c8a945488cdb01574f02c0d3',
],
    'words': 'pig cheetah',
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
    'word': 'sheep',
    'number': 6,
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
],
    'word': 'dog',
    'number': 1,
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
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'mosquito',
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
    'maybe': 'bird',
    'maybe_null': None,
},
},
    {
    'id': 19,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 119,
    'id_str': [
    '27',
    '14',
    '27',
    '08',
],
    'text_data': '75cbfd78985446f8aece132f81975852',
    'rand_digit': 1,
    'rand_number': 0.03452,
    'rand_signed_int': 10,
    'rand_datetime': '2001-01-12T10:36:40.891183',
    'text_array': [
    '0359723aae8348f883b59ecde22f0640',
    'e12f4473fc754392941b4988a19c4740',
],
    'words': 'zebra sloth',
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
    'word': 'panda',
    'number': 10,
},
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
    'hello',
],
    'word': 'jaguar',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'hyena',
    'koala',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'ladybug',
},
},
    {
    'id': 20,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 120,
    'id_str': [
    '01',
],
    'text_data': '573b6859374d4c7c9c332c0d60b22ea4',
    'rand_digit': 2,
    'rand_number': 0.93792,
    'rand_signed_int': -10,
    'rand_datetime': '2000-04-11T06:25:46.843331',
    'text_array': [
    'b5182969adf54e9294e0695b1d37ca19',
    'd0594956b702432c9f599bf52c7b19cc',
],
    'words': 'mouse rhino',
    'nested': {
    'id': 120,
    'rand_digit': 6,
    'array': [
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'turtle',
    'duck',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 21,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 121,
    'id_str': [
    '15',
],
    'text_data': '289e790c23ac4d2eb86440ff08a6331a',
    'rand_digit': 4,
    'rand_number': 0.56774,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-13T06:23:20.276541',
    'text_array': [
    'cf9f4574f4a74974933113ceaaee53ab',
    'be97e5512a6c4b5a8ff5d6b2477e4159',
],
    'words': 'fox giraffe',
    'nested': {
    'id': 121,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'sloth',
    'gorilla',
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
    'maybe': 'elephant',
},
},
    {
    'id': 22,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 122,
    'id_str': [
    '05',
    '23',
    '18',
    '18',
    '25',
],
    'text_data': '77c25979e1b4494c8768fb564087d93d',
    'rand_digit': 4,
    'rand_number': 0.26809,
    'rand_signed_int': 2,
    'rand_datetime': '2000-10-22T07:03:32',
    'text_array': [
    '2141c4fce7114085b1f37e3309b1cd73',
    '687b36506c3d474d944a5e14c39916a2',
],
    'words': 'gorilla dragonfly',
    'nested': {
    'id': 122,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'leopard',
    'number': 9,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 6,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,5__',
    'two_words': [
    'zebra',
    'tiger',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': [
    92,
],
    'rand_bool': False,
    'mixed_type': 2,
    'maybe': 'deer',
    'maybe_null': 'bee',
},
},
    {
    'id': 23,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 123,
    'id_str': [
    '10',
],
    'text_data': '7da9733c231d49dab7b451a649444a55',
    'rand_digit': 7,
    'rand_number': 0.47657,
    'rand_signed_int': 7,
    'rand_datetime': '2000-12-03',
    'text_array': [
    'f850ac3ffe5340efa8bba89fb08e1112',
    'c90b652474aa4f4bb8a9e62971f77c47',
],
    'words': 'mosquito ladybug',
    'nested': {
    'id': 123,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'leopard',
    'spider',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
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
    'id': 24,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 124,
    'id_str': [
    '28',
],
    'text_data': 'c4a382613403448dbecc96eada5197cf',
    'rand_digit': 8,
    'rand_number': 0.47995,
    'rand_signed_int': -4,
    'rand_datetime': '2000-05-25',
    'text_array': [
    '982b8ed5a78447e6b75e6af2d35757d6',
    '443d22f712504a5aac2e9da763904173',
],
    'words': 'dog goat',
    'nested': {
    'id': 124,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'giraffe',
    'lobster',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 25,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 125,
    'id_str': [
    '04',
    '19',
],
    'text_data': 'b8c2969353b742b1af2b94f8416968d2',
    'rand_digit': 7,
    'rand_number': 0.29533,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-16 19:05',
    'text_array': [
    'b3874dd401de47e496dd0617f5d3fb74',
    '3296934c38b24799bed0d4b60978a375',
],
    'words': 'leopard shark',
    'nested': {
    'id': 125,
    'rand_digit': 1,
    'array': [
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
    'word': 'jaguar',
    'number': 7,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    10,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bird',
    'fox',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 26,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 126,
    'id_str': [
    '10',
    '07',
    '13',
    '19',
    '23',
],
    'text_data': 'c0fbc0b663a248fab7e08cdf2437e720',
    'rand_digit': 4,
    'rand_number': 0.91256,
    'rand_signed_int': 10,
    'rand_datetime': '2000-06-26 00:33:54.018665-0100',
    'text_array': [
    '8daf653d76dd499bbf1c8cdfa364ea13',
    'c14f40c0a10a47bfa41dd7072a87941e',
],
    'words': 'sheep rhino',
    'nested': {
    'id': 126,
    'rand_digit': 4,
    'array': [
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'snake',
    'fish',
],
    'city': {
    'name': 'Riga',
    'geo': {
    'lat': 56.949649,
    'lon': 24.105186,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'deer',
    'maybe_null': None,
},
},
    {
    'id': 27,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 127,
    'id_str': [
    '08',
    '06',
    '19',
],
    'text_data': 'f63ed714d55d4e989b69cb2fd072a56b',
    'rand_digit': 1,
    'rand_number': 0.1048,
    'rand_signed_int': -6,
    'rand_datetime': '2000-05-25 10:43:50.608167',
    'text_array': [
    '1a8a25731d214623837b1cefdabbc46b',
    '579a37228fb64956941b1f2cd262a34e',
],
    'words': 'shark koala',
    'nested': {
    'id': 127,
    'rand_digit': 9,
    'array': [
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
    'hello',
],
    'word': 'mouse',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'sheep',
    'chicken',
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
    'mixed_type': True,
},
},
    {
    'id': 28,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 128,
    'id_str': [
    '08',
],
    'text_data': 'cdbe75179d80491788691f5f6c8c5491',
    'rand_digit': 6,
    'rand_number': 0.9642,
    'rand_signed_int': 1,
    'rand_datetime': '2000-03-23T08:50:57.240194-02:00',
    'text_array': [
    'fa82d3d116fa4197880ce94f7bec00c2',
    'ef8a76ae8ad44a8daf0158fa42b2413d',
],
    'words': 'giraffe goat',
    'nested': {
    'id': 128,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 7,
},
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -1,
],
],
    'two_words': [
    'crab',
    'hippo',
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
    'maybe_null': 'cheetah',
},
},
    {
    'id': 29,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 129,
    'id_str': [
    '03',
    '15',
    '24',
    '21',
],
    'text_data': '0348a0d2dde645deb97012fbc0da0acf',
    'rand_digit': 7,
    'rand_number': 0.13209,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-21T19:37:05.663671',
    'text_array': [
    'b81090dcdd514a938381831adc04d33a',
    'ca521b0219d940b7a3062ca108469729',
],
    'words': 'panda elephant',
    'nested': {
    'id': 129,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bear',
    'number': 9,
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
    'word': 'rabbit',
    'number': 10,
},
],
},
    'nested_array': [
    [
    0,
],
],
    'two_words': [
    'butterfly',
    'shark',
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
    'maybe_null': 'fly',
},
},
    {
    'id': 30,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 130,
    'id_str': [
    '15',
],
    'text_data': 'dc1c9bc7a15841e98118a88c18c80aba',
    'rand_digit': 4,
    'rand_number': 0.79744,
    'rand_signed_int': 8,
    'rand_datetime': '2000-12-18T17:28:59.857334',
    'text_array': [
    'd1b85a088ff544ffb33bdd4ce5e5893b',
    'ac663ea587924cc0a3e04d94a3f165b7',
],
    'words': 'sheep zebra',
    'nested': {
    'id': 130,
    'rand_digit': 8,
    'array': [
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
    'word': 'snail',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 1,
},
    {
    'nested_empty': None,
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
    [
],
],
    'two_words': [
    'rabbit',
    'horse',
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
    'mixed_type': 'bee',
    'maybe_null': 'camel',
},
},
    {
    'id': 31,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 131,
    'id_str': [
    '18',
    '01',
    '26',
],
    'text_data': '0f69fc1103ca418ebe7fca90a2c2c36a',
    'rand_digit': 8,
    'rand_number': 0.23391,
    'rand_signed_int': -10,
    'rand_datetime': '2000-12-08T03:29:45.144910',
    'text_array': [
    'bb31770a61f84f6bbe32a193e05c2f46',
    '4f6f5651ad3b4e5db108b6077a31955b',
],
    'words': 'deer ladybug',
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
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 6,
},
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'tiger',
    'ant',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 32,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 132,
    'id_str': [
    '04',
    '04',
],
    'text_data': '51d2e2c7249444e38e8956b287e4a311',
    'rand_digit': 6,
    'rand_number': 0.95174,
    'rand_signed_int': -4,
    'rand_datetime': '2000-11-29T03:09:48.683263-01:00',
    'text_array': [
    '14eee59041d2423b9e918505e8c6dabe',
    '3cac7d6534f3430f8ec6515cc63b16d8',
],
    'words': 'mouse bear',
    'nested': {
    'id': 132,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
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
    'number': 7,
},
],
},
    'nested_array': [
    [
    0,
],
    [
    6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    5,
],
],
    'two_words': [
    'fly',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bee',
    'maybe_null': 'fly',
},
},
    {
    'id': 33,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 133,
    'id_str': [
    '02',
    '07',
    '25',
    '21',
    '27',
],
    'text_data': '143bc7130a884199ab3f9d875caaa474',
    'rand_digit': 9,
    'rand_number': 0.79137,
    'rand_signed_int': -1,
    'rand_datetime': '2000-04-18 06:54:57',
    'text_array': [
    '390845b551dd45c0ae498cafce36e342',
    'e9974d1b876a4d2980be73d1f8a21b7c',
],
    'words': 'squid lizard',
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
    'word': 'duck',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'lion',
    'crab',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'camel',
    'maybe_null': 'deer',
},
},
    {
    'id': 34,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 134,
    'id_str': [
    '01',
    '08',
],
    'text_data': '5d60f44626bb495db335ca8320eef263',
    'rand_digit': 9,
    'rand_number': 0.20235,
    'rand_signed_int': -9,
    'rand_datetime': '2000-12-30T02:07:58',
    'text_array': [
    '96920be15b084b16b2aebd9dfebf2abd',
    '5a987e3bd3134306b518c4e5758fa242',
],
    'words': 'dolphin pig',
    'nested': {
    'id': 134,
    'rand_digit': 3,
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
    'word': 'squid',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    0,
],
],
    'two_words': [
    'elephant',
    'cat',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 35,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 135,
    'id_str': [
    '12',
    '30',
    '22',
    '17',
    '18',
],
    'text_data': '33a06033b3884ba8afabe20fbb8245c3',
    'rand_digit': 2,
    'rand_number': 0.81234,
    'rand_signed_int': -3,
    'rand_datetime': '2000-02-25 06:50:37-0700',
    'text_array': [
    'a30add093de945f0850014b52dd2e23c',
    '445811a13213493d90b1384170fffce6',
],
    'words': 'gorilla ape',
    'nested': {
    'id': 135,
    'rand_digit': 8,
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
],
    'word': 'rabbit',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 3,
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
    'octopus',
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
    'rand_bool': True,
    'mixed_type': 2,
    'maybe': 'gorilla',
    'maybe_null': 'ladybug',
},
},
    {
    'id': 36,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 136,
    'id_str': [
    '20',
],
    'text_data': '130f407f9c6942359f6f40e7cb925117',
    'rand_digit': 0,
    'rand_number': 0.01748,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-11T09:23:40.606812',
    'text_array': [
    'd48d06acde3f4c9fbb066a142c34fe39',
    'c1d80112cb144133881cc7b26de20b20',
],
    'words': 'lion frog',
    'nested': {
    'id': 136,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
    3,
],
    [
    9,
],
    [
    9,
],
],
    'two_words': [
    'ant',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'lizard',
    'maybe_null': 'ant',
},
},
    {
    'id': 37,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 137,
    'id_str': [
    '19',
    '27',
    '30',
    '12',
],
    'text_data': '3f2c47bbad904dfa8bfb100c654c73e7',
    'rand_digit': 5,
    'rand_number': 0.86844,
    'rand_signed_int': -10,
    'rand_datetime': '2000-10-23T20:15:28.888937+0000',
    'text_array': [
    '7535a33c2a2c446689e5edadae94585b',
    'f92970aaba064d84a61e936c7e6232c4',
],
    'words': 'elephant bird',
    'nested': {
    'id': 137,
    'rand_digit': 9,
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
    'word': 'whale',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'zebra',
    'duck',
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
    'mixed_type': True,
    'maybe_null': 'goat',
},
},
    {
    'id': 38,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 138,
    'id_str': [
    '07',
],
    'text_data': 'f4a8c4b1d0cd459988168081f82f62bb',
    'rand_digit': 5,
    'rand_number': 0.28464,
    'rand_signed_int': -8,
    'rand_datetime': '2000-01-16T02:01:32.969728-1000',
    'text_array': [
    '65fa6145a53241c1b9a726999fe86ec6',
    '037b4df58c8f4f37904020bb398a9961',
],
    'words': 'bee dragonfly',
    'nested': {
    'id': 138,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'duck',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'bee',
    'scorpion',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': [
    78,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'fly',
},
},
    {
    'id': 39,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 139,
    'id_str': [
    '03',
],
    'text_data': '6492ea9e4bac456f9703b37b7993d364',
    'rand_digit': 8,
    'rand_number': 0.04373,
    'rand_signed_int': -8,
    'rand_datetime': '2000-04-07 23:43:36-0800',
    'text_array': [
    '8863a330da7a40d79e4d84579eb44a3a',
    '134088aefcd547efaf63f5f6b4fd9b6f',
],
    'words': 'rabbit cheetah',
    'nested': {
    'id': 139,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    7,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'leopard',
    'dragonfly',
],
    'city': {
    'name': 'Riga',
    'geo': {
    'lat': 56.949649,
    'lon': 24.105186,
},
},
    'rand_tuple': [
    74,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'spider',
    'maybe_null': 'snail',
},
},
    {
    'id': 40,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 140,
    'id_str': [
    '14',
    '02',
    '04',
],
    'text_data': '86c6cd10dc9b460fa741440e17594a6d',
    'rand_digit': 4,
    'rand_number': 0.68116,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-03T13:13:55.709503+1200',
    'text_array': [
    '430b0079d53d44dcaad70406f06296c5',
    '977a9e1c6cc44974a0ee16d4df7e9345',
],
    'words': 'snake fly',
    'nested': {
    'id': 140,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -8,
],
    [
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'gorilla',
    'giraffe',
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
    'mixed_type': 'lobster',
    'maybe_null': 'sheep',
},
},
    {
    'id': 41,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 141,
    'id_str': [
    '29',
    '04',
    '06',
    '24',
    '20',
],
    'text_data': 'ec7c75da46ee45578d2eceff61ed5eb3',
    'rand_digit': 7,
    'rand_number': 0.33211,
    'rand_signed_int': -8,
    'rand_datetime': '2000-10-22 10:23',
    'text_array': [
    'ea4883aeac2145c986e8e6413b1fc54a',
    '16ecca0aa7ba4e80a10f7ce044e7d746',
],
    'words': 'lizard fish',
    'nested': {
    'id': 141,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 7,
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
    'word': 'turtle',
    'number': 7,
},
    {
    'nested_empty': None,
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
],
    'two_words': [
    'deer',
    'grasshopper',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 4,
},
},
    {
    'id': 42,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 142,
    'id_str': [
    '30',
    '23',
    '13',
    '04',
    '12',
],
    'text_data': '62435bf4d69f45a6ab6aa56928b3cf42',
    'rand_digit': 2,
    'rand_number': 0.31789,
    'rand_signed_int': -1,
    'rand_datetime': '2000-03-06T06:40:41-0800',
    'text_array': [
    '312e7cf00beb49dab949c06c9cfb9fe3',
    '535909c800d345108dea2e9990673f13',
],
    'words': 'lizard chicken',
    'nested': {
    'id': 142,
    'rand_digit': 8,
    'array': [
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
    'word': 'bear',
    'number': 10,
},
],
},
    'nested_array': [
    [
    9,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'chicken',
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
    'rand_bool': True,
    'mixed_type': 'dolphin',
    'maybe_null': 'cow',
},
},
    {
    'id': 43,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 143,
    'id_str': [
    '01',
    '23',
    '26',
],
    'text_data': '9e53fd2ecd9b42ff8de5baef846fe359',
    'rand_digit': 4,
    'rand_number': 0.40752,
    'rand_signed_int': 8,
    'rand_datetime': '2000-08-22T23:18:54.019301-0900',
    'text_array': [
    'e9d8aaf612234d70b4a73007867da5e8',
    'f7ede8d3e8644d529a8c375d47abc46b',
],
    'words': 'dog dog',
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
    'word': 'frog',
    'number': 7,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'goat',
    'monkey',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'octopus',
    'maybe_null': None,
},
},
    {
    'id': 44,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 144,
    'id_str': [
    '07',
    '08',
    '18',
    '01',
],
    'text_data': 'f985b292b5754c73b69db7b6fe13d70b',
    'rand_digit': 4,
    'rand_number': 0.59902,
    'rand_signed_int': -10,
    'rand_datetime': '2000-04-22 06:24:02.193931',
    'text_array': [
    '392c19c8c6fd47ae81668a59a7a4555c',
    'd2fd649e1b0d4ee49528cb8e24f68f14',
],
    'words': 'cow whale',
    'nested': {
    'id': 144,
    'rand_digit': 1,
    'array': [
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
],
    'word': 'squid',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
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
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    10,
],
],
    'two_words': [
    'panda',
    'mouse',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 'gorilla',
    'maybe': 'monkey',
    'maybe_null': 'ape',
},
},
    {
    'id': 45,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 145,
    'id_str': [
],
    'text_data': '13a4d7a8d906468d992c120e05d85969',
    'rand_digit': 0,
    'rand_number': 0.50268,
    'rand_signed_int': 10,
    'rand_datetime': '2000-07-15 21:23:55.370196',
    'text_array': [
    'b1004485171743578e86657710c93354',
    '488c9ac30ced4138a580c2b5437b29a2',
],
    'words': 'monkey cheetah',
    'nested': {
    'id': 145,
    'rand_digit': 5,
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
    'word': 'chicken',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 9,
},
],
},
    'nested_array': [
    [
    -2,
],
    [
    4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'snail',
    'sheep',
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
    'mixed_type': 'cow',
    'maybe': 'bear',
    'maybe_null': None,
},
},
    {
    'id': 46,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 146,
    'id_str': [
    '09',
    '06',
    '18',
    '13',
    '30',
],
    'text_data': '3534904f32ba4098a1ec60446d5d2ded',
    'rand_digit': 1,
    'rand_number': 0.00784,
    'rand_signed_int': -6,
    'rand_datetime': '2000-01-07T23:36:57.223632+0000',
    'text_array': [
    '46952364656a48278b96432484c6a374',
    '6945d115d58644b493f24e9395fa7057',
],
    'words': 'lizard tiger',
    'nested': {
    'id': 146,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'wolf',
    'dragonfly',
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
},
},
    {
    'id': 47,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 147,
    'id_str': [
    '17',
],
    'text_data': '3389c9ee569149f88552e6b75305cca4',
    'rand_digit': 1,
    'rand_number': 0.93976,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-02 05:04:38',
    'text_array': [
    '4d5b9950596a4dc39a1ae3507d04330d',
    '608c63c7e7d54a258164bcd90cfa1ad7',
],
    'words': 'lobster fox',
    'nested': {
    'id': 147,
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
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 2,
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
],
},
    'nested_array': [
],
    'two_words': [
    'wolf',
    'ladybug',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': [
    34,
],
    'rand_bool': False,
    'mixed_type': 2,
},
},
    {
    'id': 48,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 148,
    'id_str': [
    '20',
    '07',
    '02',
    '04',
    '19',
],
    'text_data': '0588a0d76938456b8df4a194a78c8fa8',
    'rand_digit': 8,
    'rand_number': 0.33335,
    'rand_signed_int': 1,
    'rand_datetime': '2000-04-18 12:43:18+0500',
    'text_array': [
    '0e75bdba0d52489f85cd2ac620c95b82',
    '71460f9bad4f4ea3ae4d98d0f516f161',
],
    'words': 'ape sloth',
    'nested': {
    'id': 148,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'mouse',
    'number': 10,
},
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'frog',
    'lion',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': [
    21,
],
    'rand_bool': True,
    'mixed_type': 3,
},
},
    {
    'id': 49,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 149,
    'id_str': [
    '21',
    '06',
    '26',
    '22',
],
    'text_data': '51a2901a439143deadabb0f7fff34c5f',
    'rand_digit': 5,
    'rand_number': 0.40333,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-02T02:49:26',
    'text_array': [
    '3617dba4eb2e4015bf2bc649a9847cf7',
    '380e53498b0041858784e76f6c6c3880',
],
    'words': 'fox chicken',
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
    'word': 'shark',
    'number': 5,
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
],
    'word': 'bee',
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
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'tiger',
    'dolphin',
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
    'maybe': 'kangaroo',
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 50,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 150,
    'id_str': [
    '20',
    '14',
    '30',
    '09',
],
    'text_data': '545be256355343f090d720f61973ab00',
    'rand_digit': 7,
    'rand_number': 0.27042,
    'rand_signed_int': 10,
    'rand_datetime': '2000-05-31 02:26',
    'text_array': [
    '85134ec26c954529829a2f76fcbdb464',
    '9d8bce1900194aaba9476ac090bf484c',
],
    'words': 'monkey hyena',
    'nested': {
    'id': 150,
    'rand_digit': 3,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
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
    'hello',
],
    'word': 'turtle',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bird',
    'hippo',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'octopus',
    'maybe_null': 'squid',
},
},
    {
    'id': 51,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 151,
    'id_str': [
    '16',
    '30',
    '22',
],
    'text_data': '2d521b7b7a3c48039202aaebf25d5897',
    'rand_digit': 8,
    'rand_number': 0.93566,
    'rand_signed_int': -7,
    'rand_datetime': '2000-06-11T13:08:50.622812',
    'text_array': [
    'f0a1c4e84ba444fa882b75a1032b5aa7',
    '1777f12393ce4204a9e4a9cc48c7ef4e',
],
    'words': 'whale whale',
    'nested': {
    'id': 151,
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
    'number': 10,
},
],
},
    'nested_array': [
    [
    6,
],
    [
    -1,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'spider',
    'snail',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': [
    53,
],
    'rand_bool': False,
    'mixed_type': True,
},
},
    {
    'id': 52,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 152,
    'id_str': [
],
    'text_data': 'ca62b70d670548b7971a1e5440ebdf8b',
    'rand_digit': 0,
    'rand_number': 0.16337,
    'rand_signed_int': -7,
    'rand_datetime': '2000-01-14T16:57:49.636209',
    'text_array': [
    'de68ae51d376477295e92326ef9d0d7b',
    '12957126a65d47efbf78309888531248',
],
    'words': 'fox bird',
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
    'word': 'bird',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ape',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 9,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,5__',
    'two_words': [
    'cow',
    'sheep',
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
    'maybe_null': None,
},
},
    {
    'id': 53,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 153,
    'id_str': [
    '14',
    '23',
    '25',
    '13',
],
    'text_data': '12008639a3ec4935bbf4d41954a0ef4a',
    'rand_digit': 6,
    'rand_number': 0.86751,
    'rand_signed_int': 0,
    'rand_datetime': '2000-02-10 23:01:32+0300',
    'text_array': [
    'ef321c98a1fc45b4adcf981cef709598',
    'e14a0c23710041d9bd944c6cb50e644b',
],
    'words': 'crab spider',
    'nested': {
    'id': 153,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    [
    5,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'shark',
    'mosquito',
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
    'maybe': 'kangaroo',
    'maybe_null': None,
},
},
    {
    'id': 54,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 154,
    'id_str': [
    '29',
],
    'text_data': '4d0d68cd5982481fbd02e2c84bc941d7',
    'rand_digit': 3,
    'rand_number': 0.04174,
    'rand_signed_int': 0,
    'rand_datetime': '2000-01-14 21:01:57.958957+0000',
    'text_array': [
    'd1c965bfa3ec4ee89fb9b629ff21ff94',
    '45544e8c22094791af3ece9a6cb82f5f',
],
    'words': 'lizard duck',
    'nested': {
    'id': 154,
    'rand_digit': 7,
    'array': [
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
],
    'word': 'monkey',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'bee',
    'squid',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cow',
    'maybe_null': None,
},
},
    {
    'id': 55,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 155,
    'id_str': [
    '24',
    '21',
    '21',
],
    'text_data': '80d22db6bcc4465eb24b9b5fe1f4aafa',
    'rand_digit': 3,
    'rand_number': 0.6464,
    'rand_signed_int': -7,
    'rand_datetime': '2000-06-06 09:01:12.817433-0600',
    'text_array': [
    '75d3ca871c6a43a78577fc8b00c3dc87',
    '5f1bc9a8f78144ea9e17183a075a3d8a',
],
    'words': 'crab fox',
    'nested': {
    'id': 155,
    'rand_digit': 6,
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
],
},
    'nested_array': [
    [
    -4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    9,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'wolf',
    'lobster',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': [
    21,
],
    'rand_bool': True,
    'mixed_type': 0.54691,
    'maybe': 'cheetah',
    'maybe_null': 'jaguar',
},
},
    {
    'id': 56,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 156,
    'id_str': [
    '08',
    '15',
],
    'text_data': '68555f47e7cb473fb6f1159c3ac4729f',
    'rand_digit': 3,
    'rand_number': 0.76065,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-31',
    'text_array': [
    'bf8ba767776a46d6aff9883bdc06a617',
    'fcb3acc30f7c45179a689d20a472c6e8',
],
    'words': 'monkey leopard',
    'nested': {
    'id': 156,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'cat',
    'number': 7,
},
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
    'word': 'dragonfly',
    'number': 4,
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
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'fox',
    'hippo',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': [
    60,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'hippo',
    'maybe_null': 'whale',
},
},
    {
    'id': 57,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 157,
    'id_str': [
    '11',
    '11',
],
    'text_data': '6a5646f209aa4c10b5df37d4f3e41ed2',
    'rand_digit': 8,
    'rand_number': 0.26527,
    'rand_signed_int': -2,
    'rand_datetime': '2000-09-18 01:24:20-0200',
    'text_array': [
    'd730266b853646858d0a006c908bcd96',
    '8fba9a2cd58f4237b5f1067d0224fe4f',
],
    'words': 'bear snake',
    'nested': {
    'id': 157,
    'rand_digit': 4,
    'array': [
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
    'nested_empty': None,
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
],
    'word': 'dragonfly',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'kangaroo',
    'chicken',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'grasshopper',
    'maybe_null': None,
},
},
    {
    'id': 58,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 158,
    'id_str': [
    '11',
    '09',
    '22',
],
    'text_data': '9de3fd83d1fc490cb19b87d64804b751',
    'rand_digit': 8,
    'rand_number': 0.43308,
    'rand_signed_int': -9,
    'rand_datetime': '2000-04-12T16:16:16.608941-04:00',
    'text_array': [
    'c8b1de03fa0142df9529ac9421c03a01',
    'b701d84a90d44599bbf0977073e53c74',
],
    'words': 'zebra rabbit',
    'nested': {
    'id': 158,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'cow',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cat',
    'cow',
],
    'city': {
    'name': 'Kuala Lumpur',
    'geo': {
    'lat': 3.139003,
    'lon': 101.686855,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'monkey',
    'maybe_null': 'tiger',
},
},
    {
    'id': 59,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 159,
    'id_str': [
    '08',
    '23',
],
    'text_data': '0bfe15ef26134c94a217cc5b9f79b480',
    'rand_digit': 9,
    'rand_number': 0.53986,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-18T20:54:09.995226+1000',
    'text_array': [
    'e41d56fff8234e5a8fe59ed96a2db26e',
    'eb6ef4fc1c404b7a8d6ebf9fa905e234',
],
    'words': 'koala shark',
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
    'word': 'panda',
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
    [
    -9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'gorilla',
    'cow',
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
    'mixed_type': 'fly',
    'maybe': 'ape',
    'maybe_null': 'snail',
},
},
    {
    'id': 60,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 160,
    'id_str': [
],
    'text_data': 'a45374085ea245238b6981a416a5e464',
    'rand_digit': 2,
    'rand_number': 0.10271,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-13T00:26:33.370431-0300',
    'text_array': [
    'ce9bc58eef7f4a7db1e038623eff4faa',
    'fe3f05b2275545c9bc149e30a7160fd0',
],
    'words': 'leopard shark',
    'nested': {
    'id': 160,
    'rand_digit': 9,
    'array': [
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
    'word': 'butterfly',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'shark',
    'fly',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': [
    69,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'hippo',
},
},
    {
    'id': 61,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 161,
    'id_str': [
    '06',
    '09',
],
    'text_data': 'e7a69bd3d7f34401a6156eec4845bd96',
    'rand_digit': 9,
    'rand_number': 0.24813,
    'rand_signed_int': -3,
    'rand_datetime': '2001-01-16 19:30',
    'text_array': [
    'b7881a833c8c480a859288fd737d7fb1',
    '0926b4f5823f48c386a09a0dd762ceaa',
],
    'words': 'zebra sloth',
    'nested': {
    'id': 161,
    'rand_digit': 0,
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
    'word': 'scorpion',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'turtle',
    'frog',
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
    'mixed_type': False,
    'maybe_null': 'spider',
},
},
    {
    'id': 62,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 162,
    'id_str': [
    '11',
    '22',
],
    'text_data': '8bf454eb0e674e3c8b871e1d5b4bf13c',
    'rand_digit': 0,
    'rand_number': 0.3187,
    'rand_signed_int': -10,
    'rand_datetime': '2000-12-05T07:23:18',
    'text_array': [
    'c5836f27a16a4dc191011bab478845b1',
    '81fde821a3cf424aa66a0d4c899ddbca',
],
    'words': 'monkey lizard',
    'nested': {
    'id': 162,
    'rand_digit': 6,
    'array': [
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
    'word': 'squid',
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
    'bee',
    'grasshopper',
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
    'mixed_type': 0.30484,
    'maybe': 'whale',
},
},
    {
    'id': 63,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 163,
    'id_str': [
    '27',
    '09',
],
    'text_data': '88f21d85951a4c2eb6dcbcb60b3d1135',
    'rand_digit': 6,
    'rand_number': 0.93483,
    'rand_signed_int': -1,
    'rand_datetime': '2000-07-30T07:03:00.511905',
    'text_array': [
    '381fd9d5ec774046893f192b817b4583',
    '32e9a8c5c2fb4f5a998f71a5b69f8425',
],
    'words': 'cheetah dragonfly',
    'nested': {
    'id': 163,
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
    'number': 8,
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
],
    'word': 'horse',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'sheep',
    'ape',
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
    'mixed_type': 0.57551,
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
    'content-length': '1104',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must_not': {
    'is_empty': {
    'key': 'nested.array[].nested_empty',
},
},
},
    'limit': 10,
    'with_vector': True,
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
        """测试请求 3 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1115',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'min_should': {
    'conditions': [
    {
    'is_empty': {
    'key': 'maybe',
},
},
],
    'min_count': 1,
},
},
    'limit': 10,
    'with_vector': True,
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
    'content-length': '1162',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must_not': {
    'key': 'rand_datetime',
    'range': {
    'lt': '2000-04-07T21:52:11.088557Z',
    'gt': '2000-05-01T08:15:13.383382-04:00',
},
},
},
    'limit': 10,
    'with_vector': True,
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
        """测试请求 5 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1159',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must_not': [
    {
    'key': 'nested_array[2][1]',
    'range': {
    'lt': 2.0,
},
},
    {
    'key': 'rand_number',
    'range': {
    'lt': 0.3561252307037647,
},
},
],
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_6(self):
        """测试请求 6 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1133',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must': [
    {
    'is_empty': {
    'key': 'maybe',
},
},
    {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
],
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_7(self):
        """测试请求 7 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1193',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'bee',
},
},
],
    'must_not': [
    {
    'key': 'number',
    'range': {
    'lt': 8.0,
},
},
],
},
},
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_8(self):
        """测试请求 8 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1238',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': [
    {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'whale',
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
    {
    'key': 'id_str',
    'values_count': {
    'gt': 2,
},
},
],
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_9(self):
        """测试请求 9 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1221',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must_not': {
    'key': 'city.geo',
    'geo_bounding_box': {
    'top_left': {
    'lon': 76.73009218521548,
    'lat': 40.787086038577854,
},
    'bottom_right': {
    'lon': -18.89519397820854,
    'lat': 60.99754195574852,
},
},
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_10(self):
        """测试请求 10 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1086',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must_not': {
    'is_null': {
    'key': 'maybe_null',
},
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_11(self):
        """测试请求 11 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1164',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': [
    {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
],
    'must': {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_12(self):
        """测试请求 12 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1101',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must': {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_13(self):
        """测试请求 13 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1143',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': {
    'key': 'words',
    'match': {
    'text': 'ladybug',
},
},
    'must': [
    {
    'key': 'id_str',
    'match': {
    'value': '08',
},
},
],
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_14(self):
        """测试请求 14 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1099',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': {
    'key': 'id_str',
    'values_count': {
    'lt': 1,
    'gt': 4,
},
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_15(self):
        """测试请求 15 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1153',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': {
    'key': 'rand_datetime',
    'range': {
    'lt': '2000-07-15T00:00:00Z',
    'gt': '2000-06-08T18:39:55.630141-01:00',
},
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_16(self):
        """测试请求 16 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1192',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': {
    'key': 'city.geo',
    'geo_radius': {
    'center': {
    'lon': 12.496366,
    'lat': 41.902782,
},
    'radius': 1446929.5475056383,
},
},
    'must': {
    'is_empty': {
    'key': 'maybe',
},
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_17(self):
        """测试请求 17 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1154',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must': {
    'key': 'city.geo',
    'geo_radius': {
    'center': {
    'lon': -70.669266,
    'lat': -33.44889,
},
    'radius': 1884973.042241245,
},
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_18(self):
        """测试请求 18 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1225',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
    'must': {
    'key': 'rand_datetime',
    'range': {
    'lt': '2000-05-04T12:34:59.438137-08:00',
    'gt': '2000-09-21T18:27:40.252543+02:00',
},
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_19(self):
        """测试请求 19 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1144',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must_not': {
    'key': 'two_words',
    'match': {
    'except': [
    '26',
    '21',
    '25',
    '23',
    '17',
    '14',
    '19',
    '21',
    '05',
    '22',
],
},
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_20(self):
        """测试请求 20 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1267',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': [
    {
    'key': 'two_words',
    'match': {
    'except': [
    '11',
    '09',
    '04',
    '05',
    '26',
    '25',
    '27',
    '01',
    '27',
    '09',
],
},
},
],
    'must': [
    {
    'key': 'rand_datetime',
    'range': {
    'lt': '2000-12-20T03:08:18.395034+03:00',
    'gt': '2000-01-06T12:26:10.031673-06:00',
},
},
],
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_21(self):
        """测试请求 21 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1101',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must_not': {
    'key': 'nested_array[10][]',
    'range': {
    'lt': 7.0,
},
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_22(self):
        """测试请求 22 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1103',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must_not': {
    'key': 'id_str',
    'match': {
    'any': [
    '01',
    '05',
    '28',
],
},
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_23(self):
        """测试请求 23 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1151',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must': {
    'key': 'rand_datetime',
    'range': {
    'lt': '2000-08-09T00:00:00Z',
    'gt': '2000-11-09T14:21:04.510979-08:00',
},
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_24(self):
        """测试请求 24 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1096',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': {
    'key': 'maybe',
    'match': {
    'value': 'kangaroo',
},
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_25(self):
        """测试请求 25 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1101',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': {
    'key': 'nested_array[0][10]',
    'range': {
    'lt': -4.0,
},
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_26(self):
        """测试请求 26 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1187',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': {
    'key': 'rand_number',
    'range': {
    'lt': 0.36561535905828757,
    'gt': 0.5698479717554827,
},
},
    'must': {
    'key': 'id_str',
    'values_count': {
    'lt': 1,
    'gt': 2,
},
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_27(self):
        """测试请求 27 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1155',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': {
    'key': 'city.geo',
    'geo_radius': {
    'center': {
    'lon': 28.978359,
    'lat': 41.008238,
},
    'radius': 454829.3159780725,
},
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_28(self):
        """测试请求 28 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '1090',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must': {
    'key': 'maybe',
    'match': {
    'value': 'crab',
},
},
},
    'limit': 10,
    'with_vector': True,
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



    def test_request_29(self):
        """测试请求 29 - DELETE http://localhost:6333/collections/congruence_test_collection?timeout=60"""
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
    'content-length': '40',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'size': 50,
    'distance': 'Dot',
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_query.test_single_dense_vector')
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
    test = TestQuerytestSingleDenseVector()
    test.run_tests()
