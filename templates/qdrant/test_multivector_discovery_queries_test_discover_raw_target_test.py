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
logger = logging.getLogger('vdb_fuzzer.test.test_multivector_discovery_queries_test_discover_raw_target')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_multivector_discovery_queries.test_discover_raw_target"
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



class TestMultivectorDiscoveryQueriestestDiscoverRawTarget:
    """自动生成的VDB模糊测试类 - test_multivector_discovery_queries.test_discover_raw_target"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_multivector_discovery_queries.test_discover_raw_target"
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
    'content-length': '515564',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 100,
    'id_str': [
],
    'text_data': 'cbf35aae39454de0b673f87572782de6',
    'rand_digit': 6,
    'rand_number': 0.11273,
    'rand_signed_int': 4,
    'rand_datetime': '2000-08-12T16:50:59-0300',
    'text_array': [
    'f4be924ee29449f09812eecdf1bbcda3',
    'f482c6093a44499c8c81d7e2db1f2443',
],
    'words': 'goat fly',
    'nested': {
    'id': 100,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'hippo',
    'scorpion',
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
    'mixed_type': 'scorpion',
    'maybe': 'deer',
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 101,
    'id_str': [
    '06',
    '26',
    '06',
    '19',
],
    'text_data': '9eb074bf6a8d4140bca28ef6837795ce',
    'rand_digit': 7,
    'rand_number': 0.77803,
    'rand_signed_int': -7,
    'rand_datetime': '2000-05-04T07:09:43.993988',
    'text_array': [
    '613ef578e58745c3894547a56697b126',
    '81d71dfe18dc41dd90af3f555bf35c46',
],
    'words': 'ape fish',
    'nested': {
    'id': 101,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'sloth',
    'sheep',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'elephant',
    'maybe_null': 'bird',
},
},
    {
    'id': 2,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 102,
    'id_str': [
    '03',
    '27',
    '28',
    '21',
],
    'text_data': '1b85850d7c234c93bf37357df5a53065',
    'rand_digit': 0,
    'rand_number': 0.00305,
    'rand_signed_int': 9,
    'rand_datetime': '2000-01-27T06:54:34+0600',
    'text_array': [
    '372f0bddce1647f7afdfdd2f9930a64a',
    'c8c7b379c5894ac99f9bd8afff8c23e5',
],
    'words': 'shark lion',
    'nested': {
    'id': 102,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 5,
},
    {
    'nested_empty': None,
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
    'word': 'koala',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'snail',
    'ape',
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
    'mixed_type': True,
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 103,
    'id_str': [
    '26',
    '24',
    '18',
    '19',
],
    'text_data': '17313ed7bcc94073a1d81891783048e9',
    'rand_digit': 7,
    'rand_number': 0.74216,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-20 06:53:49-1200',
    'text_array': [
    '71d509f36cec47b6a6b584857e49fcfd',
    '54da8f06008343dbab27963cd8e93e9b',
],
    'words': 'hippo bee',
    'nested': {
    'id': 103,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'ladybug',
    'number': 7,
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
],
    'word': 'kangaroo',
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'horse',
    'lobster',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.48631,
    'maybe_null': 'ant',
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 104,
    'id_str': [
    '28',
    '11',
    '29',
],
    'text_data': '3f88b28d9e7d41b6a764a87d5a040e10',
    'rand_digit': 6,
    'rand_number': 0.25552,
    'rand_signed_int': 6,
    'rand_datetime': '2000-08-21T23:56:03',
    'text_array': [
    'b6f770d6c03943e2bfaa066d9e63c547',
    'c2a9c9ce224a4b148f759270ca069035',
],
    'words': 'spider wolf',
    'nested': {
    'id': 104,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    5,
],
    [
    -2,
],
],
    'two_words': [
    'lobster',
    'ladybug',
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
    'mixed_type': 1,
    'maybe_null': 'camel',
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 105,
    'id_str': [
    '01',
    '08',
    '02',
],
    'text_data': 'b00300a5b7f34a72881543b503ebcd60',
    'rand_digit': 5,
    'rand_number': 0.12762,
    'rand_signed_int': 8,
    'rand_datetime': '2000-11-23T01:43:47',
    'text_array': [
    '5925f4095d104f6e9b01e0cf4bd6c747',
    '685f94c2c1ff42ddbdd6c2477abec9b5',
],
    'words': 'koala dragonfly',
    'nested': {
    'id': 105,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fox',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'lion',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'leopard',
    'leopard',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'squid',
    'maybe_null': 'pig',
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 106,
    'id_str': [
    '23',
    '25',
    '09',
    '23',
],
    'text_data': 'e49ef040f7fb47498910a69b0b36274e',
    'rand_digit': 3,
    'rand_number': 0.19226,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-14 19:28:11.856933+0600',
    'text_array': [
    '91e64baeba344464a7d7da9a974fdbc3',
    '812608df148e4697af2a30e244ad8ab2',
],
    'words': 'goat tiger',
    'nested': {
    'id': 106,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    [
    7,
],
],
    'two_words': [
    'zebra',
    'hippo',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'octopus',
    'maybe_null': None,
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 107,
    'id_str': [
    '30',
    '17',
    '30',
    '30',
],
    'text_data': 'd52bc1411ec84596ae8274a4cbf5b977',
    'rand_digit': 4,
    'rand_number': 0.81112,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-05T00:01:01.018190-1100',
    'text_array': [
    'a3de9d86124848d78623b990014b85ca',
    '4c548d65f41d43519df7ff088fe019bd',
],
    'words': 'snake snake',
    'nested': {
    'id': 107,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 1,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'tiger',
    'fly',
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
    'mixed_type': 0,
    'maybe_null': None,
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 108,
    'id_str': [
    '21',
    '09',
    '25',
    '07',
],
    'text_data': '157a412302754b32bf36c74656c51d61',
    'rand_digit': 6,
    'rand_number': 0.81421,
    'rand_signed_int': 0,
    'rand_datetime': '2000-03-13T08:39:13+0400',
    'text_array': [
    '27ab9652a5074773a2f956f8f373a92c',
    '106cfc7e75f04760bba3cd15dbfff06c',
],
    'words': 'dog jaguar',
    'nested': {
    'id': 108,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 10,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 9,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'mosquito',
    'scorpion',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'frog',
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 109,
    'id_str': [
    '06',
    '03',
    '08',
],
    'text_data': '8a74bfdf8e6e4ea7bbfb5587ed291376',
    'rand_digit': 7,
    'rand_number': 0.63297,
    'rand_signed_int': 10,
    'rand_datetime': '2000-03-15T06:58:45.245882',
    'text_array': [
    '636a665d00ee429587d6f95cf91cef16',
    'cf806cba1f8e41d480ff875bb8d32d0f',
],
    'words': 'gorilla grasshopper',
    'nested': {
    'id': 109,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'turtle',
    'butterfly',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': [
    10,
],
    'rand_bool': True,
    'mixed_type': 'giraffe',
    'maybe': 'bird',
    'maybe_null': 'duck',
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 110,
    'id_str': [
    '01',
    '13',
    '01',
],
    'text_data': '93e83b958c6a4f10905ea71d6fe3a668',
    'rand_digit': 5,
    'rand_number': 0.80619,
    'rand_signed_int': 8,
    'rand_datetime': '2000-07-22T07:03:33.956922',
    'text_array': [
    'b1bfaa0b9192486e91463e0b1cd4ab95',
    'b5561ef1400d460488f7bfe34f9e6499',
],
    'words': 'deer koala',
    'nested': {
    'id': 110,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'scorpion',
    'lobster',
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
    'mixed_type': None,
    'maybe': 'gorilla',
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 111,
    'id_str': [
],
    'text_data': '0fbcde8c21084f0d8889d66fc0499966',
    'rand_digit': 5,
    'rand_number': 0.39833,
    'rand_signed_int': 9,
    'rand_datetime': '2000-03-23T02:59:44.337338-10:00',
    'text_array': [
    '8359fede0217468b8ca935beba841810',
    '12947fc03a224f0db28d6148ce7c6013',
],
    'words': 'snail duck',
    'nested': {
    'id': 111,
    'rand_digit': 1,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'deer',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'deer',
    'shark',
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
    'mixed_type': None,
    'maybe': 'spider',
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 112,
    'id_str': [
    '25',
    '01',
    '11',
    '27',
],
    'text_data': '3eb32c1226d1421890e6c4d786af94c4',
    'rand_digit': 7,
    'rand_number': 0.18349,
    'rand_signed_int': 9,
    'rand_datetime': '2000-12-26T07:48:46.707558',
    'text_array': [
    '27d211e2d9814ff59cbf5259360b5f1f',
    'ca7e37d14b3b455eb2984c492aafeb0e',
],
    'words': 'snail bee',
    'nested': {
    'id': 112,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dog',
    'number': 4,
},
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
    'word': 'koala',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'chicken',
    'fish',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'lion',
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 113,
    'id_str': [
    '21',
    '18',
    '05',
    '01',
],
    'text_data': '870553e09c8d436b84d8f91383f5b419',
    'rand_digit': 4,
    'rand_number': 0.86152,
    'rand_signed_int': 8,
    'rand_datetime': '2000-11-21 03:26',
    'text_array': [
    'ee62b6bbdfc244b795cf9517e591bcef',
    '24439136449e4542bb0f89a03786adad',
],
    'words': 'rabbit mosquito',
    'nested': {
    'id': 113,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 8,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -10,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'tiger',
    'wolf',
],
    'city': {
    'name': 'Barcelona',
    'geo': {
    'lat': 41.385064,
    'lon': 2.173403,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'butterfly',
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 114,
    'id_str': [
    '29',
],
    'text_data': 'b1410157451647ab8dd3c0f04a0bca72',
    'rand_digit': 2,
    'rand_number': 0.76492,
    'rand_signed_int': -6,
    'rand_datetime': '2000-05-18',
    'text_array': [
    '06fcd69686a44501b4a7404976c29896',
    'eb04f259be954cd4b49907bfb915877a',
],
    'words': 'duck ant',
    'nested': {
    'id': 114,
    'rand_digit': 7,
    'array': [
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
],
    'two_words': [
    'bear',
    'scorpion',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': [
    33,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 115,
    'id_str': [
    '04',
    '10',
],
    'text_data': '362de21c114448d990b0b521765f6cdc',
    'rand_digit': 5,
    'rand_number': 0.89049,
    'rand_signed_int': 7,
    'rand_datetime': '2000-02-16 09:45:43',
    'text_array': [
    '159aff79f32344c5ae0b0bcc64524999',
    'c4000f0e887d452c996d72502e520049',
],
    'words': 'jaguar jaguar',
    'nested': {
    'id': 115,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'fly',
    'number': 4,
},
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'spider',
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
    'mixed_type': 0.43221,
    'maybe': 'leopard',
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 116,
    'id_str': [
    '19',
    '07',
    '17',
],
    'text_data': 'd5e4e2b03f704a588f71859d73d8d264',
    'rand_digit': 2,
    'rand_number': 0.77693,
    'rand_signed_int': 7,
    'rand_datetime': '2000-07-01T16:07:31.422011+02:00',
    'text_array': [
    '7fb00f2cc00948d6b634c9b8143f86fa',
    '215476db9de44cabb086170e6aacc667',
],
    'words': 'rhino wolf',
    'nested': {
    'id': 116,
    'rand_digit': 7,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'jaguar',
    'number': 8,
},
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
    'hello',
],
    'word': 'wolf',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'rabbit',
    'mouse',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 117,
    'id_str': [
    '01',
    '12',
],
    'text_data': '2f0bd10745c4450398911555c3c909c7',
    'rand_digit': 1,
    'rand_number': 0.03248,
    'rand_signed_int': 0,
    'rand_datetime': '2000-03-31T00:27:30.296660-09:00',
    'text_array': [
    'e2186c3b849e4ae89314c47d9090a85e',
    'dadee97973bf4b57a8405ce843081793',
],
    'words': 'jaguar bird',
    'nested': {
    'id': 117,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'leopard',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'cheetah',
    'cat',
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
    'mixed_type': False,
    'maybe': 'hippo',
},
},
    {
    'id': 18,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 118,
    'id_str': [
    '23',
    '16',
    '23',
    '15',
],
    'text_data': '8f8a3272fdb84c99bf995625521de7a4',
    'rand_digit': 2,
    'rand_number': 0.17327,
    'rand_signed_int': 1,
    'rand_datetime': '2000-02-02 22:57:04',
    'text_array': [
    '286696e4584943b0886fa3068820e475',
    '4981db7e59e441828625f55a9bd2d637',
],
    'words': 'dragonfly butterfly',
    'nested': {
    'id': 118,
    'rand_digit': 4,
    'array': [
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
    'hello',
],
    'word': 'cow',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'turtle',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'grasshopper',
    'snail',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'mouse',
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
    '09',
    '09',
    '09',
    '28',
],
    'text_data': '76444dfda2be4e99a1c7944fd45b40ef',
    'rand_digit': 5,
    'rand_number': 0.24384,
    'rand_signed_int': -7,
    'rand_datetime': '2000-11-03 09:14:19+1200',
    'text_array': [
    '658bc2a5a3814dffb11ca8e76b2c059e',
    'c2633b902380415aaa9b6f2f828b8e0f',
],
    'words': 'crab fish',
    'nested': {
    'id': 119,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 5,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hyena',
    'mouse',
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
    'maybe': 'gorilla',
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 120,
    'id_str': [
    '06',
],
    'text_data': '94594db4026b48c4afb122876d1f6abb',
    'rand_digit': 2,
    'rand_number': 0.8853,
    'rand_signed_int': -10,
    'rand_datetime': '2000-06-11 07:21',
    'text_array': [
    'a256a85e93b64dafb58609f084971bf2',
    '6fd6de8e4d9f404f9bde7b2f5e8e4cbe',
],
    'words': 'jaguar bee',
    'nested': {
    'id': 120,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'wolf',
    'panda',
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
    'mixed_type': False,
    'maybe': 'deer',
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 121,
    'id_str': [
    '01',
    '24',
    '05',
    '05',
],
    'text_data': '65112eba865f4c57b3743b1f3bf7aa91',
    'rand_digit': 7,
    'rand_number': 0.23993,
    'rand_signed_int': 10,
    'rand_datetime': '2000-06-27T16:25:08.722049-0100',
    'text_array': [
    '229334c77920418bbeed6d5df3b69e53',
    '370e3573cf1f4d88a3e0991d30c6dc2e',
],
    'words': 'mosquito mosquito',
    'nested': {
    'id': 121,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'octopus',
    'number': 2,
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
],
    'two_words': [
    'spider',
    'hippo',
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
    'maybe_null': 'elephant',
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
    '15',
    '14',
    '04',
    '24',
],
    'text_data': 'd166649056244b708a09af0252c44957',
    'rand_digit': 2,
    'rand_number': 0.48327,
    'rand_signed_int': 5,
    'rand_datetime': '2000-02-27',
    'text_array': [
    'a73808380d0943dead5086eaeca64fba',
    '5204fa6a010e4673bf74d9848d3d77a4',
],
    'words': 'fish ladybug',
    'nested': {
    'id': 122,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -4,
],
],
    'two_words': [
    'cheetah',
    'lizard',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 123,
    'id_str': [
    '14',
],
    'text_data': '44463889b6064553a8e772d924506200',
    'rand_digit': 0,
    'rand_number': 0.17347,
    'rand_signed_int': -1,
    'rand_datetime': '2000-01-12 18:06:30.014398',
    'text_array': [
    'f4f16599ef6e46a6a3f60437c62d4db8',
    'cef2d256b2cb4ec097312e5f1009c782',
],
    'words': 'snail bee',
    'nested': {
    'id': 123,
    'rand_digit': 8,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 5,
},
],
},
    'nested_array': [
    [
    7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -9,
],
],
    'two_words': [
    'horse',
    'cat',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'panda',
    'maybe_null': 'horse',
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 124,
    'id_str': [
    '05',
    '18',
    '10',
    '28',
],
    'text_data': 'a8adf142a77e4c73904a0256f614c7dc',
    'rand_digit': 8,
    'rand_number': 0.9119,
    'rand_signed_int': -5,
    'rand_datetime': '2001-01-21T11:39:05.612642-0900',
    'text_array': [
    '825e4b038ec74062961bdab261f71d00',
    '82362cb011434c29872255a3e8d33172',
],
    'words': 'shark sheep',
    'nested': {
    'id': 124,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'snake',
    'number': 10,
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
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'ape',
    'kangaroo',
],
    'city': {
    'name': 'Copenhagen',
    'geo': {
    'lat': 55.676097,
    'lon': 12.568337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 2,
    'maybe': 'horse',
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
    '15',
    '20',
    '08',
],
    'text_data': '01eb8c57aaa34a57b28f511c6dde74ca',
    'rand_digit': 8,
    'rand_number': 0.63211,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-31 20:21:12.480059',
    'text_array': [
    '02e181abc0b64532881a1978e3f482b6',
    'ddee6d1f01c24c4bac42bfc9222fb46c',
],
    'words': 'scorpion gorilla',
    'nested': {
    'id': 125,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 1,
},
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lobster',
    'scorpion',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'snake',
    'maybe': 'koala',
    'maybe_null': None,
},
},
    {
    'id': 26,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 126,
    'id_str': [
    '20',
    '20',
],
    'text_data': '7199a939c1a345979e0350cf7976c4e3',
    'rand_digit': 1,
    'rand_number': 0.0887,
    'rand_signed_int': -3,
    'rand_datetime': '2000-01-09 05:34:37.062219-0500',
    'text_array': [
    '751a0e490c6744478710614d8925f4af',
    '443b7a3e80a2499aa7045c4de7272bf1',
],
    'words': 'rabbit jaguar',
    'nested': {
    'id': 126,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 8,
},
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
    'word': 'lion',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'frog',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'duck',
    'grasshopper',
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
    'mixed_type': False,
    'maybe_null': 'fly',
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 127,
    'id_str': [
    '14',
],
    'text_data': '07148b7e89654a57a7feb2f7de82a24a',
    'rand_digit': 0,
    'rand_number': 0.27633,
    'rand_signed_int': 2,
    'rand_datetime': '2000-02-08',
    'text_array': [
    '0dad5190cdc94d5f9d4bd8c128aea083',
    'e7b942a7b69b4c84aafbdd3326f0eea4',
],
    'words': 'tiger whale',
    'nested': {
    'id': 127,
    'rand_digit': 6,
    'array': [
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
    'word': 'mosquito',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    6,
],
],
    'two_words': [
    'mouse',
    'bird',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'fly',
},
},
    {
    'id': 28,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 128,
    'id_str': [
    '02',
    '12',
    '24',
    '18',
],
    'text_data': 'f3eb513294c14f668d15f1e0d2e8cddb',
    'rand_digit': 1,
    'rand_number': 0.20484,
    'rand_signed_int': -6,
    'rand_datetime': '2000-05-04T05:18:22',
    'text_array': [
    'a6ea2e7c45b14660b22efe6cf66ff859',
    '72c1d085dfdb41dc8613236d01dea763',
],
    'words': 'frog ladybug',
    'nested': {
    'id': 128,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 4,
},
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bear',
    'crab',
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
    'mixed_type': False,
    'maybe': 'kangaroo',
    'maybe_null': 'mouse',
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
    '11',
    '27',
    '24',
],
    'text_data': 'f1fb928b72fa4a30ad17944e87ee7499',
    'rand_digit': 4,
    'rand_number': 0.64995,
    'rand_signed_int': -2,
    'rand_datetime': '2000-08-22 12:45:00',
    'text_array': [
    '0ea4484288c44bfdb83e12ec1962189e',
    '4806b57b9a664de1b851bbc37a58f8cd',
],
    'words': 'snail squid',
    'nested': {
    'id': 129,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
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
    'hello',
],
    'word': 'bear',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -8,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'cheetah',
    'mouse',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fly',
    'maybe_null': 'ape',
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 130,
    'id_str': [
    '03',
],
    'text_data': '13bc1a71dd34406a824c67425be39208',
    'rand_digit': 0,
    'rand_number': 0.60025,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-11T19:32:13.567162-0300',
    'text_array': [
    'e57303db291a45b5aa125e1637f0d003',
    'c3a799e8ec5e4da7b3ddff976937dd65',
],
    'words': 'hippo lobster',
    'nested': {
    'id': 130,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'dog',
    'number': 1,
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
    'word': 'deer',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'duck',
    'fly',
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
    'mixed_type': 'rhino',
    'maybe': 'rabbit',
    'maybe_null': None,
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 131,
    'id_str': [
    '11',
    '06',
    '12',
    '09',
],
    'text_data': 'c9a66340aacd4c02984a9e4277c71c08',
    'rand_digit': 7,
    'rand_number': 0.243,
    'rand_signed_int': -1,
    'rand_datetime': '2000-12-08T15:30:52.053508-0800',
    'text_array': [
    'd5f8a35463384d77a7d35baf89df7f2a',
    '86c28896c7ca4af19fd634e5a7d5f7d6',
],
    'words': 'wolf bear',
    'nested': {
    'id': 131,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ape',
    'number': 10,
},
    {
    'nested_empty': None,
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
],
    'word': 'dog',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'jaguar',
    'snake',
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
    'mixed_type': 6,
    'maybe_null': 'goat',
},
},
    {
    'id': 32,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 132,
    'id_str': [
    '02',
    '02',
    '13',
    '03',
    '20',
],
    'text_data': '11c96cf715984cc5b1a050391792ff1b',
    'rand_digit': 1,
    'rand_number': 0.8488,
    'rand_signed_int': 9,
    'rand_datetime': '2001-01-15 11:45:31+1100',
    'text_array': [
    '61792337e03142a69108fe4e3bfad290',
    '69a927f2d49e4fbf94081b220832cbfc',
],
    'words': 'pig gorilla',
    'nested': {
    'id': 132,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 10,
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
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -1,
],
],
    'two_words': [
    'giraffe',
    'lion',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'snail',
    'maybe_null': 'dog',
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 133,
    'id_str': [
    '15',
    '01',
    '06',
],
    'text_data': 'cd16b04467e24695b057b942ece6a042',
    'rand_digit': 7,
    'rand_number': 0.15844,
    'rand_signed_int': -1,
    'rand_datetime': '2000-12-10T09:28:01.396460+0900',
    'text_array': [
    'b77f5b89e02347eeb5757da1410fdf61',
    '01c3a9c361e84ba2b6a4006188653b24',
],
    'words': 'butterfly turtle',
    'nested': {
    'id': 133,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 2,
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
    'hello',
],
    'word': 'scorpion',
    'number': 4,
},
],
},
    'nested_array': [
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
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 4,
    'maybe': 'kangaroo',
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 134,
    'id_str': [
],
    'text_data': '10f22e35f2764fe6bdadbbee0837a33f',
    'rand_digit': 7,
    'rand_number': 0.05108,
    'rand_signed_int': 9,
    'rand_datetime': '2000-04-12',
    'text_array': [
    '174d5607f9cd48ada6363e168a87cbbc',
    '02e569533c51480fb2d3f9ce9efbea53',
],
    'words': 'wolf goat',
    'nested': {
    'id': 134,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    8,
],
],
    'two_words': [
    'mouse',
    'crab',
],
    'city': {
    'name': 'Cardiff',
    'geo': {
    'lat': 51.481581,
    'lon': -3.17909,
},
},
    'rand_tuple': [
    45,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'whale',
    'maybe_null': 'bear',
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
    '07',
    '21',
    '18',
    '28',
],
    'text_data': '17512f34cac048d9aba5ac937b92fe52',
    'rand_digit': 4,
    'rand_number': 0.12644,
    'rand_signed_int': 1,
    'rand_datetime': '2000-02-14T03:33:29+0600',
    'text_array': [
    'dbe2b15a44e2446485879c36bc5aab68',
    '5cf4afbe78f44c3e9bb1f13bd30ded6e',
],
    'words': 'panda horse',
    'nested': {
    'id': 135,
    'rand_digit': 2,
    'array': [
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
],
    'word': 'cheetah',
    'number': 1,
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
    [
    -8,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'tiger',
    'sloth',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 36,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 136,
    'id_str': [
    '03',
    '22',
    '30',
    '26',
    '16',
],
    'text_data': '35404be7ef3f4f4597073ae02663f0c3',
    'rand_digit': 4,
    'rand_number': 0.76149,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-14T16:45:44.430324+0400',
    'text_array': [
    'ea71f7356d4840e0858322b7c7a825e8',
    '1ee773bc2ad34ef98320177480479262',
],
    'words': 'octopus bee',
    'nested': {
    'id': 136,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'chicken',
    'mosquito',
],
    'city': {
    'name': 'Riga',
    'geo': {
    'lat': 56.949649,
    'lon': 24.105186,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'frog',
    'maybe': 'camel',
    'maybe_null': 'shark',
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
    '14',
    '22',
    '17',
    '11',
    '07',
],
    'text_data': 'f6085270ca9749e492b07747de5b1a7d',
    'rand_digit': 2,
    'rand_number': 0.30344,
    'rand_signed_int': 1,
    'rand_datetime': '2000-08-14 20:30:10.442085',
    'text_array': [
    '1ed911f344f74b08bf7bb8aa51277c79',
    'd0a1853fa8d749e4a394c82b4ebf7053',
],
    'words': 'lizard panda',
    'nested': {
    'id': 137,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'ladybug',
    'dog',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.19542,
    'maybe_null': None,
},
},
    {
    'id': 38,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 138,
    'id_str': [
    '19',
    '22',
    '30',
    '11',
    '28',
],
    'text_data': '8074d70182914d8f886c6171c149b53f',
    'rand_digit': 8,
    'rand_number': 0.92268,
    'rand_signed_int': 6,
    'rand_datetime': '2000-11-04T19:58:44.972070',
    'text_array': [
    '20c9952bd1564cb3832b50029b6b4dc1',
    'ad8bb7a910a54daa852478a339f6f49f',
],
    'words': 'sheep squid',
    'nested': {
    'id': 138,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'turtle',
    'turtle',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 139,
    'id_str': [
    '01',
    '18',
    '03',
],
    'text_data': 'c439d5f513c64d25b638d3c7bbdae345',
    'rand_digit': 9,
    'rand_number': 0.30756,
    'rand_signed_int': -1,
    'rand_datetime': '2000-06-13',
    'text_array': [
    'f3b0541c2f8c43639d476803e1743423',
    '2e7dcc3e6408448dbc3376da5afcf60e',
],
    'words': 'ladybug dolphin',
    'nested': {
    'id': 139,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'lion',
    'mosquito',
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
    'maybe': 'snail',
    'maybe_null': 'lizard',
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 140,
    'id_str': [
],
    'text_data': '169ea09c6dd54afea612d38a70e7ba70',
    'rand_digit': 7,
    'rand_number': 0.18702,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-15T14:26:59.410067',
    'text_array': [
    '2ee280b627544eca8df34ef6ded1229f',
    'cc97615ec827441a98c985a740cba034',
],
    'words': 'bear lion',
    'nested': {
    'id': 140,
    'rand_digit': 9,
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
    'hello',
],
    'word': 'turtle',
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
    'number': 1,
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
],
},
    'nested_array': [
    [
    1,
],
],
    'two_words': [
    'horse',
    'dragonfly',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': [
    74,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 141,
    'id_str': [
    '05',
    '28',
    '28',
    '23',
],
    'text_data': 'bfa9f92edae048f69d133c24d95ef6fe',
    'rand_digit': 3,
    'rand_number': 0.99937,
    'rand_signed_int': 5,
    'rand_datetime': '2001-01-12',
    'text_array': [
    '3aca449166fa4dc684c9a51c9ae906a9',
    '7c15116716f145428a69e85343b92129',
],
    'words': 'jaguar dolphin',
    'nested': {
    'id': 141,
    'rand_digit': 4,
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
],
},
    'nested_array': [
],
    'two_words': [
    'jaguar',
    'cheetah',
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
    'mixed_type': 'ladybug',
    'maybe_null': 'deer',
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 142,
    'id_str': [
],
    'text_data': 'fe9ba23e736a4665a35854bc37881250',
    'rand_digit': 3,
    'rand_number': 0.66249,
    'rand_signed_int': -7,
    'rand_datetime': '2001-01-22 12:28:13',
    'text_array': [
    'e09e9e5a65c549fa9700ee64636a2ccc',
    'd6dce98e347c475298fc5accfe42bf22',
],
    'words': 'grasshopper dog',
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
    'word': 'lion',
    'number': 5,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -2,
],
],
    'two_words': [
    'spider',
    'bird',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'fly',
},
},
    {
    'id': 43,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 143,
    'id_str': [
    '22',
    '23',
    '24',
],
    'text_data': '22c43c990fcb4d2bafea5aeeb33eb325',
    'rand_digit': 3,
    'rand_number': 0.24614,
    'rand_signed_int': -2,
    'rand_datetime': '2000-02-02T07:59:47.952820',
    'text_array': [
    '6996bc7ac19849b6bd152852440d97d3',
    '50f0ded811224a29b9452e9a3c0c448f',
],
    'words': 'leopard rhino',
    'nested': {
    'id': 143,
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
    'hello',
],
    'word': 'jaguar',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'gorilla',
    'rhino',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': [
    79,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'bear',
    'maybe_null': 'ladybug',
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 144,
    'id_str': [
    '04',
    '17',
    '09',
],
    'text_data': 'd4aefddb67314bb9a21677a751ddc9d2',
    'rand_digit': 6,
    'rand_number': 0.82833,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-08 22:06:45.258412',
    'text_array': [
    '198ae7f1dc464092b5fbdf164d3f7b2e',
    '9ed9af83bf0e4c10af78c8544a78820a',
],
    'words': 'leopard monkey',
    'nested': {
    'id': 144,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -4,
],
],
    'two_words': [
    'elephant',
    'cow',
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
    'mixed_type': 'giraffe',
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 145,
    'id_str': [
    '03',
    '16',
    '28',
    '17',
],
    'text_data': '219100c9e7da45fca2745240f27189f1',
    'rand_digit': 9,
    'rand_number': 0.36031,
    'rand_signed_int': -3,
    'rand_datetime': '2000-08-03 14:21',
    'text_array': [
    '7bcf6236a44b418cb357f23fc878d3e4',
    '2901f89cb783412a93c06332b0d668a3',
],
    'words': 'duck jaguar',
    'nested': {
    'id': 145,
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
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ant',
    'octopus',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': [
    47,
],
    'rand_bool': False,
    'mixed_type': None,
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
    '20',
],
    'text_data': 'd0b5879ee84c47cca0ae42c45cdb3339',
    'rand_digit': 0,
    'rand_number': 0.07225,
    'rand_signed_int': 7,
    'rand_datetime': '2000-01-02 01:49:35.634583',
    'text_array': [
    'd31938ccf8004ee8be8d4efe2047c4d5',
    '7f4e31b482a34da998399a0e56fcb655',
],
    'words': 'deer cat',
    'nested': {
    'id': 146,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
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
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 6,
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
],
    'two_words': [
    'whale',
    'grasshopper',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': [
    19,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fox',
},
},
    {
    'id': 47,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 147,
    'id_str': [
    '11',
    '24',
    '13',
    '05',
],
    'text_data': '670d9d7f5fcd4683a9e30702148d2773',
    'rand_digit': 9,
    'rand_number': 0.45732,
    'rand_signed_int': -2,
    'rand_datetime': '2000-11-02 19:56:23',
    'text_array': [
    'd8de38a5832641c7bd8da95dbbe187c5',
    '2b0611d6952747c4a5b1398e6134e649',
],
    'words': 'pig sloth',
    'nested': {
    'id': 147,
    'rand_digit': 5,
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
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'dolphin',
    'cow',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 3,
    'maybe': 'dragonfly',
},
},
    {
    'id': 48,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 148,
    'id_str': [
    '08',
],
    'text_data': 'bf500cfcc8e14bed8ba97d542c4dfe04',
    'rand_digit': 8,
    'rand_number': 0.9557,
    'rand_signed_int': 5,
    'rand_datetime': '2000-02-11 11:51:32.401099',
    'text_array': [
    '4852531b177f4655a0c90be276fffb56',
    'a259b839144c48b493fe240289c4bbe1',
],
    'words': 'spider grasshopper',
    'nested': {
    'id': 148,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'elephant',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ape',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    [
    -9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'spider',
    'octopus',
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
    'maybe': 'hyena',
    'maybe_null': 'mosquito',
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 149,
    'id_str': [
    '29',
],
    'text_data': 'c24a03431b004789ba215e881cc4a170',
    'rand_digit': 2,
    'rand_number': 0.71029,
    'rand_signed_int': -5,
    'rand_datetime': '2001-01-05 15:25:24.037584',
    'text_array': [
    '380422711d97481ca2b68a2a2ec7d63c',
    '02f5e4bbbb544a42b21c3123ab75f54d',
],
    'words': 'shark lizard',
    'nested': {
    'id': 149,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'goat',
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
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 3,
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
],
    'two_words': [
    'snail',
    'snail',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.04539,
    'maybe': 'ladybug',
},
},
    {
    'id': 50,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 150,
    'id_str': [
    '19',
    '30',
    '30',
    '09',
    '05',
],
    'text_data': '0d0ba70ccd174743a510388d1dd80855',
    'rand_digit': 0,
    'rand_number': 0.50848,
    'rand_signed_int': -1,
    'rand_datetime': '2000-12-29T16:13:37.405125',
    'text_array': [
    'b5b7e860476b4566944a0bfba9ba1289',
    'a9a902e0b3c6490f944b61ae9227db08',
],
    'words': 'fly rhino',
    'nested': {
    'id': 150,
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
],
    'word': 'lizard',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lion',
    'shark',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 51,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 151,
    'id_str': [
],
    'text_data': '64402102f2524c67a9c91ad494776c8f',
    'rand_digit': 8,
    'rand_number': 0.88512,
    'rand_signed_int': -8,
    'rand_datetime': '2000-07-22 03:41',
    'text_array': [
    'c61da8960e3e4a1c8ead5ef7505dafa0',
    '221581dd406447d3b8d9c8c5a80ccc55',
],
    'words': 'bear monkey',
    'nested': {
    'id': 151,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'ladybug',
    'sheep',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'tiger',
    'maybe': 'koala',
    'maybe_null': 'goat',
},
},
    {
    'id': 52,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 152,
    'id_str': [
    '27',
],
    'text_data': 'e84f04302b884e26b295a5e163b18bde',
    'rand_digit': 5,
    'rand_number': 0.0046,
    'rand_signed_int': 9,
    'rand_datetime': '2000-09-17T18:00:07.998583',
    'text_array': [
    'a7ac15a54bf84c6fa119a32292762782',
    'af7cbeef77234018afb9e8365d417ae4',
],
    'words': 'fly fly',
    'nested': {
    'id': 152,
    'rand_digit': 1,
    'array': [
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
    'word': 'snail',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'crab',
    'ape',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'whale',
},
},
    {
    'id': 53,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 153,
    'id_str': [
    '22',
    '03',
    '30',
    '25',
],
    'text_data': 'f8f20df5eabf45b7adba5c609ff39838',
    'rand_digit': 2,
    'rand_number': 0.63482,
    'rand_signed_int': 0,
    'rand_datetime': '2000-06-29 10:51:05-0100',
    'text_array': [
    '0589a9b14fec40fe9f23745b60198d28',
    '01d070f2911446f1a140c6c22579a79b',
],
    'words': 'sloth leopard',
    'nested': {
    'id': 153,
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
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'shark',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -10,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dolphin',
    'horse',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'leopard',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 54,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 154,
    'id_str': [
    '08',
    '14',
    '11',
],
    'text_data': '774bd5aa31c04de4801c2c2767983769',
    'rand_digit': 8,
    'rand_number': 0.17571,
    'rand_signed_int': -9,
    'rand_datetime': '2000-02-07 11:25:01+1100',
    'text_array': [
    'ee5181acfca7465a84276911ca493d89',
    '3a99aab866a442748ce1d994648ccac5',
],
    'words': 'scorpion gorilla',
    'nested': {
    'id': 154,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 8,
},
    {
    'nested_empty': None,
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
    'word': 'fox',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -1,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ant',
    'gorilla',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 55,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 155,
    'id_str': [
    '18',
    '02',
    '14',
    '17',
],
    'text_data': 'ba94c89b42e64314870569953fffd1a3',
    'rand_digit': 4,
    'rand_number': 0.48365,
    'rand_signed_int': -2,
    'rand_datetime': '2000-03-26 14:55:23',
    'text_array': [
    '33f1cbd674df4eb2b0488259e0f65cb7',
    '037772ffd69e419bb2e1c79941c47dbf',
],
    'words': 'fox snail',
    'nested': {
    'id': 155,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 9,
},
    {
    'nested_empty': None,
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
    'word': 'cheetah',
    'number': 3,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'rhino',
    'pig',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': [
    73,
],
    'rand_bool': True,
    'mixed_type': 0,
    'maybe_null': 'squid',
},
},
    {
    'id': 56,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 156,
    'id_str': [
    '15',
],
    'text_data': 'd3922165bf4e45ce906572a5ff0250d7',
    'rand_digit': 4,
    'rand_number': 0.21886,
    'rand_signed_int': 3,
    'rand_datetime': '2001-01-30T13:04:17.189589',
    'text_array': [
    '543ec2381b694abca9a6a5b0cffa8da4',
    '40cac4040e1c4d318c81adf0407aa767',
],
    'words': 'fox lizard',
    'nested': {
    'id': 156,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'leopard',
    'koala',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': [
    78,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'ant',
    'maybe_null': 'gorilla',
},
},
    {
    'id': 57,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 157,
    'id_str': [
    '25',
],
    'text_data': 'a1aa58e21d384e9ab876f516e3a0cf38',
    'rand_digit': 8,
    'rand_number': 0.93877,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-21 07:41:29',
    'text_array': [
    '96f860ee65f448c2aeba9c2e8259edf6',
    '40c84bfe27eb425f85e7ab73bcb05ee4',
],
    'words': 'dragonfly hyena',
    'nested': {
    'id': 157,
    'rand_digit': 5,
    'array': [
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lobster',
    'snail',
],
    'city': {
    'name': 'Barcelona',
    'geo': {
    'lat': 41.385064,
    'lon': 2.173403,
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
    'id': 58,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 158,
    'id_str': [
    '16',
    '28',
],
    'text_data': '6aff29ced7dd45ed9643b0b07397854c',
    'rand_digit': 5,
    'rand_number': 0.76442,
    'rand_signed_int': 2,
    'rand_datetime': '2000-11-27T05:19:43.118007-1100',
    'text_array': [
    '655adb5a85d84474af88fab94fcb0867',
    '72099a0a728e441faecd57173a6fddaa',
],
    'words': 'bear panda',
    'nested': {
    'id': 158,
    'rand_digit': 1,
    'array': [
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
    'word': 'frog',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'koala',
    'rhino',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'panda',
    'maybe_null': 'lizard',
},
},
    {
    'id': 59,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 159,
    'id_str': [
],
    'text_data': 'f3cd74e880764f098c615f8075502f10',
    'rand_digit': 5,
    'rand_number': 0.8716,
    'rand_signed_int': 7,
    'rand_datetime': '2000-05-27 16:09:16',
    'text_array': [
    '75d51af8d03944319b806c88ddd5b660',
    '0651a02e3a9c4c9eb4c8aeafe0ac2c0d',
],
    'words': 'ladybug mouse',
    'nested': {
    'id': 159,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
    'number': 1,
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
],
    'two_words': [
    'lobster',
    'elephant',
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
    'mixed_type': 7,
    'maybe_null': 'giraffe',
},
},
    {
    'id': 60,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 160,
    'id_str': [
],
    'text_data': '6a8ab08e4fb04963be8d1df2fed3b7b1',
    'rand_digit': 2,
    'rand_number': 0.75318,
    'rand_signed_int': 2,
    'rand_datetime': '2001-01-29T00:07:39.845523+1100',
    'text_array': [
    '0fbcbd83c7b243c78ecf21447cba2330',
    'c40ccc72cadb499fb3a8422a428bdfa2',
],
    'words': 'wolf rabbit',
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
    'word': 'lobster',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
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
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'turtle',
    'number': 5,
},
],
},
    'nested_array': [
    [
    -5,
],
    [
    -2,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    4,
],
],
    'two_words': [
    'squid',
    'lion',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'fly',
},
},
    {
    'id': 61,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 161,
    'id_str': [
    '14',
    '02',
    '18',
    '17',
    '23',
],
    'text_data': 'b7d8cc383e1c4b4db4497dbeaa767622',
    'rand_digit': 7,
    'rand_number': 0.29067,
    'rand_signed_int': 3,
    'rand_datetime': '2000-07-18 13:21:24.690287',
    'text_array': [
    '3ae2f089b3a8489085fe167a2038c8b2',
    '6f70bca214c04ba3a2bf55c0e340a31f',
],
    'words': 'bird cheetah',
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
    'word': 'cheetah',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 7,
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
    'word': 'leopard',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'wolf',
    'fly',
],
    'city': {
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
},
},
    {
    'id': 62,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 162,
    'id_str': [
    '02',
    '12',
],
    'text_data': 'fe34a8555ba4422eacb738e06d89c11d',
    'rand_digit': 9,
    'rand_number': 0.72596,
    'rand_signed_int': -3,
    'rand_datetime': '2000-11-15T10:48:49.269236+02:00',
    'text_array': [
    '16e7b94f95a4431d9d77e325f5685c01',
    '11cc73f007d6447681c18c969367e7b4',
],
    'words': 'mosquito lion',
    'nested': {
    'id': 162,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    [
    -9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -10,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'tiger',
    'ape',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'mosquito',
    'maybe_null': 'lizard',
},
},
    {
    'id': 63,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 163,
    'id_str': [
    '02',
    '14',
    '24',
    '16',
],
    'text_data': '71dabdac7fb040a7bee68a2b4baed717',
    'rand_digit': 4,
    'rand_number': 0.85328,
    'rand_signed_int': 10,
    'rand_datetime': '2000-08-21T03:04:59+0300',
    'text_array': [
    'd14b74b50b7445e2886c51febf854d1e',
    'dead4454db094e18b9cb018d2ab3f50a',
],
    'words': 'whale panda',
    'nested': {
    'id': 163,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -9,
],
],
    'two_words': [
    'camel',
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
    'content-length': '415013',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 100,
    'id_str': [
    '17',
    '23',
    '28',
],
    'text_data': '5082c22ec14d4b188042583f053f2067',
    'rand_digit': 1,
    'rand_number': 0.01752,
    'rand_signed_int': 10,
    'rand_datetime': '2000-03-28T20:36:56.216799',
    'text_array': [
    '12a85b2b42a24a81a30554c18e2e6d6f',
    'c8da7c68f3c84a06ba55a215829fc8df',
],
    'words': 'bee duck',
    'nested': {
    'id': 100,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    [
    -6,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snail',
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
    'mixed_type': None,
    'maybe': 'deer',
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 101,
    'id_str': [
],
    'text_data': '5bb8e54d430b4e9d8861c6aa449ada09',
    'rand_digit': 8,
    'rand_number': 0.872,
    'rand_signed_int': 4,
    'rand_datetime': '2000-12-05 21:41:26.385650',
    'text_array': [
    '25f5b5b617c24438ad9466aaff76f277',
    '09abf0ea731c4bf5a41b9844e085999c',
],
    'words': 'scorpion turtle',
    'nested': {
    'id': 101,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    [
    -10,
],
    [
    -4,
],
],
    'two_words': [
    'hippo',
    'pig',
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
    'mixed_type': None,
    'maybe_null': 'fox',
},
},
    {
    'id': 2,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 102,
    'id_str': [
    '04',
    '05',
    '18',
],
    'text_data': '854db3337be0495bb48e5063411d21c2',
    'rand_digit': 0,
    'rand_number': 0.00991,
    'rand_signed_int': 0,
    'rand_datetime': '2001-01-04 23:50:37.402454+0300',
    'text_array': [
    '93fa93cf4a4b46ce909966350f2c1ddc',
    '2f671127f6544f87a5f65b8bd9978fa7',
],
    'words': 'ape hippo',
    'nested': {
    'id': 102,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'crab',
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
    'number': 3,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'hyena',
    'wolf',
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
    'mixed_type': 'crab',
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 103,
    'id_str': [
    '20',
],
    'text_data': 'c4571bd3232b4f1587447c9355573e7b',
    'rand_digit': 1,
    'rand_number': 0.31069,
    'rand_signed_int': 5,
    'rand_datetime': '2000-11-08',
    'text_array': [
    '072794e3eb8e4dc4adb15fa0585596f1',
    '4347f8e336f24f67ad308f4871f7998c',
],
    'words': 'fly frog',
    'nested': {
    'id': 103,
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
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'kangaroo',
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
    [
    -1,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -2,
],
],
    'two_words': [
    'panda',
    'crab',
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
    'mixed_type': True,
    'maybe_null': 'horse',
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 104,
    'id_str': [
    '03',
    '05',
],
    'text_data': '87f294c7131349479166dd16f1fe2c00',
    'rand_digit': 4,
    'rand_number': 0.50735,
    'rand_signed_int': 1,
    'rand_datetime': '2000-09-14T04:34:10',
    'text_array': [
    '870c1ca833c0479c827124069beadd05',
    '5f45dfa7738349869e28e0ddc8b63962',
],
    'words': 'snake squid',
    'nested': {
    'id': 104,
    'rand_digit': 1,
    'array': [
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
    'word': 'gorilla',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'hippo',
    'fox',
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
    'mixed_type': None,
    'maybe': 'lizard',
    'maybe_null': 'spider',
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 105,
    'id_str': [
    '18',
    '14',
    '21',
    '10',
],
    'text_data': '1b29327bcdc64664b04e34883d3d5e7e',
    'rand_digit': 7,
    'rand_number': 0.22016,
    'rand_signed_int': 1,
    'rand_datetime': '2000-07-27T12:26:46-0700',
    'text_array': [
    '68692a0b5bb74e85bb518acb08c54579',
    'fac095579928407280cd25477e4b279b',
],
    'words': 'fish lion',
    'nested': {
    'id': 105,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
    6,
],
],
    'two_words': [
    'snail',
    'pig',
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
    'mixed_type': True,
    'maybe_null': 'horse',
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 106,
    'id_str': [
    '14',
    '02',
    '04',
],
    'text_data': '53525d59d27547de8e00f45c5ce81084',
    'rand_digit': 3,
    'rand_number': 0.0509,
    'rand_signed_int': 5,
    'rand_datetime': '2000-11-06 07:36:34',
    'text_array': [
    'ce9600f4f5ff4321a1f1e7e7d104759c',
    'c027e89f0fee44538bbfeb5e59948742',
],
    'words': 'fox octopus',
    'nested': {
    'id': 106,
    'rand_digit': 0,
    'array': [
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
    'word': 'dog',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 9,
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
    'nested_array': [
],
    'two_words': [
    'zebra',
    'sheep',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'koala',
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 107,
    'id_str': [
],
    'text_data': '82326fc5c451492aae07425d3fe988e4',
    'rand_digit': 9,
    'rand_number': 0.71937,
    'rand_signed_int': -2,
    'rand_datetime': '2000-11-13 10:44:15.081943',
    'text_array': [
    '75fdf3a6abe34ec6b463c67d558fe417',
    '5f188d8823cf4ea086d3cb9b9e5de886',
],
    'words': 'ape whale',
    'nested': {
    'id': 107,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'pig',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'crab',
    'gorilla',
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
    'mixed_type': 0.35377,
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 108,
    'id_str': [
    '25',
    '17',
    '17',
    '18',
    '04',
],
    'text_data': '1d89dedf83cd470d9ecc2c6813466359',
    'rand_digit': 4,
    'rand_number': 0.95167,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-26T04:02:50',
    'text_array': [
    '71ca79c6726149f4b07f77437115390b',
    '976d0c119fe3438f82d09c422e80ba02',
],
    'words': 'bird fly',
    'nested': {
    'id': 108,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
    -3,
],
    [
    -3,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dog',
    'leopard',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': [
    18,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'mouse',
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 109,
    'id_str': [
    '19',
],
    'text_data': '212fa578eed9474ca75c75e240ee6737',
    'rand_digit': 6,
    'rand_number': 0.98445,
    'rand_signed_int': 8,
    'rand_datetime': '2000-09-16',
    'text_array': [
    'dd38f880c9824fda8e0b341e5e8f4bf7',
    '3365012892314f82bd505afa958296c4',
],
    'words': 'rabbit sloth',
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
    'word': 'bird',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cheetah',
    'squid',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': [
    72,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'koala',
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 110,
    'id_str': [
    '26',
    '22',
    '01',
],
    'text_data': '040ebdd2fdae467d85f4c4526724b6a7',
    'rand_digit': 8,
    'rand_number': 0.61697,
    'rand_signed_int': 2,
    'rand_datetime': '2000-02-18T08:25:52.115188+1100',
    'text_array': [
    'c494920f1add4756a33bac4c09bd0f87',
    'ff13ac04ecf74bf78130bf1bfa4de350',
],
    'words': 'dolphin ape',
    'nested': {
    'id': 110,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'mouse',
    'snail',
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
    'maybe_null': 'octopus',
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 111,
    'id_str': [
    '24',
    '04',
    '28',
    '17',
],
    'text_data': 'f2d1d1298a4043e39a892e0febbb89e6',
    'rand_digit': 6,
    'rand_number': 0.59563,
    'rand_signed_int': 9,
    'rand_datetime': '2000-05-01T19:48:58.881644',
    'text_array': [
    'eb2ae59017694dbeadb77890e977f1f4',
    '3630aa4339fe45158742584ebc73c066',
],
    'words': 'hyena dragonfly',
    'nested': {
    'id': 111,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'bear',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    3,
],
],
    'two_words': [
    'hyena',
    'bear',
],
    'city': {
    'name': 'Barcelona',
    'geo': {
    'lat': 41.385064,
    'lon': 2.173403,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'grasshopper',
    'maybe': 'rhino',
    'maybe_null': None,
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 112,
    'id_str': [
    '01',
    '08',
    '25',
    '10',
    '14',
],
    'text_data': '15adba1dc4204eee8d1f133827c04276',
    'rand_digit': 1,
    'rand_number': 0.11778,
    'rand_signed_int': -2,
    'rand_datetime': '2000-03-07T11:19:58+1100',
    'text_array': [
    'a1a904adb8034efe8174437078d66126',
    'a1addedaeac9461991269fd38360debe',
],
    'words': 'panda horse',
    'nested': {
    'id': 112,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 1,
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
],
},
    'nested_array': [
    [
    -1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bird',
    'shark',
],
    'city': {
    'name': 'Johannesburg',
    'geo': {
    'lat': -26.204103,
    'lon': 28.047305,
},
},
    'rand_tuple': [
    27,
],
    'rand_bool': False,
    'mixed_type': 0.17985,
    'maybe': 'octopus',
    'maybe_null': None,
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 113,
    'id_str': [
    '24',
    '10',
    '13',
],
    'text_data': '2344dddf5f5143b79f5a403e84d1b32e',
    'rand_digit': 4,
    'rand_number': 0.22359,
    'rand_signed_int': 8,
    'rand_datetime': '2000-08-05 01:43:48+0800',
    'text_array': [
    '78a1e35280ee4d9191439a1f91a823ec',
    'c6490a5f9c37422daa8b1ef8a8d28378',
],
    'words': 'lizard rhino',
    'nested': {
    'id': 113,
    'rand_digit': 9,
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
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'snake',
    'frog',
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
    'maybe_null': 'deer',
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 114,
    'id_str': [
    '02',
    '13',
    '02',
    '20',
],
    'text_data': '01463fec3ade4588b54c2d0072b2d892',
    'rand_digit': 2,
    'rand_number': 0.04882,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-19T00:41:18.870627',
    'text_array': [
    'a33930a77c6b437a866b31791fd9954f',
    'be39a10ea834421fbccd3d959544e19b',
],
    'words': 'cow koala',
    'nested': {
    'id': 114,
    'rand_digit': 0,
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
],
    'word': 'snail',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'lobster',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'grasshopper',
    'maybe_null': 'ant',
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 115,
    'id_str': [
    '23',
    '25',
    '18',
    '27',
],
    'text_data': 'ed934dc280fd4150813b623be748ccba',
    'rand_digit': 9,
    'rand_number': 0.78705,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-16T19:32:23.682302',
    'text_array': [
    '4b093ab27cd74a918ab663b72e21c91d',
    '5b7a853e2f9840fcaa02b141b9bf9110',
],
    'words': 'bee frog',
    'nested': {
    'id': 115,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 7,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 7,
},
],
},
    'nested_array': [
    [
    -8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'shark',
    'horse',
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
    'mixed_type': 'pig',
    'maybe': 'squid',
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 116,
    'id_str': [
    '27',
    '20',
    '03',
],
    'text_data': '2e27a2a37e374577892abd5349172a97',
    'rand_digit': 7,
    'rand_number': 0.14165,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-22T19:14:44-0400',
    'text_array': [
    '4fafefd904b24c919326cbe2cdaa0742',
    'cd592618bb1a46938e14896d62a85b03',
],
    'words': 'tiger scorpion',
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
    'word': 'octopus',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'pig',
    'ladybug',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'jaguar',
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 117,
    'id_str': [
    '15',
],
    'text_data': '80964c6deccd4b4da389c17ab34a0ef8',
    'rand_digit': 9,
    'rand_number': 0.08818,
    'rand_signed_int': -3,
    'rand_datetime': '2000-08-26T15:20:28.157065-0300',
    'text_array': [
    '6a1b76875ba540a9b4231a5d5ff2cc87',
    '16e5315babb54c4097bf865b472d853e',
],
    'words': 'cat leopard',
    'nested': {
    'id': 117,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'frog',
    'gorilla',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': [
    93,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cheetah',
},
},
    {
    'id': 18,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 118,
    'id_str': [
    '24',
    '01',
],
    'text_data': '37bf04490f1a46fa972ee5b496e272e7',
    'rand_digit': 4,
    'rand_number': 0.40286,
    'rand_signed_int': 0,
    'rand_datetime': '2000-08-07',
    'text_array': [
    '23230c311cde4e36a77c2e7a3071bfe6',
    'a87fa4702aa24a87b2524fba6aaf5423',
],
    'words': 'zebra duck',
    'nested': {
    'id': 118,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'fish',
    'goat',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
    '12',
    '21',
    '14',
    '04',
],
    'text_data': '99e248ab660349c3b530e037328e02d5',
    'rand_digit': 3,
    'rand_number': 0.33446,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-08T02:04:05.265314',
    'text_array': [
    'e18e1c0d27164333979eb74402b14ac8',
    'dc3b3db5bbc84c0eb73c7f2352e251e4',
],
    'words': 'koala panda',
    'nested': {
    'id': 119,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'tiger',
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
    'hippo',
    'mosquito',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 'lobster',
    'maybe': 'koala',
    'maybe_null': None,
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 120,
    'id_str': [
    '13',
    '17',
    '03',
],
    'text_data': '139340c983a0428bb8d3518afe57390d',
    'rand_digit': 7,
    'rand_number': 0.8788,
    'rand_signed_int': 1,
    'rand_datetime': '2000-03-22T23:15:21',
    'text_array': [
    '7af837b0252545a59ef1da9a746f52b7',
    '343e1cdab89440789d80d61b4d4b3191',
],
    'words': 'goat leopard',
    'nested': {
    'id': 120,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -1,
],
],
    'two_words': [
    'ant',
    'monkey',
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
    'maybe_null': None,
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 121,
    'id_str': [
    '05',
    '05',
    '02',
    '26',
    '25',
],
    'text_data': 'a3f11ee8bcf3486e871d4e732823f226',
    'rand_digit': 7,
    'rand_number': 0.34971,
    'rand_signed_int': -4,
    'rand_datetime': '2000-07-03T07:29:56',
    'text_array': [
    '5b708b16be7b44e58aa8b2a6e806a112',
    '60a6371e5b214730969a780e57dd5d2a',
],
    'words': 'zebra frog',
    'nested': {
    'id': 121,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 10,
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
    'word': 'ape',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'mosquito',
    'shark',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': [
    93,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
    '17',
    '11',
],
    'text_data': 'adfdaf46312f40d58ec52e50350a9d35',
    'rand_digit': 3,
    'rand_number': 0.60886,
    'rand_signed_int': -5,
    'rand_datetime': '2000-02-11 06:54',
    'text_array': [
    '9b4615f7c93b402b9c942937d4132e39',
    '57c042668fab417194eae39e72ef6c99',
],
    'words': 'bird mosquito',
    'nested': {
    'id': 122,
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
    'word': 'wolf',
    'number': 9,
},
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'koala',
    'giraffe',
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
    'mixed_type': True,
    'maybe_null': 'squid',
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 123,
    'id_str': [
],
    'text_data': '4b293ee2c34a4b81a98fd37e1cdb27a9',
    'rand_digit': 5,
    'rand_number': 0.98896,
    'rand_signed_int': 10,
    'rand_datetime': '2000-08-28 19:48:35.605893',
    'text_array': [
    'ee4c754abb2c4f1bb888fc3d1a2edd21',
    '7c42dcf357c94e259484a65272219406',
],
    'words': 'goat scorpion',
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
    'word': 'bear',
    'number': 8,
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
    'hello',
],
    'word': 'sheep',
    'number': 2,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'butterfly',
    'number': 2,
},
],
},
    'nested_array': [
    [
    -10,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'turtle',
    'lizard',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': [
    66,
],
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'dog',
    'maybe_null': None,
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 124,
    'id_str': [
    '28',
    '29',
],
    'text_data': '5e8fb1237a1743fa918dd92bc732c73f',
    'rand_digit': 2,
    'rand_number': 0.01365,
    'rand_signed_int': 5,
    'rand_datetime': '2000-02-29T23:53:24',
    'text_array': [
    '01c16f545afe4f12bf8537877fd418a4',
    '4ad0777a4a904c6892d2c356823fb6fc',
],
    'words': 'scorpion whale',
    'nested': {
    'id': 124,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'rhino',
    'ant',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': [
    33,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'pig',
    'maybe_null': None,
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
    '04',
    '19',
],
    'text_data': '593bbb7c3c7e49e7b1e1f712be801e4b',
    'rand_digit': 1,
    'rand_number': 0.0783,
    'rand_signed_int': -1,
    'rand_datetime': '2000-12-01 06:43:49.497019-0400',
    'text_array': [
    '9fe013704a2e497aabf9cd91a6cc8dbe',
    'b209758ac74d4314a6465c4da63b85e6',
],
    'words': 'ant panda',
    'nested': {
    'id': 125,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'ladybug',
    'turtle',
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
    'mixed_type': 4,
    'maybe': 'panda',
    'maybe_null': 'snail',
},
},
    {
    'id': 26,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 126,
    'id_str': [
    '16',
    '26',
    '19',
    '14',
],
    'text_data': '9c39abb25f3141bc970424490cb0ba40',
    'rand_digit': 1,
    'rand_number': 0.81627,
    'rand_signed_int': -7,
    'rand_datetime': '2000-05-24 00:26:39.769604',
    'text_array': [
    'd27a6d0cd134485c8ccd7ea36b96d1e1',
    'a1f223e4679c4a0ab86341c2e4c51fef',
],
    'words': 'rabbit snake',
    'nested': {
    'id': 126,
    'rand_digit': 7,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
    1,
],
],
    'two_words': [
    'rhino',
    'frog',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'dolphin',
    'maybe_null': 'snake',
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 127,
    'id_str': [
],
    'text_data': '8b6313315fca41698c11845870d7b4c2',
    'rand_digit': 0,
    'rand_number': 0.62565,
    'rand_signed_int': -8,
    'rand_datetime': '2000-10-29 10:02:51-1000',
    'text_array': [
    '406390c12c404ee2b9487b651a8deb24',
    '4d11a30b921746e18a1a76fdf9480d85',
],
    'words': 'kangaroo snail',
    'nested': {
    'id': 127,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    7,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'mouse',
    'mouse',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'bee',
},
},
    {
    'id': 28,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 128,
    'id_str': [
    '15',
    '09',
    '14',
    '11',
    '26',
],
    'text_data': 'e435211e97704e749657c5e66a182626',
    'rand_digit': 1,
    'rand_number': 0.32065,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-08T15:20:11',
    'text_array': [
    '061adb6eab9b472b9eb74e0755ac1bc5',
    '5fc52cfdc7d84e20a601f8a4a527d2ae',
],
    'words': 'dolphin leopard',
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
    'word': 'goat',
    'number': 3,
},
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'sheep',
    'sheep',
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
    'maybe_null': 'crab',
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
    '08',
    '06',
    '30',
    '04',
    '04',
],
    'text_data': '881196dbffbc45b69cf891a0344e206b',
    'rand_digit': 8,
    'rand_number': 0.71151,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-18 13:21',
    'text_array': [
    '53eaafeef0e14a69b5684c7723a11660',
    '3a55b1f0c81545c9b3b03083d1107aad',
],
    'words': 'panda wolf',
    'nested': {
    'id': 129,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
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
    'snake',
    'goat',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'bear',
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 130,
    'id_str': [
    '30',
    '07',
    '04',
],
    'text_data': '22568d4455fc4e13a8005953abcbd164',
    'rand_digit': 3,
    'rand_number': 0.69152,
    'rand_signed_int': 7,
    'rand_datetime': '2000-12-31T07:01:14.280996-05:00',
    'text_array': [
    '7d3d5475304d415e969b211d04b37430',
    'abe3820eeb1349ecaf89c8273eb03234',
],
    'words': 'rabbit snake',
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
    'word': 'jaguar',
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
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'pig',
    'sheep',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'bee',
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 131,
    'id_str': [
    '01',
    '01',
],
    'text_data': 'b4ea7a86f42f4539b1ac191c898f1e63',
    'rand_digit': 2,
    'rand_number': 0.10596,
    'rand_signed_int': 8,
    'rand_datetime': '2000-03-12T14:06:36.950782-09:00',
    'text_array': [
    'dfba3745ff2b46bab0377e9d119504ee',
    '8e82f0a0af6d4781881d54932ac0d89e',
],
    'words': 'lion grasshopper',
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
    'word': 'spider',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'octopus',
    'ape',
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
    'mixed_type': None,
},
},
    {
    'id': 32,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 132,
    'id_str': [
    '29',
    '15',
],
    'text_data': '51d37e06e9b04c3e8520ad9b6dda5ded',
    'rand_digit': 6,
    'rand_number': 0.57564,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-18',
    'text_array': [
    'ee4425119a314af5b123714739eb2e3c',
    '897dfe1af8464af981ca1adf7c17d381',
],
    'words': 'ladybug koala',
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
    'word': 'ape',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'frog',
    'horse',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'bee',
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 133,
    'id_str': [
    '29',
    '28',
    '11',
    '03',
    '16',
],
    'text_data': '68cf6fa3166942c6b0cfd14c420cf457',
    'rand_digit': 6,
    'rand_number': 0.40919,
    'rand_signed_int': 1,
    'rand_datetime': '2000-04-27T14:15:25+0100',
    'text_array': [
    'f537bfc848b44c1bb495fed524c8ee2f',
    '4936c4e21cff41d28952e5d4a94d70d2',
],
    'words': 'giraffe ape',
    'nested': {
    'id': 133,
    'rand_digit': 3,
    'array': [
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'tiger',
    'cheetah',
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
    'mixed_type': True,
    'maybe_null': 'pig',
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 134,
    'id_str': [
    '30',
    '11',
    '22',
    '03',
],
    'text_data': '29979675fe1643c893f617a936b910e7',
    'rand_digit': 2,
    'rand_number': 0.74798,
    'rand_signed_int': 7,
    'rand_datetime': '2000-09-20T09:58:51.172555',
    'text_array': [
    'd25846774a6a413f9f76ba340f3e6659',
    '8301ac3c992846309bdddd47e7594f2d',
],
    'words': 'scorpion koala',
    'nested': {
    'id': 134,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 4,
},
],
},
    'nested_array': [
    [
    -3,
],
    [
    -4,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'sloth',
    'lobster',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'camel',
    'maybe': 'squid',
    'maybe_null': 'mouse',
},
},
    {
    'id': 35,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 135,
    'id_str': [
    '04',
],
    'text_data': '803128e96369410ab76b497aa82a4448',
    'rand_digit': 6,
    'rand_number': 0.88902,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-13 08:07:16.216790',
    'text_array': [
    'deaaab1de99448de9c9efcbbff3f52b5',
    '95d50927b73f408086f37b341b30da19',
],
    'words': 'panda jaguar',
    'nested': {
    'id': 135,
    'rand_digit': 5,
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
    'word': 'shark',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -5,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hippo',
    'hyena',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'bee',
},
},
    {
    'id': 36,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 136,
    'id_str': [
    '17',
],
    'text_data': '82c7bc072cb74e5a879e90bc9438ff67',
    'rand_digit': 5,
    'rand_number': 0.55357,
    'rand_signed_int': 6,
    'rand_datetime': '2000-11-18T15:53:32',
    'text_array': [
    '317e815e8954434ba1088122aa9801bc',
    '5e3582a3db144aa093d7b3804831c6cb',
],
    'words': 'hippo pig',
    'nested': {
    'id': 136,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 10,
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
    'word': 'cow',
    'number': 4,
},
],
},
    'nested_array': [
    [
    -1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -4,
],
    [
    10,
],
    [
],
],
    'two_words': [
    'sloth',
    'crab',
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
    'mixed_type': None,
    'maybe_null': 'ant',
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
    '28',
    '02',
    '24',
    '30',
],
    'text_data': '03cafe09e6a5493fa2bed2411c5e30b5',
    'rand_digit': 3,
    'rand_number': 0.44998,
    'rand_signed_int': 4,
    'rand_datetime': '2000-08-26T19:33:11.482512+1200',
    'text_array': [
    'b3406b8444364c178eeddfede3410c70',
    '028f2485d3a84d00be467fd5adb99e62',
],
    'words': 'scorpion bear',
    'nested': {
    'id': 137,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lizard',
    'whale',
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
    'id': 38,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 138,
    'id_str': [
    '28',
],
    'text_data': 'd7d60db434314b43bb9cd96096f37504',
    'rand_digit': 8,
    'rand_number': 0.03611,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-19T04:43:21.904436',
    'text_array': [
    '8ac33c00bc4645799d88a11be9bd1ddf',
    'da8f4171e5854f6aa4105371fb1202dc',
],
    'words': 'ape kangaroo',
    'nested': {
    'id': 138,
    'rand_digit': 2,
    'array': [
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
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'mosquito',
    'cat',
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
    'mixed_type': 0,
    'maybe': 'camel',
    'maybe_null': 'panda',
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 139,
    'id_str': [
    '26',
    '03',
],
    'text_data': 'f4e29544c6f84d818fdd32ce26fc1cfa',
    'rand_digit': 1,
    'rand_number': 0.28856,
    'rand_signed_int': 0,
    'rand_datetime': '2001-01-26T22:40:34',
    'text_array': [
    '7a5c136c5ce74b5da5204d436c5f181f',
    '59e0f55eadc7465fa0dc36c58b82e4bc',
],
    'words': 'shark mosquito',
    'nested': {
    'id': 139,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 7,
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'rhino',
    'leopard',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 'goat',
    'maybe_null': None,
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 140,
    'id_str': [
    '29',
    '23',
    '12',
    '23',
],
    'text_data': '26cf75d947754a6ebe991d5a28b29b93',
    'rand_digit': 1,
    'rand_number': 0.65871,
    'rand_signed_int': -6,
    'rand_datetime': '2000-12-28T16:29:04',
    'text_array': [
    '3d831ff7f18a4462b1dcf975a748e242',
    '6fa584a580694cb48c4427e0500e08a3',
],
    'words': 'fish ladybug',
    'nested': {
    'id': 140,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'panda',
    'number': 7,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 10,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,2__',
    'two_words': [
    'ant',
    'camel',
],
    'city': {
    'name': 'Frankfurt',
    'geo': {
    'lat': 50.110922,
    'lon': 8.682127,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'mouse',
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 141,
    'id_str': [
    '17',
],
    'text_data': 'f6f3aa404a2943ad82ea040f176dfd9e',
    'rand_digit': 2,
    'rand_number': 0.32569,
    'rand_signed_int': -8,
    'rand_datetime': '2000-06-09 15:13:04.438977+0800',
    'text_array': [
    'ee5b7f22d6c649edb42e8585dc1216b5',
    '44b5799625e74955b81d01351c7bbb28',
],
    'words': 'shark bee',
    'nested': {
    'id': 141,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'crab',
    'dolphin',
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
    'mixed_type': 0.98725,
    'maybe': 'octopus',
    'maybe_null': 'monkey',
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 142,
    'id_str': [
    '29',
],
    'text_data': '39c2d84e84124cbaa12aab6d0a246293',
    'rand_digit': 4,
    'rand_number': 0.60568,
    'rand_signed_int': -2,
    'rand_datetime': '2001-01-02T17:24:17',
    'text_array': [
    '71feea1d6d2343a0bce711be53cc23d8',
    '61bb4140508e44a2a914a1aa8a1789b3',
],
    'words': 'bear lion',
    'nested': {
    'id': 142,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'camel',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'bee',
},
},
    {
    'id': 43,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 143,
    'id_str': [
],
    'text_data': 'bfdd674e5ffe44cf872ba774f4cd5bd6',
    'rand_digit': 8,
    'rand_number': 0.92912,
    'rand_signed_int': 2,
    'rand_datetime': '2000-01-16',
    'text_array': [
    'f00dcdd7255940828e1bb40abd43566f',
    '5583a5ab7fd141db848faf081b02178f',
],
    'words': 'snail scorpion',
    'nested': {
    'id': 143,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'squid',
    'ape',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'mouse',
    'maybe_null': 'rabbit',
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 144,
    'id_str': [
    '22',
    '05',
    '28',
    '14',
],
    'text_data': 'b1367d2ea4544a6bbf68be65236ff93c',
    'rand_digit': 4,
    'rand_number': 0.97098,
    'rand_signed_int': -9,
    'rand_datetime': '2000-02-22 07:56:00.493683-0400',
    'text_array': [
    'eecb52d87e3047a2b44d0c1d8a26f207',
    '3ea39eeb35154d41bc93b1ec2ce6cc74',
],
    'words': 'fox frog',
    'nested': {
    'id': 144,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -7,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ant',
    'shark',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.08618,
    'maybe_null': None,
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 145,
    'id_str': [
    '13',
    '22',
    '12',
    '30',
],
    'text_data': '3768aeaaee5e45928ea2e49988c4eddd',
    'rand_digit': 8,
    'rand_number': 0.26623,
    'rand_signed_int': 2,
    'rand_datetime': '2000-11-08 10:48:36.840182+0200',
    'text_array': [
    'd2d90331c46940ab9dad643dd3aad4c2',
    'dfb953eab3314f809adf5c668c5a9beb',
],
    'words': 'deer dragonfly',
    'nested': {
    'id': 145,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ape',
    'number': 1,
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
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'pig',
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
    'mixed_type': None,
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
],
    'text_data': '944e513d086246d7bc98c93f3282bdfd',
    'rand_digit': 9,
    'rand_number': 0.51767,
    'rand_signed_int': 10,
    'rand_datetime': '2000-07-31T10:41:29+0300',
    'text_array': [
    '4b3cda46fcd04ed185ac326b446cd100',
    '7fc61b6d81ec4d2b9d5e40efec1ed12d',
],
    'words': 'rhino hippo',
    'nested': {
    'id': 146,
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
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 4,
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
],
    'two_words': [
    'lizard',
    'horse',
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
    'mixed_type': None,
    'maybe': 'squid',
},
},
    {
    'id': 47,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 147,
    'id_str': [
    '12',
    '13',
    '24',
],
    'text_data': '01cd39a82eec449fbb23d1072bad242c',
    'rand_digit': 7,
    'rand_number': 0.66045,
    'rand_signed_int': 7,
    'rand_datetime': '2000-12-31 12:23:26',
    'text_array': [
    '684d8884332d46439d76c9eb49e600ba',
    '8a346ed14b5f44339e4b192bad0fa79f',
],
    'words': 'leopard fly',
    'nested': {
    'id': 147,
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
],
    'word': 'crab',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'whale',
    'snail',
],
    'city': {
    'name': 'Seoul',
    'geo': {
    'lat': 37.566535,
    'lon': 126.977969,
},
},
    'rand_tuple': [
    82,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'duck',
    'maybe_null': 'ant',
},
},
    {
    'id': 48,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 148,
    'id_str': [
    '30',
    '18',
],
    'text_data': 'd5694a56ce664680a114d59398f16b9f',
    'rand_digit': 2,
    'rand_number': 0.48625,
    'rand_signed_int': -5,
    'rand_datetime': '2000-01-05T21:12:50-1100',
    'text_array': [
    'f2c5880191d8452e95f2f0c37e27cdae',
    '817edd5de32d498ea61fb7d77aac1a1e',
],
    'words': 'leopard bear',
    'nested': {
    'id': 148,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
    7,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'sheep',
    'elephant',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': [
    82,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 149,
    'id_str': [
    '19',
    '15',
    '12',
    '16',
],
    'text_data': '1065a5b032c8497a9c9381779a524c15',
    'rand_digit': 6,
    'rand_number': 0.00244,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-27T04:49:09.374921',
    'text_array': [
    'e4eb7eaf63bc417f92bea01cab7fdabe',
    'ff2f2ca0a7e54730a703e10fe0d0e99b',
],
    'words': 'scorpion chicken',
    'nested': {
    'id': 149,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 6,
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
    'word': 'koala',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'whale',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -2,
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'giraffe',
    'shark',
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
    'mixed_type': 4,
    'maybe_null': 'crab',
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
    'content-length': '17267',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'discover': {
    'target': '__FLOAT_MULTI_DIM_29,100__',
    'context': {
    'positive': 10,
    'negative': 19,
},
},
},
    'using': 'multi-image',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_multivector_discovery_queries.test_discover_raw_target')
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
    test = TestMultivectorDiscoveryQueriestestDiscoverRawTarget()
    test.run_tests()
