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
logger = logging.getLogger('vdb_fuzzer.test.test_collections_test_init_from')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_collections.test_init_from"
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


def send_request(content, request_type="PUT", url_path="http://localhost:6333/collections/test_collection", custom_headers=None):
    """
    发送请求到目标服务器

    Args:
        content: 请求内容
        request_type: 请求方法，默认为"PUT"
        url_path: URL路径，默认为"http://localhost:6333/collections/test_collection"
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



class TestCollectionstestInitFrom:
    """自动生成的VDB模糊测试类 - test_collections.test_init_from"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_collections.test_init_from"
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
        """测试请求 0 - PUT http://localhost:6333/collections/test_collection"""
        logger.info(f"跳过非写请求或无内容请求: PUT http://localhost:6333/collections/test_collection")
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/test_collection'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '42',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'size': 2,
    'distance': 'Cosine',
},
}


        send_request(original_content, method, url_path, headers)
        return True



    def test_request_1(self):
        """测试请求 1 - PUT http://localhost:6333/collections/test_collection/points?wait=true"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/test_collection/points?wait=true")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/test_collection/points?wait=true'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '50165',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 100,
    'id_str': [
    '06',
    '05',
    '15',
    '05',
],
    'text_data': 'd32957280a3f4fb2ad0b983100c29352',
    'rand_digit': 2,
    'rand_number': 0.69824,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-09',
    'text_array': [
    'd7c52c76484b4bdd899fdf1b5732b63b',
    '8dfa67dd666b4af9afd3d7251026cdb9',
],
    'words': 'goat zebra',
    'nested': {
    'id': 100,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fly',
    'number': 5,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'whale',
    'grasshopper',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 6,
    'maybe_null': None,
},
},
    {
    'id': 1,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 101,
    'id_str': [
    '19',
],
    'text_data': '8886bb62785b443fad1e86a607aa5e10',
    'rand_digit': 8,
    'rand_number': 0.05099,
    'rand_signed_int': -4,
    'rand_datetime': '2000-07-12 07:35:33.669500',
    'text_array': [
    '381c71ee49594106bb1324d1ac1e51ef',
    'b0a9a767639345368abfc049d99372e3',
],
    'words': 'koala lobster',
    'nested': {
    'id': 101,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 1,
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
    'hello',
],
    'word': 'frog',
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
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    [
    -6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'lion',
    'gorilla',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'kangaroo',
    'maybe': 'squid',
    'maybe_null': None,
},
},
    {
    'id': 2,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 102,
    'id_str': [
    '21',
    '18',
    '30',
],
    'text_data': '6cabf575eaf74babb80b8158d489a0f1',
    'rand_digit': 5,
    'rand_number': 0.57536,
    'rand_signed_int': 2,
    'rand_datetime': '2001-01-30T07:00:34-0700',
    'text_array': [
    'e209464277824e959bf53caa35e5ca96',
    'b978d83e2f094ceb8ffc464eedda9c5f',
],
    'words': 'ladybug dolphin',
    'nested': {
    'id': 102,
    'rand_digit': 4,
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
],
    'word': 'pig',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'crab',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 2,
},
],
},
    'nested_array': [
    [
    -8,
],
    [
    -9,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lizard',
    'hippo',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'monkey',
},
},
    {
    'id': 3,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 103,
    'id_str': [
    '09',
    '06',
    '04',
],
    'text_data': '5a74ac32da244a4193ee40358ba55c36',
    'rand_digit': 5,
    'rand_number': 0.78347,
    'rand_signed_int': -7,
    'rand_datetime': '2000-11-16 17:50:46.262947',
    'text_array': [
    '288f311d32e64cbf9770038c7deb6df3',
    'a7af37d25f704aa38627f64b6eb93ba2',
],
    'words': 'dolphin cow',
    'nested': {
    'id': 103,
    'rand_digit': 0,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 10,
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
    'word': 'lobster',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'shark',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'panda',
    'lizard',
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
    'mixed_type': None,
    'maybe': 'scorpion',
    'maybe_null': None,
},
},
    {
    'id': 4,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 104,
    'id_str': [
],
    'text_data': '729bb45c7696475ea8ecc751b1fce25b',
    'rand_digit': 2,
    'rand_number': 0.99093,
    'rand_signed_int': -7,
    'rand_datetime': '2001-01-05',
    'text_array': [
    '5a8b508c61124f62a585fe41cfb4f7b4',
    'c13bdbf1d8264c7fa08042a057a94b56',
],
    'words': 'tiger bee',
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
    'word': 'fox',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'mouse',
    'bear',
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
    'mixed_type': 0.44553,
    'maybe_null': 'turtle',
},
},
    {
    'id': 5,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 105,
    'id_str': [
    '27',
    '21',
    '09',
],
    'text_data': '324994fc023849b8bcae646feecb59db',
    'rand_digit': 8,
    'rand_number': 0.60807,
    'rand_signed_int': 10,
    'rand_datetime': '2000-08-05T17:21:52+0200',
    'text_array': [
    'd8dfbbe435b644c7a6b54ba6ace032e1',
    '8b82e07beee449b884796f0c6f0a2ece',
],
    'words': 'octopus hyena',
    'nested': {
    'id': 105,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cheetah',
    'jaguar',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'dragonfly',
    'maybe_null': None,
},
},
    {
    'id': 6,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 106,
    'id_str': [
],
    'text_data': '1fdbb692cb3c4fdc9dc9c41b5e553e9b',
    'rand_digit': 2,
    'rand_number': 0.58293,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-19T08:16:02.893630',
    'text_array': [
    'b2571071550e4c1396f55f59551bf3f5',
    'eae95b65f88f435d8f2888ced9fd62b6',
],
    'words': 'leopard squid',
    'nested': {
    'id': 106,
    'rand_digit': 3,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'camel',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 1,
},
],
},
    'nested_array': [
    [
    3,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'deer',
    'turtle',
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
    'mixed_type': None,
    'maybe_null': 'lobster',
},
},
    {
    'id': 7,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 107,
    'id_str': [
    '25',
    '26',
    '23',
    '19',
],
    'text_data': '441e5d0219c84dbe9d350ec4d83c10bf',
    'rand_digit': 1,
    'rand_number': 0.20216,
    'rand_signed_int': -10,
    'rand_datetime': '2000-12-17T13:33:03.326479',
    'text_array': [
    '9d44ff4e201e4d7aab3f61f731fa852f',
    'a75e237dbc2a47ecbd1740e97204299f',
],
    'words': 'squid cheetah',
    'nested': {
    'id': 107,
    'rand_digit': 1,
    'array': [
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
    'word': 'cat',
    'number': 10,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 3,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -9,
],
],
    'two_words': [
    'koala',
    'fox',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.49661,
    'maybe': 'squid',
    'maybe_null': 'lobster',
},
},
    {
    'id': 8,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 108,
    'id_str': [
    '26',
    '13',
    '05',
],
    'text_data': '12544cda33cc42c19d81b0d6fd43cf5e',
    'rand_digit': 9,
    'rand_number': 0.58027,
    'rand_signed_int': -5,
    'rand_datetime': '2000-04-29T08:18:18.228738',
    'text_array': [
    'b1dd812828cd4932bb0bd97459523de7',
    '13fda1eb1f9a44f4ab163f5f3fd0e36d',
],
    'words': 'koala turtle',
    'nested': {
    'id': 108,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'squid',
    'cheetah',
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
    'mixed_type': 0.75156,
    'maybe_null': 'jaguar',
},
},
    {
    'id': 9,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 109,
    'id_str': [
    '21',
    '24',
    '12',
    '30',
    '03',
],
    'text_data': '3dad9674a20e4c5c99aef2729741aab1',
    'rand_digit': 4,
    'rand_number': 0.1741,
    'rand_signed_int': -1,
    'rand_datetime': '2000-01-13 05:43:32.813548+0600',
    'text_array': [
    'b92b1019e68746c084d36b352015bf92',
    'f4231e6f72bc4c26a07734636b5f5024',
],
    'words': 'goat leopard',
    'nested': {
    'id': 109,
    'rand_digit': 5,
    'array': [
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
    'word': 'dragonfly',
    'number': 4,
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
    'word': 'monkey',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dog',
    'dog',
],
    'city': {
    'name': 'London',
    'geo': {
    'lat': 51.507351,
    'lon': -0.127758,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'whale',
    'maybe_null': None,
},
},
    {
    'id': 10,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 110,
    'id_str': [
    '08',
    '20',
],
    'text_data': 'ba1d426f4876440797de655298d181bd',
    'rand_digit': 2,
    'rand_number': 0.46561,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-04 02:18:13+0200',
    'text_array': [
    '274dc23e38864e669f50d0ca03749dd3',
    '019a9ed57fdf40c78057787ddc48a4c5',
],
    'words': 'rabbit cow',
    'nested': {
    'id': 110,
    'rand_digit': 7,
    'array': [
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
    'word': 'panda',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 4,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,2__',
    'two_words': [
    'sloth',
    'rhino',
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
},
},
    {
    'id': 11,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 111,
    'id_str': [
    '24',
    '11',
    '12',
    '24',
    '30',
],
    'text_data': 'dbdf1cb659ac4a8eba3c350dade5e4ea',
    'rand_digit': 9,
    'rand_number': 0.49002,
    'rand_signed_int': -8,
    'rand_datetime': '2000-02-25 03:41:56.196684+1200',
    'text_array': [
    'daac155a2f0149b099e38b05d6c9d626',
    '18a1915c882d4c2cbb7127e6f4c1c4c1',
],
    'words': 'scorpion zebra',
    'nested': {
    'id': 111,
    'rand_digit': 7,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 5,
},
    {
    'nested_empty': None,
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
    'word': 'squid',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ape',
    'bee',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 12,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 112,
    'id_str': [
],
    'text_data': 'a5914d1aaae8451fae22ee3c0fbc5516',
    'rand_digit': 9,
    'rand_number': 0.35007,
    'rand_signed_int': 7,
    'rand_datetime': '2000-07-18T17:46:09+0300',
    'text_array': [
    'da4d2b6d5247484f9fd064112aa34938',
    'c68e7db8e0e24a2facc3def0baed09f5',
],
    'words': 'panda bee',
    'nested': {
    'id': 112,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'pig',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'turtle',
    'deer',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 13,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 113,
    'id_str': [
    '24',
    '24',
    '26',
],
    'text_data': '3b2d3286f3b24d4aa69b850777992986',
    'rand_digit': 6,
    'rand_number': 0.68758,
    'rand_signed_int': 0,
    'rand_datetime': '2000-01-24T07:34:03.551281',
    'text_array': [
    '4781597690c94debabcd4d680474e7f4',
    'bca44c8db8fa46418b44834a2e48c1b3',
],
    'words': 'pig crab',
    'nested': {
    'id': 113,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 8,
},
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
    'word': 'frog',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'giraffe',
    'wolf',
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
    'mixed_type': 0.73671,
    'maybe_null': 'hippo',
},
},
    {
    'id': 14,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 114,
    'id_str': [
    '21',
    '24',
    '25',
    '05',
    '10',
],
    'text_data': '0b9789f4718e4ac69ba707be2cf86845',
    'rand_digit': 2,
    'rand_number': 0.38976,
    'rand_signed_int': 8,
    'rand_datetime': '2000-01-30T13:23:17.152448-06:00',
    'text_array': [
    '0532cf1cc34549e99959a18028bb2e99',
    '23ea75edd6444783a6f829982f54db57',
],
    'words': 'kangaroo fly',
    'nested': {
    'id': 114,
    'rand_digit': 2,
    'array': [
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
],
],
    'two_words': [
    'grasshopper',
    'hyena',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': [
    2,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'deer',
},
},
    {
    'id': 15,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 115,
    'id_str': [
],
    'text_data': 'd9402511a63843e7a715efa08ee2e670',
    'rand_digit': 4,
    'rand_number': 0.60068,
    'rand_signed_int': 2,
    'rand_datetime': '2000-11-03 20:31:10.785989',
    'text_array': [
    'dc937683b00746caa7ec4445d3e43136',
    '6f4808bf7c084c1d9b651ff29761ec52',
],
    'words': 'gorilla rabbit',
    'nested': {
    'id': 115,
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
    'number': 7,
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
],
    'word': 'hyena',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'squid',
    'pig',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 7,
    'maybe_null': 'butterfly',
},
},
    {
    'id': 16,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 116,
    'id_str': [
    '24',
    '28',
    '18',
    '05',
    '01',
],
    'text_data': 'a367f0165015405d95b6f76c4c849cec',
    'rand_digit': 6,
    'rand_number': 0.79711,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-02T13:15:09.631377',
    'text_array': [
    '70d78a158639467ba0d2eb4b67f5ea89',
    '73fe533512274a85b2bf74acf89626e7',
],
    'words': 'koala tiger',
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
    'word': 'octopus',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'octopus',
    'wolf',
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
    'mixed_type': True,
},
},
    {
    'id': 17,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 117,
    'id_str': [
    '28',
],
    'text_data': '902b4a9239034133ab825806d77960cc',
    'rand_digit': 5,
    'rand_number': 0.50197,
    'rand_signed_int': 1,
    'rand_datetime': '2001-01-14T17:48:15.312628',
    'text_array': [
    '7811af26eb604b5b84dc0e281c2dcfc6',
    '722adfcefe414bcfb4fdea3944eefba5',
],
    'words': 'kangaroo sheep',
    'nested': {
    'id': 117,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'jaguar',
    'whale',
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
    'mixed_type': True,
},
},
    {
    'id': 18,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 118,
    'id_str': [
],
    'text_data': 'a1095a796a2648f7920de4d60bd9ce3c',
    'rand_digit': 4,
    'rand_number': 0.46933,
    'rand_signed_int': -3,
    'rand_datetime': '2000-09-22',
    'text_array': [
    'dc06ceda772f49d3ba9dea90084f31c7',
    '57366c29fd434607af00f5860fb6e05d',
],
    'words': 'panda dragonfly',
    'nested': {
    'id': 118,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'whale',
    'horse',
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
    'mixed_type': 'frog',
    'maybe': 'zebra',
    'maybe_null': 'gorilla',
},
},
    {
    'id': 19,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 119,
    'id_str': [
    '02',
    '11',
    '17',
    '18',
],
    'text_data': '06b7869aa168456dabe25a56f148df6b',
    'rand_digit': 0,
    'rand_number': 0.69773,
    'rand_signed_int': -3,
    'rand_datetime': '2000-11-22 06:48:04',
    'text_array': [
    '643cc8b5f9874d0794a9635bafe34b0b',
    'f96ca73be5984829993f1526cdb42e08',
],
    'words': 'hyena leopard',
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
    'word': 'snail',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fish',
    'shark',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'koala',
},
},
    {
    'id': 20,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 120,
    'id_str': [
    '10',
    '03',
    '16',
    '14',
    '11',
],
    'text_data': '10864c11657f4aa9a245e548e26fbaed',
    'rand_digit': 7,
    'rand_number': 0.19417,
    'rand_signed_int': 6,
    'rand_datetime': '2000-03-13 01:25:42',
    'text_array': [
    '74a323191254462cbd32eff57d2a7c16',
    'e56113ceff30458eaf16ea35b37e99f3',
],
    'words': 'chicken lion',
    'nested': {
    'id': 120,
    'rand_digit': 7,
    'array': [
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
    'word': 'dolphin',
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
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    9,
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fox',
    'pig',
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
    'mixed_type': False,
    'maybe': 'scorpion',
},
},
    {
    'id': 21,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 121,
    'id_str': [
    '12',
    '01',
],
    'text_data': '72a2d2a9e2a34f50b986a120e11f6f63',
    'rand_digit': 3,
    'rand_number': 0.90792,
    'rand_signed_int': 4,
    'rand_datetime': '2000-10-23 16:11:17-0900',
    'text_array': [
    'a13e6815d8c340aaacc824a003734682',
    'ce71ce004fa645d597013aa27dd421f9',
],
    'words': 'leopard dog',
    'nested': {
    'id': 121,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'turtle',
    'number': 8,
},
    {
    'nested_empty': None,
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
],
    'word': 'monkey',
    'number': 3,
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
],
    'two_words': [
    'dolphin',
    'butterfly',
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
    'mixed_type': 6,
    'maybe_null': 'crab',
},
},
    {
    'id': 22,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 122,
    'id_str': [
    '28',
    '02',
    '18',
    '28',
],
    'text_data': '89d7d025e8bb476f837f7a6afb1f3b87',
    'rand_digit': 1,
    'rand_number': 0.65121,
    'rand_signed_int': -5,
    'rand_datetime': '2000-10-18 23:56',
    'text_array': [
    '7d27cf4d6574467082ccb1967ac6b6a0',
    '5377288c082d48b3b1013137d2a6863f',
],
    'words': 'squid turtle',
    'nested': {
    'id': 122,
    'rand_digit': 8,
    'array': [
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
],
    'word': 'octopus',
    'number': 2,
},
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
    'hello',
],
    'word': 'lion',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'octopus',
    'spider',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.35638,
    'maybe': 'mosquito',
    'maybe_null': 'cheetah',
},
},
    {
    'id': 23,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 123,
    'id_str': [
    '20',
    '16',
    '27',
    '24',
    '24',
],
    'text_data': '58128b83cec34ee3b333638f30c1d7a4',
    'rand_digit': 2,
    'rand_number': 0.21036,
    'rand_signed_int': -3,
    'rand_datetime': '2001-01-07T14:22:56.770289-08:00',
    'text_array': [
    '66a5c92f1a2b4e78b12aba7ea5247405',
    '5d524da207764d4e8d072394dc48a83b',
],
    'words': 'cheetah rhino',
    'nested': {
    'id': 123,
    'rand_digit': 3,
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
],
    'word': 'sheep',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'shark',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'snake',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'deer',
    'maybe_null': None,
},
},
    {
    'id': 24,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 124,
    'id_str': [
    '12',
    '27',
    '05',
],
    'text_data': 'eeb5ff0fc6c64eb3aeb4befb9b3a152e',
    'rand_digit': 8,
    'rand_number': 0.68127,
    'rand_signed_int': -5,
    'rand_datetime': '2000-02-23 05:54:29',
    'text_array': [
    '6704ca7dbc2e4909a5de35b85c6ae012',
    'b8652571bd9d4062ab3ccf0d84a40cef',
],
    'words': 'rabbit ape',
    'nested': {
    'id': 124,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 10,
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
    [
],
],
    'two_words': [
    'frog',
    'dog',
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
    'maybe_null': 'dog',
},
},
    {
    'id': 25,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 125,
    'id_str': [
    '08',
],
    'text_data': 'af13a1047e244582915a342acf10ad76',
    'rand_digit': 7,
    'rand_number': 0.66534,
    'rand_signed_int': -7,
    'rand_datetime': '2000-05-11T12:51:57.123036+0300',
    'text_array': [
    '7adf1181af8049568fe82e733cf11f86',
    '13e629add15f4397ab47a2375269d7f1',
],
    'words': 'rhino panda',
    'nested': {
    'id': 125,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 3,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'octopus',
    'elephant',
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
    'mixed_type': 0,
    'maybe': 'zebra',
    'maybe_null': 'pig',
},
},
    {
    'id': 26,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 126,
    'id_str': [
    '24',
],
    'text_data': '1f85b952eb834c5ab8395feebc5cd4c6',
    'rand_digit': 3,
    'rand_number': 0.14268,
    'rand_signed_int': 9,
    'rand_datetime': '2000-03-07T05:23:23+1100',
    'text_array': [
    '610f51621ca54d9088af0f0a0c1ec73c',
    '034a77693dad44dcae9512082406dc57',
],
    'words': 'gorilla mosquito',
    'nested': {
    'id': 126,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'cow',
    'number': 9,
},
],
},
    'nested_array': [
    [
    6,
],
    [
    -5,
],
],
    'two_words': [
    'shark',
    'hippo',
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
    'mixed_type': 0.49783,
    'maybe_null': 'mosquito',
},
},
    {
    'id': 27,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 127,
    'id_str': [
    '06',
    '01',
    '02',
    '10',
],
    'text_data': 'b8706e35bfa24e13a7604c430026ca7d',
    'rand_digit': 1,
    'rand_number': 0.72376,
    'rand_signed_int': -5,
    'rand_datetime': '2001-01-19 06:08:40+0900',
    'text_array': [
    'a557cbf4867a4a118e15740c02bb7f6c',
    '39d178449321464ba50dfd6762d38f06',
],
    'words': 'frog crab',
    'nested': {
    'id': 127,
    'rand_digit': 8,
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
    'word': 'mouse',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 10,
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
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'shark',
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
    'mixed_type': 4,
},
},
    {
    'id': 28,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 128,
    'id_str': [
    '23',
    '30',
    '20',
    '14',
    '21',
],
    'text_data': 'ecf187519a8e41d3865d5d50aafd7909',
    'rand_digit': 0,
    'rand_number': 0.5505,
    'rand_signed_int': 0,
    'rand_datetime': '2000-03-09 01:34:00+0600',
    'text_array': [
    'f6ce971ee6464017a00f43b27fd7f3c7',
    'eb5c9acd394c41549d1776d4d2d7afb1',
],
    'words': 'cheetah cheetah',
    'nested': {
    'id': 128,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'snake',
    'chicken',
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
    'mixed_type': 0.70466,
    'maybe': 'duck',
    'maybe_null': None,
},
},
    {
    'id': 29,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 129,
    'id_str': [
    '20',
    '17',
    '05',
    '14',
    '30',
],
    'text_data': '70771ba07af940029926f0b2dd7c7bb0',
    'rand_digit': 6,
    'rand_number': 0.42816,
    'rand_signed_int': -2,
    'rand_datetime': '2001-01-14 17:56:23-1100',
    'text_array': [
    '87ec888d5db943c294c9541cc718619e',
    '80d36f6022c4477b88bea9147780d199',
],
    'words': 'rhino bear',
    'nested': {
    'id': 129,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
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
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fox',
    'hippo',
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
    'maybe': 'horse',
},
},
    {
    'id': 30,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 130,
    'id_str': [
    '12',
    '11',
    '30',
    '08',
],
    'text_data': 'c45cfd43ecdb40cf811dfdaab861b597',
    'rand_digit': 2,
    'rand_number': 0.96805,
    'rand_signed_int': -6,
    'rand_datetime': '2000-02-19 17:55:57+0300',
    'text_array': [
    '3030c350696c4c88ab162f56e18acf46',
    'd819073ebbf9441899dc2a1a13426a7d',
],
    'words': 'pig sheep',
    'nested': {
    'id': 130,
    'rand_digit': 6,
    'array': [
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
    'word': 'bird',
    'number': 6,
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
],
    'two_words': [
    'fly',
    'kangaroo',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'lobster',
},
},
    {
    'id': 31,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 131,
    'id_str': [
    '13',
    '15',
    '22',
    '09',
    '11',
],
    'text_data': '6e7796711d6948479155934b11835368',
    'rand_digit': 6,
    'rand_number': 0.99443,
    'rand_signed_int': -5,
    'rand_datetime': '2000-02-16T18:29:44.342801+08:00',
    'text_array': [
    '2d760ab3cf6a4be4ac833a952ccd9f4d',
    'ceb6ed64abaa4c429f2d395f5a6cb98d',
],
    'words': 'sloth rabbit',
    'nested': {
    'id': 131,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
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
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'frog',
    'snake',
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
    'mixed_type': 0.35075,
    'maybe': 'octopus',
    'maybe_null': None,
},
},
    {
    'id': 32,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 132,
    'id_str': [
],
    'text_data': 'bfb4d971479b414ea99d47c64b20f9a1',
    'rand_digit': 9,
    'rand_number': 0.88678,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-09 21:07:54.779645+1100',
    'text_array': [
    '86921a8c690c4a38bdf6957256404bf7',
    'b85cad94b47e4a74bef970c5d4b9daed',
],
    'words': 'fox pig',
    'nested': {
    'id': 132,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -10,
],
    [
    -9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'shark',
    'lobster',
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
    'maybe_null': 'cat',
},
},
    {
    'id': 33,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 133,
    'id_str': [
    '25',
    '13',
],
    'text_data': 'c56313f653714ddaafe9b5ed884ee7b0',
    'rand_digit': 5,
    'rand_number': 0.95509,
    'rand_signed_int': 3,
    'rand_datetime': '2000-03-24 12:20:17',
    'text_array': [
    'e71845148cca49ce874de870ce1fc798',
    'cab961bcdba44424968927d58d30e60a',
],
    'words': 'elephant panda',
    'nested': {
    'id': 133,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    [
],
    [
    5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dragonfly',
    'sheep',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'snake',
    'maybe_null': None,
},
},
    {
    'id': 34,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 134,
    'id_str': [
    '11',
    '10',
    '10',
    '25',
],
    'text_data': 'd3e48d53117f4fee9ff45cf4dc74b604',
    'rand_digit': 1,
    'rand_number': 0.92945,
    'rand_signed_int': 0,
    'rand_datetime': '2000-05-03 08:07',
    'text_array': [
    '50d9615c7bdd4273b955cb876f2361c6',
    'e338bb0aaea447f99cb3d82c6b55dcf4',
],
    'words': 'giraffe rabbit',
    'nested': {
    'id': 134,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'mosquito',
    'panda',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 35,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 135,
    'id_str': [
    '20',
    '27',
    '26',
    '29',
    '02',
],
    'text_data': 'c24ed88fa3a04708bd911ceea2131b63',
    'rand_digit': 3,
    'rand_number': 0.779,
    'rand_signed_int': -6,
    'rand_datetime': '2000-06-26T21:42:14',
    'text_array': [
    '1694e3c9e23c4927ad53c7a1b4bae94c',
    '8bc2dc49ea01466a822aef05a527c05b',
],
    'words': 'snail ape',
    'nested': {
    'id': 135,
    'rand_digit': 9,
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
],
},
    'nested_array': [
    [
    -8,
],
    [
    -5,
],
],
    'two_words': [
    'snake',
    'monkey',
],
    'city': {
    'name': 'Copenhagen',
    'geo': {
    'lat': 55.676097,
    'lon': 12.568337,
},
},
    'rand_tuple': [
    58,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'hippo',
    'maybe_null': 'pig',
},
},
    {
    'id': 36,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 136,
    'id_str': [
    '02',
],
    'text_data': 'd4453215d73f42e4bf9f06bacb5feeff',
    'rand_digit': 9,
    'rand_number': 0.77942,
    'rand_signed_int': -8,
    'rand_datetime': '2000-04-30T22:08:32',
    'text_array': [
    'dc2313add6834d3e957d9af368b3a3aa',
    '2f050429136441dbb20f789c154035bb',
],
    'words': 'fish pig',
    'nested': {
    'id': 136,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -6,
],
    [
    6,
],
    [
    7,
],
],
    'two_words': [
    'cat',
    'fish',
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
    'mixed_type': 0.48238,
    'maybe_null': None,
},
},
    {
    'id': 37,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 137,
    'id_str': [
    '01',
],
    'text_data': 'bd3752a7905c40228a7fd4e6881edb3c',
    'rand_digit': 5,
    'rand_number': 0.86598,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-25 04:49:52',
    'text_array': [
    '3c1e9f060b0c44629f76c4cfbe22001a',
    '52c6347a2249429e845a66d32126b498',
],
    'words': 'bear camel',
    'nested': {
    'id': 137,
    'rand_digit': 2,
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
],
},
    'nested_array': [
],
    'two_words': [
    'panda',
    'goat',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'gorilla',
    'maybe_null': 'rhino',
},
},
    {
    'id': 38,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 138,
    'id_str': [
    '21',
    '18',
    '08',
    '18',
],
    'text_data': 'b4d12d04ac6f4e8ab29f3ab5f348128a',
    'rand_digit': 4,
    'rand_number': 0.06106,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-21',
    'text_array': [
    'aea65b643c85405983d3e761e75960fd',
    'ad950158084e4952a38f0d78d5240b5d',
],
    'words': 'goat dragonfly',
    'nested': {
    'id': 138,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    8,
],
    [
],
],
    'two_words': [
    'lion',
    'lion',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'wolf',
    'maybe_null': 'fly',
},
},
    {
    'id': 39,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 139,
    'id_str': [
    '11',
    '04',
],
    'text_data': 'baf47342322d49d3a701990408f0ba7b',
    'rand_digit': 1,
    'rand_number': 0.44575,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-11 04:29:21',
    'text_array': [
    '71b64f360df54c17abcb971c3d19f0d8',
    'ac83b70e5a934de7a9d29d3d1b5c08b4',
],
    'words': 'bird shark',
    'nested': {
    'id': 139,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'wolf',
    'fly',
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
    'mixed_type': 'squid',
    'maybe_null': None,
},
},
    {
    'id': 40,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 140,
    'id_str': [
    '24',
    '23',
    '11',
    '02',
    '22',
],
    'text_data': '7df10b3ad0704950812296ee09ef797b',
    'rand_digit': 2,
    'rand_number': 0.29213,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-08T16:37:26.916984',
    'text_array': [
    '0dee9545eb38475c92c9dc70b3e6c840',
    'b45b4f5cad974dd4bb92d1a037854505',
],
    'words': 'giraffe mouse',
    'nested': {
    'id': 140,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'dolphin',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
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
    10,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'fish',
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
    'mixed_type': 0.49944,
    'maybe': 'bee',
    'maybe_null': None,
},
},
    {
    'id': 41,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 141,
    'id_str': [
],
    'text_data': 'e4fe9fda63bf4bdb9239c265181eb1e2',
    'rand_digit': 6,
    'rand_number': 0.79249,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-07 10:31:01.639592',
    'text_array': [
    '337e9f730b764685a1774891815955c2',
    'ab1ccc873fb04f34a2ef303f2002b30d',
],
    'words': 'cat leopard',
    'nested': {
    'id': 141,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'giraffe',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ape',
    'butterfly',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
},
},
    {
    'id': 42,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 142,
    'id_str': [
    '14',
    '17',
    '06',
    '05',
    '06',
],
    'text_data': 'b3222d66f4d347fa869553af81c24a7a',
    'rand_digit': 7,
    'rand_number': 0.61682,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-27T13:43:52',
    'text_array': [
    '387f2ab3c45045d28078b3543f8c35d5',
    '08110b7de4be4b54af0d4804c611a856',
],
    'words': 'fish giraffe',
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
    'word': 'octopus',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'sloth',
    'sloth',
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
    'mixed_type': 8,
    'maybe': 'gorilla',
},
},
    {
    'id': 43,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 143,
    'id_str': [
    '04',
    '18',
    '06',
    '06',
    '25',
],
    'text_data': 'dc33e8cae6e4435ab27f171e77f9e466',
    'rand_digit': 5,
    'rand_number': 0.28731,
    'rand_signed_int': -9,
    'rand_datetime': '2000-02-22T12:34:36.265026-09:00',
    'text_array': [
    '6a209742571748fe98e85d7c79afe435',
    'dca4d7b29f6c464bb3ce566c5a1aaafa',
],
    'words': 'scorpion duck',
    'nested': {
    'id': 143,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'sheep',
    'pig',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'grasshopper',
    'maybe_null': 'whale',
},
},
    {
    'id': 44,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 144,
    'id_str': [
],
    'text_data': '24695a8bf37f4936a0da7db659b03678',
    'rand_digit': 6,
    'rand_number': 0.43078,
    'rand_signed_int': -6,
    'rand_datetime': '2000-09-02 10:15:05.099726-0300',
    'text_array': [
    '747b3daed29148ee87a0bf7ab9bc2688',
    '6a2df9cdb16c4674ab94b8f6a83eb6f9',
],
    'words': 'lizard zebra',
    'nested': {
    'id': 144,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 3,
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
    'nested_array': [
],
    'two_words': [
    'panda',
    'dolphin',
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
    'maybe_null': None,
},
},
    {
    'id': 45,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 145,
    'id_str': [
    '17',
    '03',
    '23',
    '03',
],
    'text_data': '9598e1256492405f83f89d247aade93e',
    'rand_digit': 4,
    'rand_number': 0.69154,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-05T21:54:24.949960-0900',
    'text_array': [
    '9279b1135e924489b943c34f2aa6b724',
    '5f20de91815f49119540c71ebe20d70f',
],
    'words': 'zebra dragonfly',
    'nested': {
    'id': 145,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'camel',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ant',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'elephant',
    'spider',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.89963,
    'maybe': 'elephant',
    'maybe_null': 'horse',
},
},
    {
    'id': 46,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 146,
    'id_str': [
    '28',
    '30',
    '07',
    '02',
    '05',
],
    'text_data': 'e40005e6d92e4494bab548055f2bebe7',
    'rand_digit': 4,
    'rand_number': 0.61418,
    'rand_signed_int': 3,
    'rand_datetime': '2000-10-16T23:27:20.603577',
    'text_array': [
    'e38668c4aff84b7baee2e6f0ec81f125',
    'ed7609104a8e47eba5e9754ae36b80e9',
],
    'words': 'rabbit camel',
    'nested': {
    'id': 146,
    'rand_digit': 1,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'spider',
    'scorpion',
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
    'mixed_type': 7,
    'maybe': 'leopard',
    'maybe_null': 'squid',
},
},
    {
    'id': 47,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 147,
    'id_str': [
    '18',
],
    'text_data': 'e3b1da2a97c4443a9c2b13e0b86c82c1',
    'rand_digit': 2,
    'rand_number': 0.34671,
    'rand_signed_int': 0,
    'rand_datetime': '2000-05-19T07:51:05+1200',
    'text_array': [
    '1b4f46addb254e2a959452a650810614',
    '9e0f65a1e64343c5992918f3afc7c508',
],
    'words': 'snail snake',
    'nested': {
    'id': 147,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'grasshopper',
    'cow',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'lobster',
    'maybe_null': 'chicken',
},
},
    {
    'id': 48,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 148,
    'id_str': [
    '21',
    '19',
    '01',
],
    'text_data': '547b3da16bcd410787a342b243726a11',
    'rand_digit': 0,
    'rand_number': 0.28077,
    'rand_signed_int': -6,
    'rand_datetime': '2000-11-02T16:55:26.601603',
    'text_array': [
    'a5b9c76f43ee4b2fbca74d58895252ba',
    'fe4784dd7d57445bb46888821d7b2559',
],
    'words': 'crab ant',
    'nested': {
    'id': 148,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fly',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'lizard',
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
    'nested_array': [
],
    'two_words': [
    'wolf',
    'lizard',
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
    'mixed_type': 'deer',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 49,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 149,
    'id_str': [
    '02',
],
    'text_data': '510e984001774dd68378d34ec1a3423d',
    'rand_digit': 5,
    'rand_number': 0.11874,
    'rand_signed_int': -8,
    'rand_datetime': '2000-08-26T03:59:00',
    'text_array': [
    '79b5e9d881ca46269bd92aae751fc412',
    '542a733f3a64404ab18ddf377ea20331',
],
    'words': 'lizard fish',
    'nested': {
    'id': 149,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 5,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 4,
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
],
},
    'nested_array': [
    [
],
    [
],
],
    'two_words': [
    'turtle',
    'snake',
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
    'mixed_type': 'rhino',
},
},
    {
    'id': 50,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 150,
    'id_str': [
    '18',
    '02',
    '02',
],
    'text_data': 'a76a1169ce9d431e9755f51e48ce9aa4',
    'rand_digit': 8,
    'rand_number': 0.83457,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-27T08:22:27.539139',
    'text_array': [
    '9c77658a5936430d862d9e77626d51d5',
    'c849afef9a66442dacf1adcb9d456df2',
],
    'words': 'deer zebra',
    'nested': {
    'id': 150,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 1,
},
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
    'hello',
],
    'word': 'gorilla',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bee',
    'deer',
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
    'mixed_type': 0.3381,
    'maybe': 'sheep',
    'maybe_null': None,
},
},
    {
    'id': 51,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 151,
    'id_str': [
    '15',
],
    'text_data': '6eaa302fcafa469bb19dcb4fc3477ac7',
    'rand_digit': 7,
    'rand_number': 0.18317,
    'rand_signed_int': 2,
    'rand_datetime': '2000-05-19T06:05:51.054018-0700',
    'text_array': [
    '29468ac1004e4f6ba053f28ac321159b',
    'c5dff244f68a419db5757c6b05d67d0e',
],
    'words': 'rhino ant',
    'nested': {
    'id': 151,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'tiger',
    'cheetah',
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
    'mixed_type': False,
},
},
    {
    'id': 52,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 152,
    'id_str': [
],
    'text_data': 'd0f63de15b264e8590a5e90cdbfa0492',
    'rand_digit': 1,
    'rand_number': 0.79598,
    'rand_signed_int': 5,
    'rand_datetime': '2000-06-19',
    'text_array': [
    '6d617bc67891429f8d357c0619402657',
    'a1968e8b96434043b5ce732b009e2fdb',
],
    'words': 'shark horse',
    'nested': {
    'id': 152,
    'rand_digit': 1,
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
    'hello',
],
    'word': 'cow',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -8,
],
],
    'two_words': [
    'squid',
    'giraffe',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'shark',
},
},
    {
    'id': 53,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 153,
    'id_str': [
    '08',
    '04',
    '12',
],
    'text_data': '4a296daa80ef427189a6cc266a3c31af',
    'rand_digit': 3,
    'rand_number': 0.41592,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-28T09:49:32.010899+0900',
    'text_array': [
    '96809a3aa06e41a3af7891fb2681935a',
    '91705f3f0c3542be9ea4b347fd765639',
],
    'words': 'whale hippo',
    'nested': {
    'id': 153,
    'rand_digit': 6,
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
    'word': 'mouse',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'dolphin',
    'giraffe',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 5,
    'maybe': 'giraffe',
},
},
    {
    'id': 54,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 154,
    'id_str': [
],
    'text_data': 'f086e181cc8541209b67c5c3f14d08b4',
    'rand_digit': 5,
    'rand_number': 0.65494,
    'rand_signed_int': -4,
    'rand_datetime': '2000-11-04 04:16:15',
    'text_array': [
    'b3fcba503ca648b485017420c61d7cd1',
    'ac383956104c42e7aba0784c7d878c0a',
],
    'words': 'squid hippo',
    'nested': {
    'id': 154,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lion',
    'snake',
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
    'mixed_type': 'dolphin',
    'maybe': 'rhino',
    'maybe_null': None,
},
},
    {
    'id': 55,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 155,
    'id_str': [
],
    'text_data': '38f19a7a5be14055a93169cf6876ae26',
    'rand_digit': 1,
    'rand_number': 0.03498,
    'rand_signed_int': 10,
    'rand_datetime': '2000-10-20 18:45:10.329343',
    'text_array': [
    '907969a22ca446ab94e2f8863575c2e1',
    'e7b2aea4c9ff46049a347be8ee54e90d',
],
    'words': 'tiger bird',
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
    'word': 'mouse',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 9,
},
    {
    'nested_empty': None,
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
    'word': 'hyena',
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
    'lobster',
    'cheetah',
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
    'mixed_type': 'giraffe',
    'maybe_null': None,
},
},
    {
    'id': 56,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 156,
    'id_str': [
    '23',
    '03',
],
    'text_data': 'f6c7348a62414244a7d1f013598dfeb1',
    'rand_digit': 1,
    'rand_number': 0.3823,
    'rand_signed_int': -5,
    'rand_datetime': '2000-03-07 17:48:51',
    'text_array': [
    'dac935f77ac94d5baa950c2231708dc8',
    'cd1fe3604648470d80a191a1cab65f96',
],
    'words': 'rabbit hyena',
    'nested': {
    'id': 156,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
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
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'dog',
    'crab',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': [
    4,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'giraffe',
    'maybe_null': 'tiger',
},
},
    {
    'id': 57,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 157,
    'id_str': [
    '07',
    '11',
    '04',
],
    'text_data': 'b20fcd10398347749ef2b8952e830fbe',
    'rand_digit': 4,
    'rand_number': 0.43288,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-19T20:51:16.811443+02:00',
    'text_array': [
    '722002c4c493499186730a318c014a92',
    '9f5fabe77eac4a8fab4a786498694e28',
],
    'words': 'lion whale',
    'nested': {
    'id': 157,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'giraffe',
    'ape',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'zebra',
},
},
    {
    'id': 58,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 158,
    'id_str': [
    '09',
],
    'text_data': 'ae28b94eb65f440b915f18701e85b759',
    'rand_digit': 0,
    'rand_number': 0.43962,
    'rand_signed_int': 7,
    'rand_datetime': '2000-01-27T00:54:11+0800',
    'text_array': [
    '8c900b5a76c847c6a0fed274d19c9944',
    'ab763f2b241b4072a2478bed978dc613',
],
    'words': 'kangaroo duck',
    'nested': {
    'id': 158,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'whale',
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
    'maybe': 'bear',
    'maybe_null': None,
},
},
    {
    'id': 59,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 159,
    'id_str': [
    '12',
    '19',
    '06',
],
    'text_data': '69b5c97d35144fbbb397b3b028204654',
    'rand_digit': 4,
    'rand_number': 0.8057,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-16T05:02:45.227657-0500',
    'text_array': [
    '96f90048a38d4eb7bc9ed828c275663f',
    'e3963511ec0c4869a0ba64d482bcecde',
],
    'words': 'ant frog',
    'nested': {
    'id': 159,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    2,
],
],
    'two_words': [
    'lobster',
    'wolf',
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
},
},
    {
    'id': 60,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 160,
    'id_str': [
    '24',
    '22',
    '06',
    '16',
    '08',
],
    'text_data': '9ad5eb087c824ee2b7670617cdd8944d',
    'rand_digit': 7,
    'rand_number': 0.88015,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-09T05:05:40-0400',
    'text_array': [
    '20ad5195f55f420195eea7f603d8889d',
    '0bbbc0e1b45641e195b583e5f2e11a0e',
],
    'words': 'rabbit whale',
    'nested': {
    'id': 160,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'scorpion',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'scorpion',
    'snail',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'bear',
},
},
    {
    'id': 61,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 161,
    'id_str': [
    '12',
    '03',
    '01',
],
    'text_data': 'd156813fd6554a6099c31098a241dcd7',
    'rand_digit': 1,
    'rand_number': 0.2614,
    'rand_signed_int': -8,
    'rand_datetime': '2000-07-23 23:38:04',
    'text_array': [
    'eacfeef017c34ffc847586de811ed31c',
    '19853ad1138c432d9176816553229882',
],
    'words': 'fish elephant',
    'nested': {
    'id': 161,
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
    [
    -8,
],
],
    'two_words': [
    'fox',
    'snail',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'goat',
},
},
    {
    'id': 62,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 162,
    'id_str': [
    '12',
    '23',
    '20',
],
    'text_data': '403f9d09504f47ea8da350cb490b8833',
    'rand_digit': 9,
    'rand_number': 0.3709,
    'rand_signed_int': 6,
    'rand_datetime': '2000-10-18 11:32',
    'text_array': [
    'ab23b4ead73b4a70b57401dd8cc5ac52',
    'd06a4be0394d415ea6fec38ab0353853',
],
    'words': 'grasshopper mosquito',
    'nested': {
    'id': 162,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'ant',
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
    'word': 'lobster',
    'number': 6,
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
],
},
    'nested_array': [
    [
    -10,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'octopus',
    'fish',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': [
    82,
],
    'rand_bool': True,
    'mixed_type': None,
},
},
    {
    'id': 63,
    'vector': self.mutator.generate_float_array(dimension=2, normalized=True),
    'payload': {
    'id': 163,
    'id_str': [
    '18',
    '05',
    '19',
    '11',
],
    'text_data': 'e76802eba2e840cd8aacf0c57f4a4728',
    'rand_digit': 4,
    'rand_number': 0.66218,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-01 11:30:58.856039-1200',
    'text_array': [
    'ae31a89b77724907bc08f912baa259fe',
    '9d810205f0c44dbdba0d98af94e0b4fa',
],
    'words': 'giraffe elephant',
    'nested': {
    'id': 163,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 2,
},
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
    'hello',
],
    'word': 'lion',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dolphin',
    'mouse',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'ladybug',
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
        """测试请求 2 - POST http://localhost:6333/collections/test_collection/points/scroll"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/test_collection/points/scroll")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/test_collection/points/scroll'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '53',
}
        
        # 原始请求内容
        original_content = {
    'limit': 2000,
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



    def test_request_3(self):
        """测试请求 3 - PUT http://localhost:6333/collections/test_collection_new"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/test_collection_new")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/test_collection_new'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '87',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'size': 2,
    'distance': 'Cosine',
},
    'init_from': {
    'collection': 'test_collection',
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
        """测试请求 4 - POST http://localhost:6333/collections/test_collection_new/points/scroll"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/test_collection_new/points/scroll")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/test_collection_new/points/scroll'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '53',
}
        
        # 原始请求内容
        original_content = {
    'limit': 2000,
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
        """测试请求 5 - DELETE http://localhost:6333/collections/test_collection"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://localhost:6333/collections/test_collection")
        method = 'DELETE'
        url_path = 'http://localhost:6333/collections/test_collection'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '42',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'size': 2,
    'distance': 'Cosine',
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_collections.test_init_from')
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
    test = TestCollectionstestInitFrom()
    test.run_tests()
