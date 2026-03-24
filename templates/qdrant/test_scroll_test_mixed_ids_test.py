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
logger = logging.getLogger('vdb_fuzzer.test.test_scroll_test_mixed_ids')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_scroll.test_mixed_ids"
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



class TestScrolltestMixedIds:
    """自动生成的VDB模糊测试类 - test_scroll.test_mixed_ids"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_scroll.test_mixed_ids"
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
    'content-length': '137441',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': '2c74d1ac-c529-41e3-b69d-ec74608da792',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 128,
    'id_str': [
    '17',
    '26',
],
    'text_data': 'f5abab51c5294115999ded89a547c704',
    'rand_digit': 5,
    'rand_number': 0.67539,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-24 04:39:21+0300',
    'text_array': [
    '83315979281f4d32b3ad4da052a7091e',
    'caa61a5ace39437e9de9680e778e88e5',
],
    'words': 'zebra bear',
    'nested': {
    'id': 128,
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
    'word': 'frog',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'goat',
    'rhino',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': '1ae633a6-e811-46d8-833f-59cd47ea17d3',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 126,
    'id_str': [
],
    'text_data': '811ef4905808443985f2f6c9cea79616',
    'rand_digit': 6,
    'rand_number': 0.49473,
    'rand_signed_int': -10,
    'rand_datetime': '2000-11-20T20:25:33+1200',
    'text_array': [
    '6f91e8ba296d432f8d87da9e8dd9fef3',
    '82bebd4cf04341bf8ecef0ecde3563ac',
],
    'words': 'koala mouse',
    'nested': {
    'id': 126,
    'rand_digit': 5,
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
],
    'word': 'cat',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 9,
},
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'frog',
    'fish',
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
    'mixed_type': 'spider',
    'maybe': 'rhino',
    'maybe_null': 'hyena',
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
    '02',
],
    'text_data': '45a08dacdde04ec58b46f7c3f6a901b0',
    'rand_digit': 2,
    'rand_number': 0.9273,
    'rand_signed_int': -9,
    'rand_datetime': '2000-03-16T15:11:15-1000',
    'text_array': [
    '3cf78a07f2554af696b033cb99eab6b1',
    'dbd1564b89004902af73415a6a47724c',
],
    'words': 'lion camel',
    'nested': {
    'id': 132,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bear',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'frog',
    'spider',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': [
    44,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'duck',
},
},
    {
    'id': '322a5647-1161-429f-9ee3-bc98b9c348b2',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 197,
    'id_str': [
],
    'text_data': '86153ce2cb1f4f56a509543573888aad',
    'rand_digit': 3,
    'rand_number': 0.91169,
    'rand_signed_int': 3,
    'rand_datetime': '2000-10-08T18:22:15.540897',
    'text_array': [
    '046a249edd5f44acb16a9deab2c3b9c5',
    'f38b5c6f1f004ee9a35173ec6b1d7857',
],
    'words': 'bird rhino',
    'nested': {
    'id': 197,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'gorilla',
    'number': 8,
},
],
},
    'nested_array': [
    [
    -9,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dolphin',
    'camel',
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
    'mixed_type': 3,
},
},
    {
    'id': 'da410869-c3c6-45fc-90dc-cfe816b2a761',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 137,
    'id_str': [
],
    'text_data': 'f63ba3041d3047f5a5e13a843cdc780b',
    'rand_digit': 7,
    'rand_number': 0.64373,
    'rand_signed_int': -5,
    'rand_datetime': '2000-04-03T16:42:34.537218',
    'text_array': [
    '9a6a4f2af2f749f9a16eb9868c4f843e',
    'acd5b1f8c95b4ff8bfe6d2964ed142c7',
],
    'words': 'elephant cat',
    'nested': {
    'id': 137,
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
    'number': 6,
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
],
    'word': 'spider',
    'number': 5,
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
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'hippo',
},
},
    {
    'id': 69,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 169,
    'id_str': [
    '25',
],
    'text_data': 'bce409bb0fb643a6bf432b2ed92bddc8',
    'rand_digit': 3,
    'rand_number': 0.06054,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-19 23:32:25+0600',
    'text_array': [
    'b5d92c4da62c42a6bc101b3666c88d69',
    'b72dcc4ea48d4f3fa6124519534e6e12',
],
    'words': 'cow frog',
    'nested': {
    'id': 169,
    'rand_digit': 7,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 6,
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
    'word': 'whale',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'spider',
    'dragonfly',
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
    'maybe_null': 'gorilla',
},
},
    {
    'id': 89,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 189,
    'id_str': [
    '27',
    '06',
],
    'text_data': '0bdbfa99a7f34dceaca5ba121a4b84cf',
    'rand_digit': 5,
    'rand_number': 0.23358,
    'rand_signed_int': 0,
    'rand_datetime': '2000-01-14 08:41:12',
    'text_array': [
    'e08b20a851734e5cae94b41294e493d4',
    '0be03bd913734b85bf12ececa8c4d00f',
],
    'words': 'leopard crab',
    'nested': {
    'id': 189,
    'rand_digit': 5,
    'array': [
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
    'word': 'turtle',
    'number': 10,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mouse',
    'crab',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.79105,
    'maybe_null': None,
},
},
    {
    'id': 87,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 187,
    'id_str': [
    '24',
    '10',
    '21',
    '05',
    '27',
],
    'text_data': '3709ecd78f1b449a9683ef68ba6d1a16',
    'rand_digit': 3,
    'rand_number': 0.02243,
    'rand_signed_int': -6,
    'rand_datetime': '2000-01-05',
    'text_array': [
    'ad405abd62ce4737a7396582ef0c1179',
    '5eec560625154ceab15c9c85b3228495',
],
    'words': 'cow mouse',
    'nested': {
    'id': 187,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'horse',
    'frog',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': [
    41,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'rhino',
},
},
    {
    'id': 82,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 182,
    'id_str': [
    '26',
    '12',
    '11',
],
    'text_data': 'fc5c8d3b7f4c4454a46336bc5e4fc11c',
    'rand_digit': 0,
    'rand_number': 0.27424,
    'rand_signed_int': 7,
    'rand_datetime': '2000-01-11',
    'text_array': [
    'a214589c1c3b49d9ac88ce984c3bf088',
    'add4f84396874d30aa020572f1924e69',
],
    'words': 'zebra zebra',
    'nested': {
    'id': 182,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'panda',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 5,
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
],
    'two_words': [
    'deer',
    'elephant',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'pig',
    'maybe_null': 'ape',
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
    '03',
],
    'text_data': '2d5fa358be9f42f1b24b3abd5be393e7',
    'rand_digit': 6,
    'rand_number': 0.80563,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-23 15:24',
    'text_array': [
    'cf74eac9555841e58eb5564556bfb81d',
    '57e0ddc4297441f1a10150f4429f092d',
],
    'words': 'zebra fish',
    'nested': {
    'id': 159,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snake',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'leopard',
    'fly',
],
    'city': {
    'name': 'Rome',
    'geo': {
    'lat': 41.902782,
    'lon': 12.496366,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'butterfly',
    'maybe_null': None,
},
},
    {
    'id': 'bfa93ab6-e7d7-451b-a150-17da032fac56',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 160,
    'id_str': [
    '23',
    '26',
    '30',
    '27',
    '28',
],
    'text_data': '84465e2582d341ee956a3becb1208160',
    'rand_digit': 8,
    'rand_number': 0.9922,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-09 13:47',
    'text_array': [
    '3d31694abbab4b69a74d8773452d6a4f',
    'd18d841e5b324f388a983ffd193ee766',
],
    'words': 'squid tiger',
    'nested': {
    'id': 160,
    'rand_digit': 4,
    'array': [
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
    'word': 'zebra',
    'number': 7,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,5__',
    'two_words': [
    'ape',
    'dolphin',
],
    'city': {
    'name': 'Moscow',
    'geo': {
    'lat': 55.755826,
    'lon': 37.6173,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': '500d5bfd-854f-49ca-8d6c-d5f2aa280335',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 168,
    'id_str': [
    '26',
    '19',
],
    'text_data': 'd0d66d44c3a348049ec030d38c1fed8a',
    'rand_digit': 6,
    'rand_number': 0.71203,
    'rand_signed_int': 6,
    'rand_datetime': '2000-10-01 13:04:34.485165-0100',
    'text_array': [
    '2678977c871c48bfbddd720cb1f60f2c',
    '725716ab9aa343d09aa6938365fa70d7',
],
    'words': 'whale chicken',
    'nested': {
    'id': 168,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 3,
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
    'hello',
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
    'word': 'octopus',
    'number': 2,
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
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'tiger',
    'horse',
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
    'mixed_type': True,
    'maybe': 'lobster',
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
],
    'text_data': 'ded18cf0ae1944bfb7dff025de8442d1',
    'rand_digit': 0,
    'rand_number': 0.85637,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-20 19:36:45+0100',
    'text_array': [
    'cc88dc9ba8e04dcea4be92dbfbb8125f',
    'd7eca789cffe4c188635a1294266b52b',
],
    'words': 'tiger chicken',
    'nested': {
    'id': 122,
    'rand_digit': 8,
    'array': [
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'zebra',
    'chicken',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': [
    86,
],
    'rand_bool': False,
    'mixed_type': 3,
},
},
    {
    'id': '8e9b0311-307d-4104-9961-0a2e1aa99f38',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 163,
    'id_str': [
],
    'text_data': '5ca9b35e1dac46da9db808930ffbc7f7',
    'rand_digit': 4,
    'rand_number': 0.92538,
    'rand_signed_int': -10,
    'rand_datetime': '2000-05-31T17:36:27.386796+0000',
    'text_array': [
    '43d786d96a554487be6a7e40d17e5329',
    '4b99b54d7d4d4fc6a38fef2b9e49d38d',
],
    'words': 'mosquito ant',
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
    'word': 'monkey',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fly',
    'number': 9,
},
],
},
    'nested_array': [
    [
    1,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lobster',
    'cow',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'hyena',
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
    '07',
    '24',
    '07',
],
    'text_data': 'ac34e163d4d84e35a131cf80bdeaff1e',
    'rand_digit': 6,
    'rand_number': 0.41682,
    'rand_signed_int': -4,
    'rand_datetime': '2000-05-20T06:39:09.996944-11:00',
    'text_array': [
    '3c239930ab7343d88137fb56f1c0ff29',
    '6a9771d372b24a4290145ef4a2ca361b',
],
    'words': 'butterfly turtle',
    'nested': {
    'id': 140,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'elephant',
    'squid',
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
    'mixed_type': False,
    'maybe': 'jaguar',
    'maybe_null': None,
},
},
    {
    'id': '38f6c6fc-3d91-4336-a5e9-1d7bdcaa646a',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 108,
    'id_str': [
    '10',
],
    'text_data': 'fc646c0047a74e8899b114532579b601',
    'rand_digit': 9,
    'rand_number': 0.67732,
    'rand_signed_int': 8,
    'rand_datetime': '2000-11-12 20:21',
    'text_array': [
    '3314a6183f77435180a57b02627516ba',
    '02d16a5e298c4d04ba9b81dc067a66e9',
],
    'words': 'octopus rabbit',
    'nested': {
    'id': 108,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'fly',
    'jaguar',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': [
    12,
],
    'rand_bool': False,
    'mixed_type': 'leopard',
    'maybe_null': 'whale',
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
],
    'text_data': 'e35ce8eb8c074a2182e3438560e41a2c',
    'rand_digit': 3,
    'rand_number': 0.63212,
    'rand_signed_int': -10,
    'rand_datetime': '2000-07-26 07:59:44.996730-0600',
    'text_array': [
    'a749bc40db1a4728aeed77ca91e85aac',
    'e1dd339cd42147a2b1a789f19838e388',
],
    'words': 'fox leopard',
    'nested': {
    'id': 151,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'panda',
    'dragonfly',
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
    'maybe_null': None,
},
},
    {
    'id': '356aa061-3f97-4a4c-9929-0523d8225b69',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 198,
    'id_str': [
    '03',
    '19',
    '25',
    '27',
],
    'text_data': '79f7aeb7cc604f45992d6434cba7d04c',
    'rand_digit': 4,
    'rand_number': 0.36029,
    'rand_signed_int': -8,
    'rand_datetime': '2000-01-18T13:21:29.893378',
    'text_array': [
    '3a93b92d1e93448b9c059cf9d7620cac',
    '120171a91c6045c9a750f5f2f9e7a59c',
],
    'words': 'snake cheetah',
    'nested': {
    'id': 198,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 3,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'panda',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'scorpion',
    'cheetah',
],
    'city': {
    'name': 'Johannesburg',
    'geo': {
    'lat': -26.204103,
    'lon': 28.047305,
},
},
    'rand_tuple': [
    25,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': '61adedfd-7212-40db-b055-5798f8b08cb9',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 157,
    'id_str': [
],
    'text_data': 'e8e9dd6a54584ec5b75c6203c0c72e9c',
    'rand_digit': 5,
    'rand_number': 0.73922,
    'rand_signed_int': -5,
    'rand_datetime': '2000-12-22T18:23:23',
    'text_array': [
    '04e0f95d1bb94a0699b0ed848645b407',
    '2eaae5daa8964ecca379239bd5ef43a0',
],
    'words': 'fly cow',
    'nested': {
    'id': 157,
    'rand_digit': 1,
    'array': [
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
    'word': 'pig',
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ladybug',
    'wolf',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'panda',
},
},
    {
    'id': 83,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 183,
    'id_str': [
    '07',
    '15',
],
    'text_data': '0a53e06c94ea4b36b415ac683bc1f782',
    'rand_digit': 7,
    'rand_number': 0.59158,
    'rand_signed_int': -7,
    'rand_datetime': '2000-09-16 03:35:03',
    'text_array': [
    '7d5035d432224ace82417880fd25109e',
    '4396ae77b6ea4c0689fd8a0467965699',
],
    'words': 'pig leopard',
    'nested': {
    'id': 183,
    'rand_digit': 1,
    'array': [
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
],
    'word': 'squid',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'horse',
    'camel',
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
    'mixed_type': False,
},
},
    {
    'id': 73,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 173,
    'id_str': [
    '02',
],
    'text_data': 'eac60451f8a1468589b710f609614f2e',
    'rand_digit': 9,
    'rand_number': 0.85522,
    'rand_signed_int': 3,
    'rand_datetime': '2000-09-07 09:00:06.247226+0500',
    'text_array': [
    '982519e7e0cc4c0ab9dcbe889eb66157',
    'e25d2563148a42ed9a1b7d28fd3257c5',
],
    'words': 'leopard deer',
    'nested': {
    'id': 173,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'crab',
    'number': 5,
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
    'word': 'goat',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 9,
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
    'tiger',
    'ape',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'fish',
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
    '21',
],
    'text_data': '5f0f02a5442546cba39dbf6adf1214ce',
    'rand_digit': 3,
    'rand_number': 0.28799,
    'rand_signed_int': 5,
    'rand_datetime': '2000-05-16 08:35',
    'text_array': [
    '10367c6f53fd46a2a3e916efba83bf76',
    '4151d13999b1470eadd33bd6ccea8fe1',
],
    'words': 'cow octopus',
    'nested': {
    'id': 108,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    5,
],
],
    'two_words': [
    'leopard',
    'tiger',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': None,
},
},
    {
    'id': 88,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 188,
    'id_str': [
    '09',
],
    'text_data': 'e93aa014c7f04ffb83fcdd10fc9fb5d6',
    'rand_digit': 6,
    'rand_number': 0.88378,
    'rand_signed_int': -6,
    'rand_datetime': '2000-08-15T10:34:45.771488',
    'text_array': [
    '51170765839642b0864e8c05e60a1279',
    '1d465548bb6f49b684bbfa32090ce321',
],
    'words': 'bird tiger',
    'nested': {
    'id': 188,
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
    'number': 8,
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
],
    'word': 'fox',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'camel',
    'gorilla',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '03',
    '16',
    '24',
    '12',
    '23',
],
    'text_data': '74de55f8281b4ab5b84e1b5e26a8b571',
    'rand_digit': 2,
    'rand_number': 0.22779,
    'rand_signed_int': -7,
    'rand_datetime': '2000-05-22',
    'text_array': [
    'fce8787dabd54ec78b0d07ae2579a437',
    'a54b75bb81ef487bb10809007152ad79',
],
    'words': 'scorpion whale',
    'nested': {
    'id': 110,
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
    'word': 'horse',
    'number': 8,
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
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ladybug',
    'giraffe',
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
    'mixed_type': 0.44918,
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
    '21',
    '20',
],
    'text_data': 'a0b69d74412e4956be5e223e06844fbe',
    'rand_digit': 4,
    'rand_number': 0.78285,
    'rand_signed_int': 7,
    'rand_datetime': '2000-10-23T13:18:35.489723',
    'text_array': [
    'd37203b0231f42778796b0349fa6183b',
    'dcc066cb6a904f29b31be887646ef232',
],
    'words': 'turtle octopus',
    'nested': {
    'id': 144,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'rabbit',
    'number': 2,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'ladybug',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'hyena',
    'maybe_null': None,
},
},
    {
    'id': '07bed3a6-9365-4f15-8989-da899a934792',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 117,
    'id_str': [
    '21',
    '24',
    '21',
],
    'text_data': '75de6b7ed83340619b37ee088e992dc8',
    'rand_digit': 3,
    'rand_number': 0.57624,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-08',
    'text_array': [
    'bb1a1ef5408b4eb7bb1d07f766f21760',
    '354079ade2e94f61b00e0c9f7e7d0ee4',
],
    'words': 'dog chicken',
    'nested': {
    'id': 117,
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
    'hyena',
    'koala',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'hyena',
    'maybe_null': 'fish',
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
    '18',
    '22',
],
    'text_data': 'ba6881c544c94f2f867c816ff4ae8962',
    'rand_digit': 3,
    'rand_number': 0.38712,
    'rand_signed_int': -8,
    'rand_datetime': '2000-06-05',
    'text_array': [
    '52585098cbc6418bbfa850f2ad2e31e2',
    'c736c557cb9140ab96adc178341938c8',
],
    'words': 'ant rhino',
    'nested': {
    'id': 117,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'scorpion',
    'shark',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': [
    36,
],
    'rand_bool': False,
    'mixed_type': 0.86531,
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
    '25',
    '04',
    '11',
    '08',
],
    'text_data': 'deb7eb9c04c6412a9448a61198749a02',
    'rand_digit': 6,
    'rand_number': 0.35416,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-06T05:52:49.728047',
    'text_array': [
    'fdbcf360e35c43a7a7fec6c576adc4d2',
    'ed7b6d39b33747bbb1e524cb4154f3cc',
],
    'words': 'chicken deer',
    'nested': {
    'id': 134,
    'rand_digit': 9,
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
],
},
    'nested_array': [
],
    'two_words': [
    'scorpion',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bee',
    'maybe_null': 'rhino',
},
},
    {
    'id': 80,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 180,
    'id_str': [
],
    'text_data': '79df8b993afd49d397331f74e0b5707d',
    'rand_digit': 3,
    'rand_number': 0.65234,
    'rand_signed_int': -6,
    'rand_datetime': '2000-06-14T07:53:36.921186',
    'text_array': [
    '57fe859bff8444c8805eb5ef24c2344a',
    'c394ce3a78254aaea1fcd8cc06ad1aef',
],
    'words': 'duck spider',
    'nested': {
    'id': 180,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'scorpion',
    'lizard',
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
    'mixed_type': 7,
    'maybe': 'panda',
    'maybe_null': 'zebra',
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
    '11',
],
    'text_data': 'ec042b75c929482b8b5845233c8f2793',
    'rand_digit': 6,
    'rand_number': 0.20233,
    'rand_signed_int': 3,
    'rand_datetime': '2001-01-03T11:00:06',
    'text_array': [
    '43869e8ad2c9458dad18f42f20398350',
    'f67c4471ce4c4abd88aabdacc0781e23',
],
    'words': 'scorpion mosquito',
    'nested': {
    'id': 103,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
    'number': 3,
},
],
},
    'nested_array': [
    [
    -7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    1,
],
    [
    -7,
],
],
    'two_words': [
    'butterfly',
    'bear',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': '7d3bde3e-f051-4b08-8121-7eb9ba06d2b2',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 101,
    'id_str': [
    '25',
    '08',
    '14',
    '24',
],
    'text_data': 'a86938c48bf94fdead5696de7aeb1bbd',
    'rand_digit': 9,
    'rand_number': 0.90599,
    'rand_signed_int': -10,
    'rand_datetime': '2000-11-27T12:54:55.490927',
    'text_array': [
    'b4a0e3a155ab4089a816330a7b423cec',
    '602f509d398946c38934001c1568ba60',
],
    'words': 'koala tiger',
    'nested': {
    'id': 101,
    'rand_digit': 4,
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
    'hello',
],
    'word': 'fox',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ape',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    2,
],
    [
],
],
    'two_words': [
    'fox',
    'leopard',
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
    'maybe': 'fox',
    'maybe_null': 'pig',
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
    '13',
    '26',
    '14',
    '23',
    '29',
],
    'text_data': '6ff0d9f5337642bda9470172b6b072bb',
    'rand_digit': 1,
    'rand_number': 0.71075,
    'rand_signed_int': -8,
    'rand_datetime': '2000-10-24 16:12:56-0900',
    'text_array': [
    'bd948c74d7ff4ef1ab8dc96265c67828',
    'ea60cd255ec64364bfd471e33d9f76a7',
],
    'words': 'ladybug bear',
    'nested': {
    'id': 119,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'goat',
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
    'mixed_type': 1,
    'maybe_null': 'lobster',
},
},
    {
    'id': '1c780d66-f233-49e7-9900-74f5213e1f0c',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 179,
    'id_str': [
    '18',
],
    'text_data': '228c7f1b645648ff9ded0376d107f01c',
    'rand_digit': 5,
    'rand_number': 0.83013,
    'rand_signed_int': 5,
    'rand_datetime': '2000-08-17',
    'text_array': [
    '1a32045398eb45b6bbb7400e09c66bab',
    '298f079d012b483696ca4841527296b3',
],
    'words': 'frog horse',
    'nested': {
    'id': 179,
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
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'rabbit',
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
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    10,
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'giraffe',
    'dragonfly',
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
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': '95efd10e-ebf4-42ab-8e63-a614327e4b44',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 167,
    'id_str': [
],
    'text_data': 'c7f1ccffbd1643bbb086b85a25feb882',
    'rand_digit': 3,
    'rand_number': 0.67832,
    'rand_signed_int': -10,
    'rand_datetime': '2000-10-13T07:04:39.676938+04:00',
    'text_array': [
    'f0a71537dc2d4357bd6090557d3d7343',
    'f4c867d025754688b3b3a0aea0bcf4a1',
],
    'words': 'frog dog',
    'nested': {
    'id': 167,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    [
    8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ape',
    'deer',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'lobster',
    'maybe_null': 'horse',
},
},
    {
    'id': 70,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 170,
    'id_str': [
    '14',
    '12',
    '10',
    '24',
    '07',
],
    'text_data': 'ac9dd4fe7ad845bdb4d017e2d333f3ef',
    'rand_digit': 9,
    'rand_number': 0.26385,
    'rand_signed_int': -5,
    'rand_datetime': '2000-07-31 08:34',
    'text_array': [
    '84e28bb570094cd8b0f76732efb9de16',
    'e6b65bba87b047d78954442f7206591d',
],
    'words': 'snake scorpion',
    'nested': {
    'id': 170,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
    -1,
],
    [
],
],
    'two_words': [
    'scorpion',
    'lobster',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe_null': 'spider',
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
    '29',
    '01',
    '28',
],
    'text_data': '3b6177f2b9d84913b8d7923365b0ed35',
    'rand_digit': 1,
    'rand_number': 0.3574,
    'rand_signed_int': 1,
    'rand_datetime': '2001-01-02T03:41:53+0400',
    'text_array': [
    'cc7b47eebe774cbaa369dd9ea7cb52b7',
    'b1ee9a616c764364af1199b0e2887ed9',
],
    'words': 'crab fly',
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
    'word': 'ladybug',
    'number': 10,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'monkey',
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
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': '5ff4740e-fa57-4529-8d7d-2531e290b515',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 188,
    'id_str': [
    '29',
],
    'text_data': '05aa80fe82b748e2a1260f66c63303b5',
    'rand_digit': 0,
    'rand_number': 0.5124,
    'rand_signed_int': -2,
    'rand_datetime': '2000-03-14 11:28:43.805873+0600',
    'text_array': [
    'd9ab8b9c898c49ba9aedf20ffb3ff31b',
    '2f34175b3122486d94ff335cbebf9c24',
],
    'words': 'koala kangaroo',
    'nested': {
    'id': 188,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 8,
},
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    7,
],
],
    'two_words': [
    'wolf',
    'frog',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.07326,
    'maybe': 'dragonfly',
    'maybe_null': 'koala',
},
},
    {
    'id': 68,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 168,
    'id_str': [
    '14',
    '20',
],
    'text_data': '2fb52b9c4cf2413094ef77f80e0ae0ec',
    'rand_digit': 6,
    'rand_number': 0.59278,
    'rand_signed_int': 8,
    'rand_datetime': '2000-01-20T20:33:23-0800',
    'text_array': [
    '17ead968bc4c45498df25d744e088942',
    '9d4f4e6ab6724134a660c093c5a6df94',
],
    'words': 'grasshopper deer',
    'nested': {
    'id': 168,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
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
    'number': 9,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'giraffe',
    'fly',
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
    'mixed_type': False,
},
},
    {
    'id': '11154663-361b-408b-acf7-01f985650ebb',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 115,
    'id_str': [
    '26',
    '04',
    '04',
],
    'text_data': '09d83e59e0da49fd8f533eb1cdf28529',
    'rand_digit': 4,
    'rand_number': 0.42661,
    'rand_signed_int': -5,
    'rand_datetime': '2000-03-04 09:57:30.804757',
    'text_array': [
    '2dede156ca6a4b8983b08d5a7fdde415',
    '7825749791694839b5e8f9f580186493',
],
    'words': 'dog whale',
    'nested': {
    'id': 115,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
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
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'cat',
    'hippo',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 4,
    'maybe': 'wolf',
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
    '19',
    '26',
    '17',
],
    'text_data': '07137d684f5f48e2af8a89a26c2dbf7f',
    'rand_digit': 2,
    'rand_number': 0.85396,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-11 16:11:27+0800',
    'text_array': [
    '5d083f6b803646b19f0d040d4507859b',
    '9aa878ded4564030a2e99593463274d1',
],
    'words': 'cat fish',
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
    'word': 'pig',
    'number': 10,
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
    'hippo',
    'wolf',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 'fox',
    'maybe_null': None,
},
},
    {
    'id': 79,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 179,
    'id_str': [
    '20',
    '14',
    '12',
    '16',
    '12',
],
    'text_data': '819bc3d99c8a4e1eb32d14fb36820d53',
    'rand_digit': 1,
    'rand_number': 0.3582,
    'rand_signed_int': -3,
    'rand_datetime': '2000-09-26',
    'text_array': [
    'dcc9a848969a4516ad9a444f5434ca0b',
    '9f6d96e8ec934000863e5125e3300088',
],
    'words': 'tiger kangaroo',
    'nested': {
    'id': 179,
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
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'goat',
    'gorilla',
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
    'mixed_type': True,
    'maybe': 'giraffe',
    'maybe_null': 'snail',
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
    '30',
    '29',
    '19',
    '13',
],
    'text_data': 'a34c808d940c4b92b6c7a65204dfb4d3',
    'rand_digit': 7,
    'rand_number': 0.1059,
    'rand_signed_int': -7,
    'rand_datetime': '2001-01-20',
    'text_array': [
    'bbc59cc2a40a4085afd1593e33459222',
    '53a65276429d4f278512fe17bd95d3ee',
],
    'words': 'sloth cat',
    'nested': {
    'id': 104,
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
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'hyena',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'giraffe',
    'panda',
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
    'mixed_type': False,
    'maybe': 'turtle',
    'maybe_null': None,
},
},
    {
    'id': '9a26ebff-12f0-47f3-b375-34bb0fa46725',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 177,
    'id_str': [
    '05',
],
    'text_data': '872546fdb8154e92860edc0f0a832c92',
    'rand_digit': 2,
    'rand_number': 0.7733,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-14 11:25:48.282849',
    'text_array': [
    'af1c4be9e7e440c2997cdbc1ed2bb26a',
    '98a88e0599d9456899897a10762a1cea',
],
    'words': 'butterfly chicken',
    'nested': {
    'id': 177,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
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
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bear',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 3,
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
    'fly',
    'koala',
],
    'city': {
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': [
    12,
],
    'rand_bool': False,
    'mixed_type': 0.82815,
},
},
    {
    'id': '47e476c1-979d-4598-805c-bb8cb1c84f1d',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 110,
    'id_str': [
    '27',
    '09',
    '29',
    '24',
],
    'text_data': '29e31d081912425dbc8f0eb418a1f357',
    'rand_digit': 4,
    'rand_number': 0.0566,
    'rand_signed_int': 8,
    'rand_datetime': '2000-06-08 16:03:31.707162-0800',
    'text_array': [
    '27524d1c7f114e028e4a62c6d5b36ec8',
    '7e31da79e6eb4a85bbe995890081ebaf',
],
    'words': 'lion tiger',
    'nested': {
    'id': 110,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'shark',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'sheep',
    'lizard',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 96,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 196,
    'id_str': [
    '18',
    '13',
    '19',
    '24',
    '26',
],
    'text_data': '7ce6074b915b4d48a7bbf6632da3b44d',
    'rand_digit': 3,
    'rand_number': 0.45404,
    'rand_signed_int': -4,
    'rand_datetime': '2000-05-29T09:20:50.181900',
    'text_array': [
    'd5d1479ca5314482a2a40ddf7e464f8e',
    'c349daa947544444a5b7793832c771e8',
],
    'words': 'mosquito cheetah',
    'nested': {
    'id': 196,
    'rand_digit': 8,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 1,
},
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
],
    'two_words': [
    'camel',
    'tiger',
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
    'mixed_type': True,
},
},
    {
    'id': '2141c76b-4d61-412e-8f83-52136343d8a7',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 114,
    'id_str': [
    '14',
    '25',
],
    'text_data': '4ac6ade32e2b4709bf045c92ab326c3e',
    'rand_digit': 1,
    'rand_number': 0.99176,
    'rand_signed_int': 10,
    'rand_datetime': '2000-11-09 10:00',
    'text_array': [
    '60b4bff8a58642798fe96ddcc9faee9e',
    'cbbbcc8a16ce40f7b6a12a985c2e95f1',
],
    'words': 'spider pig',
    'nested': {
    'id': 114,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 2,
},
    {
    'nested_empty': None,
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
    'word': 'jaguar',
    'number': 8,
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
    [
    10,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'horse',
    'mosquito',
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
    'mixed_type': 7,
},
},
    {
    'id': 'b96778f8-5ba2-4b96-a39d-9514f3c220ff',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 121,
    'id_str': [
    '10',
    '24',
    '13',
    '11',
    '14',
],
    'text_data': 'f63b4414fef44645995ddef6b969ddda',
    'rand_digit': 9,
    'rand_number': 0.58002,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-06T17:17:50.937496',
    'text_array': [
    'c4b09081302e4a888ea15fc77dd04aa0',
    'e0ab03d9e3424fc3974f579c74a32514',
],
    'words': 'ant turtle',
    'nested': {
    'id': 121,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 2,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    9,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -3,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'frog',
    'snail',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'bee',
    'maybe_null': None,
},
},
    {
    'id': 'b59a3a37-b7c0-4713-a8bc-62c574c03df2',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 195,
    'id_str': [
    '01',
],
    'text_data': 'a0cec6b860bb4adeb26a2a87a1c19062',
    'rand_digit': 5,
    'rand_number': 0.19043,
    'rand_signed_int': -8,
    'rand_datetime': '2000-05-19T02:19:26+0100',
    'text_array': [
    '04ef9a8ab5504bc79f2c5b2008ee4109',
    '2085387964ab47d1beb54f547aacc5f2',
],
    'words': 'sloth deer',
    'nested': {
    'id': 195,
    'rand_digit': 7,
    'array': [
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
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'dragonfly',
    'hyena',
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
    'mixed_type': 5,
    'maybe': 'fox',
    'maybe_null': 'fish',
},
},
    {
    'id': 90,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 190,
    'id_str': [
    '02',
    '20',
    '11',
],
    'text_data': '7b79000e288841d4982d02ee7a550cda',
    'rand_digit': 7,
    'rand_number': 0.65455,
    'rand_signed_int': -8,
    'rand_datetime': '2000-09-28T20:41:18-0300',
    'text_array': [
    'fcdb143820104b1283cc534ed5243b89',
    'bb883a069eb04402a3111d8b2f7b0a87',
],
    'words': 'snake gorilla',
    'nested': {
    'id': 190,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'cat',
    'scorpion',
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
    'mixed_type': 0.5438,
    'maybe': 'ant',
},
},
    {
    'id': '1b7eef40-bae5-47bd-adbf-f50ecfdf3545',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 172,
    'id_str': [
    '21',
    '13',
    '24',
    '02',
],
    'text_data': 'bf1b3025b3974cf59c1fef703a80e1bc',
    'rand_digit': 0,
    'rand_number': 0.219,
    'rand_signed_int': 2,
    'rand_datetime': '2000-10-15 04:51:26.069708+0200',
    'text_array': [
    '0f6ed3e783814e9db7ac0931aa71fbe7',
    '72b347fa7e1b4f638ab7c6519f64639d',
],
    'words': 'gorilla mouse',
    'nested': {
    'id': 172,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'scorpion',
    'koala',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 0,
    'maybe': 'fish',
    'maybe_null': None,
},
},
    {
    'id': '2386d609-d23d-4893-8dac-f740ac28bf54',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 193,
    'id_str': [
    '14',
],
    'text_data': '7f87bf58241745c2a513ed8c8c1006ed',
    'rand_digit': 9,
    'rand_number': 0.38963,
    'rand_signed_int': 9,
    'rand_datetime': '2000-06-26T12:00:14.000245',
    'text_array': [
    '472bab61c19d4e4cbc5acf9309c456a2',
    '35a9ce9113634b64b5f769aaf5438f01',
],
    'words': 'rhino whale',
    'nested': {
    'id': 193,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'lobster',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'fox',
    'squid',
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
    'maybe': 'cow',
    'maybe_null': 'dolphin',
},
},
    {
    'id': '78f817cf-43a6-4c48-9efc-c37dadaaf67d',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 154,
    'id_str': [
    '17',
    '06',
    '06',
],
    'text_data': 'dab9eaf749da493f8ecda2f9c0cc836a',
    'rand_digit': 3,
    'rand_number': 0.48545,
    'rand_signed_int': 6,
    'rand_datetime': '2001-01-10T17:24:05.476473',
    'text_array': [
    '471338f5333c4caab4c797d0008d6837',
    '376a97f59a48463ca1975907c37412f3',
],
    'words': 'fox zebra',
    'nested': {
    'id': 154,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
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
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fly',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'snail',
    'hippo',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': [
    15,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'elephant',
},
},
    {
    'id': 75,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 175,
    'id_str': [
    '18',
    '27',
    '29',
],
    'text_data': '78445bd8727a4c71998d90ffb88d667c',
    'rand_digit': 2,
    'rand_number': 0.29484,
    'rand_signed_int': 8,
    'rand_datetime': '2000-07-12T03:24:49.648075+01:00',
    'text_array': [
    'e6b61e0a36d64d77b64288b9dda5f018',
    'c4afb46c3daf47e88662003dc60eb0f5',
],
    'words': 'deer crab',
    'nested': {
    'id': 175,
    'rand_digit': 1,
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
    'whale',
    'goat',
],
    'city': {
    'name': 'Barcelona',
    'geo': {
    'lat': 41.385064,
    'lon': 2.173403,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'lobster',
},
},
    {
    'id': 81,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 181,
    'id_str': [
    '07',
],
    'text_data': '5612b41d72f0432883e4b0ecf5af0180',
    'rand_digit': 8,
    'rand_number': 0.41325,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-24T18:26:24.329412+11:00',
    'text_array': [
    'c7ddad1d0dc34b4a8d6e3e6c729f2f66',
    '6eac6ea1be6141879f2a526566d352c9',
],
    'words': 'fly giraffe',
    'nested': {
    'id': 181,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'bee',
    'wolf',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 6,
    'maybe': 'sloth',
},
},
    {
    'id': '77d016b6-5f0f-47ab-9c44-0b1dd1577197',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 149,
    'id_str': [
    '15',
    '24',
],
    'text_data': '8187c873243e477ca6fdc5127cb8d918',
    'rand_digit': 2,
    'rand_number': 0.06675,
    'rand_signed_int': 0,
    'rand_datetime': '2000-06-22T04:39:05.907960',
    'text_array': [
    '1b8028b1c2714a2d814cd9f22141fff3',
    '8f67aeb558d0482195dc481f42edb62d',
],
    'words': 'hyena pig',
    'nested': {
    'id': 149,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'snake',
    'leopard',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '10',
],
    'text_data': '7a14622dbc3246d196d58f37d3689944',
    'rand_digit': 2,
    'rand_number': 0.15811,
    'rand_signed_int': 8,
    'rand_datetime': '2000-12-10 04:36:21.121854-0600',
    'text_array': [
    '9f4c64b9013542dcafdbe584a6608b3b',
    '6a0913392ab244ce940a0c6e3b35f642',
],
    'words': 'ladybug hyena',
    'nested': {
    'id': 156,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    [
    1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'squid',
    'kangaroo',
],
    'city': {
    'name': 'Zurich',
    'geo': {
    'lat': 47.376887,
    'lon': 8.541694,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 7,
    'maybe_null': 'ant',
},
},
    {
    'id': 'f8e7dd3c-4a81-4497-b841-b3befb5f4f9d',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 181,
    'id_str': [
    '22',
    '07',
    '01',
    '12',
    '20',
],
    'text_data': '2f88cf109d3c447084c878c9ef55e27f',
    'rand_digit': 1,
    'rand_number': 0.70959,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-21',
    'text_array': [
    'f52457a749ff4bed8affe44be64f4b65',
    '44653f568cf64997be19f0d166d09c9a',
],
    'words': 'grasshopper fox',
    'nested': {
    'id': 181,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ladybug',
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
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'spider',
    'number': 8,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,5__',
    'two_words': [
    'bear',
    'chicken',
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
    'mixed_type': True,
},
},
    {
    'id': 'c30b906b-ed42-4c16-a0be-7f6413068fa4',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 139,
    'id_str': [
    '24',
    '01',
    '25',
],
    'text_data': '8a9e85a1942b4e8f8eeed3e411a6f920',
    'rand_digit': 0,
    'rand_number': 0.76909,
    'rand_signed_int': -1,
    'rand_datetime': '2000-04-13T15:17:00-1200',
    'text_array': [
    'f98fa6d3952840c9ad6c805fda014cd4',
    '160cf48460b74d5e97f4be160013356b',
],
    'words': 'lizard camel',
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
    'word': 'crab',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'jaguar',
    'koala',
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
    'mixed_type': 0.43174,
    'maybe_null': 'frog',
},
},
    {
    'id': 'aeadddb0-1b2f-4c98-adf9-47a454ed3dc5',
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 174,
    'id_str': [
    '07',
    '06',
    '08',
    '01',
    '06',
],
    'text_data': '858fe94a187b4112b469665b0ee922ca',
    'rand_digit': 0,
    'rand_number': 0.81805,
    'rand_signed_int': 1,
    'rand_datetime': '2000-02-10T00:25:02.563829',
    'text_array': [
    '1b9b4f6bf54d43758da1d8f22a1dff87',
    'f52705cbe7b9497f8c189f8e9c3919b4',
],
    'words': 'lizard squid',
    'nested': {
    'id': 174,
    'rand_digit': 9,
    'array': [
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
    'word': 'ape',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'cat',
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
    99,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': None,
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
    '06',
],
    'text_data': 'c3da836138784be7b70a9bf1963f2e75',
    'rand_digit': 0,
    'rand_number': 0.39688,
    'rand_signed_int': -1,
    'rand_datetime': '2000-09-28T13:21:40',
    'text_array': [
    '2175fbac5b6a4133bd75ad0b93f6b2c3',
    '502b4916c9884de2964fa380a513e343',
],
    'words': 'goat zebra',
    'nested': {
    'id': 136,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    0,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'butterfly',
    'rabbit',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'chicken',
    'maybe_null': None,
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
    '06',
    '03',
    '24',
    '05',
],
    'text_data': 'b0e975c094ba4a26a8a2aeb05660e007',
    'rand_digit': 9,
    'rand_number': 0.50492,
    'rand_signed_int': -6,
    'rand_datetime': '2000-04-06T12:48:39.735841+09:00',
    'text_array': [
    '01332ea5645949b9af85824751b419f9',
    '9c74c513b33e46cd931c0d608b53bf7f',
],
    'words': 'lion dolphin',
    'nested': {
    'id': 155,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'snake',
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
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    10,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'kangaroo',
    'cat',
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
    'maybe_null': 'kangaroo',
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
    '18',
    '22',
    '26',
],
    'text_data': '6db2ba58757d4573887c4a36b464702c',
    'rand_digit': 8,
    'rand_number': 0.24125,
    'rand_signed_int': -5,
    'rand_datetime': '2000-01-29 16:04:01',
    'text_array': [
    'e08ab4578cd24aa4937efab22a3e7dfe',
    '07a8d774911843af922780b552aaf4e7',
],
    'words': 'koala crab',
    'nested': {
    'id': 118,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'sloth',
    'hippo',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': [
    57,
],
    'rand_bool': False,
    'mixed_type': 0.83079,
    'maybe': 'monkey',
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
    '28',
    '29',
],
    'text_data': '340235cc8a5349d3a7ace46e5639bcf7',
    'rand_digit': 0,
    'rand_number': 0.82068,
    'rand_signed_int': 1,
    'rand_datetime': '2000-03-28T08:51:42.494868',
    'text_array': [
    '5e8ed06df2a44f70a037ed15e2890f1a',
    '3e13210c890a4d1db44e2ea78f179978',
],
    'words': 'koala dog',
    'nested': {
    'id': 158,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'squid',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'chicken',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    0,
],
    [
    3,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'squid',
    'lizard',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'sheep',
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
    '05',
],
    'text_data': '3252331a11384011969b8390f5871987',
    'rand_digit': 9,
    'rand_number': 0.1413,
    'rand_signed_int': -1,
    'rand_datetime': '2001-01-25 16:34:51',
    'text_array': [
    '823d94c5a3fd4fd7b7f12e11748fcca4',
    '3de7b8f3487148dd9e1a57b8ac00ab09',
],
    'words': 'koala lobster',
    'nested': {
    'id': 148,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    [
    0,
],
    [
    -2,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'horse',
    'leopard',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': [
    61,
],
    'rand_bool': True,
    'mixed_type': 0.09269,
    'maybe_null': 'snail',
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
        """测试请求 2 - POST http://localhost:6333/collections/congruence_test_collection/points/scroll"""
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
    'content-length': '64',
}
        
        # 原始请求内容
        original_content = {
    'offset': 10,
    'limit': 20,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_scroll.test_mixed_ids')
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
    test = TestScrolltestMixedIds()
    test.run_tests()
