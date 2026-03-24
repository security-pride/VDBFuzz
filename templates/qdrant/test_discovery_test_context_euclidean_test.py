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
logger = logging.getLogger('vdb_fuzzer.test.test_discovery_test_context_euclidean')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_discovery.test_context_euclidean"
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



class TestDiscoverytestContextEuclidean:
    """自动生成的VDB模糊测试类 - test_discovery.test_context_euclidean"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_discovery.test_context_euclidean"
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
    'content-length': '137824',
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
    '30',
    '10',
    '26',
    '20',
],
    'text_data': '5ba6b33d08f3473bbee8ac253e8dd526',
    'rand_digit': 7,
    'rand_number': 0.99297,
    'rand_signed_int': -10,
    'rand_datetime': '2000-02-01T12:28:37',
    'text_array': [
    '0f141c915c9147e0a7ce2b2d8b90a0ce',
    'd70426105ea844ec986f12c9ed43a402',
],
    'words': 'ape turtle',
    'nested': {
    'id': 100,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 9,
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
    'hello',
],
    'word': 'octopus',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mosquito',
    'mouse',
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
    'mixed_type': 0.77946,
    'maybe': 'snake',
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
    '07',
    '23',
],
    'text_data': '6c89aae0c133437b89b82b5c490b6cad',
    'rand_digit': 7,
    'rand_number': 0.34546,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-27 07:10:30-1200',
    'text_array': [
    '0fb98a7c2b834d78a862bfaccd198ea7',
    '505f32e909cc4bc98edd49bbee3d6fb8',
],
    'words': 'lion frog',
    'nested': {
    'id': 101,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
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
    'number': 7,
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
],
    'word': 'whale',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'frog',
    'spider',
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
    '06',
    '24',
    '11',
],
    'text_data': 'f649f30bbd5e47359171d313ee857f5f',
    'rand_digit': 4,
    'rand_number': 0.69872,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-04 04:26:36',
    'text_array': [
    '7682e2e793fe4ac4a87a4e322ef64bbe',
    '60faa2dae1e545018919be23a637cb43',
],
    'words': 'lobster scorpion',
    'nested': {
    'id': 102,
    'rand_digit': 7,
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
],
},
    'nested_array': [
],
    'two_words': [
    'fish',
    'octopus',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'koala',
    'maybe_null': 'ant',
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
    '28',
    '19',
    '17',
    '09',
],
    'text_data': 'e4ea49dcab744af2b721a4315e945052',
    'rand_digit': 2,
    'rand_number': 0.29795,
    'rand_signed_int': -4,
    'rand_datetime': '2000-02-28T17:56:26.201851+0900',
    'text_array': [
    '7fb17abfb5854a04bcf3b204e44ccddb',
    'f672c7e7458c49099e630eca28bcb9fd',
],
    'words': 'dolphin panda',
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
    'word': 'fox',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'camel',
    'wolf',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': [
    34,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'rhino',
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
    '24',
    '01',
    '13',
    '09',
],
    'text_data': '8b7f7c181c0f48e18c97151a0d2d8d5f',
    'rand_digit': 0,
    'rand_number': 0.89099,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-19',
    'text_array': [
    'd8653976fc2a4956ac41331a08c7cf67',
    'df52ee366cd94975b50624ca344c5dd2',
],
    'words': 'deer fish',
    'nested': {
    'id': 104,
    'rand_digit': 2,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 3,
},
],
},
    'nested_array': [
    [
    -8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'panda',
    'wolf',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'lizard',
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
    '04',
],
    'text_data': '1b8df4e4cdb94819bf7b9ea28e2439fd',
    'rand_digit': 8,
    'rand_number': 0.57708,
    'rand_signed_int': 7,
    'rand_datetime': '2000-09-09',
    'text_array': [
    '476cb65116d74a8c8913771b3ab7d7cf',
    '08f9ee8556ad47bcbdf800ca6cc10937',
],
    'words': 'tiger bee',
    'nested': {
    'id': 105,
    'rand_digit': 3,
    'array': [
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
    'nested_empty': None,
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
],
    'word': 'koala',
    'number': 9,
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    4,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'sloth',
    'scorpion',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.09514,
    'maybe': 'ladybug',
    'maybe_null': None,
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
    '08',
    '01',
],
    'text_data': 'ec230dc4297b43d686331cb5fbe021fc',
    'rand_digit': 7,
    'rand_number': 0.90356,
    'rand_signed_int': 8,
    'rand_datetime': '2000-07-15 11:42:04-0200',
    'text_array': [
    '2b83d719b1984905a2478d3e54b76658',
    '6dbca7dae7174d769a6e1b1273734551',
],
    'words': 'butterfly jaguar',
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
    'word': 'bear',
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'elephant',
    'deer',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 5,
    'maybe': 'frog',
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
    '19',
],
    'text_data': 'aeecdf15ecf146d1a732e524ab33185e',
    'rand_digit': 6,
    'rand_number': 0.92368,
    'rand_signed_int': 5,
    'rand_datetime': '2000-01-24T08:25:32.366810',
    'text_array': [
    '7c7936d822264023a3d8addcd43afa07',
    'fe2bfe5cf18c4b38a416398aa2fe59fc',
],
    'words': 'rabbit duck',
    'nested': {
    'id': 107,
    'rand_digit': 9,
    'array': [
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
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'hyena',
    'zebra',
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
    'mixed_type': 0.28445,
    'maybe': 'ape',
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
    '22',
    '23',
    '15',
    '01',
],
    'text_data': 'a55747e839dd409bb80393e10c090701',
    'rand_digit': 6,
    'rand_number': 0.16986,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-21T06:49:36+0500',
    'text_array': [
    'c6bf63b4a0c04a35a2c088413c66c03f',
    'cad2cd6e9ae54e02aee85032bd1c5704',
],
    'words': 'squid bee',
    'nested': {
    'id': 108,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 5,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 3,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'bird',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'elephant',
    'spider',
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
    'maybe': 'fox',
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
],
    'text_data': '89aab6c1311d409f974ec75a76ad35ff',
    'rand_digit': 0,
    'rand_number': 0.09424,
    'rand_signed_int': 6,
    'rand_datetime': '2000-11-24 23:58:06+0700',
    'text_array': [
    'cec51a71b81f4b49ab7898681d46842f',
    'edf3b9cccf85465b986d61f45b180bfc',
],
    'words': 'sloth monkey',
    'nested': {
    'id': 109,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'giraffe',
    'fox',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': [
    66,
],
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'spider',
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
    '18',
    '19',
    '24',
],
    'text_data': '2bdb9c47755e44ac89412867cd70f4fb',
    'rand_digit': 9,
    'rand_number': 0.77444,
    'rand_signed_int': -5,
    'rand_datetime': '2000-02-14 23:22',
    'text_array': [
    '83b7c23b624c48a99128eee01547b1f9',
    '1614bc5d187f4efa93200a48da7c509a',
],
    'words': 'hippo leopard',
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
    'word': 'leopard',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'snake',
    'camel',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 1,
    'maybe_null': 'sheep',
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
    '03',
    '27',
    '24',
    '28',
    '28',
],
    'text_data': '2621140322484fd5b33be57d501c5644',
    'rand_digit': 9,
    'rand_number': 0.98947,
    'rand_signed_int': 1,
    'rand_datetime': '2000-02-12 01:38:45',
    'text_array': [
    '9786118bae87424ab7aab3ed2682a3d0',
    '8157edabe0804b88a0f284df43cabdbd',
],
    'words': 'snail chicken',
    'nested': {
    'id': 111,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'squid',
    'hippo',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': [
    46,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'lizard',
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
],
    'text_data': 'af205db6642143f59c441c5973ee1d95',
    'rand_digit': 3,
    'rand_number': 0.5143,
    'rand_signed_int': 7,
    'rand_datetime': '2001-01-21 07:50:35-0300',
    'text_array': [
    'c7749a7b051a4db0baac667e0c6ce0a3',
    '2570171290b048549d5be1b308684016',
],
    'words': 'bee zebra',
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
    'word': 'mosquito',
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
],
},
    'nested_array': [
],
    'two_words': [
    'kangaroo',
    'bear',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': [
    13,
],
    'rand_bool': True,
    'mixed_type': 7,
    'maybe_null': 'wolf',
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
    '30',
    '17',
],
    'text_data': '12732c81171a410e9ab7cdee800169ca',
    'rand_digit': 6,
    'rand_number': 0.88131,
    'rand_signed_int': -7,
    'rand_datetime': '2000-06-11',
    'text_array': [
    '78cf749df2b2419bba00e6c0effb9c56',
    'dc729419a4cf4942a24f94ad6e868a5c',
],
    'words': 'lobster rabbit',
    'nested': {
    'id': 113,
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
    'word': 'fox',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snake',
    'bird',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 'duck',
    'maybe': 'grasshopper',
    'maybe_null': 'rhino',
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
    'text_data': 'a9cf9329bbef45feb0df897bc4514b79',
    'rand_digit': 4,
    'rand_number': 0.51019,
    'rand_signed_int': -10,
    'rand_datetime': '2000-12-18',
    'text_array': [
    '612967ecd49e4ca4b00d7523977c3856',
    '53c734c5a76c45839537b779e53e3a2d',
],
    'words': 'shark cow',
    'nested': {
    'id': 114,
    'rand_digit': 1,
    'array': [
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
    'word': 'ladybug',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 10,
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
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'mouse',
    'maybe_null': 'spider',
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
    '13',
    '06',
],
    'text_data': '551139f5cb814f05bbe11c32e357cd79',
    'rand_digit': 7,
    'rand_number': 0.59408,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-10 10:14',
    'text_array': [
    'dd8ac14e0d014ce79a2b22ebc99a5988',
    'd977302732a6455a8e680167edd80136',
],
    'words': 'turtle mouse',
    'nested': {
    'id': 115,
    'rand_digit': 7,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
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
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'bird',
    'panda',
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
    'maybe': 'monkey',
    'maybe_null': 'bee',
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
    '26',
    '09',
],
    'text_data': '7e49f42062da4baa8a26d961cfcd2024',
    'rand_digit': 6,
    'rand_number': 0.73845,
    'rand_signed_int': 5,
    'rand_datetime': '2000-02-03 09:27:21-0800',
    'text_array': [
    'efefd3ab3a8e4bb79fb52a7a3cee18b4',
    '880d175abd794689ae06ff253051bb43',
],
    'words': 'gorilla rhino',
    'nested': {
    'id': 116,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
    'number': 5,
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
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -1,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fox',
    'rhino',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'shark',
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
    '25',
],
    'text_data': '9e1f0eb833e646ff9a537d1a9e1a6767',
    'rand_digit': 1,
    'rand_number': 0.7779,
    'rand_signed_int': 3,
    'rand_datetime': '2000-05-24T11:12:19.920641-02:00',
    'text_array': [
    '1104314f48354a9695fc470798f236dc',
    '85671b7fd5384ac5acc7804eab66b4e5',
],
    'words': 'whale fly',
    'nested': {
    'id': 117,
    'rand_digit': 9,
    'array': [
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
],
    'word': 'dog',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ladybug',
    'cheetah',
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
    'mixed_type': 'snake',
    'maybe': 'ladybug',
    'maybe_null': 'mouse',
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
    '13',
    '04',
    '23',
],
    'text_data': 'a4b8f41e32794ef28c3df2f6c5c518ee',
    'rand_digit': 7,
    'rand_number': 0.17073,
    'rand_signed_int': -10,
    'rand_datetime': '2000-01-04 08:57:03.360577+0700',
    'text_array': [
    '7ab0832d83844a778b6c689afe6447b7',
    '76326ffe7ea149e7824d3c18a0d8e918',
],
    'words': 'butterfly mosquito',
    'nested': {
    'id': 118,
    'rand_digit': 2,
    'array': [
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
    'word': 'camel',
    'number': 3,
},
],
},
    'nested_array': [
    [
    -6,
],
    [
    -6,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fox',
    'mosquito',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'whale',
    'maybe_null': 'snake',
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
    '08',
    '25',
],
    'text_data': 'a822ab4d4c344759847971431b7bb095',
    'rand_digit': 7,
    'rand_number': 0.23269,
    'rand_signed_int': -7,
    'rand_datetime': '2000-06-22 13:01:48.115447',
    'text_array': [
    'cbd3f50507594bb6b83891863b65d4b1',
    'b4e1674086e5461389ea37ca375671af',
],
    'words': 'dolphin frog',
    'nested': {
    'id': 119,
    'rand_digit': 8,
    'array': [
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
    'zebra',
    'mouse',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': [
    78,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'squid',
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
],
    'text_data': 'ec7b197a15324e93a1c902a837330506',
    'rand_digit': 5,
    'rand_number': 0.21871,
    'rand_signed_int': -2,
    'rand_datetime': '2000-06-17 18:12:39',
    'text_array': [
    '19d63751791c40cbbe458035d214cbf1',
    '3691aeb10cc24532ae3cb703f5c5a79f',
],
    'words': 'squid fish',
    'nested': {
    'id': 120,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
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
    'number': 8,
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
],
    'word': 'fish',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'lizard',
    'fox',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 0,
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
    '27',
    '12',
    '28',
],
    'text_data': '1639c33704644d1fa2cf56a978b45546',
    'rand_digit': 1,
    'rand_number': 0.22178,
    'rand_signed_int': 8,
    'rand_datetime': '2000-11-06 03:01:54.333114',
    'text_array': [
    '76e0d51daaa545d69c7f1146b67db00c',
    '4017dedb1d83477c8f07ac4c3e005014',
],
    'words': 'grasshopper wolf',
    'nested': {
    'id': 121,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'deer',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 8,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,2__',
    'two_words': [
    'rabbit',
    'kangaroo',
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
    'mixed_type': 4,
    'maybe': 'cat',
    'maybe_null': None,
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
    '17',
    '09',
],
    'text_data': '81edeca7bb8841ec9434ea7438d8ad54',
    'rand_digit': 0,
    'rand_number': 0.64757,
    'rand_signed_int': 8,
    'rand_datetime': '2000-01-23T04:42:19.392724',
    'text_array': [
    '3f12206126064e4cbdb721fdcbd8a0f3',
    'd53c3fa89d43439d852de530dfbc3e18',
],
    'words': 'dragonfly sloth',
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
    'word': 'bee',
    'number': 5,
},
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
    'nested_empty': None,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'elephant',
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
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'rabbit',
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
],
    'text_data': 'a1eff9229753446988e09de50505ea5e',
    'rand_digit': 1,
    'rand_number': 0.40395,
    'rand_signed_int': -7,
    'rand_datetime': '2000-11-03 18:04',
    'text_array': [
    '21c0de70f0aa47a39c0cb5087e42611d',
    'fce220c0c1b445da9ae232fae15e861f',
],
    'words': 'camel octopus',
    'nested': {
    'id': 123,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    4,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lizard',
    'chicken',
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
    'mixed_type': 0.56088,
    'maybe_null': 'dolphin',
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
    '05',
    '23',
    '13',
    '12',
],
    'text_data': '228f872766fc413ab5a10d3165a11ac6',
    'rand_digit': 5,
    'rand_number': 0.12746,
    'rand_signed_int': -10,
    'rand_datetime': '2000-03-17 04:06:29+0500',
    'text_array': [
    'fb4a135dead4403e9634e3ea33019f6b',
    '4705897b0ae7498dbc4420ad0acba002',
],
    'words': 'giraffe deer',
    'nested': {
    'id': 124,
    'rand_digit': 6,
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
    'hello',
],
    'word': 'grasshopper',
    'number': 8,
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
    'word': 'fish',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fish',
    'pig',
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
    'mixed_type': 'lizard',
    'maybe': 'lizard',
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
    '05',
],
    'text_data': '17bab873f77c46b395ddb390861d9eca',
    'rand_digit': 5,
    'rand_number': 0.83625,
    'rand_signed_int': 5,
    'rand_datetime': '2000-01-07T08:29:30.469895',
    'text_array': [
    'b9f90bf804654b059fe8455bd607cb3e',
    '9a0ba75a344a47e598b088d2bdd88128',
],
    'words': 'fish leopard',
    'nested': {
    'id': 125,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'frog',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'frog',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    4,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'turtle',
    'octopus',
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
    'maybe_null': 'camel',
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
    '01',
    '26',
    '05',
],
    'text_data': '29f964d9da544b44877fd806a1153b61',
    'rand_digit': 6,
    'rand_number': 0.42106,
    'rand_signed_int': 0,
    'rand_datetime': '2000-09-20 03:16:44',
    'text_array': [
    '5c91f8f67a42493081177ee7be62441b',
    '442d4ecf13964634b32364d354a8edcf',
],
    'words': 'rhino shark',
    'nested': {
    'id': 126,
    'rand_digit': 4,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -4,
],
],
    'two_words': [
    'mosquito',
    'wolf',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'crab',
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
],
    'text_data': '4e021633295a4693bdb4b1171fbbab34',
    'rand_digit': 5,
    'rand_number': 0.33534,
    'rand_signed_int': -6,
    'rand_datetime': '2000-04-05 18:54:41.583092-0400',
    'text_array': [
    'e44e990e16264293ade9e608d43861e7',
    'bff9b85bed2647ca9ee900fad7a6c4c5',
],
    'words': 'koala bear',
    'nested': {
    'id': 127,
    'rand_digit': 5,
    'array': [
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
    'hello',
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
    'word': 'deer',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 9,
},
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
],
},
    'nested_array': [
],
    'two_words': [
    'mosquito',
    'ant',
],
    'city': {
    'name': 'Barcelona',
    'geo': {
    'lat': 41.385064,
    'lon': 2.173403,
},
},
    'rand_tuple': [
    35,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'tiger',
    'maybe_null': 'ladybug',
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
    '12',
    '05',
    '18',
    '25',
],
    'text_data': '75e2353fa00c4732b67025e6214b01e7',
    'rand_digit': 0,
    'rand_number': 0.47851,
    'rand_signed_int': 4,
    'rand_datetime': '2000-05-08 09:57:32+0900',
    'text_array': [
    '409bd15c71ba4784870d11a0d14dc643',
    '8989404d90504c67b11366b7ae296fd8',
],
    'words': 'cow fox',
    'nested': {
    'id': 128,
    'rand_digit': 1,
    'array': [
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
    'hello',
],
    'word': 'crab',
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
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'panda',
    'koala',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': [
    97,
],
    'rand_bool': False,
    'mixed_type': 0.05823,
    'maybe_null': 'camel',
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
    '24',
    '29',
],
    'text_data': '488bfad2f29642c5b9e504b922a94654',
    'rand_digit': 7,
    'rand_number': 0.9887,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-13 00:27',
    'text_array': [
    'd2bd5d6bcd784a0ebc57c50d35e27e58',
    '30881c16997d4656bf28b07facccbd4a',
],
    'words': 'rabbit leopard',
    'nested': {
    'id': 129,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -3,
],
    [
],
],
    'two_words': [
    'leopard',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'kangaroo',
    'maybe_null': 'lion',
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
],
    'text_data': '464da2ac312f4bc8a035617072300d8e',
    'rand_digit': 5,
    'rand_number': 0.61186,
    'rand_signed_int': 4,
    'rand_datetime': '2000-05-20',
    'text_array': [
    '5f48cd7416fa45d0b4674c10314f5239',
    'd7aa93aca6a64be58673a27a5a00b37e',
],
    'words': 'rabbit koala',
    'nested': {
    'id': 130,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'scorpion',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fly',
    'panda',
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
    'mixed_type': 0.53711,
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
    '09',
    '18',
    '09',
    '18',
    '10',
],
    'text_data': 'a3ea73652db941b081f48646ae0a5184',
    'rand_digit': 4,
    'rand_number': 0.42331,
    'rand_signed_int': -2,
    'rand_datetime': '2000-03-21 04:10:16.496430-1100',
    'text_array': [
    '97946d13006440f5962159febbd2e82a',
    '97efcc4b907b40c496b22b2cfaa67d90',
],
    'words': 'mouse sloth',
    'nested': {
    'id': 131,
    'rand_digit': 5,
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
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'lion',
    'bird',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'frog',
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
    '16',
    '03',
    '15',
    '09',
    '14',
],
    'text_data': '0a514a84e8ad41c088d372dfba48c963',
    'rand_digit': 2,
    'rand_number': 0.73216,
    'rand_signed_int': 8,
    'rand_datetime': '2000-05-04T15:55:57.446689+0100',
    'text_array': [
    '0492f1f419b74b84a36a2d9001383355',
    'e7985b9caf6a48fab95bccaecb2e91f2',
],
    'words': 'goat wolf',
    'nested': {
    'id': 132,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'horse',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fish',
    'lizard',
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
    'mixed_type': False,
    'maybe': 'mouse',
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
    '02',
    '06',
    '11',
    '13',
    '27',
],
    'text_data': '5445040a9b314f4fac68b8cdfb32ca15',
    'rand_digit': 4,
    'rand_number': 0.42092,
    'rand_signed_int': -4,
    'rand_datetime': '2000-11-24T19:29:37.711174',
    'text_array': [
    '26fdf7b255d3484b8663fa978c196891',
    '00504643c2c04b5090a93ac16cbd0f41',
],
    'words': 'turtle lobster',
    'nested': {
    'id': 133,
    'rand_digit': 3,
    'array': [
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
    'hello',
],
    'word': 'cheetah',
    'number': 8,
},
],
},
    'nested_array': [
    [
    1,
],
    [
    -4,
],
    [
    -5,
],
],
    'two_words': [
    'grasshopper',
    'shark',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': [
    22,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'panda',
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
    '21',
],
    'text_data': '67450f364b3e4b178cab4aa39a12d6c2',
    'rand_digit': 3,
    'rand_number': 0.6135,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-28 04:40',
    'text_array': [
    'b1f74b6b0dd4439abd2b6ed9163ecbd0',
    '52c08b8ac711432d8eabd37ee7e2f691',
],
    'words': 'tiger lizard',
    'nested': {
    'id': 134,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'deer',
    'panda',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': [
    98,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
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
    '26',
],
    'text_data': '2ac69d7546e047f3a479dd3c85dd092f',
    'rand_digit': 6,
    'rand_number': 0.2853,
    'rand_signed_int': 9,
    'rand_datetime': '2000-04-30T09:28:00',
    'text_array': [
    'b01dada508604d9e87d10c4891e28381',
    '76b46d3335f9496ab0091f649a255509',
],
    'words': 'rhino octopus',
    'nested': {
    'id': 135,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'duck',
    'sheep',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'lobster',
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
    '20',
],
    'text_data': '1c6160aee8d94677bbaf8c75058548a2',
    'rand_digit': 8,
    'rand_number': 0.97226,
    'rand_signed_int': -8,
    'rand_datetime': '2000-07-13 09:06',
    'text_array': [
    '305dfd85c9804b138561e6f135b884a1',
    'b5aabc061aca40738f2d12185e71e629',
],
    'words': 'mouse whale',
    'nested': {
    'id': 136,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'lion',
    'rabbit',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.24764,
    'maybe': 'horse',
    'maybe_null': 'monkey',
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
    'text_data': 'ed81f7e370f945918c657c9664ccd37f',
    'rand_digit': 3,
    'rand_number': 0.76801,
    'rand_signed_int': -9,
    'rand_datetime': '2000-04-02 14:25:25-0900',
    'text_array': [
    '916748a06eaa48758dae29d1d43ae8e4',
    '1aa111e5d32548818053ee6d22dbd6a8',
],
    'words': 'wolf wolf',
    'nested': {
    'id': 137,
    'rand_digit': 4,
    'array': [
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
    5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    10,
],
],
    'two_words': [
    'dog',
    'squid',
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
    'mixed_type': 0.53391,
    'maybe_null': None,
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
    '07',
],
    'text_data': '1a892ceb52524c5bbe71ea1046fce009',
    'rand_digit': 3,
    'rand_number': 0.16939,
    'rand_signed_int': -5,
    'rand_datetime': '2000-07-27 19:12:19-1200',
    'text_array': [
    'da73a12885634244b62e42a3475db624',
    '61ed68abd9cc462f849e831a1cdbe61e',
],
    'words': 'bird deer',
    'nested': {
    'id': 138,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'sloth',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    1,
],
    [
    1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fish',
    'bear',
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
    'mixed_type': 'crab',
    'maybe': 'elephant',
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
    '22',
    '17',
    '12',
],
    'text_data': 'eefca9c7367a4e62b749c3d1e599be75',
    'rand_digit': 1,
    'rand_number': 0.59999,
    'rand_signed_int': 4,
    'rand_datetime': '2000-04-01T06:54:02.649860',
    'text_array': [
    'ca362bc7f5d84859bb741c181f292eb4',
    '0543aaa5fb214e2681a299b462112360',
],
    'words': 'elephant camel',
    'nested': {
    'id': 139,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'wolf',
    'gorilla',
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
    'id': 40,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 140,
    'id_str': [
    '15',
    '04',
    '03',
    '29',
    '01',
],
    'text_data': '37620484c0974fd5b98366a330bc0e7c',
    'rand_digit': 8,
    'rand_number': 0.3494,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-05T01:16:40.782286',
    'text_array': [
    '6cb83527c9cc4e8aa2f1a955d26e1729',
    '5a159385cbf14a948aefe9a236deb634',
],
    'words': 'deer bee',
    'nested': {
    'id': 140,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
    5,
],
],
    'two_words': [
    'sheep',
    'grasshopper',
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
    'mixed_type': 0.50677,
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
    '17',
    '25',
],
    'text_data': '1547fce778ea4a1dbf86091f86166480',
    'rand_digit': 6,
    'rand_number': 0.29502,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-14 20:57:39.221092',
    'text_array': [
    '3ff2def10d8843299d3a00cea62102f8',
    '0f20d9bd3ea6436bb2877959e548fbce',
],
    'words': 'dog giraffe',
    'nested': {
    'id': 141,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'monkey',
    'gorilla',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fox',
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
    '27',
    '08',
    '28',
    '15',
    '24',
],
    'text_data': '97d45616bc5e46f5b7d781645447d5d1',
    'rand_digit': 6,
    'rand_number': 0.30189,
    'rand_signed_int': 1,
    'rand_datetime': '2000-03-09 18:47:31.615305+0400',
    'text_array': [
    'd88fc3aefb534c91ba4260da11defd68',
    'bb9d9b0a3a3d43df9cb31dc6b1923bdc',
],
    'words': 'horse zebra',
    'nested': {
    'id': 142,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 4,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fly',
    'fish',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'cow',
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
    '30',
],
    'text_data': '63c6be51cbd342fe9d5113015333f4eb',
    'rand_digit': 3,
    'rand_number': 0.7269,
    'rand_signed_int': 3,
    'rand_datetime': '2000-04-06 15:37:45.688709',
    'text_array': [
    '6869b600c21c436996deef6d19fdf01a',
    'd6c665ee7cc74eb38636fc82e3abb057',
],
    'words': 'chicken hyena',
    'nested': {
    'id': 143,
    'rand_digit': 6,
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
],
    'word': 'octopus',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    [
    6,
],
    [
    6,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'koala',
    'bird',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 7,
    'maybe_null': 'cow',
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
    '23',
    '28',
    '15',
    '01',
    '10',
],
    'text_data': '0844b060687b4f44afbaf1613260bc9e',
    'rand_digit': 4,
    'rand_number': 0.28918,
    'rand_signed_int': 9,
    'rand_datetime': '2000-02-24',
    'text_array': [
    'fe8a724bb5864470816d75126b9d59f5',
    'a808027d089d4da0848e371edb5be400',
],
    'words': 'cat dragonfly',
    'nested': {
    'id': 144,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'zebra',
    'deer',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '22',
],
    'text_data': '49451b1505ee4cc48f49d617c9972811',
    'rand_digit': 5,
    'rand_number': 0.49486,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-06 06:34:11.060229+1100',
    'text_array': [
    '38795f6bcd6b43cfad83d49b2fea98f0',
    '941ca427abc4425eab6ac8e0338d9c47',
],
    'words': 'giraffe fox',
    'nested': {
    'id': 145,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'deer',
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
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'snake',
    'koala',
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
    'mixed_type': 0.83495,
    'maybe': 'rhino',
    'maybe_null': None,
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
    '24',
    '11',
    '01',
    '14',
],
    'text_data': '1b6e8bbfd8504767a1b6ece465d5c67e',
    'rand_digit': 5,
    'rand_number': 0.78914,
    'rand_signed_int': 0,
    'rand_datetime': '2000-04-12T19:09:27',
    'text_array': [
    '70ad6b5867da4fc0969d868c0399ac6b',
    'd060eda481bc430a8f3c865a0df4d110',
],
    'words': 'snake chicken',
    'nested': {
    'id': 146,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 9,
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
],
    'word': 'chicken',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'camel',
    'lion',
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
    'mixed_type': 'koala',
    'maybe_null': 'cheetah',
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
    '30',
    '13',
],
    'text_data': '27120b83cdb14eeea6fea07a8b4105b0',
    'rand_digit': 0,
    'rand_number': 0.18087,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-15',
    'text_array': [
    'f0236d2bf8784debb693e5f9d0ecbe9a',
    '076458dd6445498da50d3c9046a151e6',
],
    'words': 'koala lion',
    'nested': {
    'id': 147,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'mouse',
    'mosquito',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'mosquito',
    'maybe_null': 'hippo',
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
    '16',
],
    'text_data': 'cc4f536447304f3281dc267efcd604d3',
    'rand_digit': 0,
    'rand_number': 0.29146,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-15T07:57:45',
    'text_array': [
    'fdd59dabb299428288210faa03a96e3a',
    'e01f83bb58a248918ee5ee98874887c7',
],
    'words': 'chicken giraffe',
    'nested': {
    'id': 148,
    'rand_digit': 5,
    'array': [
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
    'hello',
],
    'word': 'frog',
    'number': 9,
},
],
},
    'nested_array': [
    [
    0,
],
    [
    5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lion',
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
    'mixed_type': 5,
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
],
    'text_data': 'dade7fcfc97343e781286540374ef506',
    'rand_digit': 6,
    'rand_number': 0.82991,
    'rand_signed_int': -7,
    'rand_datetime': '2000-07-20 22:55:26',
    'text_array': [
    'fc04e0fa208d430e8f86f26af3e0f8c5',
    '7e2803bb8de94980b974d43ff2dc1fb3',
],
    'words': 'bird goat',
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
    'number': 2,
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
    'word': 'pig',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dog',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'chicken',
    'horse',
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
    'mixed_type': 'cow',
    'maybe': 'grasshopper',
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
    '24',
    '21',
    '17',
    '29',
    '21',
],
    'text_data': 'b0a0fb0149444401ba3c9de872ed1055',
    'rand_digit': 9,
    'rand_number': 0.60453,
    'rand_signed_int': 5,
    'rand_datetime': '2000-05-15 09:43:45.940051',
    'text_array': [
    'a763e3ec4ff44a058b36b130287ad342',
    '831d21471a084b7a98e7d65b6d5956c7',
],
    'words': 'camel cat',
    'nested': {
    'id': 150,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ape',
    'number': 2,
},
],
},
    'nested_array': [
    [
    6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'cow',
    'lizard',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '11',
    '01',
    '10',
    '27',
    '24',
],
    'text_data': 'debae6cd726c4a9785a6db9273c383a9',
    'rand_digit': 2,
    'rand_number': 0.27893,
    'rand_signed_int': -4,
    'rand_datetime': '2000-01-20T18:18:34-0400',
    'text_array': [
    '1cad68ee1d21416988169c1a1d855e36',
    'c7f46396faa14218b9562b63f4d1489e',
],
    'words': 'grasshopper deer',
    'nested': {
    'id': 151,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'snail',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'panda',
    'duck',
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
],
    'text_data': '2ef4b940d42145aaa0f34136a89eab19',
    'rand_digit': 6,
    'rand_number': 0.43051,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-31T07:09:14.087037+0800',
    'text_array': [
    'f215133a52754678989b1c5273b65028',
    '996055f35b4344e5aa6ddcc05420a543',
],
    'words': 'dolphin bear',
    'nested': {
    'id': 152,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'lion',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ape',
    'grasshopper',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'giraffe',
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
    '08',
    '10',
],
    'text_data': '2ff74eeeff764d67888a8a05071a8cca',
    'rand_digit': 4,
    'rand_number': 0.80996,
    'rand_signed_int': -1,
    'rand_datetime': '2000-07-06 15:12:47.771164',
    'text_array': [
    '15ba2c51088e4bc9ac28aa0759e14433',
    'ced252f7b69e4945a30368284294618b',
],
    'words': 'bird jaguar',
    'nested': {
    'id': 153,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'horse',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
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
    'number': 9,
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'koala',
    'hippo',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': [
    80,
],
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'cheetah',
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
    '23',
],
    'text_data': 'fcfdabedc8c54f81a1d62d7214f77020',
    'rand_digit': 6,
    'rand_number': 0.07327,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-05 12:58:48.820059-0800',
    'text_array': [
    '4c80d30bc02e4707a9fde1e68aaccad4',
    'ed33b90feb6744a68757e7c9efc061d5',
],
    'words': 'ant scorpion',
    'nested': {
    'id': 154,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'ladybug',
    'sheep',
],
    'city': {
    'name': 'Barcelona',
    'geo': {
    'lat': 41.385064,
    'lon': 2.173403,
},
},
    'rand_tuple': [
    11,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'dolphin',
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
    '27',
    '27',
    '09',
],
    'text_data': '7bafcc6a69da40d7911f35c058b57a78',
    'rand_digit': 7,
    'rand_number': 0.11034,
    'rand_signed_int': 4,
    'rand_datetime': '2000-06-30T20:30:46.869554',
    'text_array': [
    'e02a807b739d4383acaf274965c5ad68',
    '3cd5183cc79a448eb6733c13343fc5f1',
],
    'words': 'rhino duck',
    'nested': {
    'id': 155,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'octopus',
    'hyena',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': [
    83,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'zebra',
    'maybe_null': 'crab',
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
    '15',
    '17',
    '29',
],
    'text_data': '2a5e0275fef24da9be5d7f75a83d50dd',
    'rand_digit': 4,
    'rand_number': 0.35714,
    'rand_signed_int': 0,
    'rand_datetime': '2000-08-08 03:13',
    'text_array': [
    '7fad405290f54d2ebeb1d8491bd57075',
    '0379cea8f8bf4a54ba4f64e220ddcf05',
],
    'words': 'lizard hyena',
    'nested': {
    'id': 156,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'monkey',
    'ape',
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
    'mixed_type': 6,
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
    '28',
    '09',
    '01',
    '02',
],
    'text_data': '355e87ca82ec45ccbdf9a230b2cb4740',
    'rand_digit': 7,
    'rand_number': 0.95168,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-28T17:49:06.194355',
    'text_array': [
    'e2c5ef4ebd464984b19530966bb48541',
    'c2a8b8f9c5cd42b1ae8c62ab9949d4b8',
],
    'words': 'duck dog',
    'nested': {
    'id': 157,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'pig',
    'cheetah',
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
    '06',
    '20',
    '06',
],
    'text_data': 'b8fcdb1ea3a34e17aaec5320e9834cb3',
    'rand_digit': 3,
    'rand_number': 0.11859,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-26 18:35:40+0600',
    'text_array': [
    'ddefdc3ff0c54ec99e1a41d74db615bb',
    'b68956b471f348de9ae9cf32f95cc944',
],
    'words': 'octopus fox',
    'nested': {
    'id': 158,
    'rand_digit': 1,
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
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'tiger',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -5,
],
    [
    8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'sloth',
    'snake',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 1,
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
    '07',
    '25',
    '15',
],
    'text_data': '77e6c218a6e64c60bbc686c6f747cd16',
    'rand_digit': 0,
    'rand_number': 0.09617,
    'rand_signed_int': 3,
    'rand_datetime': '2000-09-09T04:52:17.231709-03:00',
    'text_array': [
    '05c950dbdd2b4cc7b805144bb7188545',
    'f9dda8127c794a7f9f59e0ef1278a6a6',
],
    'words': 'whale lobster',
    'nested': {
    'id': 159,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'cheetah',
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
    'mixed_type': 9,
    'maybe': 'grasshopper',
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
    '16',
    '04',
    '26',
],
    'text_data': 'd92f97b6bbb149268655e65b61f91c7a',
    'rand_digit': 8,
    'rand_number': 0.24422,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-03 04:44:10-0600',
    'text_array': [
    'b4f386a683464dc5a587fa5f7b486195',
    '1e929cf9a3f541509d42ebda4542b1de',
],
    'words': 'tiger ant',
    'nested': {
    'id': 160,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'cow',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lion',
    'camel',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': [
    77,
],
    'rand_bool': False,
    'mixed_type': 0.87301,
    'maybe': 'hyena',
    'maybe_null': None,
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
    '04',
],
    'text_data': 'dbcd7165817344098f06f6c4f5d2321d',
    'rand_digit': 4,
    'rand_number': 0.9926,
    'rand_signed_int': 5,
    'rand_datetime': '2000-05-18 20:33:18.159481',
    'text_array': [
    '26e665bf481348dcb4e278d5dbc000f8',
    '97aadb711a614844bbdc5724cf29bf87',
],
    'words': 'octopus elephant',
    'nested': {
    'id': 161,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'panda',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'squid',
    'bear',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'lobster',
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
    '20',
],
    'text_data': '92e31ba94c954fab9f349ab47c6eb2e1',
    'rand_digit': 6,
    'rand_number': 0.17768,
    'rand_signed_int': 1,
    'rand_datetime': '2000-07-25 08:00:00',
    'text_array': [
    'b8b500a36fcd4e92bf870a3cd034a79e',
    '072c8b43df1441869e88dcfb03332e7b',
],
    'words': 'tiger zebra',
    'nested': {
    'id': 162,
    'rand_digit': 0,
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
    'word': 'cat',
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
    'hello',
],
    'word': 'dolphin',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'duck',
    'lobster',
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
    'maybe': 'snake',
    'maybe_null': 'bee',
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
    '22',
    '16',
],
    'text_data': '439fb9f9a3604293adfe224ecb872501',
    'rand_digit': 6,
    'rand_number': 0.39482,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-02T07:24:11.545422-0500',
    'text_array': [
    '670d4342290a46d590c7d31c60716870',
    'ef2e352bff1d4c55a879f7f45610f950',
],
    'words': 'goat dog',
    'nested': {
    'id': 163,
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
    'word': 'wolf',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'cow',
    'horse',
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
    'mixed_type': 1,
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
    'content-length': '136861',
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
    '02',
],
    'text_data': '86c001d32b9b44ec915a382da884f3aa',
    'rand_digit': 5,
    'rand_number': 0.07387,
    'rand_signed_int': 6,
    'rand_datetime': '2000-03-09 13:41:01.440024-0500',
    'text_array': [
    '4713fc411f3d4dc783104f6b411967bb',
    'de0acf0b711c4f7790aeca5eee3c4b91',
],
    'words': 'panda wolf',
    'nested': {
    'id': 100,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
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
    'number': 4,
},
    {
    'nested_empty': None,
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
    'word': 'shark',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'gorilla',
    'gorilla',
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
    'mixed_type': 'shark',
    'maybe_null': 'zebra',
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
    'text_data': 'e04992402b9e4e8f8873270bfc9a3f57',
    'rand_digit': 7,
    'rand_number': 0.87674,
    'rand_signed_int': 4,
    'rand_datetime': '2000-02-13',
    'text_array': [
    '91e515c8b9a046e0b58ca21c6d76babd',
    'a48c748beeb74ca08225a7ca11dafdd0',
],
    'words': 'frog monkey',
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
    'word': 'pig',
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snail',
    'lizard',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': [
    22,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
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
    '30',
],
    'text_data': '1d0e7a49d50a417cb49bbc888b323fb1',
    'rand_digit': 5,
    'rand_number': 0.62344,
    'rand_signed_int': -2,
    'rand_datetime': '2000-09-19 17:21:01.171907-0100',
    'text_array': [
    'e6e6ce50b3194af0b693724573bebb06',
    '873c828942d94419a9d32c48387c2268',
],
    'words': 'crab chicken',
    'nested': {
    'id': 102,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 5,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'jaguar',
    'ant',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': [
    54,
],
    'rand_bool': False,
    'mixed_type': 0,
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
],
    'text_data': '44d8d0a4472d45a4bd1b0cb05882ded6',
    'rand_digit': 1,
    'rand_number': 0.07457,
    'rand_signed_int': 1,
    'rand_datetime': '2000-03-10T23:28:31.295085',
    'text_array': [
    'b5b2376cb20e4f9db642ed9a363c9625',
    'ea659b9953094432a42e17e798800ecf',
],
    'words': 'grasshopper deer',
    'nested': {
    'id': 103,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'turtle',
    'ant',
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
    'mixed_type': 8,
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
    '11',
    '11',
],
    'text_data': 'db8b6db9404e46928bb729627b362c6c',
    'rand_digit': 4,
    'rand_number': 0.6258,
    'rand_signed_int': -3,
    'rand_datetime': '2000-06-20T14:07:03.789093-02:00',
    'text_array': [
    'f78817b7b79f4fca8f5d2517e11e8f15',
    '388f38be39984edbba14a2bd62edc2db',
],
    'words': 'chicken scorpion',
    'nested': {
    'id': 104,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 9,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'squid',
    'dolphin',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'hippo',
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
    '28',
],
    'text_data': 'b1e104a277ea4187b6a15e5cab7afcb0',
    'rand_digit': 3,
    'rand_number': 0.6368,
    'rand_signed_int': -9,
    'rand_datetime': '2000-06-19 15:50',
    'text_array': [
    'b1108de917a146a0884b8548633d09d2',
    '7227c9f01c4c450cadeaed468ebde28a',
],
    'words': 'cheetah whale',
    'nested': {
    'id': 105,
    'rand_digit': 9,
    'array': [
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
    'nested_empty': [
    'hello',
],
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
    'word': 'bird',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'rabbit',
    'turtle',
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
    'mixed_type': 0.68307,
    'maybe': 'whale',
    'maybe_null': 'cheetah',
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
    '11',
    '15',
    '13',
],
    'text_data': '95ce417e2fc24782a9e1c9072e08da0e',
    'rand_digit': 8,
    'rand_number': 0.8935,
    'rand_signed_int': -6,
    'rand_datetime': '2000-06-05 12:09:44.928267+0200',
    'text_array': [
    'de33182af2814b61b96ee1166a5e8e8e',
    'f067fe758fe64f16a277bb9a8f1ebeee',
],
    'words': 'cow octopus',
    'nested': {
    'id': 106,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'lion',
    'cheetah',
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
    'mixed_type': None,
    'maybe': 'butterfly',
    'maybe_null': 'dolphin',
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
    'text_data': '7504e9373edd4f2fa9d875e82bd319ef',
    'rand_digit': 2,
    'rand_number': 0.03658,
    'rand_signed_int': -7,
    'rand_datetime': '2000-07-21T15:14:51.263305',
    'text_array': [
    '43e5336adfdd479d8048dc6a718d1b2e',
    'ae18ec28be0249a6b1e886509d4874e8',
],
    'words': 'lion tiger',
    'nested': {
    'id': 107,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'leopard',
    'mouse',
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
    'maybe_null': 'ladybug',
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
],
    'text_data': '48753968976f45bca8c803f4454795ac',
    'rand_digit': 3,
    'rand_number': 0.03534,
    'rand_signed_int': 0,
    'rand_datetime': '2000-06-07T06:38:17',
    'text_array': [
    'a18637c668d94636be0cd355c5256d05',
    '5e47c35bfe224a47a83effef40fe1266',
],
    'words': 'ape cow',
    'nested': {
    'id': 108,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'ant',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'camel',
    'koala',
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
    'mixed_type': 'bee',
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
    '27',
    '07',
    '12',
    '28',
],
    'text_data': 'c6e5d8e5eb0e45ae8b982879dcd63491',
    'rand_digit': 4,
    'rand_number': 0.05867,
    'rand_signed_int': 7,
    'rand_datetime': '2000-06-02T15:35:05',
    'text_array': [
    '53ad5042e9ba4993966ab98ca8109ea7',
    'fc4de77700394b0aa76fc18ff466e738',
],
    'words': 'ant sloth',
    'nested': {
    'id': 109,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'crab',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'koala',
    'horse',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'mosquito',
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
    '01',
],
    'text_data': 'ee0ff29d045e4c4c856af5e963872d40',
    'rand_digit': 0,
    'rand_number': 0.39511,
    'rand_signed_int': 9,
    'rand_datetime': '2000-06-12 03:42',
    'text_array': [
    'f9efa60122be4bcc9b095a187256f6ea',
    'e6fb95807fa4483996f4bd530f049797',
],
    'words': 'cheetah bear',
    'nested': {
    'id': 110,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
    3,
],
    [
],
],
    'two_words': [
    'kangaroo',
    'dragonfly',
],
    'city': {
    'name': 'Copenhagen',
    'geo': {
    'lat': 55.676097,
    'lon': 12.568337,
},
},
    'rand_tuple': [
    72,
],
    'rand_bool': True,
    'mixed_type': 0.50012,
    'maybe': 'zebra',
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
    '02',
    '13',
    '01',
],
    'text_data': '1921aec188074292b24427f94c07734b',
    'rand_digit': 9,
    'rand_number': 0.39601,
    'rand_signed_int': -5,
    'rand_datetime': '2000-01-17T18:32:25.258124',
    'text_array': [
    '2addc8ddd80648a0a811f9b36df4b7d5',
    '90a90dbabeac404eaed0ba42e14ac802',
],
    'words': 'hyena cheetah',
    'nested': {
    'id': 111,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lion',
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
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'gorilla',
    'leopard',
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
    'mixed_type': None,
    'maybe': 'panda',
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
    '22',
    '22',
    '12',
],
    'text_data': '3051191dffd346088951128c1ea159be',
    'rand_digit': 4,
    'rand_number': 0.65907,
    'rand_signed_int': -7,
    'rand_datetime': '2000-10-11T12:23:14.971367',
    'text_array': [
    '6f69ab00ad254892ad6e60c5c70b7f51',
    '6c77da517ff240d082ebdc43cf551f37',
],
    'words': 'tiger mosquito',
    'nested': {
    'id': 112,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'mosquito',
    'goat',
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
    'mixed_type': None,
    'maybe_null': 'fish',
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
    '06',
    '03',
],
    'text_data': 'cee49067716a4ef49be9c1ef7bb9f149',
    'rand_digit': 4,
    'rand_number': 0.87845,
    'rand_signed_int': -6,
    'rand_datetime': '2000-04-16T09:11:24.076003',
    'text_array': [
    '906c92465d944ab6836ec5f0193e33ec',
    '61f6a7a63a9d4dec9b1cc884e82c9737',
],
    'words': 'monkey bee',
    'nested': {
    'id': 113,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 3,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'hippo',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'snail',
    'deer',
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
    'mixed_type': False,
    'maybe': 'dragonfly',
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
    '03',
    '08',
    '16',
],
    'text_data': '4208eff94ebe4ed889caa0d341aea275',
    'rand_digit': 7,
    'rand_number': 0.82847,
    'rand_signed_int': -8,
    'rand_datetime': '2000-02-01 03:12:08-0900',
    'text_array': [
    '2248e23e07684f9380df6be7aa67cd91',
    '757dd1a97e7a41e98ac89306d4ac00b8',
],
    'words': 'spider ladybug',
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
    'word': 'mouse',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bird',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'tiger',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'koala',
    'tiger',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': [
    34,
],
    'rand_bool': False,
    'mixed_type': 0.25384,
    'maybe': 'lion',
    'maybe_null': 'mouse',
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
    '14',
    '12',
    '05',
    '06',
],
    'text_data': '002621a9e9764ceaa888f097b70d3582',
    'rand_digit': 4,
    'rand_number': 0.13571,
    'rand_signed_int': -5,
    'rand_datetime': '2000-10-04 01:48:27+0300',
    'text_array': [
    'f855fe812fbf4de59ba3b955eb823fa7',
    '55c3b2b9f0154bef85e0e72d780c2249',
],
    'words': 'whale ant',
    'nested': {
    'id': 115,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'turtle',
    'cow',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '06',
    '05',
    '04',
],
    'text_data': '53a312c94a1b45a6bd982972e90b94cf',
    'rand_digit': 4,
    'rand_number': 0.28363,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-09',
    'text_array': [
    '6377d78e9562431fa2d74328f39826fa',
    '8af8676f003c4a368bc75b3d3afea351',
],
    'words': 'jaguar bird',
    'nested': {
    'id': 116,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'panda',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'tiger',
    'snake',
],
    'city': {
    'name': 'Kuala Lumpur',
    'geo': {
    'lat': 3.139003,
    'lon': 101.686855,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '26',
    '01',
    '28',
    '25',
    '12',
],
    'text_data': '15823d9bf79d4fe9a90bc5be203e8c52',
    'rand_digit': 1,
    'rand_number': 0.4919,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-27T08:47:20',
    'text_array': [
    'eb66437f34ef492fbcd6d4bf59098233',
    '33ca16388a6f419e9e6f45b5e0d56c0c',
],
    'words': 'deer mouse',
    'nested': {
    'id': 117,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 6,
},
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
    'hello',
],
    'word': 'frog',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 9,
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
],
    'two_words': [
    'dragonfly',
    'wolf',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
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
    '23',
    '04',
],
    'text_data': '7748acd33c9d4e4aa61ba046f5e22df2',
    'rand_digit': 6,
    'rand_number': 0.53418,
    'rand_signed_int': -4,
    'rand_datetime': '2000-02-19T13:43:35',
    'text_array': [
    'a1b29f999cf14f4babcf9ed05c163c36',
    '762f7b20a1724fa7901de7f54cbf716d',
],
    'words': 'butterfly jaguar',
    'nested': {
    'id': 118,
    'rand_digit': 2,
    'array': [
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
    'hello',
],
    'word': 'pig',
    'number': 7,
},
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
    [
    -4,
],
    [
    -6,
],
],
    'two_words': [
    'gorilla',
    'bear',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': [
    75,
],
    'rand_bool': False,
    'mixed_type': None,
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
    '11',
    '27',
    '04',
],
    'text_data': '7c71203fe20f4b5196f4ad2823fd3dea',
    'rand_digit': 9,
    'rand_number': 0.57241,
    'rand_signed_int': 7,
    'rand_datetime': '2000-11-28T11:32:55+0600',
    'text_array': [
    '3deb6fd4ab7648589368b05ecac8ee43',
    '8d7ae375b7c3473da21ce51107fede04',
],
    'words': 'cow horse',
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
    'word': 'ant',
    'number': 7,
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
    'hello',
],
    'word': 'leopard',
    'number': 8,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mouse',
    'ladybug',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fox',
    'maybe_null': 'lizard',
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
    '13',
    '10',
],
    'text_data': '75b45c3a4f2441ce967e2b72315b8b6e',
    'rand_digit': 3,
    'rand_number': 0.71561,
    'rand_signed_int': 0,
    'rand_datetime': '2000-06-10T04:33:15.977269+03:00',
    'text_array': [
    'da4e861d33a84e9393ffc55011de3b25',
    '3de67cf1223040fbb4dfd2b5422d3c60',
],
    'words': 'bee mosquito',
    'nested': {
    'id': 120,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lion',
    'dragonfly',
],
    'city': {
    'name': 'London',
    'geo': {
    'lat': 51.507351,
    'lon': -0.127758,
},
},
    'rand_tuple': [
    66,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'wolf',
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
    '09',
],
    'text_data': '3b2649e2dd854a50920b77871c5c987b',
    'rand_digit': 3,
    'rand_number': 0.89479,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-12',
    'text_array': [
    'cde789cbbbce481085a9c663f12bff91',
    '8fa164b6ce824b5fb4776e419b6bf82d',
],
    'words': 'lobster lobster',
    'nested': {
    'id': 121,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'sloth',
    'dog',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': [
    32,
],
    'rand_bool': False,
    'mixed_type': 0.75775,
    'maybe': 'butterfly',
    'maybe_null': None,
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
],
    'text_data': '1f3111a4572d4f0dadecddb1633eab83',
    'rand_digit': 7,
    'rand_number': 0.21182,
    'rand_signed_int': 4,
    'rand_datetime': '2000-12-05',
    'text_array': [
    '3b55289b57b54256bbb992d096deaa5d',
    '5efc13853cf24f048d1e12ccfb1f26d3',
],
    'words': 'ladybug jaguar',
    'nested': {
    'id': 122,
    'rand_digit': 8,
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
    'word': 'rhino',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'octopus',
    'mouse',
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
    'mixed_type': 'cat',
    'maybe': 'monkey',
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
    '12',
    '03',
    '02',
    '23',
    '16',
],
    'text_data': '8d4bb34dafd146deb94e571ca3ad559a',
    'rand_digit': 5,
    'rand_number': 0.65923,
    'rand_signed_int': -2,
    'rand_datetime': '2000-11-06 18:50:24-1200',
    'text_array': [
    'ab3c5e2e7db24c26a2104aa8215c7d27',
    '2db3cfcdb0444a80a689db56b4b688ef',
],
    'words': 'gorilla cheetah',
    'nested': {
    'id': 123,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'turtle',
    'deer',
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
    'mixed_type': None,
    'maybe_null': None,
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
    '02',
    '20',
    '24',
],
    'text_data': '938b900ef60d417886e10ed4e23bd132',
    'rand_digit': 8,
    'rand_number': 0.08681,
    'rand_signed_int': 8,
    'rand_datetime': '2000-04-21T14:23:13-0800',
    'text_array': [
    'c027423a1daf4c0cbff88874b0a4d687',
    '373bba1f53e04b3e96d246a372b2809a',
],
    'words': 'frog dolphin',
    'nested': {
    'id': 124,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 10,
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
],
    'word': 'zebra',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'chicken',
    'goat',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'hippo',
    'maybe_null': None,
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
    '08',
    '28',
    '27',
],
    'text_data': '71bf354cbc2d4d00a6d414ea2d644c64',
    'rand_digit': 8,
    'rand_number': 0.06804,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-13T23:22:07.214944+11:00',
    'text_array': [
    '73bcd72c8c5442e1b80b22b68545a982',
    'aa9c05a6ce1c40058a4274425d2e90d3',
],
    'words': 'zebra kangaroo',
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
    'word': 'sloth',
    'number': 1,
},
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
],
    'word': 'hyena',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'shark',
    'lizard',
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
    'mixed_type': 'fox',
    'maybe_null': 'chicken',
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
    '14',
    '04',
    '26',
    '20',
],
    'text_data': '84699538f9c84cc4b8733b07c6f2d577',
    'rand_digit': 2,
    'rand_number': 0.44016,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-20 00:18',
    'text_array': [
    'a19b73868c9745809ca62397458af947',
    'bf71cbdd76ba47108cf7b5e32b433db1',
],
    'words': 'butterfly goat',
    'nested': {
    'id': 126,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
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
    'number': 1,
},
    {
    'nested_empty': None,
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
    'word': 'elephant',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'tiger',
    'gorilla',
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
    'mixed_type': True,
    'maybe': 'bee',
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
    '04',
],
    'text_data': '7bf101f80bbd4ff9b98e0af2784f8662',
    'rand_digit': 5,
    'rand_number': 0.46344,
    'rand_signed_int': 2,
    'rand_datetime': '2000-10-14 14:47:56-0200',
    'text_array': [
    'f9cf4cbf2fdb4c05ad0e1643c0f8dc2f',
    'dfc6b236ef6c43a79208a81d5161d3c9',
],
    'words': 'spider shark',
    'nested': {
    'id': 127,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'zebra',
    'wolf',
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
    'mixed_type': 6,
    'maybe_null': None,
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
    '30',
    '30',
    '08',
    '15',
],
    'text_data': '9754b7889ad541c29580b2a7483f7516',
    'rand_digit': 8,
    'rand_number': 0.45569,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-25',
    'text_array': [
    '1a6489ead37547e4a2e2c58a619d2293',
    'bfbec0cf65d54860b18517a15919b820',
],
    'words': 'bee rhino',
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
    'word': 'spider',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 9,
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
    'hello',
],
    'word': 'fish',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'snake',
    'sloth',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '07',
    '02',
],
    'text_data': 'fa65f73ce5154fadb6777f5e431d5272',
    'rand_digit': 2,
    'rand_number': 0.00165,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-27T02:23:31.589034+0400',
    'text_array': [
    '60503f33e9164b719e8fc1bb6232b75c',
    'a9501ba4a5d843f1928d3a57ebe98bcb',
],
    'words': 'jaguar dog',
    'nested': {
    'id': 129,
    'rand_digit': 6,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    3,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'hippo',
    'lion',
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
    'mixed_type': 2,
    'maybe': 'giraffe',
    'maybe_null': 'ant',
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
    '29',
],
    'text_data': '91e4abbd25444bb1ad79613f0243f1c1',
    'rand_digit': 5,
    'rand_number': 0.38006,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-23',
    'text_array': [
    'ac47e9113e2a43ad8744b6db57f35db9',
    '31587bb9c35c4de8b8c6b64970eb053f',
],
    'words': 'bear turtle',
    'nested': {
    'id': 130,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'chicken',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'turtle',
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
    'dolphin',
    'ladybug',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'ladybug',
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
    '17',
    '04',
    '19',
    '04',
],
    'text_data': 'd19b26bc7c174bf6b40aa151ddb9169d',
    'rand_digit': 8,
    'rand_number': 0.8761,
    'rand_signed_int': 7,
    'rand_datetime': '2000-02-28T12:00:25.944120',
    'text_array': [
    '7ee3176cd7184cbdaa32b4955d9b5e16',
    'b7acca300e9c42c09c7b862cae78353a',
],
    'words': 'sheep zebra',
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
    'word': 'monkey',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 10,
},
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 10,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'chicken',
    'dolphin',
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
    'mixed_type': True,
    'maybe_null': 'snake',
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
    '13',
    '15',
    '18',
    '04',
],
    'text_data': 'c37dee28559b4e098e66eb521736ea32',
    'rand_digit': 0,
    'rand_number': 0.31777,
    'rand_signed_int': 4,
    'rand_datetime': '2000-05-23',
    'text_array': [
    '65d41b652d5e491db4c733e59e1f0d00',
    '248c7830f1fa460d80889e82e2221139',
],
    'words': 'camel chicken',
    'nested': {
    'id': 132,
    'rand_digit': 2,
    'array': [
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
    'word': 'dragonfly',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bird',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fish',
    'fish',
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
    'mixed_type': 4,
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
    '08',
    '12',
    '16',
],
    'text_data': 'e705f64f05614d38952bda4a131293eb',
    'rand_digit': 3,
    'rand_number': 0.84815,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-28T18:57:06',
    'text_array': [
    '7d2f69857a424a9e84434ee20c44e15c',
    '3b80197b94a546a8be61d0dadcd8b172',
],
    'words': 'pig ape',
    'nested': {
    'id': 133,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'lion',
    'horse',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': [
    74,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'crab',
    'maybe_null': 'fly',
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
    '23',
    '18',
    '03',
],
    'text_data': 'e2a0d2790e6e43eba4893eb6aef09e3e',
    'rand_digit': 3,
    'rand_number': 0.25779,
    'rand_signed_int': 0,
    'rand_datetime': '2000-01-16 09:12:44-0600',
    'text_array': [
    '30607703622245b68a7d38c3f17f2ec9',
    '1a245edc33f24336871d2df076f0f74f',
],
    'words': 'horse monkey',
    'nested': {
    'id': 134,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'goat',
    'bird',
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
    'mixed_type': 'cow',
    'maybe': 'deer',
    'maybe_null': 'dragonfly',
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
    '11',
],
    'text_data': 'ef8a55b67200413f97f8956abafa30d1',
    'rand_digit': 7,
    'rand_number': 0.66585,
    'rand_signed_int': -1,
    'rand_datetime': '2000-05-04 14:04',
    'text_array': [
    '60b515577d154ae580ba052818cf7488',
    '0ca5c23949404d7cbfe5f983ebf8d152',
],
    'words': 'fish dolphin',
    'nested': {
    'id': 135,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
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
    'number': 8,
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
],
    'word': 'wolf',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'dolphin',
    'turtle',
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
    'mixed_type': 'jaguar',
    'maybe': 'bee',
    'maybe_null': 'rabbit',
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
    '21',
    '07',
],
    'text_data': '5d78acfa988f49a7a2053f93f7b35877',
    'rand_digit': 3,
    'rand_number': 0.13034,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-07 02:01:39.055323+0000',
    'text_array': [
    'a6c69b2a829a436fa235ee25c3ba47fe',
    'bea5c482f5fb4726a29de7748219d753',
],
    'words': 'camel sheep',
    'nested': {
    'id': 136,
    'rand_digit': 1,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ladybug',
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
    'mixed_type': True,
    'maybe_null': 'jaguar',
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
],
    'text_data': '32db4bb0e59f49cd8cc10a123d3ee36d',
    'rand_digit': 2,
    'rand_number': 0.86933,
    'rand_signed_int': -8,
    'rand_datetime': '2000-05-27T17:22:57.754025-1000',
    'text_array': [
    '047df1e8cee44798bf4241570f5e84f3',
    '9ae44faab7bb42338c6a10d2c169b579',
],
    'words': 'scorpion ladybug',
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
    'word': 'kangaroo',
    'number': 8,
},
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
    'word': 'panda',
    'number': 8,
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
],
},
    'nested_array': [
],
    'two_words': [
    'pig',
    'spider',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': [
    84,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'zebra',
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
],
    'text_data': 'ce67839c0cbb4392880d77161f1b72a1',
    'rand_digit': 9,
    'rand_number': 0.12784,
    'rand_signed_int': -7,
    'rand_datetime': '2000-04-29 03:34',
    'text_array': [
    '64410e678ba543189484d6ebd49d901f',
    'eee536f53fc54b949e50334d3b1fb8ea',
],
    'words': 'tiger squid',
    'nested': {
    'id': 138,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'pig',
    'fish',
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
    'mixed_type': 'lizard',
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
    '13',
    '01',
    '25',
],
    'text_data': 'd1abc0b3d14d4020bdf709c21ac58ed8',
    'rand_digit': 7,
    'rand_number': 0.57822,
    'rand_signed_int': 1,
    'rand_datetime': '2000-10-21T05:42:58.276667',
    'text_array': [
    'ac9d8371ede0406fbdaf81e0979fbcbd',
    'cf8366d934204ce0ad26dee4998eb4cc',
],
    'words': 'turtle shark',
    'nested': {
    'id': 139,
    'rand_digit': 7,
    'array': [
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
    [
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lobster',
    'lion',
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
    'mixed_type': 0.93198,
    'maybe': 'hyena',
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
    '06',
    '22',
    '08',
],
    'text_data': '97b12a5dd3ee48c5868e904223e302d2',
    'rand_digit': 8,
    'rand_number': 0.43694,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-11T09:33:22.392797',
    'text_array': [
    'da9958fe0dff488087ee6b779449eab8',
    '790a6a6d23be4c4a9b444f1ec5bde285',
],
    'words': 'turtle squid',
    'nested': {
    'id': 140,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'snail',
    'horse',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'mouse',
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
    '23',
    '18',
],
    'text_data': '7496eb4d80e445c9a19d7602a8c24566',
    'rand_digit': 7,
    'rand_number': 0.00894,
    'rand_signed_int': -10,
    'rand_datetime': '2001-01-11T10:44:59.423138',
    'text_array': [
    '8888d6e43aef4bf59fa3894e62ad48a9',
    '1826783840704a998801a9bfc7d8f08b',
],
    'words': 'octopus shark',
    'nested': {
    'id': 141,
    'rand_digit': 0,
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
    'hello',
],
    'word': 'snail',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'ladybug',
    'elephant',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'bear',
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
    '19',
    '14',
    '21',
    '27',
],
    'text_data': 'f97ed259a0fb4a30981faf37854add1a',
    'rand_digit': 1,
    'rand_number': 0.37352,
    'rand_signed_int': -5,
    'rand_datetime': '2000-07-10 14:40:18+0000',
    'text_array': [
    '960a00c1afd7479b8eda8551d548284a',
    'b5896735bd504d65b3b94351942d6130',
],
    'words': 'lizard bee',
    'nested': {
    'id': 142,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'deer',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lizard',
    'kangaroo',
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
    'mixed_type': 1,
    'maybe': 'sheep',
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
    '11',
],
    'text_data': '28f1c142ed354b4db9a3fb0292b8a4c3',
    'rand_digit': 9,
    'rand_number': 0.0911,
    'rand_signed_int': -6,
    'rand_datetime': '2000-09-20T07:36:15',
    'text_array': [
    'dc9780929979415db2959b5567506656',
    'ab5b6f892a284f47b3e3a148c0f120df',
],
    'words': 'tiger wolf',
    'nested': {
    'id': 143,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'dragonfly',
    'snake',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': [
    59,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'whale',
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
    '08',
    '14',
],
    'text_data': 'f32a0afd57f646c094a49df84fadc1d9',
    'rand_digit': 4,
    'rand_number': 0.70199,
    'rand_signed_int': -9,
    'rand_datetime': '2000-08-20T00:53:57.614688',
    'text_array': [
    '494f63d2029b497e8ded67956a057524',
    '8eb6df134e7c4fb0a4fba509f0194ee7',
],
    'words': 'ladybug sheep',
    'nested': {
    'id': 144,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'zebra',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'chicken',
    'ape',
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
    'maybe': 'deer',
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
    '24',
    '21',
],
    'text_data': '7ecbbfc357b745b9befffd8e10ae1b97',
    'rand_digit': 2,
    'rand_number': 0.98912,
    'rand_signed_int': -2,
    'rand_datetime': '2000-05-02T20:34:38.842726+1000',
    'text_array': [
    '752747a8b17a438abdde8944f66c62ca',
    'dd79a28bcf704da292704c87377ee5b1',
],
    'words': 'sheep panda',
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
    'word': 'kangaroo',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'deer',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'rabbit',
    'ant',
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
    'maybe': 'butterfly',
    'maybe_null': 'tiger',
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
    '25',
    '04',
    '29',
    '09',
    '25',
],
    'text_data': 'd78f7e249edd4fe1b023c10e5412f162',
    'rand_digit': 9,
    'rand_number': 0.78028,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-26T20:22:36.428675',
    'text_array': [
    '8d9888a5e49e4bc0809891dd3ab7830c',
    '8b77d12e31c3486d8ce81d1fbfa2f1c6',
],
    'words': 'whale fish',
    'nested': {
    'id': 146,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'rhino',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'tiger',
    'mosquito',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bird',
    'maybe_null': 'deer',
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
    '14',
    '12',
    '13',
],
    'text_data': '65f2649e37b5422185a9e3e6528e09da',
    'rand_digit': 0,
    'rand_number': 0.96553,
    'rand_signed_int': -1,
    'rand_datetime': '2000-05-05 02:20:37.793567-1200',
    'text_array': [
    '37bcb060bc87407192bfd188f570adf3',
    'c93094d43c9c4f1cb69804e6a3fe488b',
],
    'words': 'grasshopper scorpion',
    'nested': {
    'id': 147,
    'rand_digit': 3,
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
    'word': 'grasshopper',
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
    'number': 6,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'pig',
    'snail',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'elephant',
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
    '02',
    '24',
    '24',
],
    'text_data': '0f51110e038045fea244d0cc0a1722f0',
    'rand_digit': 2,
    'rand_number': 0.75725,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-02',
    'text_array': [
    '8f9c6707b4214897830152b30babd6f9',
    'ad754bfae6a84894a9deea07be2c7a05',
],
    'words': 'turtle giraffe',
    'nested': {
    'id': 148,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    0,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'zebra',
    'cat',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'hippo',
    'maybe_null': 'fish',
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
    '19',
],
    'text_data': '6882225c841d42af859634c14fd7acae',
    'rand_digit': 6,
    'rand_number': 0.84861,
    'rand_signed_int': 1,
    'rand_datetime': '2000-07-31 00:59:52',
    'text_array': [
    'fd69eef543cb49a18e24d7f7e5551e88',
    '7a31f509dfcc471192113ef82b51cf6e',
],
    'words': 'rhino dog',
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'kangaroo',
    'kangaroo',
],
    'city': {
    'name': 'London',
    'geo': {
    'lat': 51.507351,
    'lon': -0.127758,
},
},
    'rand_tuple': [
    9,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'lion',
    'maybe_null': None,
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
    '30',
    '06',
    '25',
    '28',
],
    'text_data': 'fab3b0722a4a4627bc9b67b5f70d4c8b',
    'rand_digit': 1,
    'rand_number': 0.52153,
    'rand_signed_int': -2,
    'rand_datetime': '2000-02-07T04:31:17.419726',
    'text_array': [
    '39e5f78d74f943bd878cddd4414a8ffa',
    '9c67eb50dcce4524a18982f95d2a2bbf',
],
    'words': 'mouse camel',
    'nested': {
    'id': 150,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bee',
    'wolf',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 'scorpion',
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
    '03',
],
    'text_data': '9566a1ff6ea04f7188dc77654927cc05',
    'rand_digit': 5,
    'rand_number': 0.88209,
    'rand_signed_int': -10,
    'rand_datetime': '2000-02-18T07:25:09.272888',
    'text_array': [
    '151d6e25911a4283b31c776148445004',
    '3ec8de670d6e4bfd837a010b4458ac7d',
],
    'words': 'lion dolphin',
    'nested': {
    'id': 151,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'panda',
    'chicken',
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
    '25',
    '19',
    '05',
    '27',
],
    'text_data': '5e31a52844a34bdd9c463d7443e03b16',
    'rand_digit': 8,
    'rand_number': 0.71405,
    'rand_signed_int': -4,
    'rand_datetime': '2000-02-06T13:28:21.170987-0300',
    'text_array': [
    '4ea8b6f995494551969343a11e7f9ee2',
    'dcf2d3fa063e439fad3572613ab37ea5',
],
    'words': 'camel leopard',
    'nested': {
    'id': 152,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ladybug',
    'whale',
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
    'mixed_type': None,
    'maybe_null': 'ladybug',
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
    '10',
    '05',
    '20',
    '23',
],
    'text_data': '46c3510713c741a38af144e88bf5d975',
    'rand_digit': 9,
    'rand_number': 0.78775,
    'rand_signed_int': 0,
    'rand_datetime': '2000-02-06T08:07:36.322054',
    'text_array': [
    'f158136b38fd4697b77059e433e8c231',
    '652f26731dd7468cb925ade346d7e604',
],
    'words': 'monkey leopard',
    'nested': {
    'id': 153,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'bee',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ladybug',
    'pig',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 3,
    'maybe_null': 'cat',
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
    '24',
    '14',
    '27',
    '29',
],
    'text_data': 'cfe8add8059140dea4a83ba58ca54544',
    'rand_digit': 7,
    'rand_number': 0.23399,
    'rand_signed_int': -1,
    'rand_datetime': '2000-11-08T23:33:20.710728-0100',
    'text_array': [
    '9e9233eb0a294200a8b12f3c6d9f5cc7',
    '4cd2698eab8a43d782e1c6b639550171',
],
    'words': 'frog goat',
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
    'word': 'chicken',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'leopard',
    'goat',
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
    'maybe': 'bee',
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
    '07',
    '22',
],
    'text_data': 'f3be10027c054112bc2c6598fbbefed3',
    'rand_digit': 6,
    'rand_number': 0.17362,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-16',
    'text_array': [
    '07a5583e94ae4a8b8cd91020e8ebafe2',
    '35c14c6d9a4e41b18e9a29528093d8b8',
],
    'words': 'monkey giraffe',
    'nested': {
    'id': 155,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'kangaroo',
    'panda',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cow',
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
    '05',
    '06',
    '06',
],
    'text_data': '92a3abebedcb449a9dbb66908b43da4e',
    'rand_digit': 7,
    'rand_number': 0.21127,
    'rand_signed_int': -5,
    'rand_datetime': '2000-10-01 19:55:36',
    'text_array': [
    '2ca150b133a1424ea23aa23164a67d8d',
    '8a651d9c819943fb9848ef6363a1f147',
],
    'words': 'whale octopus',
    'nested': {
    'id': 156,
    'rand_digit': 7,
    'array': [
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
    'word': 'horse',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'deer',
    'pig',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
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
    '16',
    '28',
    '27',
],
    'text_data': 'c4498d5254af42a1a0e39842d3e4b006',
    'rand_digit': 9,
    'rand_number': 0.58719,
    'rand_signed_int': -3,
    'rand_datetime': '2000-04-10T21:28:53.438188+1200',
    'text_array': [
    '97ba71cb2f8d40acafacfef2b0a30efa',
    'e28758f73f6d4613916367a6bf619f79',
],
    'words': 'deer deer',
    'nested': {
    'id': 157,
    'rand_digit': 5,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dragonfly',
    'fly',
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
    'mixed_type': 'snail',
    'maybe_null': None,
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
    '19',
    '18',
    '23',
    '15',
    '03',
],
    'text_data': 'b58ea4b6ffe7498ba1f1e283e433642c',
    'rand_digit': 7,
    'rand_number': 0.38805,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-01T03:35:09+0400',
    'text_array': [
    '7ff9d58dbcff4989aa77dc3be5f441dc',
    '2bc6daa969794685aa72210fbbd73e75',
],
    'words': 'sloth squid',
    'nested': {
    'id': 158,
    'rand_digit': 7,
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
    'word': 'spider',
    'number': 9,
},
    {
    'nested_empty': None,
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
    'word': 'scorpion',
    'number': 3,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'goat',
    'ladybug',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'snake',
    'maybe_null': 'dolphin',
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
    '03',
],
    'text_data': '3b87207688654dec81afd8294da28058',
    'rand_digit': 1,
    'rand_number': 0.58267,
    'rand_signed_int': -1,
    'rand_datetime': '2000-07-26 16:45:34.331773',
    'text_array': [
    'd2174fb610d241ceb1dc0f9cab3ca4d1',
    'a041ec288e414bda9b0c002b7bd6a886',
],
    'words': 'wolf sheep',
    'nested': {
    'id': 159,
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
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fox',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'cat',
    'duck',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
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
    '03',
    '10',
    '13',
],
    'text_data': '54e0b128a82b4098b70571a38a0af295',
    'rand_digit': 9,
    'rand_number': 0.85265,
    'rand_signed_int': -5,
    'rand_datetime': '2000-04-09T02:21:20',
    'text_array': [
    '71993f020e3742db9d78d01bb4c1ede3',
    'f26f428f6076423cbbac21e679cc9a43',
],
    'words': 'snail ant',
    'nested': {
    'id': 160,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    [
    1,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lizard',
    'elephant',
],
    'city': {
    'name': 'Dubai',
    'geo': {
    'lat': 25.204849,
    'lon': 55.270783,
},
},
    'rand_tuple': [
    69,
],
    'rand_bool': False,
    'mixed_type': 'tiger',
    'maybe': 'koala',
    'maybe_null': 'shark',
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
    '28',
    '26',
    '05',
    '20',
    '19',
],
    'text_data': '5d6b27f8e7514344be3d4c2b5637a5e7',
    'rand_digit': 8,
    'rand_number': 0.82221,
    'rand_signed_int': 2,
    'rand_datetime': '2000-05-18T13:37:51.579708+0100',
    'text_array': [
    'ee4af130214242d18605d26ede84cae9',
    '76a327bf994d4ecabfdce923b38b34d2',
],
    'words': 'hyena sloth',
    'nested': {
    'id': 161,
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
    'number': 5,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,2__',
    'two_words': [
    'lobster',
    'pig',
],
    'city': {
    'name': 'Kuala Lumpur',
    'geo': {
    'lat': 3.139003,
    'lon': 101.686855,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'ant',
    'maybe': 'horse',
    'maybe_null': 'scorpion',
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
    '11',
    '12',
    '21',
    '04',
],
    'text_data': 'ab43fa5d8cf244d8a31936c6632870ec',
    'rand_digit': 3,
    'rand_number': 0.07794,
    'rand_signed_int': -1,
    'rand_datetime': '2000-05-14T12:42:42-0500',
    'text_array': [
    '3d0c82fcab644d07b37baaba34d0c576',
    '4826bcb42350483cb21449aace838f4d',
],
    'words': 'octopus shark',
    'nested': {
    'id': 162,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'ant',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'bird',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    10,
],
],
    'two_words': [
    'fox',
    'dolphin',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'chicken',
    'maybe_null': None,
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
    '03',
    '01',
],
    'text_data': '00a8c5238b1c44b4b37806eba62d643a',
    'rand_digit': 3,
    'rand_number': 0.23475,
    'rand_signed_int': -4,
    'rand_datetime': '2000-06-03T00:00:29.951939-02:00',
    'text_array': [
    'f4020e61553946618d7ae79fba465b2e',
    'e7d11b31bf36454cb70382c9bbc7dcba',
],
    'words': 'spider dog',
    'nested': {
    'id': 163,
    'rand_digit': 7,
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
    'hello',
],
    'word': 'crab',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 4,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'lion',
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
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'giraffe',
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
    'content-length': '122',
}
        
        # 原始请求内容
        original_content = {
    'context': [
    {
    'positive': 11,
    'negative': 19,
},
],
    'limit': 1000,
    'offset': 0,
    'with_payload': True,
    'with_vector': False,
    'using': 'code',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_discovery.test_context_euclidean')
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
    test = TestDiscoverytestContextEuclidean()
    test.run_tests()
