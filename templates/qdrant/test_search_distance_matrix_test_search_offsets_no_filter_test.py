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
logger = logging.getLogger('vdb_fuzzer.test.test_search_distance_matrix_test_search_offsets_no_filter')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_search_distance_matrix.test_search_offsets_no_filter"
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



class TestSearchDistanceMatrixtestSearchOffsetsNoFilter:
    """自动生成的VDB模糊测试类 - test_search_distance_matrix.test_search_offsets_no_filter"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_search_distance_matrix.test_search_offsets_no_filter"
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
    'content-length': '136876',
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
    '23',
    '09',
    '19',
    '23',
],
    'text_data': '57ab8c8c411e458795d1671adfa54b9b',
    'rand_digit': 2,
    'rand_number': 0.71746,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-23 14:03',
    'text_array': [
    '3fe222c5f816408895910b44d5547283',
    '3f01cfe964d74e1b81b1ff31bfcc5683',
],
    'words': 'spider cheetah',
    'nested': {
    'id': 100,
    'rand_digit': 0,
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
    'hello',
],
    'word': 'snake',
    'number': 10,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'cat',
    'number': 6,
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
    'lion',
    'camel',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': [
    69,
],
    'rand_bool': False,
    'mixed_type': 0.73262,
    'maybe_null': 'panda',
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
    '30',
],
    'text_data': '8d56b10a13a54f5c8771acb19d0b5b9b',
    'rand_digit': 2,
    'rand_number': 0.00963,
    'rand_signed_int': 3,
    'rand_datetime': '2000-04-25 18:13',
    'text_array': [
    'c5721345b98d426590bce075ba7851dd',
    '0624118d7563442f99f33fcc5a3ccb65',
],
    'words': 'bee rhino',
    'nested': {
    'id': 101,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'monkey',
    'whale',
],
    'city': {
    'name': 'Rome',
    'geo': {
    'lat': 41.902782,
    'lon': 12.496366,
},
},
    'rand_tuple': [
    73,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'fly',
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
    '19',
    '13',
    '19',
],
    'text_data': '0f509bfd7467407ba4705e15ded81ec2',
    'rand_digit': 9,
    'rand_number': 0.12396,
    'rand_signed_int': 6,
    'rand_datetime': '2001-01-24',
    'text_array': [
    '3a9c0eb6e3f64a85b23808588903b2ac',
    '3e6ceaafc72c4c41a7d3eb384c601368',
],
    'words': 'wolf elephant',
    'nested': {
    'id': 102,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'hyena',
    'gorilla',
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
    'mixed_type': None,
    'maybe_null': 'lobster',
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
    'text_data': '00ce71007ffc4edb915155e3eb8e238f',
    'rand_digit': 4,
    'rand_number': 0.8023,
    'rand_signed_int': 0,
    'rand_datetime': '2001-01-01T17:50:26+0300',
    'text_array': [
    'a5bc0ff2256044518e07f7b69f4370a2',
    'efdc12eda93141bd8baad24eb91e5006',
],
    'words': 'monkey panda',
    'nested': {
    'id': 103,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'pig',
    'pig',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': [
    56,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'gorilla',
    'maybe_null': 'deer',
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
    '09',
    '29',
],
    'text_data': '3a64f5a99fac4545822a5b7d09eaeba7',
    'rand_digit': 4,
    'rand_number': 0.13623,
    'rand_signed_int': 7,
    'rand_datetime': '2000-07-28T10:02:16.155097',
    'text_array': [
    '04232aabda01494980671d03311c5cd2',
    '7b00a002f12a4c75a3ac08ec248e82ef',
],
    'words': 'butterfly lizard',
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
    'word': 'bear',
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
    'word': 'grasshopper',
    'number': 9,
},
],
},
    'nested_array': [
    [
    -1,
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dragonfly',
    'crab',
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
    'mixed_type': 0,
    'maybe_null': 'lobster',
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
    '25',
    '29',
    '15',
    '23',
],
    'text_data': 'a859c6a3ea1948e98266fcc482c7c938',
    'rand_digit': 9,
    'rand_number': 0.1886,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-28 23:10:29',
    'text_array': [
    '2ff869caa5554986b00480443f4b833f',
    '75403b0bf1a44ff9b0c9d4609a3cfa6e',
],
    'words': 'duck bee',
    'nested': {
    'id': 105,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'tiger',
    'lion',
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
    'mixed_type': 'monkey',
    'maybe_null': 'ladybug',
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
    '18',
    '17',
    '18',
],
    'text_data': '3753e539afef41a4a1c61c7e58c812b3',
    'rand_digit': 0,
    'rand_number': 0.8476,
    'rand_signed_int': -3,
    'rand_datetime': '2000-05-19T11:17:53',
    'text_array': [
    'eb4dbcaaf06848949fafad2af4a7b99f',
    'd2d36b67c68247c88103e4c7d69a896c',
],
    'words': 'snake frog',
    'nested': {
    'id': 106,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
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
    'word': 'koala',
    'number': 9,
},
    {
    'nested_empty': None,
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
    8,
],
],
    'two_words': [
    'cow',
    'kangaroo',
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
    'mixed_type': True,
    'maybe': 'fox',
    'maybe_null': 'cat',
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
    '23',
    '28',
],
    'text_data': '686d1967890947e8a6918208218365b3',
    'rand_digit': 8,
    'rand_number': 0.03184,
    'rand_signed_int': -2,
    'rand_datetime': '2000-09-14',
    'text_array': [
    'f1810e27bd5e4b33b7804b65a0800646',
    '3367b14bbc524c3dae68675e3a9b596f',
],
    'words': 'ant leopard',
    'nested': {
    'id': 107,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
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
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 9,
},
    {
    'nested_empty': None,
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
    'word': 'chicken',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'snake',
    'leopard',
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
    'maybe': 'gorilla',
    'maybe_null': 'butterfly',
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
    '17',
    '23',
],
    'text_data': '7601cbb963694f2ba9beefd068581684',
    'rand_digit': 6,
    'rand_number': 0.63243,
    'rand_signed_int': -2,
    'rand_datetime': '2000-08-27T16:07:59.633963',
    'text_array': [
    'b93b8ce231db4b1d8c74b4a34f894bc3',
    '185bf8b2062741ff9c49db702e92629a',
],
    'words': 'hippo deer',
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
    'word': 'turtle',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 2,
},
    {
    'nested_empty': None,
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
    'word': 'lion',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'rabbit',
    'fox',
],
    'city': {
    'name': 'Cardiff',
    'geo': {
    'lat': 51.481581,
    'lon': -3.17909,
},
},
    'rand_tuple': [
    3,
],
    'rand_bool': True,
    'mixed_type': None,
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
    '28',
    '10',
    '10',
    '21',
    '22',
],
    'text_data': '45494080660241909f110a9592637926',
    'rand_digit': 8,
    'rand_number': 0.70877,
    'rand_signed_int': 10,
    'rand_datetime': '2000-10-22T07:28:44.561738+10:00',
    'text_array': [
    '72a5ada8986446f0b0f33194503582c2',
    'a53e78ac4a1e4ffd83749564dc73db0f',
],
    'words': 'fox dog',
    'nested': {
    'id': 109,
    'rand_digit': 6,
    'array': [
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
],
    'two_words': [
    'monkey',
    'dog',
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
    'mixed_type': True,
    'maybe': 'ant',
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
    '02',
],
    'text_data': 'f120972eae2e4af09394f8641a6e6442',
    'rand_digit': 8,
    'rand_number': 0.6227,
    'rand_signed_int': -1,
    'rand_datetime': '2000-10-06 14:30:32.254895-1100',
    'text_array': [
    '58b53ceed6544353a9433c6b1980c98b',
    '7946575de0d641999bb32efd49495654',
],
    'words': 'fly camel',
    'nested': {
    'id': 110,
    'rand_digit': 7,
    'array': [
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
    9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'cheetah',
    'hyena',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'sloth',
    'maybe': 'mosquito',
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
    '19',
    '23',
    '28',
],
    'text_data': 'ad0a8d82fab9490da682cc2866f0a917',
    'rand_digit': 1,
    'rand_number': 0.0014,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-12T16:22:12.145308',
    'text_array': [
    'ac0da136636442b2b2a4b03b12555432',
    'c687cc2523354398a6c78cd1c309ca99',
],
    'words': 'spider frog',
    'nested': {
    'id': 111,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
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
    'rhino',
    'bee',
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
    'maybe': 'sloth',
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
    '25',
    '13',
    '14',
    '01',
],
    'text_data': '7ceae28e6b87406d80504a5bed624a8e',
    'rand_digit': 0,
    'rand_number': 0.7563,
    'rand_signed_int': 7,
    'rand_datetime': '2000-05-10 21:56',
    'text_array': [
    '13f3a3e73da2402eaa91022e03a244af',
    'dbc3a5b4081b4dbcb56de61fff0e6784',
],
    'words': 'frog hyena',
    'nested': {
    'id': 112,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'spider',
    'squid',
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
    'maybe': 'panda',
    'maybe_null': 'rabbit',
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
    '03',
    '12',
],
    'text_data': 'e27189cdbb3d4b828587d87003622176',
    'rand_digit': 0,
    'rand_number': 0.22699,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-30 09:09:34+0900',
    'text_array': [
    'b01b576533554610a67f13e07e864c45',
    'cc3e9585e0c043d0be1a09eb48f23c97',
],
    'words': 'squid whale',
    'nested': {
    'id': 113,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    [
],
    [
    5,
],
],
    'two_words': [
    'cow',
    'wolf',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': [
    72,
],
    'rand_bool': False,
    'mixed_type': 'dragonfly',
    'maybe': 'leopard',
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
    '09',
],
    'text_data': 'b3472573dd2f43fbbf469d976125690c',
    'rand_digit': 9,
    'rand_number': 0.35135,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-27 13:49:52.313780-0500',
    'text_array': [
    '1e53869f115c46ae80e877da1dea6c64',
    '68f2528732b241089bd53d403c93f47f',
],
    'words': 'dolphin elephant',
    'nested': {
    'id': 114,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
    10,
],
    [
    -8,
],
    [
],
],
    'two_words': [
    'deer',
    'gorilla',
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
    'mixed_type': 'elephant',
    'maybe_null': 'tiger',
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
    '16',
    '22',
    '05',
],
    'text_data': '7f43ec70f9f349ebbaaa9b1ffdeb667e',
    'rand_digit': 5,
    'rand_number': 0.92028,
    'rand_signed_int': -2,
    'rand_datetime': '2000-04-23 07:19',
    'text_array': [
    'ec5efaa719bd4308a129844ab14bd760',
    'a2909423e2784f59af065a28ee35d6ed',
],
    'words': 'elephant wolf',
    'nested': {
    'id': 115,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 9,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 10,
},
],
},
    'nested_array': [
    [
    8,
],
    [
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'giraffe',
    'dragonfly',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'camel',
    'maybe_null': 'cheetah',
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
    '24',
],
    'text_data': 'c3edb6c954e844108a4f3a99cda9c08e',
    'rand_digit': 7,
    'rand_number': 0.94175,
    'rand_signed_int': -8,
    'rand_datetime': '2000-08-07 23:10:15.925059+0500',
    'text_array': [
    'e6e25cf17b30435f95b944f29401c179',
    'af6c20bed06f489abc65a945962544ca',
],
    'words': 'rabbit gorilla',
    'nested': {
    'id': 116,
    'rand_digit': 4,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'goat',
    'goat',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'horse',
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
    '04',
],
    'text_data': 'cfbbbc0ccfde41f78744b5a53891b70f',
    'rand_digit': 8,
    'rand_number': 0.26989,
    'rand_signed_int': 9,
    'rand_datetime': '2000-03-31T01:12:48+1100',
    'text_array': [
    '9092e5666fbf405ab77e8f839b96ad1b',
    '4eae6f65219f4a108ee39dcb6e9734ef',
],
    'words': 'shark mouse',
    'nested': {
    'id': 117,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'hippo',
    'snake',
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
    'mixed_type': False,
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
    '02',
    '12',
    '06',
],
    'text_data': '09622ff45f974877a96cec60ac2f7411',
    'rand_digit': 3,
    'rand_number': 0.93211,
    'rand_signed_int': -2,
    'rand_datetime': '2000-03-19T09:14:35-0900',
    'text_array': [
    'db370a3f99ff4b90b7dc58d3e48a9e3c',
    'ca76ebd16e5f45d9a473f06d22b6e1f8',
],
    'words': 'dolphin dragonfly',
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
    'word': 'rhino',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 9,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bear',
    'hyena',
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
    '09',
    '03',
    '25',
    '03',
],
    'text_data': '9127ec4eec47460494cbf1100a8c314e',
    'rand_digit': 6,
    'rand_number': 0.69787,
    'rand_signed_int': -8,
    'rand_datetime': '2000-03-28T02:30:05.900168',
    'text_array': [
    '0caa5c28d13e48d5a41b0b883d769ebb',
    'cdb77f6c1ca64dbb9d01d00310c3ca41',
],
    'words': 'fly scorpion',
    'nested': {
    'id': 119,
    'rand_digit': 1,
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
    'hello',
],
    'word': 'dog',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'rhino',
    'spider',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'dog',
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
    '16',
],
    'text_data': '2a64e492e6364fbe9f7e880741bf57e4',
    'rand_digit': 9,
    'rand_number': 0.64446,
    'rand_signed_int': 5,
    'rand_datetime': '2000-03-21',
    'text_array': [
    '1fd55487fe6d46238b36175f8b8e69a4',
    '6c2c4df15440436ba561a0b7ae6a9de5',
],
    'words': 'elephant crab',
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
    'word': 'mouse',
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
    'hello',
],
    'word': 'horse',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'jaguar',
    'rhino',
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
    'mixed_type': 0.44445,
    'maybe_null': 'cow',
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
    '21',
],
    'text_data': '2668299e6c8140119aaef961ce3560a9',
    'rand_digit': 5,
    'rand_number': 0.81325,
    'rand_signed_int': -9,
    'rand_datetime': '2000-04-25',
    'text_array': [
    '320f81e8d840496cbfc5b38b783d2269',
    '59f6d6b2e73445f3834cc6134c042da9',
],
    'words': 'rhino hippo',
    'nested': {
    'id': 121,
    'rand_digit': 4,
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
    'word': 'fly',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'snail',
    'fish',
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
    'mixed_type': 'lion',
    'maybe': 'monkey',
    'maybe_null': 'lizard',
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
    'text_data': '2805e26d641749ed95cd91f1f071ddd9',
    'rand_digit': 7,
    'rand_number': 0.28762,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-16T16:10:54.002295',
    'text_array': [
    '36477e2433b848d8a8e49f15764485fe',
    '3b5e2b057c1f42d4804bd881c5aadc79',
],
    'words': 'lizard bear',
    'nested': {
    'id': 122,
    'rand_digit': 6,
    'array': [
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
    'number': 7,
},
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ant',
    'hyena',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': [
    21,
],
    'rand_bool': True,
    'mixed_type': 0.20397,
    'maybe_null': 'ant',
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
    '10',
    '04',
    '15',
    '27',
    '08',
],
    'text_data': '2a0b675472ec46d8822ba0319056123d',
    'rand_digit': 5,
    'rand_number': 0.74371,
    'rand_signed_int': 8,
    'rand_datetime': '2000-05-06T11:36:54.096751',
    'text_array': [
    '9b39bdf6c3134729b3098553c7f181df',
    '9032d0bf794642119ddade238b1ce1a6',
],
    'words': 'hippo fly',
    'nested': {
    'id': 123,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
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
],
},
    'nested_array': [
],
    'two_words': [
    'mosquito',
    'lizard',
],
    'city': {
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': [
    18,
],
    'rand_bool': False,
    'mixed_type': True,
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
    '01',
    '04',
],
    'text_data': 'd153462c86a5441b9d6e478516793591',
    'rand_digit': 1,
    'rand_number': 0.61137,
    'rand_signed_int': -2,
    'rand_datetime': '2000-03-17',
    'text_array': [
    '58d46aca538a4b2d8a4b36613e15ed59',
    '66e1001653a5468b8f398a122159b004',
],
    'words': 'frog crab',
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
    'word': 'panda',
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 1,
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
    'giraffe',
    'lion',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'whale',
    'maybe_null': 'ape',
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
],
    'text_data': '4e859d0bb1e94e1a9bfdf5f61c05e731',
    'rand_digit': 0,
    'rand_number': 0.34809,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-29T20:15:07.767584',
    'text_array': [
    '96c29446770d4f5eb33fe39056082a75',
    'af11a2f9aff84419897905f8b285df1a',
],
    'words': 'goat scorpion',
    'nested': {
    'id': 125,
    'rand_digit': 1,
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
    'word': 'fly',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -5,
],
],
    'two_words': [
    'monkey',
    'fish',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'ant',
    'maybe_null': 'panda',
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
    '23',
    '07',
    '14',
],
    'text_data': 'f5da1ea7a041496bb769cfbaf081a673',
    'rand_digit': 0,
    'rand_number': 0.77242,
    'rand_signed_int': -4,
    'rand_datetime': '2000-08-03T20:38:47',
    'text_array': [
    'aaa36310b31c4037999408d1bead10e8',
    '00a63ea08b1548c79acb9377c45f520d',
],
    'words': 'squid goat',
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
    'word': 'fox',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ant',
    'number': 2,
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
],
    'word': 'elephant',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lobster',
    'grasshopper',
],
    'city': {
    'name': 'Riga',
    'geo': {
    'lat': 56.949649,
    'lon': 24.105186,
},
},
    'rand_tuple': [
    63,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'butterfly',
    'maybe_null': 'cat',
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
    'text_data': 'c35e4a32e377478fb05e2fd314023fd3',
    'rand_digit': 1,
    'rand_number': 0.12874,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-09T09:12:39.989006+05:00',
    'text_array': [
    '4b159fcdff7d474d814fbe886cbcabcd',
    'a828008983444d97882f39fa468f915e',
],
    'words': 'bear whale',
    'nested': {
    'id': 127,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    3,
],
],
    'two_words': [
    'fly',
    'spider',
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
    'mixed_type': None,
    'maybe': 'lizard',
    'maybe_null': 'octopus',
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
    '23',
    '20',
    '21',
    '11',
],
    'text_data': '1f070e6051e8403fb92486f02f208784',
    'rand_digit': 5,
    'rand_number': 0.74536,
    'rand_signed_int': 1,
    'rand_datetime': '2000-09-11 07:15:08.336244',
    'text_array': [
    '36a629d9cbfe4614bf5e840f68165d36',
    'f0cc7782377e45438427aa93b46d2e00',
],
    'words': 'cow chicken',
    'nested': {
    'id': 128,
    'rand_digit': 3,
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
    'word': 'leopard',
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
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 7,
},
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
],
    'two_words': [
    'cow',
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
    'mixed_type': 5,
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
    '03',
],
    'text_data': '4bcf6e21a3d04ae69568f0d21738d378',
    'rand_digit': 0,
    'rand_number': 0.06293,
    'rand_signed_int': 1,
    'rand_datetime': '2000-05-25',
    'text_array': [
    '9738dbb0474a415291851acb98e1adca',
    '4edfe6ee4f454158a07fb7c726cb01ac',
],
    'words': 'dolphin mosquito',
    'nested': {
    'id': 129,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 1,
},
],
},
    'nested_array': [
    [
    6,
],
    [
],
],
    'two_words': [
    'gorilla',
    'koala',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'mosquito',
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
    '22',
    '19',
    '30',
    '12',
    '18',
],
    'text_data': 'b4306aed30934c9e818080312660b505',
    'rand_digit': 4,
    'rand_number': 0.92315,
    'rand_signed_int': 3,
    'rand_datetime': '2000-09-02T05:03:05',
    'text_array': [
    '0b1c08291bcb440897bf9083af6bc577',
    '71fdc3d171e7489c9ea943503dd8d9e6',
],
    'words': 'sloth pig',
    'nested': {
    'id': 130,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 3,
},
],
},
    'nested_array': [
    [
    2,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'turtle',
    'spider',
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
    'mixed_type': 'lobster',
    'maybe': 'dolphin',
    'maybe_null': 'pig',
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
    '02',
],
    'text_data': '2d087559811244b8adf1e7c8f8d0a076',
    'rand_digit': 7,
    'rand_number': 0.34885,
    'rand_signed_int': -10,
    'rand_datetime': '2000-07-14T03:54:37.481180-1200',
    'text_array': [
    'a50529806aa44d0a9964b3dd8a5075f3',
    '8296c5c96cdb471f980e1accde8eb104',
],
    'words': 'fox mouse',
    'nested': {
    'id': 131,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'pig',
    'leopard',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'zebra',
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
    '28',
],
    'text_data': '067b779cba0e4dd9a68baed04ae699f0',
    'rand_digit': 5,
    'rand_number': 0.25237,
    'rand_signed_int': 5,
    'rand_datetime': '2000-02-20 16:18:12-0400',
    'text_array': [
    '853c2a9340444fdd9af0a646f5066d65',
    '428136aa803b4dc98890fdfc21086599',
],
    'words': 'cow rhino',
    'nested': {
    'id': 132,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lion',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'koala',
    'panda',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'fox',
    'maybe_null': 'mouse',
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
    '03',
    '30',
],
    'text_data': 'ae7b9875b18a4593a9dba1825c8fd8d9',
    'rand_digit': 5,
    'rand_number': 0.51966,
    'rand_signed_int': -5,
    'rand_datetime': '2000-06-04T08:56:47.900475-0600',
    'text_array': [
    '595f76d3e36844e88459914fcf2daa4b',
    '90a17ba099b142808149fce0266cbadf',
],
    'words': 'koala wolf',
    'nested': {
    'id': 133,
    'rand_digit': 9,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'leopard',
    'panda',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': [
    11,
],
    'rand_bool': True,
    'mixed_type': 0.0734,
    'maybe': 'grasshopper',
    'maybe_null': 'rhino',
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
    '02',
],
    'text_data': 'b3644926abc647778d2798135e120fae',
    'rand_digit': 7,
    'rand_number': 0.52406,
    'rand_signed_int': -3,
    'rand_datetime': '2000-04-13T16:30:32',
    'text_array': [
    '2e0fb622beed449f93b999abaef961a0',
    'd51d1e76eaff406ebfe598d0c7865d73',
],
    'words': 'tiger bear',
    'nested': {
    'id': 134,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 4,
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
    'word': 'fish',
    'number': 6,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'leopard',
    'koala',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'leopard',
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
    'text_data': '76bf2c931d654983809571de8d58e17f',
    'rand_digit': 7,
    'rand_number': 0.33413,
    'rand_signed_int': 7,
    'rand_datetime': '2000-12-13T02:07:40.220088',
    'text_array': [
    'e83379f6bd3c4b1e97f68de7e70f0bb6',
    'bc99807d8c904eff97bfbcca0d7bdf77',
],
    'words': 'squid bear',
    'nested': {
    'id': 135,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'deer',
    'hyena',
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
    'mixed_type': None,
    'maybe': 'horse',
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
    '25',
    '19',
    '28',
    '04',
],
    'text_data': 'b64e16e3e35f4f489f3af24cacd5febc',
    'rand_digit': 2,
    'rand_number': 0.80719,
    'rand_signed_int': 0,
    'rand_datetime': '2000-04-17 06:31:22',
    'text_array': [
    '09c1e84ff3724f089ce8cee793262dbd',
    'c67cdb6790504e91a05642ac82d41bdf',
],
    'words': 'rhino lizard',
    'nested': {
    'id': 136,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'turtle',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ape',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'octopus',
    'lizard',
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
    'mixed_type': True,
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
    '16',
    '12',
],
    'text_data': 'a73cdc29691641ef917e6fa567456d68',
    'rand_digit': 2,
    'rand_number': 0.96143,
    'rand_signed_int': -3,
    'rand_datetime': '2000-06-12T23:25:11.437666',
    'text_array': [
    '03faf8c142104950a54adf9048fde1c2',
    '0063eaf6c45f4307b45fb4e233e6f6a7',
],
    'words': 'leopard wolf',
    'nested': {
    'id': 137,
    'rand_digit': 1,
    'array': [
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
    'hello',
],
    'word': 'octopus',
    'number': 8,
},
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
    'word': 'ladybug',
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'giraffe',
    'dolphin',
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
    'mixed_type': 'goat',
    'maybe': 'bird',
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
    '20',
],
    'text_data': 'a29e21d0b6f74676800fe8b075dce31b',
    'rand_digit': 9,
    'rand_number': 0.24265,
    'rand_signed_int': -6,
    'rand_datetime': '2000-01-15T09:39:02-1100',
    'text_array': [
    '0dbc94a3ce784d2ba270a54479039624',
    'f1e2dd6aef9f4ef0a659e56a5fa3a8f6',
],
    'words': 'camel bee',
    'nested': {
    'id': 138,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'crab',
    'gorilla',
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
    'mixed_type': 'lobster',
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
    '11',
],
    'text_data': 'ee0decbd6ab44e4597a032f7e9efaef8',
    'rand_digit': 4,
    'rand_number': 0.84266,
    'rand_signed_int': -8,
    'rand_datetime': '2000-09-26T14:18:18+0500',
    'text_array': [
    'a557cea198ce480f995a3dba52ed6029',
    '544393792c0a4149989394604e2340c5',
],
    'words': 'shark bird',
    'nested': {
    'id': 139,
    'rand_digit': 0,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'sheep',
    'cat',
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
    'mixed_type': 0.41025,
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
    '10',
    '26',
    '26',
    '05',
],
    'text_data': 'fb044fe7e8ad4ee89f0d396f04af4ba1',
    'rand_digit': 4,
    'rand_number': 0.15902,
    'rand_signed_int': -7,
    'rand_datetime': '2000-02-16T22:37:30',
    'text_array': [
    '237c4b28e955435e9f8e98f329547642',
    'c52832bf8d0a480584a12c15aae7cf72',
],
    'words': 'cow horse',
    'nested': {
    'id': 140,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 4,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bird',
    'crab',
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
    'mixed_type': 0.45713,
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
    '13',
    '19',
    '20',
    '03',
],
    'text_data': '699329387b744e93a6ae6ec5eb6d4a22',
    'rand_digit': 5,
    'rand_number': 0.21659,
    'rand_signed_int': -5,
    'rand_datetime': '2000-11-14',
    'text_array': [
    'e34cd71379f14aca94b05f116cfb6b95',
    '281489ca22d34a21afc5e09e95929fad',
],
    'words': 'rabbit fish',
    'nested': {
    'id': 141,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    [
],
    [
    8,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'horse',
    'octopus',
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
    'mixed_type': None,
    'maybe': 'deer',
    'maybe_null': 'ladybug',
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
    '28',
    '09',
],
    'text_data': 'e0b30218603b46ebb4552f36a7d93515',
    'rand_digit': 8,
    'rand_number': 0.75228,
    'rand_signed_int': 4,
    'rand_datetime': '2000-12-28 02:22:31',
    'text_array': [
    '40b6e898185342bc90876e3fd9dca087',
    '3ba42c19833f4eeaaf980fa6bed445dd',
],
    'words': 'grasshopper whale',
    'nested': {
    'id': 142,
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
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    [
    3,
],
],
    'two_words': [
    'mouse',
    'butterfly',
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
    'maybe': 'camel',
    'maybe_null': 'butterfly',
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
],
    'text_data': '3343e524c84a419f812dc3ad42be17b0',
    'rand_digit': 3,
    'rand_number': 0.22876,
    'rand_signed_int': -8,
    'rand_datetime': '2000-07-04 02:54:52-0500',
    'text_array': [
    'fb082ce87d76450a900338d5e1c648f9',
    'ab659e7638064a69a18c42e2b9432b61',
],
    'words': 'sheep hyena',
    'nested': {
    'id': 143,
    'rand_digit': 1,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'sheep',
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
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'giraffe',
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
    'text_data': '7c50bd4344164133898d10a4f9ebff4a',
    'rand_digit': 8,
    'rand_number': 0.03962,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-08T12:11:06-1000',
    'text_array': [
    '8073e0bbdf9d4853bee18fbd256c2cc7',
    'f500b622462e43c5a11bd202f7b11326',
],
    'words': 'lobster scorpion',
    'nested': {
    'id': 144,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'camel',
    'bird',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': [
    4,
],
    'rand_bool': False,
    'mixed_type': 'dog',
    'maybe_null': None,
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
    '28',
    '02',
    '04',
    '19',
],
    'text_data': '266436875442402d8be0ecea29ea9279',
    'rand_digit': 7,
    'rand_number': 0.81958,
    'rand_signed_int': -4,
    'rand_datetime': '2000-05-09T21:42:15.884891+12:00',
    'text_array': [
    '703f4181a1724743a97389830f5803f1',
    '255bf57e58b0475783a28979cdb91fd9',
],
    'words': 'crab sheep',
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
    'word': 'lobster',
    'number': 10,
},
    {
    'nested_empty': None,
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
    'word': 'goat',
    'number': 4,
},
],
},
    'nested_array': [
    [
    7,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'cow',
    'whale',
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
    'mixed_type': {
    'key': 'value',
},
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
    '10',
],
    'text_data': 'de73750adb364074bdc31d24df9937a2',
    'rand_digit': 6,
    'rand_number': 0.60644,
    'rand_signed_int': 3,
    'rand_datetime': '2000-06-30 09:46:03.739559+1100',
    'text_array': [
    'c10bf257f4e74526bc6c97c8b69a7e9b',
    '2a8735348f0245b7a19b345742487f19',
],
    'words': 'jaguar camel',
    'nested': {
    'id': 146,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 10,
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
    'hello',
],
    'word': 'cheetah',
    'number': 9,
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
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'rhino',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'snake',
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
    '22',
    '10',
    '18',
    '28',
    '26',
],
    'text_data': 'd5c22b4635964a8a88bcd4c232e3f908',
    'rand_digit': 5,
    'rand_number': 0.70546,
    'rand_signed_int': 9,
    'rand_datetime': '2000-07-31T04:00:59.571216-1000',
    'text_array': [
    'a298402b776f47d0b7101510c3480dcb',
    '2ff07e9040ff4773bc0cbfd82eb1779e',
],
    'words': 'butterfly turtle',
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
    'word': 'octopus',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 8,
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
    'word': 'bird',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'bear',
    'squid',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'lion',
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
    '03',
    '01',
    '25',
],
    'text_data': '0928f4685fbf4db4b42a17874b68ba61',
    'rand_digit': 9,
    'rand_number': 0.17961,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-04T17:35:13.129872',
    'text_array': [
    'a7f047a95f9449e5acce46a6b45ff26c',
    '5f8c9919f128465cb9f8782a56d36af7',
],
    'words': 'chicken tiger',
    'nested': {
    'id': 148,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'zebra',
    'snake',
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
    'mixed_type': 5,
    'maybe_null': 'squid',
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
    '13',
    '10',
    '16',
    '10',
    '05',
],
    'text_data': '8e019f3b42c24acb88abaa2292cf6d8b',
    'rand_digit': 2,
    'rand_number': 0.07669,
    'rand_signed_int': 4,
    'rand_datetime': '2000-05-15 08:49:23',
    'text_array': [
    '88e4d29bff264b8cbc9fcc63647c61be',
    'f5d09cbb61bf43dbb1923f351e7e8e72',
],
    'words': 'bird tiger',
    'nested': {
    'id': 149,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fish',
    'bee',
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
    'maybe': 'hyena',
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
    '16',
    '11',
    '09',
],
    'text_data': '7e5c9f29df534445bdc41ebb71bfe63d',
    'rand_digit': 4,
    'rand_number': 0.7673,
    'rand_signed_int': 7,
    'rand_datetime': '2000-12-02T05:04:45',
    'text_array': [
    '017cea44fb7e4444989a28e014a77f43',
    '1d064e0dc399450caec4d2139b7fd41c',
],
    'words': 'crab rabbit',
    'nested': {
    'id': 150,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 4,
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
],
    'word': 'fly',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lobster',
    'mouse',
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
    '02',
    '18',
    '21',
],
    'text_data': '57507fb7c6d344d88072c37e9dfbaf66',
    'rand_digit': 3,
    'rand_number': 0.55926,
    'rand_signed_int': 5,
    'rand_datetime': '2000-11-27T21:21:02.331004+1200',
    'text_array': [
    '120994a306344ab5af045a054d9a1ea9',
    '11f196631c284654b42582060c3a4fb4',
],
    'words': 'panda leopard',
    'nested': {
    'id': 151,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
    2,
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -8,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'pig',
    'squid',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'horse',
    'maybe_null': 'cow',
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
    '01',
    '08',
    '17',
    '12',
],
    'text_data': 'd2b9aac5be6c4fafbde4ec216c6b3d8b',
    'rand_digit': 2,
    'rand_number': 0.00433,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-30',
    'text_array': [
    '4c595c0dfa504821a8f3ab5d82d622b8',
    '658a4d19758c4fe3b9fb33172426bb60',
],
    'words': 'frog fly',
    'nested': {
    'id': 152,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'lizard',
    'number': 7,
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
    'pig',
    'zebra',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.97926,
    'maybe_null': None,
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
    '20',
    '24',
    '19',
    '01',
],
    'text_data': '434d2116b7ce443dbd896a030352cc3c',
    'rand_digit': 0,
    'rand_number': 0.86687,
    'rand_signed_int': 2,
    'rand_datetime': '2001-01-08T20:39:25.332430+05:00',
    'text_array': [
    'a584e35684d84047b32b10e85aca3cf5',
    '92814fb1c235406783dc0d36bf270421',
],
    'words': 'snail cat',
    'nested': {
    'id': 153,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 6,
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
    'word': 'frog',
    'number': 6,
},
],
},
    'nested_array': [
    [
    3,
],
],
    'two_words': [
    'dog',
    'lobster',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 9,
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
    '21',
    '03',
    '27',
],
    'text_data': 'a1a4cc0a159849a6add2fdc8559bb2c2',
    'rand_digit': 9,
    'rand_number': 0.72337,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-24 02:35:37.921021',
    'text_array': [
    'd68483b480344b30a9afc1ab79bf0991',
    '2e83fa50a79e4633b6badb21a4720d9f',
],
    'words': 'butterfly bee',
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
    'word': 'rabbit',
    'number': 1,
},
    {
    'nested_empty': None,
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
    'word': 'whale',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'crab',
    'scorpion',
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
    'mixed_type': None,
    'maybe': 'mouse',
    'maybe_null': 'pig',
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
    '12',
    '13',
],
    'text_data': '8bba7151fe474feab09ce8314153b423',
    'rand_digit': 5,
    'rand_number': 0.84171,
    'rand_signed_int': -7,
    'rand_datetime': '2000-07-06T16:17:02-0200',
    'text_array': [
    'f15a1f64615f4e22986d3ce80ac0bff0',
    '33fe7fd17732438dabe47b2fa02c7faa',
],
    'words': 'crab panda',
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
    'word': 'dolphin',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -5,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    3,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'turtle',
    'crab',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fly',
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
    '14',
],
    'text_data': 'd817365cb73549af86889de7323b0072',
    'rand_digit': 7,
    'rand_number': 0.31232,
    'rand_signed_int': 9,
    'rand_datetime': '2000-01-17 14:45',
    'text_array': [
    '5f9eb0cee4d44793951916c43685c8b7',
    'e9efee90a0d34bfc9bb600876691ed1e',
],
    'words': 'chicken sloth',
    'nested': {
    'id': 156,
    'rand_digit': 4,
    'array': [
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
    'word': 'monkey',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'squid',
    'deer',
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
    'mixed_type': 'rhino',
    'maybe': 'leopard',
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
    '05',
    '02',
],
    'text_data': 'b4a4a7ad255449b6b299d11d7c1ef46d',
    'rand_digit': 9,
    'rand_number': 0.31781,
    'rand_signed_int': 4,
    'rand_datetime': '2000-08-25T11:09:07.028122-0700',
    'text_array': [
    '90016b9112ca455da2fb95f050e49e9a',
    'b27380e6d5c64bd1a00c8b2fe396546a',
],
    'words': 'lobster bear',
    'nested': {
    'id': 157,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 2,
},
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
],
    'two_words': [
    'grasshopper',
    'mosquito',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'deer',
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
    '23',
    '09',
    '27',
    '03',
    '20',
],
    'text_data': 'df1894232be649b2a02e9e9da69d1fff',
    'rand_digit': 2,
    'rand_number': 0.73212,
    'rand_signed_int': 3,
    'rand_datetime': '2000-10-26T07:34:08',
    'text_array': [
    'a55c98d8ab3349229e7656e929e062f1',
    'eb926a13be23430c82bfb09f21aa9000',
],
    'words': 'snail sloth',
    'nested': {
    'id': 158,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'chicken',
    'rabbit',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': [
    11,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'pig',
    'maybe_null': 'fish',
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
],
    'text_data': 'ce02e2eec10b4772b2c677cc8df39f56',
    'rand_digit': 3,
    'rand_number': 0.72878,
    'rand_signed_int': -1,
    'rand_datetime': '2000-09-15 14:23',
    'text_array': [
    '2344907cbed746e2809ee97274df8bd6',
    'aa378503910c4eb2959c6f617066419c',
],
    'words': 'fish turtle',
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
    'word': 'koala',
    'number': 9,
},
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
    'word': 'rabbit',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'squid',
    'number': 2,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_3,5__',
    'two_words': [
    'snake',
    'crab',
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
    '03',
    '27',
    '20',
],
    'text_data': '7f7583cec14d4c368b6578ece2a7fbfe',
    'rand_digit': 8,
    'rand_number': 0.99174,
    'rand_signed_int': 3,
    'rand_datetime': '2000-06-20T17:12:17.378487+0400',
    'text_array': [
    '6b035c4459314d779a9cb211cb8edc42',
    '86a0c6c6035e4a30826553d4a624a8d9',
],
    'words': 'sloth tiger',
    'nested': {
    'id': 160,
    'rand_digit': 7,
    'array': [
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'whale',
    'duck',
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
    'mixed_type': 'gorilla',
    'maybe_null': 'fly',
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
    '19',
    '23',
    '15',
],
    'text_data': '2c0ed7f31ccc4bbeb807abb86a8ca98b',
    'rand_digit': 1,
    'rand_number': 0.79006,
    'rand_signed_int': -8,
    'rand_datetime': '2000-01-04 09:43',
    'text_array': [
    '30ef0697cb9645f691ee4501f7795395',
    'fba4d31b61d94f38a2d927c265f04ef9',
],
    'words': 'fly mouse',
    'nested': {
    'id': 161,
    'rand_digit': 0,
    'array': [
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
    'word': 'lion',
    'number': 9,
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
    'word': 'leopard',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    4,
],
],
    'two_words': [
    'duck',
    'hyena',
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
    'maybe': 'wolf',
    'maybe_null': None,
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
],
    'text_data': '47994831d50f46b79b1c35adc8757b93',
    'rand_digit': 3,
    'rand_number': 0.81289,
    'rand_signed_int': -3,
    'rand_datetime': '2000-01-20T01:10:54.996324',
    'text_array': [
    '34c0e4ba091646c19d255f30078c0abd',
    '24a2cef43f614f928d3b8415d562320e',
],
    'words': 'hyena chicken',
    'nested': {
    'id': 162,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'camel',
    'number': 10,
},
],
},
    'nested_array': [
    [
    9,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'hippo',
    'gorilla',
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
    'mixed_type': 1,
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
],
    'text_data': '727f95966afc4b6cbf3ed83e12008d99',
    'rand_digit': 6,
    'rand_number': 0.71758,
    'rand_signed_int': 6,
    'rand_datetime': '2000-10-05 11:14:56.300242+1100',
    'text_array': [
    'a7d3391e37d743de89cbe1843a846320',
    'f710614fc6994eddb71f0185c155907c',
],
    'words': 'butterfly sheep',
    'nested': {
    'id': 163,
    'rand_digit': 1,
    'array': [
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
    'word': 'grasshopper',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'panda',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'squid',
    'deer',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.13628,
    'maybe': 'horse',
    'maybe_null': 'ant',
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
        """测试请求 2 - POST http://localhost:6333/collections/congruence_test_collection/points/search/matrix/offsets"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/matrix/offsets")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/matrix/offsets'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '39',
}
        
        # 原始请求内容
        original_content = {
    'sample': 100,
    'limit': 3,
    'using': 'text',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_search_distance_matrix.test_search_offsets_no_filter')
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
    test = TestSearchDistanceMatrixtestSearchOffsetsNoFilter()
    test.run_tests()
