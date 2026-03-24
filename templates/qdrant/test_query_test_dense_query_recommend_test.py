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
logger = logging.getLogger('vdb_fuzzer.test.test_query_test_dense_query_recommend')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_query.test_dense_query_recommend"
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



class TestQuerytestDenseQueryRecommend:
    """自动生成的VDB模糊测试类 - test_query.test_dense_query_recommend"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_query.test_dense_query_recommend"
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
    'content-length': '134834',
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
    '14',
],
    'text_data': '74ded7aa63eb47c5891917015906f49a',
    'rand_digit': 0,
    'rand_number': 0.36336,
    'rand_signed_int': 10,
    'rand_datetime': '2000-05-14T11:41:21+0000',
    'text_array': [
    '27fdadb1f8284f6a874c9a211b2f952c',
    'de33ebd81e674fa7a1ed456ace3f0b54',
],
    'words': 'cat lizard',
    'nested': {
    'id': 100,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'grasshopper',
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'spider',
    'mouse',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': [
    99,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'camel',
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
    '01',
    '26',
],
    'text_data': '5dac50c82ff84a1ea667c4e28bd0d78f',
    'rand_digit': 7,
    'rand_number': 0.03427,
    'rand_signed_int': -6,
    'rand_datetime': '2000-08-08 06:28:55-0100',
    'text_array': [
    '451cda4748d24f72a5eb6493dfb82387',
    '8f66b318e1854d878195c2cc6d5f7420',
],
    'words': 'fox crab',
    'nested': {
    'id': 101,
    'rand_digit': 3,
    'array': [
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
    'word': 'turtle',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'wolf',
    'turtle',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': [
    86,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'horse',
    'maybe_null': 'lobster',
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
    '25',
    '14',
    '13',
    '03',
],
    'text_data': '30b42882efe34a17be17ffd1786b1160',
    'rand_digit': 3,
    'rand_number': 0.30939,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-03 20:06:28-0200',
    'text_array': [
    'bec835b23587438994934a31f1a937e6',
    '03b54388468148c2907d443525092767',
],
    'words': 'crab snake',
    'nested': {
    'id': 102,
    'rand_digit': 5,
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
],
    'word': 'zebra',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'zebra',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    0,
],
],
    'two_words': [
    'koala',
    'zebra',
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
    'mixed_type': 8,
    'maybe': 'kangaroo',
    'maybe_null': None,
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
    '23',
    '14',
    '12',
],
    'text_data': '0f85b9eb72c84e6cbc64f6f17105b933',
    'rand_digit': 5,
    'rand_number': 0.28401,
    'rand_signed_int': 7,
    'rand_datetime': '2000-07-01 04:25:49.777340+0400',
    'text_array': [
    'de1511a4b48f41a69debcdd25dd0f4af',
    '7af2da482fa541fbaadbf7035d3251ac',
],
    'words': 'wolf bird',
    'nested': {
    'id': 103,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'panda',
    'crab',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': [
    34,
],
    'rand_bool': False,
    'mixed_type': 1,
    'maybe': 'bee',
    'maybe_null': 'cat',
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
    '02',
],
    'text_data': '369d673a8c19440cbb36a13a32cfa83f',
    'rand_digit': 5,
    'rand_number': 0.24754,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-18T06:50:22.643794-0600',
    'text_array': [
    'e824137b27704998855705ce1d486250',
    'c449a205259e4bcd910cb0d5da30fffe',
],
    'words': 'cheetah cheetah',
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
    'word': 'dragonfly',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 7,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'grasshopper',
    'pig',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.78494,
    'maybe': 'jaguar',
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
    '14',
    '26',
    '13',
],
    'text_data': '889f68f2a67c4dd898fd6c7a709e2c7f',
    'rand_digit': 7,
    'rand_number': 0.21453,
    'rand_signed_int': -2,
    'rand_datetime': '2000-01-25T11:26:26',
    'text_array': [
    'b6980e1d2b3b460481597b0819ac626b',
    'da833059f01c42f2a279f0675eb92c89',
],
    'words': 'crab snail',
    'nested': {
    'id': 105,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'mosquito',
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
    'mixed_type': None,
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
    '19',
    '07',
],
    'text_data': 'e88218dd11664d28b26f3a28a5128b44',
    'rand_digit': 7,
    'rand_number': 0.74651,
    'rand_signed_int': 0,
    'rand_datetime': '2000-01-18 10:14',
    'text_array': [
    '13bc6ef68bc14cb099f24122d3c9e40a',
    '567e43dc2ab148f4b335331f5b2f5b2d',
],
    'words': 'leopard snake',
    'nested': {
    'id': 106,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'lion',
    'monkey',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'dragonfly',
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
    '27',
    '30',
],
    'text_data': '812dd338abb1418cbaf53d60d69a4c17',
    'rand_digit': 3,
    'rand_number': 0.54006,
    'rand_signed_int': -4,
    'rand_datetime': '2000-11-23T11:02:34.592380',
    'text_array': [
    '661ced1b53d04da8a67ba694fd2f605c',
    '857de6a297624de4b4a4171f4d15d0ff',
],
    'words': 'butterfly ladybug',
    'nested': {
    'id': 107,
    'rand_digit': 2,
    'array': [
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'deer',
    'mouse',
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
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cow',
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
    'text_data': '436e26740591466d9424b7c3d10694d0',
    'rand_digit': 9,
    'rand_number': 0.19614,
    'rand_signed_int': 1,
    'rand_datetime': '2000-09-23 19:55',
    'text_array': [
    'd640b0824082421da7a10b0b268918c7',
    '60a63dda9b4f4ade84ea3c449defc405',
],
    'words': 'octopus cheetah',
    'nested': {
    'id': 108,
    'rand_digit': 2,
    'array': [
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ape',
    'dolphin',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': [
    71,
],
    'rand_bool': False,
    'mixed_type': 'duck',
    'maybe': 'snail',
    'maybe_null': 'duck',
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
    '26',
    '29',
    '05',
    '09',
    '16',
],
    'text_data': '2e74688dfac64a5ebd6d1675ae42fab6',
    'rand_digit': 2,
    'rand_number': 0.64053,
    'rand_signed_int': -10,
    'rand_datetime': '2000-06-03',
    'text_array': [
    'd4b8287d33d2413a9d6f8ec5c469117a',
    'f457b2d27949435c9eabbab3a06a4044',
],
    'words': 'dog bear',
    'nested': {
    'id': 109,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'monkey',
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
    17,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'lion',
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
],
    'text_data': 'd5f7ec3e5d3b47f880645a3914b9e1e3',
    'rand_digit': 1,
    'rand_number': 0.9091,
    'rand_signed_int': 0,
    'rand_datetime': '2001-01-13T16:25:28.830338',
    'text_array': [
    '9d185d90daf844ab89e10d0375613171',
    'd7e51c82084b46cd84cb3f40ada3522d',
],
    'words': 'koala bird',
    'nested': {
    'id': 110,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'monkey',
    'number': 9,
},
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
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'ant',
    'scorpion',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'rabbit',
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
    '01',
],
    'text_data': '4cf2eb46b5cc40308353c5935263d38c',
    'rand_digit': 4,
    'rand_number': 0.02796,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-11 15:41:57',
    'text_array': [
    'bd362298ded14e56adb376fbd4a88aa4',
    'dfdc54574c6a4378a21a254e3e0bfe7e',
],
    'words': 'pig panda',
    'nested': {
    'id': 111,
    'rand_digit': 2,
    'array': [
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'giraffe',
    'tiger',
],
    'city': {
    'name': 'Copenhagen',
    'geo': {
    'lat': 55.676097,
    'lon': 12.568337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
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
    'text_data': '6038e5c9bc01424d808bff7c0cdcda2e',
    'rand_digit': 8,
    'rand_number': 0.05581,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-20 23:17:38.496437+0000',
    'text_array': [
    '751e3d0bd7f74b5ea83272b9cbe362c2',
    '76c42e4e49854432a3b46b82a60c466c',
],
    'words': 'lion fox',
    'nested': {
    'id': 112,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'lion',
    'lion',
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
    'maybe': 'bee',
    'maybe_null': 'cow',
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
    '15',
    '28',
    '26',
    '25',
    '14',
],
    'text_data': 'f58e3c9c62324e1f8f38b8cd54dfd97c',
    'rand_digit': 4,
    'rand_number': 0.43418,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-28 21:29:53.206234+0000',
    'text_array': [
    '5f6b13c2ed3146db916030eb1e8f8dac',
    '178b6484e28d4809bf4802923c1d11ae',
],
    'words': 'rabbit octopus',
    'nested': {
    'id': 113,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 2,
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
    'goat',
    'zebra',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.37673,
    'maybe_null': 'fly',
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
    '15',
],
    'text_data': '96ceb544f89948d59c74d2cccdbd8ac1',
    'rand_digit': 7,
    'rand_number': 0.81353,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-12 07:23:54.255579+0500',
    'text_array': [
    'c0ff3c65b7c54273ac3630cfe915c193',
    '53d8cf6f496e439b9ec9b2e103838bc4',
],
    'words': 'wolf dolphin',
    'nested': {
    'id': 114,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'elephant',
    'cow',
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
    'mixed_type': True,
    'maybe': 'dog',
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
],
    'text_data': 'ebe6c2eb96d5432bb113f25fca2e77b5',
    'rand_digit': 6,
    'rand_number': 0.40935,
    'rand_signed_int': -6,
    'rand_datetime': '2001-01-20T15:59:27.166650',
    'text_array': [
    '4978c71cd2a142a1982163d58a382db7',
    'e5183d9b3c8340edb79b5ca27bc9ffbf',
],
    'words': 'shark kangaroo',
    'nested': {
    'id': 115,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'koala',
    'cat',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'hippo',
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
    '01',
    '20',
    '01',
    '29',
    '28',
],
    'text_data': 'd6eb3e084d1140e8b8b147dcedb349e1',
    'rand_digit': 9,
    'rand_number': 0.48424,
    'rand_signed_int': 5,
    'rand_datetime': '2000-06-02T06:16:55',
    'text_array': [
    '0f64f06bfb2748fca8187a89c8e5d8e0',
    '5039a965bde046fbaa8e92ff00855fec',
],
    'words': 'fly lobster',
    'nested': {
    'id': 116,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 10,
},
],
},
    'nested_array': [
    [
    -2,
],
],
    'two_words': [
    'ape',
    'ladybug',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'hyena',
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
    '15',
],
    'text_data': '5f5cc29d1ecd499abc39523e6d04efc8',
    'rand_digit': 7,
    'rand_number': 0.43114,
    'rand_signed_int': -8,
    'rand_datetime': '2000-01-27 23:24:45',
    'text_array': [
    '5bd426390fdc473999c9cc947e0a999a',
    '62509286d5014f83ae86bcafb5d055c3',
],
    'words': 'elephant panda',
    'nested': {
    'id': 117,
    'rand_digit': 3,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
    [
    -3,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'snake',
    'frog',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': [
    23,
],
    'rand_bool': False,
    'mixed_type': 'jaguar',
    'maybe': 'fish',
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
    '30',
    '15',
    '04',
],
    'text_data': 'de822bbf2b1f43349096249e1c1f5335',
    'rand_digit': 6,
    'rand_number': 0.25108,
    'rand_signed_int': 7,
    'rand_datetime': '2000-10-07 01:08',
    'text_array': [
    '9d36a89c5e2f4d03af6125522410b6ba',
    '9065e99650254b9688945de7018ccb73',
],
    'words': 'cow dog',
    'nested': {
    'id': 118,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 1,
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
    'hello',
],
    'word': 'dog',
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
    'number': 8,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,5__',
    'two_words': [
    'koala',
    'pig',
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
    'maybe': 'jaguar',
    'maybe_null': 'goat',
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
],
    'text_data': '7a2dabb60011480fa4e3f4074d036a5e',
    'rand_digit': 1,
    'rand_number': 0.41255,
    'rand_signed_int': 9,
    'rand_datetime': '2000-06-05T21:45:38.692442-0100',
    'text_array': [
    '1809f39f1830400ba5535bb6172e7ef5',
    '05153cbd56a449b5865d9d1d90292118',
],
    'words': 'kangaroo pig',
    'nested': {
    'id': 119,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'snake',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    5,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'leopard',
    'lion',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.30786,
    'maybe_null': None,
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
    '26',
],
    'text_data': '2f0893f9edfe49bd88b066809fbcbd2a',
    'rand_digit': 7,
    'rand_number': 0.46607,
    'rand_signed_int': -7,
    'rand_datetime': '2000-09-19T19:33:24.564141',
    'text_array': [
    '5a12f53eb1c649a287796bdf6481dd54',
    'eeb24204e8024e56bfddf45875c74ed9',
],
    'words': 'lion mosquito',
    'nested': {
    'id': 120,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 9,
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
    'word': 'hippo',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mosquito',
    'crab',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe_null': 'leopard',
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
    '30',
    '03',
],
    'text_data': 'b56003fa01754e86b0d57fb335255779',
    'rand_digit': 3,
    'rand_number': 0.67995,
    'rand_signed_int': -4,
    'rand_datetime': '2000-05-18T21:45:34.236066',
    'text_array': [
    '01bb8563dd6c4c97ae0ed202c32f8784',
    '9aae798cea444e36b7415d3cd138c9de',
],
    'words': 'squid shark',
    'nested': {
    'id': 121,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
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
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 1,
},
],
},
    'nested_array': [
    [
    5,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'mouse',
    'duck',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'panda',
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
    '20',
    '21',
],
    'text_data': '83d871dfe9064c5a81b8ca06d6c47408',
    'rand_digit': 7,
    'rand_number': 0.22794,
    'rand_signed_int': -2,
    'rand_datetime': '2000-12-04T21:09:32.205901',
    'text_array': [
    '2362347bd1b74b97bef60585ebd68897',
    'a3d74c87688a4b80a6766548e491ade8',
],
    'words': 'frog fish',
    'nested': {
    'id': 122,
    'rand_digit': 5,
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
    'word': 'deer',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 1,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,3__',
    'two_words': [
    'giraffe',
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
    'mixed_type': 0,
    'maybe_null': 'fly',
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
    '18',
    '06',
    '07',
],
    'text_data': '9d1a2c80f3524dc5ab5ee9238fc03ded',
    'rand_digit': 7,
    'rand_number': 0.45582,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-14 16:40:51',
    'text_array': [
    'dba10f378e424a048ff32bd1f447b340',
    '471369919f1b4b08a92165911929c7ea',
],
    'words': 'pig ape',
    'nested': {
    'id': 123,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'octopus',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 1,
},
],
},
    'nested_array': [
    [
    -4,
],
    [
],
    [
    6,
],
    [
],
    [
],
],
    'two_words': [
    'frog',
    'cat',
],
    'city': {
    'name': 'Kuala Lumpur',
    'geo': {
    'lat': 3.139003,
    'lon': 101.686855,
},
},
    'rand_tuple': [
    47,
],
    'rand_bool': False,
    'mixed_type': 'camel',
    'maybe': 'hyena',
    'maybe_null': 'leopard',
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
    '06',
],
    'text_data': 'c90f5949cbfa4509b7176d0944f2b6c9',
    'rand_digit': 8,
    'rand_number': 0.45077,
    'rand_signed_int': -6,
    'rand_datetime': '2000-04-27T12:36:15.383980',
    'text_array': [
    '2e12dd303175405298bbbbfe51688ba6',
    '354a2a1453b94322b2144c4d32c43b89',
],
    'words': 'fish spider',
    'nested': {
    'id': 124,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
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
    'hello',
],
    'word': 'fly',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'elephant',
    'hyena',
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
    'mixed_type': None,
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
    '11',
    '01',
    '11',
    '06',
],
    'text_data': '366e0d7ee1ef4eb0a4e967b20fdbf78e',
    'rand_digit': 4,
    'rand_number': 0.84185,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-18 08:01:59.547093',
    'text_array': [
    '5b159fc52c0d4d798c42197375ac0581',
    'aab61cda77ee41d8b66197234f12a49d',
],
    'words': 'whale leopard',
    'nested': {
    'id': 125,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'wolf',
    'lion',
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
    'mixed_type': None,
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
    '26',
    '02',
],
    'text_data': '9b5e1bab70364341ab885d209635a8df',
    'rand_digit': 9,
    'rand_number': 0.51367,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-18 19:12:39',
    'text_array': [
    '0b870d0ad7b5423fb6cc94e2b0fa803a',
    'e93801af878845abbf04a98dafb58ec2',
],
    'words': 'snake koala',
    'nested': {
    'id': 126,
    'rand_digit': 6,
    'array': [
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
    'word': 'koala',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'whale',
    'mouse',
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
    'maybe': 'wolf',
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
    'text_data': '5323ef29daf247df94664c4f4198637c',
    'rand_digit': 4,
    'rand_number': 0.4804,
    'rand_signed_int': -3,
    'rand_datetime': '2000-02-13 14:56:56.566644+0800',
    'text_array': [
    'b06d171aa3844b1480db55d134d4f725',
    'dd18a7193f6241729290e4354b9c66f9',
],
    'words': 'horse goat',
    'nested': {
    'id': 127,
    'rand_digit': 7,
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
    'monkey',
    'deer',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': [
    98,
],
    'rand_bool': False,
    'mixed_type': 'hippo',
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
    '25',
    '17',
],
    'text_data': 'fedf4e0f50324147ad65fc8bd6256ce4',
    'rand_digit': 1,
    'rand_number': 0.9008,
    'rand_signed_int': -2,
    'rand_datetime': '2000-02-05T08:05:36.800409+1100',
    'text_array': [
    'bfeb1f5baed34e0890715f21ff8c8942',
    'ff91b219a64740cebcff3f04384cc364',
],
    'words': 'bee elephant',
    'nested': {
    'id': 128,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'koala',
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'gorilla',
    'frog',
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
    'mixed_type': True,
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
],
    'text_data': '54305d4a52ba4804852aaad4b637b207',
    'rand_digit': 0,
    'rand_number': 0.41297,
    'rand_signed_int': 5,
    'rand_datetime': '2000-02-18 21:24:27.744389-0500',
    'text_array': [
    'a8c1e5d14bc84c82b866712b4c7f5322',
    '16b51db2295c42689a205585a2ca9d80',
],
    'words': 'koala ape',
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
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'monkey',
    'rabbit',
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
    'mixed_type': False,
    'maybe_null': None,
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
    '07',
],
    'text_data': '837672f0863d40ae828cba5520d37ee5',
    'rand_digit': 1,
    'rand_number': 0.27099,
    'rand_signed_int': 7,
    'rand_datetime': '2000-12-07 09:10:32-1000',
    'text_array': [
    'db4f0f3b440d4778999c01ceaa158a97',
    '15860acc386b467d9fd4f0c5f32b2dc9',
],
    'words': 'fly turtle',
    'nested': {
    'id': 130,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 6,
},
    {
    'nested_empty': None,
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
    'word': 'frog',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'kangaroo',
    'fox',
],
    'city': {
    'name': 'Riga',
    'geo': {
    'lat': 56.949649,
    'lon': 24.105186,
},
},
    'rand_tuple': [
    5,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': None,
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
    '10',
    '11',
],
    'text_data': 'a15e69a12dcb481f951b703c26a367e2',
    'rand_digit': 3,
    'rand_number': 0.09489,
    'rand_signed_int': 0,
    'rand_datetime': '2000-10-26 03:12:18',
    'text_array': [
    'aa56087cdff0448f81e69c71878ac72b',
    'e1d7a54e4b3a42fc93e07ab3686dc015',
],
    'words': 'cow gorilla',
    'nested': {
    'id': 131,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -8,
],
],
    'two_words': [
    'rhino',
    'grasshopper',
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
    'mixed_type': 6,
    'maybe': 'bee',
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
    '23',
    '08',
    '18',
],
    'text_data': '43825f83a92a47df9d4d582e1608c48a',
    'rand_digit': 5,
    'rand_number': 0.50931,
    'rand_signed_int': -8,
    'rand_datetime': '2000-06-03T20:03:08',
    'text_array': [
    'b758dafad12045cba7c480da5f637e4b',
    'be34b84269de4992aae166fffd3cd99c',
],
    'words': 'cat cat',
    'nested': {
    'id': 132,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'bear',
    'giraffe',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': [
    61,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'butterfly',
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
    '22',
    '21',
    '06',
    '14',
    '15',
],
    'text_data': 'd4f6853b1aee47eb89d74f880245975b',
    'rand_digit': 1,
    'rand_number': 0.21169,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-01T17:34:01.895661',
    'text_array': [
    '563ba3166326442ea5bd9112b2f4174f',
    '040fab05a4a34ef7956f26214740c44f',
],
    'words': 'ladybug leopard',
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
    'word': 'zebra',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'grasshopper',
    'koala',
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
    'mixed_type': 'sloth',
    'maybe': 'whale',
    'maybe_null': None,
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
    '24',
    '05',
    '03',
],
    'text_data': 'e27b98cbf9ee45468b058a73d4cdf609',
    'rand_digit': 2,
    'rand_number': 0.60569,
    'rand_signed_int': 7,
    'rand_datetime': '2000-09-27 06:02',
    'text_array': [
    '8a1ad9da6f5e4c729b71ff83b24733cc',
    'e1c97dd6a6514ec3aa2529ef2e0d8e9d',
],
    'words': 'pig dolphin',
    'nested': {
    'id': 134,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'shark',
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
    'cow',
    'tiger',
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
    'mixed_type': 7,
    'maybe': 'grasshopper',
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
    '20',
    '23',
    '04',
    '13',
    '08',
],
    'text_data': 'a27d3fa5648249429f6e2295811441c9',
    'rand_digit': 7,
    'rand_number': 0.11322,
    'rand_signed_int': -6,
    'rand_datetime': '2000-11-05 23:21:13+1200',
    'text_array': [
    '6580de5ebee44d3d825817f3fc7de512',
    '00244648b5e04ca390ae6a8c53ef4b5d',
],
    'words': 'cow rhino',
    'nested': {
    'id': 135,
    'rand_digit': 3,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 6,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'leopard',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    1,
],
],
    'two_words': [
    'rabbit',
    'ant',
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
    'mixed_type': 'crab',
    'maybe': 'lobster',
    'maybe_null': 'lizard',
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
    '28',
    '15',
    '12',
    '28',
],
    'text_data': 'd39c47f866bc4f9ba5c939fd6d64cd00',
    'rand_digit': 5,
    'rand_number': 0.34682,
    'rand_signed_int': -2,
    'rand_datetime': '2001-01-21T12:32:27.591899',
    'text_array': [
    '729d0888b5f0457190c69435aa02a39d',
    'abb7a63b227348c89b8e8971788d4f66',
],
    'words': 'mosquito tiger',
    'nested': {
    'id': 136,
    'rand_digit': 0,
    'array': [
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
],
    'word': 'fish',
    'number': 2,
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
    'hello',
],
    'word': 'butterfly',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'sheep',
    'tiger',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'tiger',
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
    '19',
    '19',
    '13',
    '06',
    '13',
],
    'text_data': '575ed2c8d03348e8bdb3be2b6fdf3076',
    'rand_digit': 6,
    'rand_number': 0.88546,
    'rand_signed_int': 6,
    'rand_datetime': '2000-05-26T21:31:14-0400',
    'text_array': [
    'e741b3ed4c6e4864b7a561ce4f6b7dc0',
    '2d8f439320714c5e9cdb488de301f680',
],
    'words': 'scorpion elephant',
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
    'word': 'hippo',
    'number': 10,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fly',
    'mouse',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': [
    34,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'grasshopper',
    'maybe_null': 'duck',
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
    '12',
    '25',
    '13',
    '12',
    '21',
],
    'text_data': 'efaff7c27d304d3c9cbea7d9bb4b6738',
    'rand_digit': 5,
    'rand_number': 0.69096,
    'rand_signed_int': 0,
    'rand_datetime': '2000-03-06 18:19:59.907896',
    'text_array': [
    'cda8fdf842ae41fa8afa7f306eca4124',
    '0b1e12b26d7540659000bcb0e3b1096f',
],
    'words': 'zebra frog',
    'nested': {
    'id': 138,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bear',
    'butterfly',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'leopard',
    'maybe_null': 'hyena',
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
],
    'text_data': 'da701e85ef564571a5a0df5ecf905baa',
    'rand_digit': 3,
    'rand_number': 0.3588,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-02T10:36:52',
    'text_array': [
    '1325d16f98bf4c3c8d9713080ce4e21c',
    'e2268b65f1dc4f639cd5747cd76cd1ce',
],
    'words': 'goat ant',
    'nested': {
    'id': 139,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cat',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'cheetah',
    'giraffe',
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
    'mixed_type': 7,
    'maybe_null': 'leopard',
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
    '08',
    '08',
    '07',
],
    'text_data': 'aa0bd119e21b4100908ade15d6017881',
    'rand_digit': 0,
    'rand_number': 0.31021,
    'rand_signed_int': -4,
    'rand_datetime': '2000-04-27T14:12:00+0900',
    'text_array': [
    '5053d04161be499dabc5a1645973cdb0',
    '52c5d64c4ab74bc585ac9630f21ce86e',
],
    'words': 'hippo ladybug',
    'nested': {
    'id': 140,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'hyena',
    'chicken',
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
    'mixed_type': 2,
    'maybe_null': 'zebra',
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
    '11',
    '10',
],
    'text_data': '3172f4077fdd442d8e44c3b16247de81',
    'rand_digit': 4,
    'rand_number': 0.73232,
    'rand_signed_int': 5,
    'rand_datetime': '2000-06-18T00:38:34.328824',
    'text_array': [
    'd2ac05af01a14a59af3e6c8ec04058fd',
    '347287a718434127a797b4c511636818',
],
    'words': 'leopard bear',
    'nested': {
    'id': 141,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ladybug',
    'rabbit',
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
    'mixed_type': 0.70588,
    'maybe': 'dog',
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
    '26',
    '27',
    '27',
    '08',
],
    'text_data': 'e2dc5d513e064a679581a2b70edc5ed4',
    'rand_digit': 7,
    'rand_number': 0.8397,
    'rand_signed_int': 3,
    'rand_datetime': '2000-10-12 13:35:06.847639',
    'text_array': [
    'a4292012fedf4ca9943dbb5ebe883234',
    'b0b1dd5fa09449549b32174afc03b038',
],
    'words': 'leopard whale',
    'nested': {
    'id': 142,
    'rand_digit': 4,
    'array': [
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
    'word': 'hyena',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'horse',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 7,
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
    'tiger',
    'whale',
],
    'city': {
    'name': 'Cardiff',
    'geo': {
    'lat': 51.481581,
    'lon': -3.17909,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 3,
    'maybe_null': 'deer',
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
    'text_data': 'e444eaa411734090827470bf67454870',
    'rand_digit': 7,
    'rand_number': 0.51552,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-24',
    'text_array': [
    '1ea5cfefa3c54e61a0712314264453ce',
    'ce8593f8815a4107920e4b5b68fdc13f',
],
    'words': 'shark camel',
    'nested': {
    'id': 143,
    'rand_digit': 9,
    'array': [
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
],
    'word': 'shark',
    'number': 9,
},
],
},
    'nested_array': [
    [
    1,
],
],
    'two_words': [
    'dragonfly',
    'fly',
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
    'maybe': 'bear',
    'maybe_null': 'scorpion',
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
    '26',
    '08',
    '04',
    '17',
    '02',
],
    'text_data': '54d76d11cd4441f68c536ed73f377b58',
    'rand_digit': 4,
    'rand_number': 0.72337,
    'rand_signed_int': -2,
    'rand_datetime': '2000-10-28T00:35:54.617416',
    'text_array': [
    '03df62713d664b0c812ceef4aa92dd6b',
    'c2582b549f7f45d99d38069277d82aa9',
],
    'words': 'panda jaguar',
    'nested': {
    'id': 144,
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
    'number': 4,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'monkey',
    'dragonfly',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '27',
    '26',
    '04',
    '02',
    '15',
],
    'text_data': '3ac116ffaee748c78c2c884c683b9423',
    'rand_digit': 1,
    'rand_number': 0.69193,
    'rand_signed_int': -10,
    'rand_datetime': '2001-01-22 09:37:13',
    'text_array': [
    '70b26cfbd54040c8977b56a368663d6f',
    '241a4dfe9af14acbb5b903489f4fbf2d',
],
    'words': 'fish dolphin',
    'nested': {
    'id': 145,
    'rand_digit': 4,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lion',
    'snail',
],
    'city': {
    'name': 'London',
    'geo': {
    'lat': 51.507351,
    'lon': -0.127758,
},
},
    'rand_tuple': [
    62,
],
    'rand_bool': False,
    'mixed_type': 0.46885,
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
],
    'text_data': '571c898438244c6484428f9bd4436fc7',
    'rand_digit': 2,
    'rand_number': 0.71344,
    'rand_signed_int': 2,
    'rand_datetime': '2000-03-14 02:33:40',
    'text_array': [
    'a0ec75597a4c4af5be5b60092091e912',
    '37899a6ca5e9427f9b8d861c85c866a0',
],
    'words': 'tiger ape',
    'nested': {
    'id': 146,
    'rand_digit': 3,
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
    'nested_empty': None,
    'nested_empty2': [
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'sloth',
    'chicken',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': [
    37,
],
    'rand_bool': False,
    'mixed_type': 'crab',
    'maybe': 'elephant',
    'maybe_null': 'ladybug',
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
    '25',
    '29',
    '28',
    '23',
    '03',
],
    'text_data': 'b0e5cfe4a8674a8a98efd1cbd792885c',
    'rand_digit': 7,
    'rand_number': 0.73006,
    'rand_signed_int': -10,
    'rand_datetime': '2000-12-19T20:07:28.312276-1000',
    'text_array': [
    '660860a2872d468db7f20ed8cf9805a4',
    '3b393565f32943e684dad31e4932e6ec',
],
    'words': 'gorilla cat',
    'nested': {
    'id': 147,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'fox',
    'mouse',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': [
    97,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'scorpion',
    'maybe_null': 'mouse',
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
    '30',
    '30',
    '04',
],
    'text_data': 'b6f5f95e90ce4b13a4ebaf704459b9c6',
    'rand_digit': 6,
    'rand_number': 0.10354,
    'rand_signed_int': 3,
    'rand_datetime': '2000-12-02 04:59',
    'text_array': [
    '5ce4c48e20fe49ddae31ec5f31aeaaaf',
    'a08a2b1e6a4245d18d4957a0c7e9d311',
],
    'words': 'dolphin cat',
    'nested': {
    'id': 148,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'kangaroo',
    'cow',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'mouse',
    'maybe_null': 'crab',
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
    '15',
    '16',
    '23',
    '10',
    '14',
],
    'text_data': '80be530000ee4337ac820634dd16569f',
    'rand_digit': 8,
    'rand_number': 0.41785,
    'rand_signed_int': 4,
    'rand_datetime': '2000-05-26T12:23:10',
    'text_array': [
    '5929901c1a7249e2b77978a231409f1a',
    'c70eedee136e427480e42abf9d1e989f',
],
    'words': 'squid hyena',
    'nested': {
    'id': 149,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 9,
},
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
],
    'word': 'crab',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'goat',
    'dog',
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
    '12',
    '10',
    '01',
],
    'text_data': 'a0051f9d101d4f379f6b1ce63d5753a6',
    'rand_digit': 6,
    'rand_number': 0.19272,
    'rand_signed_int': 3,
    'rand_datetime': '2000-05-01 13:22:48',
    'text_array': [
    'fc890b41a5e243519682b8dbe5a60405',
    'e2a5bca383b54267a903a3e4f525eed8',
],
    'words': 'cheetah hyena',
    'nested': {
    'id': 150,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dog',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'cow',
    'camel',
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
    'mixed_type': 2,
    'maybe': 'dolphin',
    'maybe_null': 'shark',
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
    '22',
    '05',
    '11',
],
    'text_data': '1e5b84b38a084229b55db4c3d51df4c9',
    'rand_digit': 4,
    'rand_number': 0.82291,
    'rand_signed_int': -1,
    'rand_datetime': '2001-01-11T08:23:42.586191',
    'text_array': [
    'ef0dd1ac35a74c7295f878c2d8488dce',
    'ea05b96b6e9f478f93f6027bea1f0c5c',
],
    'words': 'squid zebra',
    'nested': {
    'id': 151,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'duck',
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
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
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'hippo',
    'turtle',
],
    'city': {
    'name': 'Johannesburg',
    'geo': {
    'lat': -26.204103,
    'lon': 28.047305,
},
},
    'rand_tuple': [
    69,
],
    'rand_bool': False,
    'mixed_type': 5,
    'maybe': 'sheep',
    'maybe_null': 'wolf',
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
    '14',
],
    'text_data': '771fb43d13c640aab768fc0ad00e687a',
    'rand_digit': 8,
    'rand_number': 0.11236,
    'rand_signed_int': -10,
    'rand_datetime': '2000-09-19 23:50:54.299343+0000',
    'text_array': [
    '4522c0d09b7d4487aaf9dbbfa06301d5',
    'ad8a09af76ea4ff8a2f2baa5b9ac7d66',
],
    'words': 'monkey squid',
    'nested': {
    'id': 152,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'panda',
    'frog',
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
    'mixed_type': False,
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
    '21',
],
    'text_data': 'defb38d16bb9455685a5210f409a12da',
    'rand_digit': 3,
    'rand_number': 0.28401,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-06',
    'text_array': [
    'a2ee515e29014012a3f8e92f41312a81',
    '8e4dfeff4e7d4fa5a36f34536337eb49',
],
    'words': 'cow spider',
    'nested': {
    'id': 153,
    'rand_digit': 9,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'spider',
    'hippo',
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
    'mixed_type': 1,
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
    '26',
    '22',
    '17',
    '29',
    '26',
],
    'text_data': '978b70420d9e478cb52a9658b407545b',
    'rand_digit': 2,
    'rand_number': 0.73633,
    'rand_signed_int': -9,
    'rand_datetime': '2000-11-06T13:22:55-0100',
    'text_array': [
    '486a5cd6f97043f086593e1c8cbcb02b',
    '10b4aab965464110a5370f366d8e26e1',
],
    'words': 'rhino wolf',
    'nested': {
    'id': 154,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'turtle',
    'number': 3,
},
    {
    'nested_empty': None,
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
],
    [
],
],
    'two_words': [
    'ant',
    'rhino',
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
    'maybe': 'monkey',
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
    '05',
    '24',
],
    'text_data': 'b2f1c487860845e694b58e242ff2bd90',
    'rand_digit': 2,
    'rand_number': 0.56808,
    'rand_signed_int': 0,
    'rand_datetime': '2000-01-08 10:33:36.463997',
    'text_array': [
    'af02de2b71d747d8be276edec495253f',
    '9204112df54849a585f135c0ecb61551',
],
    'words': 'rhino elephant',
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
    'word': 'jaguar',
    'number': 9,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -8,
],
],
    'two_words': [
    'monkey',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'ladybug',
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
    '24',
    '15',
    '17',
],
    'text_data': '4aff96bed96e4bda87b2403bf743f232',
    'rand_digit': 9,
    'rand_number': 0.04882,
    'rand_signed_int': -3,
    'rand_datetime': '2000-02-25T13:15:06.850481-1100',
    'text_array': [
    '58fb3244652149b3965fdacbe4472e33',
    'a1c6b89ba8a94453a5dbc3892c70c7d6',
],
    'words': 'cat panda',
    'nested': {
    'id': 156,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
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
    [
    9,
],
],
    'two_words': [
    'elephant',
    'turtle',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 3,
    'maybe': 'giraffe',
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
    '23',
    '07',
    '28',
],
    'text_data': '31a69dff2ffd4b45ac17f4cad09a69ef',
    'rand_digit': 0,
    'rand_number': 0.66077,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-26 00:32:09.103243',
    'text_array': [
    '5fa77f575113489da1a2c149ca4212a5',
    'c181f9f80b6941828c13cd84343fdce5',
],
    'words': 'turtle duck',
    'nested': {
    'id': 157,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    [
    7,
],
],
    'two_words': [
    'kangaroo',
    'frog',
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
    'mixed_type': 'giraffe',
    'maybe': 'scorpion',
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
    '03',
],
    'text_data': '78f85275b7d041e3bc27bd8a22fc4cb2',
    'rand_digit': 3,
    'rand_number': 0.10833,
    'rand_signed_int': 9,
    'rand_datetime': '2000-03-09 05:38:25+0200',
    'text_array': [
    '265a90ec48fe46d6bf8133b8ba228a72',
    '82f377a97fb048c7a1324905902836a6',
],
    'words': 'snake fox',
    'nested': {
    'id': 158,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'wolf',
    'squid',
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
    'mixed_type': 'lion',
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
    '12',
],
    'text_data': '11397c2400bd406ca163487d4c3b394c',
    'rand_digit': 9,
    'rand_number': 0.57703,
    'rand_signed_int': -4,
    'rand_datetime': '2000-12-15 08:19:35.513745-1100',
    'text_array': [
    'cc1536253e194e51bb86ff038e736f5c',
    '3f9d271f5f204336b18945a93ac9bbf1',
],
    'words': 'bear ape',
    'nested': {
    'id': 159,
    'rand_digit': 3,
    'array': [
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
    'word': 'mouse',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'hippo',
    'octopus',
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
    'mixed_type': 9,
    'maybe': 'camel',
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
    '29',
    '26',
    '04',
],
    'text_data': 'aa4e967d89cf4f6c9484dc3c18564094',
    'rand_digit': 9,
    'rand_number': 0.5459,
    'rand_signed_int': 8,
    'rand_datetime': '2000-03-31 08:07:50.700743',
    'text_array': [
    'fa386be3ae7f450db8660b65e12429c6',
    '4265c4bbc95649aa818ca283ff04ff86',
],
    'words': 'ape squid',
    'nested': {
    'id': 160,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'giraffe',
    'fly',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'lobster',
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
    '25',
    '27',
    '11',
    '16',
    '16',
],
    'text_data': '20f24ad89d014f668393d2fbde36e439',
    'rand_digit': 9,
    'rand_number': 0.87037,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-14T17:19:34',
    'text_array': [
    '9f09e472d1274609b66e16d31ada2b2d',
    '67007e28007a490db7d6bccdb2056ee2',
],
    'words': 'cow ant',
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
    'word': 'deer',
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
],
    'word': 'bee',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    10,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'crab',
    'butterfly',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': [
    38,
],
    'rand_bool': False,
    'mixed_type': 'dolphin',
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
    '19',
    '12',
    '17',
    '30',
],
    'text_data': '62ca45c674804bb8ad3500a6d51a6699',
    'rand_digit': 5,
    'rand_number': 0.87789,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-19',
    'text_array': [
    '7ccd0617ca494d50b39670c33549c66c',
    'ce1c3ece9c8a4a8c86016b2c743ceb38',
],
    'words': 'rhino elephant',
    'nested': {
    'id': 162,
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
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
],
    [
    -7,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'shark',
    'lizard',
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
    '08',
    '02',
    '09',
],
    'text_data': '34888230aa744cc08aa2be2e2e5aa318',
    'rand_digit': 5,
    'rand_number': 0.49523,
    'rand_signed_int': 5,
    'rand_datetime': '2000-04-20 04:56:01.528920-0900',
    'text_array': [
    '70aae5d0557b4045b450ff5cd649ce5b',
    'd83d3e6aa2fe4509b2c8f3c0d397fe97',
],
    'words': 'mosquito elephant',
    'nested': {
    'id': 163,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 3,
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
    'elephant',
    'lizard',
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
    'mixed_type': False,
    'maybe': 'mouse',
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
    'content-length': '108',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'recommend': {
    'positive': [
    10,
],
},
},
    'using': 'image',
    'limit': 10,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_query.test_dense_query_recommend')
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
    test = TestQuerytestDenseQueryRecommend()
    test.run_tests()
