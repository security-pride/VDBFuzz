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
logger = logging.getLogger('vdb_fuzzer.test.test_group_recommend_test_simple_recommend_groups')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_group_recommend.test_simple_recommend_groups"
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



class TestGroupRecommendtestSimpleRecommendGroups:
    """自动生成的VDB模糊测试类 - test_group_recommend.test_simple_recommend_groups"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_group_recommend.test_simple_recommend_groups"
        self.test_count = 14  # 测试方法数量
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
    'content-length': '139213',
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
    '13',
    '13',
    '11',
    '20',
    '12',
],
    'text_data': '4d7545c73d6142a7b6b601b6038d4481',
    'rand_digit': 9,
    'rand_number': 0.90633,
    'rand_signed_int': -4,
    'rand_datetime': '2000-11-16 22:09:47-0600',
    'text_array': [
    '81e3fab9354a45989d9c1de0e826671b',
    'a04a0f9f7b1e4060a407376201ca739c',
],
    'words': 'goat goat',
    'nested': {
    'id': 100,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'frog',
    'hyena',
],
    'city': {
    'name': 'Rome',
    'geo': {
    'lat': 41.902782,
    'lon': 12.496366,
},
},
    'rand_tuple': [
    49,
],
    'rand_bool': False,
    'mixed_type': None,
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
    '26',
],
    'text_data': 'c8c533a3df99472e9dfe94568cf15e49',
    'rand_digit': 8,
    'rand_number': 0.20974,
    'rand_signed_int': -8,
    'rand_datetime': '2000-04-10T01:44:13.252118',
    'text_array': [
    '1f52f4dd2b7d403d99ba4ac52e8c094f',
    '0216d8f48e8a4d15a2a4cccb51c4afdd',
],
    'words': 'bee horse',
    'nested': {
    'id': 101,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'cat',
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
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
    [
    2,
],
    [
    4,
],
    [
    -3,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'dragonfly',
    'ant',
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
    'mixed_type': 7,
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
    '01',
    '21',
    '16',
    '25',
],
    'text_data': '545c016d094a4c0a9f6aa8228f512ad8',
    'rand_digit': 7,
    'rand_number': 0.29147,
    'rand_signed_int': 10,
    'rand_datetime': '2000-10-09 15:10:06+0900',
    'text_array': [
    'a6e79fc8529947ab920e67f73c39fa23',
    '7558b22d32de427e990ffbe1c1b2bba8',
],
    'words': 'ape fox',
    'nested': {
    'id': 102,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 2,
},
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ant',
    'hyena',
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
    '22',
    '27',
    '03',
    '14',
    '16',
],
    'text_data': '652016daf3a948aa9f3992bdd9c1a944',
    'rand_digit': 5,
    'rand_number': 0.29602,
    'rand_signed_int': 7,
    'rand_datetime': '2000-02-11T19:16:59.929455-0500',
    'text_array': [
    '6fd39348e3df4786b0edde2e8fa4a5cb',
    'a8a22dafc3cb45c4b579637913842f10',
],
    'words': 'camel tiger',
    'nested': {
    'id': 103,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'squid',
    'horse',
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
    'mixed_type': 3,
    'maybe_null': 'spider',
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
],
    'text_data': 'a5afc9b7d2094035be19fa20e1cbcbae',
    'rand_digit': 5,
    'rand_number': 0.90175,
    'rand_signed_int': 7,
    'rand_datetime': '2000-02-05T17:16:30.586691',
    'text_array': [
    '6e7f351c748a4c028d83c6503291060b',
    '443141e24ec34e23bfa51c34a7e0c261',
],
    'words': 'crab rabbit',
    'nested': {
    'id': 104,
    'rand_digit': 9,
    'array': [
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
    'word': 'lobster',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ape',
    'elephant',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
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
    '23',
    '08',
    '05',
],
    'text_data': '45a247f602fb464c8196805d43ebf5b9',
    'rand_digit': 7,
    'rand_number': 0.9887,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-07 05:15',
    'text_array': [
    'fb6b2a0aff444209aa7eab9bc5c62007',
    '84ad8c1decdb4b87a5ca85cc71b4df47',
],
    'words': 'horse octopus',
    'nested': {
    'id': 105,
    'rand_digit': 8,
    'array': [
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
    'word': 'kangaroo',
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
    'number': 10,
},
],
},
    'nested_array': [
    [
    7,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lobster',
    'ant',
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
    'maybe': 'snail',
    'maybe_null': 'lobster',
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
    '09',
    '14',
    '08',
],
    'text_data': '7ed46b86d389413890c3929ce607ee76',
    'rand_digit': 2,
    'rand_number': 0.62537,
    'rand_signed_int': 5,
    'rand_datetime': '2000-01-14T21:28:32.044777+0000',
    'text_array': [
    '286a6794927c4353a8553b5aec6703fc',
    '5d7457bd688447f496fe750409eb6908',
],
    'words': 'dragonfly elephant',
    'nested': {
    'id': 106,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'elephant',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 8,
},
    {
    'nested_empty': None,
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
    'word': 'bear',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'ape',
    'kangaroo',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'kangaroo',
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
    '05',
],
    'text_data': '67a1051315ac4eb2b0450b7c6e0a1872',
    'rand_digit': 6,
    'rand_number': 0.25737,
    'rand_signed_int': -8,
    'rand_datetime': '2000-03-27',
    'text_array': [
    '9acb422741094ae5bb6b51128042335a',
    'f187c8fe413f42f7b35ed193a7d6e381',
],
    'words': 'bee duck',
    'nested': {
    'id': 107,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'hippo',
    'panda',
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
    'mixed_type': {
    'key': 'value',
},
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
    '23',
    '23',
    '03',
    '27',
],
    'text_data': 'a45d3fca9ae6456c9ad2300baec2af4b',
    'rand_digit': 3,
    'rand_number': 0.93865,
    'rand_signed_int': -2,
    'rand_datetime': '2000-02-11 02:07:19.707317+1000',
    'text_array': [
    '4dede66d75814947aaf2308c80cc2bf8',
    '94e0fd6ad3b94ce496e03b479b4ad400',
],
    'words': 'koala rhino',
    'nested': {
    'id': 108,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    8,
],
],
    'two_words': [
    'bee',
    'dolphin',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'hippo',
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
    '17',
    '14',
],
    'text_data': 'c01223709bdd4e619df880a2c423f42a',
    'rand_digit': 2,
    'rand_number': 0.5898,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-22 12:20',
    'text_array': [
    '0485e34985bd4181a949ae7131569d7f',
    'f27b91aaf9334071a04af4f084755707',
],
    'words': 'camel fox',
    'nested': {
    'id': 109,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    -2,
],
],
    'two_words': [
    'fish',
    'deer',
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
    'mixed_type': None,
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
    '10',
    '20',
    '28',
],
    'text_data': 'c2d3fbebc32d48c8994cf19fc7277668',
    'rand_digit': 5,
    'rand_number': 0.30965,
    'rand_signed_int': 5,
    'rand_datetime': '2000-08-06 04:47:24.886356',
    'text_array': [
    '8ba3466de0f4481ca2e03ac2ae952352',
    '19886776cfd04eed965897d68969207c',
],
    'words': 'hyena lizard',
    'nested': {
    'id': 110,
    'rand_digit': 8,
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
],
    'word': 'tiger',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    4,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'butterfly',
    'grasshopper',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': [
    96,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'fish',
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
    '06',
    '17',
    '04',
],
    'text_data': 'a2dce7614b1b4ce6ae9f18e7b35bc2ea',
    'rand_digit': 7,
    'rand_number': 0.35976,
    'rand_signed_int': -3,
    'rand_datetime': '2000-05-09T23:36:59.615148',
    'text_array': [
    'f4155971c188438582bfb82c6519545b',
    '4b6db5e1604449d1828e04a31c75d80b',
],
    'words': 'ape rabbit',
    'nested': {
    'id': 111,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'butterfly',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 7,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    4,
],
],
    'two_words': [
    'butterfly',
    'scorpion',
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
    'mixed_type': 0.48508,
    'maybe': 'bear',
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
    '29',
],
    'text_data': 'ed3b36737b8b4b4d96e76bfe9d3e448c',
    'rand_digit': 6,
    'rand_number': 0.00641,
    'rand_signed_int': 7,
    'rand_datetime': '2000-11-02T19:45:05.612760',
    'text_array': [
    '09a61c2c9cac4c63ad535bc892f103e6',
    '86436fe30d5a483381d224c828af0f6b',
],
    'words': 'hyena sloth',
    'nested': {
    'id': 112,
    'rand_digit': 9,
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
    'spider',
    'dolphin',
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
    'mixed_type': {
    'key': 'value',
},
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
    '02',
],
    'text_data': 'ebfd9daa2c874d23a8039a1fbab66a44',
    'rand_digit': 6,
    'rand_number': 0.5876,
    'rand_signed_int': -1,
    'rand_datetime': '2000-10-13 01:39',
    'text_array': [
    'aa10ec86d1a24528987f6594db9e8e54',
    '132b9d573c8944a68275220deefc5d48',
],
    'words': 'octopus giraffe',
    'nested': {
    'id': 113,
    'rand_digit': 2,
    'array': [
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
],
    'word': 'deer',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'shark',
    'snail',
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
    'mixed_type': 'snail',
    'maybe_null': 'spider',
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
    '24',
],
    'text_data': '3cf4fea4833a46c289504eceab9ba484',
    'rand_digit': 8,
    'rand_number': 0.02424,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-31T10:52:17.188123',
    'text_array': [
    '52903404299d44d29361573216fc70d0',
    '828dee8b2f1d4d19ab3d84cb90bfd60c',
],
    'words': 'rabbit lizard',
    'nested': {
    'id': 114,
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
    'number': 6,
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
    'word': 'panda',
    'number': 9,
},
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
],
    'two_words': [
    'sheep',
    'crab',
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
    'maybe': 'elephant',
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
    'text_data': '2061fc5949a24fc39470abfab165b709',
    'rand_digit': 2,
    'rand_number': 0.71261,
    'rand_signed_int': 8,
    'rand_datetime': '2000-01-04 18:41:43.663783-0500',
    'text_array': [
    'ebd6e18541664bb79dc6e55679e9293f',
    '981d3f782d2e41e6968fc22c0f9f71f5',
],
    'words': 'chicken rabbit',
    'nested': {
    'id': 115,
    'rand_digit': 5,
    'array': [
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
    'hello',
],
    'word': 'fox',
    'number': 7,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
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
    'grasshopper',
    'squid',
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
    'mixed_type': None,
    'maybe_null': 'tiger',
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
    '11',
    '01',
    '26',
],
    'text_data': 'b3a6c3ec84174cd794e955550a9ccc3a',
    'rand_digit': 7,
    'rand_number': 0.30203,
    'rand_signed_int': -6,
    'rand_datetime': '2000-01-09T01:35:27.213664',
    'text_array': [
    'ee14ce1fa6924f7eaf6a8149ec830a5d',
    'af9fa7fa39404bda8aa0501d1430a563',
],
    'words': 'hyena monkey',
    'nested': {
    'id': 116,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 7,
},
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
    'snake',
    'lobster',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': [
    18,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'pig',
    'maybe_null': 'squid',
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
    '27',
],
    'text_data': '582542fc7a7a4cd18ab34daf2b4df695',
    'rand_digit': 7,
    'rand_number': 0.95876,
    'rand_signed_int': -8,
    'rand_datetime': '2000-01-04T22:29:44',
    'text_array': [
    '86bd8a3624cb4f53b135f5836ac4d74b',
    '1fd680518fd24e49af44bfe65e603514',
],
    'words': 'panda monkey',
    'nested': {
    'id': 117,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 5,
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
    'nested_empty': None,
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
    'word': 'rhino',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'butterfly',
    'duck',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': [
    37,
],
    'rand_bool': False,
    'mixed_type': 3,
    'maybe_null': None,
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
    '04',
    '03',
    '19',
    '18',
    '09',
],
    'text_data': 'e506dfee1d244da2b303df8ca7a49ac7',
    'rand_digit': 9,
    'rand_number': 0.62893,
    'rand_signed_int': 9,
    'rand_datetime': '2000-12-20',
    'text_array': [
    '54e8847a5dd9488f9a7d430f4cd69b6a',
    '91396a26cd8a4e45b2cb4da51b3bdc05',
],
    'words': 'ape leopard',
    'nested': {
    'id': 118,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'panda',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 2,
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
    [
    4,
],
    [
    3,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'kangaroo',
    'dog',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': [
    20,
],
    'rand_bool': False,
    'mixed_type': 'cheetah',
    'maybe': 'mouse',
    'maybe_null': 'ladybug',
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
    'text_data': '3e680b51e6e04b86b04bc55734721a12',
    'rand_digit': 1,
    'rand_number': 0.374,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-21 18:51:41.326592',
    'text_array': [
    '5dd1729c109d45a5a8ed3e66c36c9f85',
    '8c4591ad84e346d69385519e98097987',
],
    'words': 'cheetah hyena',
    'nested': {
    'id': 119,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
],
    'word': 'cow',
    'number': 7,
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
    [
    7,
],
],
    'two_words': [
    'jaguar',
    'pig',
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
    'mixed_type': 'squid',
    'maybe': 'fish',
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
    '25',
    '03',
    '18',
],
    'text_data': 'ae3fcc40a6ba4d3eb407ca53f80aca29',
    'rand_digit': 7,
    'rand_number': 0.61327,
    'rand_signed_int': -2,
    'rand_datetime': '2000-08-23T10:24:02.839993',
    'text_array': [
    '64142a5d3f654a229c85ff2721214f2f',
    '66ddf410732c4db0bd7078f20868c5f9',
],
    'words': 'cow panda',
    'nested': {
    'id': 120,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dog',
    'mouse',
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
    'maybe': 'mosquito',
    'maybe_null': 'bee',
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
    '19',
    '03',
    '22',
    '30',
],
    'text_data': '39687bd4124f497585924aee947c0b7f',
    'rand_digit': 5,
    'rand_number': 0.99737,
    'rand_signed_int': -2,
    'rand_datetime': '2001-01-21T22:10:18.890093+0900',
    'text_array': [
    '77f1ae8d0ab54361a54be6ae3b4b6344',
    '156748c185834c969496fca354fc9c55',
],
    'words': 'dragonfly cow',
    'nested': {
    'id': 121,
    'rand_digit': 6,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'camel',
    'number': 4,
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
    [
    9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ape',
    'sheep',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': [
    72,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'koala',
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
    '23',
    '01',
],
    'text_data': '1e348aeceda54c108ef4ca53139e01ea',
    'rand_digit': 8,
    'rand_number': 0.62253,
    'rand_signed_int': 2,
    'rand_datetime': '2001-01-21T12:37:39.498310',
    'text_array': [
    '00a4cefe5e8e4b34922432152141343c',
    '536aed644ab64e4ea76ce7a89db69cb8',
],
    'words': 'camel turtle',
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
    'word': 'scorpion',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'giraffe',
    'lizard',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'dragonfly',
    'maybe_null': 'gorilla',
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
    '15',
],
    'text_data': 'ef5783e1f8ff4e959d27e9348852367b',
    'rand_digit': 2,
    'rand_number': 0.1371,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-10T02:33:02.911746',
    'text_array': [
    'f9c451eefe554535899523e72792313c',
    'c64ab7263acb45ecbcf013a8a14d47d5',
],
    'words': 'dolphin camel',
    'nested': {
    'id': 123,
    'rand_digit': 7,
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
    'word': 'leopard',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    3,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'turtle',
    'camel',
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
    'mixed_type': 'cow',
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
    '11',
    '05',
    '26',
],
    'text_data': '63ea191db2c54841bffa33ee0965a173',
    'rand_digit': 4,
    'rand_number': 0.71134,
    'rand_signed_int': 3,
    'rand_datetime': '2000-05-11',
    'text_array': [
    '8597d35563f14424a377ac9e13767aba',
    'fe30cb05ae774cb4a638144719c0e6b4',
],
    'words': 'leopard zebra',
    'nested': {
    'id': 124,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bear',
    'number': 10,
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
    -5,
],
    [
    -2,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'rabbit',
    'jaguar',
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
    'maybe': 'frog',
    'maybe_null': 'mosquito',
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
    '22',
    '21',
    '11',
    '12',
    '06',
],
    'text_data': '04375ed162234dd2a56a2f8355a78a69',
    'rand_digit': 1,
    'rand_number': 0.75999,
    'rand_signed_int': 9,
    'rand_datetime': '2000-01-08 12:46',
    'text_array': [
    '9ad7105d9c6141f3a95937a352e9f2f4',
    '9a5fa1573db4467d9037a4c15a156078',
],
    'words': 'snake kangaroo',
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
    'word': 'rhino',
    'number': 4,
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
    'word': 'spider',
    'number': 1,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
    -7,
],
    [
],
    [
],
],
    'two_words': [
    'jaguar',
    'bee',
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
    'mixed_type': 'frog',
    'maybe': 'gorilla',
    'maybe_null': 'hyena',
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
    '15',
    '22',
    '13',
],
    'text_data': '96c69449e30d43ec980a2a767d2339d5',
    'rand_digit': 8,
    'rand_number': 0.90056,
    'rand_signed_int': 4,
    'rand_datetime': '2000-04-23T10:32:15.943975-0200',
    'text_array': [
    '39cae47297664aa58a3d0d0807639a3c',
    'f8e1a78b80364037ace3b02cc209f332',
],
    'words': 'mosquito scorpion',
    'nested': {
    'id': 126,
    'rand_digit': 5,
    'array': [
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
    'word': 'lion',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'sloth',
    'cheetah',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': [
    52,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'bird',
    'maybe_null': 'ladybug',
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
    '26',
    '23',
    '24',
    '02',
],
    'text_data': '03475c68e1c9414f91c53b18680c47f6',
    'rand_digit': 4,
    'rand_number': 0.10628,
    'rand_signed_int': 3,
    'rand_datetime': '2000-06-06',
    'text_array': [
    'dc7f6ed4be5e4e2abf4829748021b35a',
    'bb0c62970af349039550d9194e3de5bc',
],
    'words': 'whale cat',
    'nested': {
    'id': 127,
    'rand_digit': 3,
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
],
    'word': 'gorilla',
    'number': 6,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 4,
},
],
},
    'nested_array': [
    [
    -7,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'crab',
    'camel',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': [
    69,
],
    'rand_bool': False,
    'mixed_type': 9,
    'maybe': 'bee',
    'maybe_null': 'leopard',
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
    '21',
],
    'text_data': '8edd68c719b0407a84b539a1828d595e',
    'rand_digit': 3,
    'rand_number': 0.4656,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-02 05:43',
    'text_array': [
    '3351cd02512c4129bc5ecc1af6d6360c',
    'b32ba5a4a1724f51bf2c51d2c3e77995',
],
    'words': 'octopus squid',
    'nested': {
    'id': 128,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 1,
},
    {
    'nested_empty': None,
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
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    [
    7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'camel',
    'frog',
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
    'mixed_type': 0,
    'maybe': 'fly',
    'maybe_null': 'wolf',
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
    '28',
    '27',
    '01',
],
    'text_data': '985be8016e3342eb80828000b34692f4',
    'rand_digit': 6,
    'rand_number': 0.12824,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-07',
    'text_array': [
    '12cfce24d0704094bd1e8c63982e6a10',
    '945ea85376644c28bff39243be363489',
],
    'words': 'hippo lion',
    'nested': {
    'id': 129,
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
],
    'word': 'dog',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dog',
    'duck',
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
    'mixed_type': False,
    'maybe': 'lion',
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
    '19',
    '28',
],
    'text_data': '2821e465ede444e7bcceef2bc01e2203',
    'rand_digit': 3,
    'rand_number': 0.14434,
    'rand_signed_int': -10,
    'rand_datetime': '2000-12-19T00:21:44.787488-01:00',
    'text_array': [
    'b505f2a04a604e06aff71ea2ab9bd636',
    'e983e1369f2341249374e9d870d5bcb3',
],
    'words': 'butterfly cheetah',
    'nested': {
    'id': 130,
    'rand_digit': 5,
    'array': [
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
    'word': 'elephant',
    'number': 10,
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
],
],
    'two_words': [
    'duck',
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
    'rand_bool': False,
    'mixed_type': 0.17105,
    'maybe': 'lion',
    'maybe_null': 'sheep',
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
],
    'text_data': 'ff722213807844dea0d13c5ea5db9648',
    'rand_digit': 1,
    'rand_number': 0.11191,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-30T12:39:09.789114-0200',
    'text_array': [
    'bd5ed38754b04c80bda9c215c0bedc76',
    '4278926fd67244df9c2b097a9006ef4e',
],
    'words': 'giraffe cow',
    'nested': {
    'id': 131,
    'rand_digit': 1,
    'array': [
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'monkey',
    'lobster',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
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
    '27',
    '04',
    '16',
],
    'text_data': '286be9a55f05440daa0487147e7a81ca',
    'rand_digit': 8,
    'rand_number': 0.4688,
    'rand_signed_int': -9,
    'rand_datetime': '2000-03-24',
    'text_array': [
    'e5f2f08af23d43ca8f1834c85c2d8b38',
    '8942cbfc292d4d4fb96eb1dacdeb0829',
],
    'words': 'dolphin cow',
    'nested': {
    'id': 132,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'butterfly',
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
    [
],
],
    'two_words': [
    'fly',
    'lion',
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
    'mixed_type': 'fly',
    'maybe': 'hyena',
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
    '23',
    '23',
    '26',
],
    'text_data': '7adab9ee88d64a39a6977172c498506f',
    'rand_digit': 7,
    'rand_number': 0.53657,
    'rand_signed_int': -4,
    'rand_datetime': '2000-07-05T22:19:16.243106-02:00',
    'text_array': [
    'd4f8e5a6483c4da096209c862900d94f',
    'b300d82822084360bd7c8ecdc568df9f',
],
    'words': 'mosquito cheetah',
    'nested': {
    'id': 133,
    'rand_digit': 2,
    'array': [
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
    'word': 'grasshopper',
    'number': 4,
},
],
},
    'nested_array': [
    [
    0,
],
],
    'two_words': [
    'ladybug',
    'deer',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cow',
    'maybe_null': 'cow',
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
    '09',
    '09',
    '27',
],
    'text_data': '7eacff0706064a12a9928bcf6f790ce9',
    'rand_digit': 7,
    'rand_number': 0.46303,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-30T16:37:13.793310',
    'text_array': [
    '6d113f894eb84f09a9746dd039be1290',
    '0d85a1f84b54409cb82daa0012ec823d',
],
    'words': 'snake kangaroo',
    'nested': {
    'id': 134,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'snake',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'fox',
    'horse',
],
    'city': {
    'name': 'Athens',
    'geo': {
    'lat': 37.98381,
    'lon': 23.727539,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'hippo',
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
    'text_data': 'b0f5ec6c90e74ce8acbfaebf33c80978',
    'rand_digit': 5,
    'rand_number': 0.2328,
    'rand_signed_int': -10,
    'rand_datetime': '2000-02-17T00:24:14.452702',
    'text_array': [
    '18aa3e6ae20947338c7e3a94e884ad4b',
    '41141a5942e24ea9a1157e4e6051d73c',
],
    'words': 'bear snake',
    'nested': {
    'id': 135,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -2,
],
],
    'two_words': [
    'turtle',
    'spider',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'elephant',
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
    '27',
    '01',
    '05',
    '12',
],
    'text_data': '6acf1e0608ac476180837835780992f0',
    'rand_digit': 4,
    'rand_number': 0.94024,
    'rand_signed_int': -6,
    'rand_datetime': '2001-01-22 12:57',
    'text_array': [
    '4e75a59cfc894b088b1105d9b03f1ad1',
    '4c60e636bc77449d9f634e46cfb02f0c',
],
    'words': 'sheep bear',
    'nested': {
    'id': 136,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'ape',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'grasshopper',
    'wolf',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
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
    'text_data': 'b81acb4fa1444f229d24d3bfef1da969',
    'rand_digit': 7,
    'rand_number': 0.65718,
    'rand_signed_int': -7,
    'rand_datetime': '2000-05-05T12:18:20+0100',
    'text_array': [
    'c49877f84ae943fe86900f2ff6b6b84a',
    '054d7273955c4ec3a01c49cce4684d86',
],
    'words': 'whale giraffe',
    'nested': {
    'id': 137,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 9,
},
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
],
    'word': 'octopus',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'cheetah',
    'pig',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.20223,
    'maybe': 'goat',
    'maybe_null': 'fish',
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
    '26',
    '08',
    '30',
    '07',
    '15',
],
    'text_data': '9a8eef1823ec42da93c91cdbf97aae5d',
    'rand_digit': 5,
    'rand_number': 0.21028,
    'rand_signed_int': -5,
    'rand_datetime': '2000-10-11T19:16:11.102652+12:00',
    'text_array': [
    'aabdfd2c1e784cc19c00bee9faa44912',
    '262e1936469f42b09a80c97b3eb0839c',
],
    'words': 'deer jaguar',
    'nested': {
    'id': 138,
    'rand_digit': 7,
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
    'word': 'mosquito',
    'number': 4,
},
],
},
    'nested_array': [
    [
    -4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'camel',
    'ape',
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
    '21',
    '22',
],
    'text_data': '48e76f1a031b43c6aaebd025103d1a2c',
    'rand_digit': 6,
    'rand_number': 0.09933,
    'rand_signed_int': -6,
    'rand_datetime': '2000-07-27T23:21:55',
    'text_array': [
    '2b9a2e5c30954a02b6950505fe461878',
    'b594e5d3ee1545a6858517e439a490a1',
],
    'words': 'tiger grasshopper',
    'nested': {
    'id': 139,
    'rand_digit': 9,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 9,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 2,
},
],
},
    'nested_array': [
    [
    1,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'pig',
    'dragonfly',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '25',
    '10',
],
    'text_data': '141b88224f7e497ab3c444cd25e8ed78',
    'rand_digit': 3,
    'rand_number': 0.98847,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-10T23:52:09',
    'text_array': [
    '7633d1f8196e416c9865e5df50a12215',
    '80240c6276b44c52b4f95f83b3a5ebee',
],
    'words': 'shark zebra',
    'nested': {
    'id': 140,
    'rand_digit': 5,
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
    'hello',
],
    'word': 'fly',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'duck',
    'fly',
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
],
    'text_data': '0c40dacc2c954b2dbfe1561b49d83db3',
    'rand_digit': 2,
    'rand_number': 0.05692,
    'rand_signed_int': -10,
    'rand_datetime': '2000-07-27T15:04:21.338449',
    'text_array': [
    'f37578c7b7a24455999d762379336f5f',
    '775f203e6892498f97ac04022bc18f39',
],
    'words': 'bee monkey',
    'nested': {
    'id': 141,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 8,
},
],
},
    'nested_array': [
    [
    6,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'snake',
    'tiger',
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
    'mixed_type': 'sloth',
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
    '25',
],
    'text_data': '82ff4a70602a4cb68a49d9037bd0adbc',
    'rand_digit': 4,
    'rand_number': 0.41563,
    'rand_signed_int': 6,
    'rand_datetime': '2000-10-28T18:23:22.409672',
    'text_array': [
    '7a4c3525bb5a4b59a9463737c83d3824',
    'b4fdcdaf91184e22a34fe9c22be4badb',
],
    'words': 'ant cat',
    'nested': {
    'id': 142,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'snail',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cat',
    'cheetah',
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
    'mixed_type': 9,
    'maybe': 'fox',
    'maybe_null': 'grasshopper',
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
    '20',
    '19',
    '22',
],
    'text_data': '9b946eb0fa514810b0205259db16f2ab',
    'rand_digit': 8,
    'rand_number': 0.36711,
    'rand_signed_int': 0,
    'rand_datetime': '2000-11-09T23:41:57.496551+0200',
    'text_array': [
    'f660480d71854ac3b5c01592063f1646',
    '11e474eeb9fd48118c651c9c30c5555e',
],
    'words': 'sheep lobster',
    'nested': {
    'id': 143,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 3,
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
    'word': 'grasshopper',
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
    'bird',
    'duck',
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
    'mixed_type': 0,
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
    'text_data': '181acfc23a3d4a4a9cc2f81a00a25e6c',
    'rand_digit': 1,
    'rand_number': 0.19538,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-19',
    'text_array': [
    'eafb993035f6411fbdb17967786aa3bc',
    'edee9bbef7d34244915a58d0ebcc2a93',
],
    'words': 'wolf fly',
    'nested': {
    'id': 144,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'ladybug',
    'chicken',
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
    'mixed_type': 0.1801,
    'maybe': 'kangaroo',
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
    '06',
    '02',
    '14',
],
    'text_data': 'f391f3a4eff84187868c125922039376',
    'rand_digit': 4,
    'rand_number': 0.50039,
    'rand_signed_int': -6,
    'rand_datetime': '2000-03-31 19:28:16.740493+1100',
    'text_array': [
    '3198c79f69f349af9201222017def6a5',
    '916fe9b83e9249b7acbb9e9daf059fcf',
],
    'words': 'leopard sloth',
    'nested': {
    'id': 145,
    'rand_digit': 3,
    'array': [
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
    'word': 'ant',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 1,
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
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'dragonfly',
    'mosquito',
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
    'mixed_type': 0.87417,
    'maybe': 'jaguar',
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
    '15',
    '21',
],
    'text_data': 'bbe42abfadfb4944a39187d606e150c6',
    'rand_digit': 6,
    'rand_number': 0.4533,
    'rand_signed_int': -3,
    'rand_datetime': '2000-09-26T06:46:40.184231+05:00',
    'text_array': [
    'fedc063000074572b4df6c6962a778d3',
    'cac383eaa865483eb576a57e962034f4',
],
    'words': 'elephant fox',
    'nested': {
    'id': 146,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'squid',
    'horse',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': [
    56,
],
    'rand_bool': False,
    'mixed_type': 0.4649,
    'maybe': 'koala',
    'maybe_null': 'koala',
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
    '26',
],
    'text_data': 'fd1b53f76c294b86ae5aba9b863575e7',
    'rand_digit': 5,
    'rand_number': 0.58902,
    'rand_signed_int': -10,
    'rand_datetime': '2000-12-29 05:05:01-0200',
    'text_array': [
    'bcaeb168c61b4b34962ae56a546ea69e',
    '84663e1848f14ed5a21efeae58f51070',
],
    'words': 'frog leopard',
    'nested': {
    'id': 147,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'camel',
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
    'number': 5,
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
    'word': 'cow',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ape',
    'deer',
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
    'mixed_type': 'monkey',
    'maybe': 'turtle',
    'maybe_null': None,
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
    '07',
    '22',
    '07',
],
    'text_data': '60a154c212944a90bab74fd833a4b3b8',
    'rand_digit': 0,
    'rand_number': 0.23546,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-08 06:17:26',
    'text_array': [
    '434f05a363294f2bbf186aa450c0e8cb',
    '24a88b8dad16438cbdc18f5994561569',
],
    'words': 'bee cheetah',
    'nested': {
    'id': 148,
    'rand_digit': 6,
    'array': [
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dog',
    'scorpion',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'ladybug',
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
    'text_data': 'd728db6b88b6431d951ca89d57b23fd7',
    'rand_digit': 6,
    'rand_number': 0.30576,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-02T11:52:50.280829',
    'text_array': [
    '80da00c0d8c5454eabfe71cd81abe21c',
    '4b11b1d250424db8a88f984516a2d92a',
],
    'words': 'chicken spider',
    'nested': {
    'id': 149,
    'rand_digit': 2,
    'array': [
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'frog',
    'goat',
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
    'mixed_type': 4,
    'maybe': 'butterfly',
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
],
    'text_data': 'de5178ce6ee34b12a76a61c0acac1286',
    'rand_digit': 5,
    'rand_number': 0.8175,
    'rand_signed_int': -9,
    'rand_datetime': '2000-07-22T04:09:37',
    'text_array': [
    '146c544e73ff43738da08296f9615627',
    'f9644490003d4eaeaac19395832b5591',
],
    'words': 'whale jaguar',
    'nested': {
    'id': 150,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'crab',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bear',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'bear',
    'spider',
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
    'mixed_type': 6,
    'maybe_null': None,
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
    '08',
    '30',
    '29',
    '10',
],
    'text_data': '52d7bc2c41a74e93aaabe6b2795f19cb',
    'rand_digit': 6,
    'rand_number': 0.23452,
    'rand_signed_int': -9,
    'rand_datetime': '2000-03-17',
    'text_array': [
    'ef7db24840574b3db418d3f80a43c129',
    '5691f2db3f384e37bdc9397b454805d4',
],
    'words': 'lion sloth',
    'nested': {
    'id': 151,
    'rand_digit': 9,
    'array': [
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
    'word': 'pig',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'gorilla',
    'ladybug',
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
    'mixed_type': 0.22333,
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
    '14',
    '04',
],
    'text_data': 'e95db6c71cd74ec6aa3eec4dd6f3c613',
    'rand_digit': 1,
    'rand_number': 0.66449,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-16T12:26:01.528575',
    'text_array': [
    '0d06ef8be8f64a8dbb11d9202e4df113',
    'ee92dc6666de4fe7a33ee9a0a6a9bcc7',
],
    'words': 'fish kangaroo',
    'nested': {
    'id': 152,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'deer',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'pig',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'leopard',
    'horse',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': [
    80,
],
    'rand_bool': True,
    'mixed_type': 'squid',
    'maybe_null': 'deer',
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
    '14',
    '16',
    '21',
    '11',
],
    'text_data': 'c2ed25017d1641759e79cce3cf6319ea',
    'rand_digit': 6,
    'rand_number': 0.01726,
    'rand_signed_int': 0,
    'rand_datetime': '2000-11-30 20:34:31.551728+0800',
    'text_array': [
    'b275c4b1b68345f0a5a6abf97c89f991',
    '29d6b778390a4441ac620e3add807bda',
],
    'words': 'mosquito ladybug',
    'nested': {
    'id': 153,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 3,
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
    'word': 'lion',
    'number': 6,
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
],
],
    'two_words': [
    'spider',
    'fly',
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
    'mixed_type': {
    'key': 'value',
},
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
    '11',
    '06',
],
    'text_data': '418712eb13914c5fa8b1a02d65bac0f6',
    'rand_digit': 7,
    'rand_number': 0.71397,
    'rand_signed_int': -9,
    'rand_datetime': '2000-12-11T01:26:20.917289',
    'text_array': [
    'db614b141f0e4ceebf25f4c5e00f3664',
    '1cf8063f811c4c2ca9da4eb139ce163c',
],
    'words': 'octopus camel',
    'nested': {
    'id': 154,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'lizard',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'scorpion',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'chicken',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'whale',
    'maybe_null': 'fish',
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
],
    'text_data': 'f6a7b55c78d54eddafa40e239ad90f3d',
    'rand_digit': 7,
    'rand_number': 0.50178,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-12T03:22:25',
    'text_array': [
    '084f773d0112443a9baa833738f7d8cf',
    '7663d04174fd4bee9cec24e3d924700d',
],
    'words': 'ladybug rabbit',
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
    'word': 'ant',
    'number': 10,
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
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'octopus',
    'frog',
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
    '09',
],
    'text_data': '06a5ddd439e043a5885aaa2eeef74750',
    'rand_digit': 7,
    'rand_number': 0.55221,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-04T06:52:23.135141-0600',
    'text_array': [
    'fac857fb2e624c3a93a92649d8ac918e',
    '75384e0e830f445590ca68df533e23b3',
],
    'words': 'ape dolphin',
    'nested': {
    'id': 156,
    'rand_digit': 7,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'snail',
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
    'mixed_type': 'wolf',
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
    '02',
    '13',
    '26',
    '10',
],
    'text_data': '25c90920a9b84b828d675fa8a9a24434',
    'rand_digit': 0,
    'rand_number': 0.69409,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-07 17:49:57.639480',
    'text_array': [
    '0f4f584a9ae04327aec57d49c37a0041',
    'f3e46f52e6374d9da4eed4b644860de1',
],
    'words': 'deer spider',
    'nested': {
    'id': 157,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'lobster',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'ant',
    'ape',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'grasshopper',
    'maybe_null': 'rhino',
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
    '10',
],
    'text_data': '04a00e63e7204a128ea4b0e4d4d5ba3a',
    'rand_digit': 9,
    'rand_number': 0.21928,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-03 04:22:46-0200',
    'text_array': [
    '93270a66c40b44dab2ac5ae3f984bdd0',
    'e32f2bf11a6946509c4bc8d8a09e99d6',
],
    'words': 'sloth zebra',
    'nested': {
    'id': 158,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bear',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -3,
],
],
    'two_words': [
    'wolf',
    'monkey',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cow',
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
    '25',
],
    'text_data': '3477633bab8c41509026a7d127e5cd86',
    'rand_digit': 0,
    'rand_number': 0.80201,
    'rand_signed_int': 9,
    'rand_datetime': '2001-01-25T04:43:19.862703',
    'text_array': [
    '2e8db9cb9e9d4d51a10fbcfb8a1f3d62',
    '9881247ccbc646d5b1e36f7caef5a901',
],
    'words': 'ant ladybug',
    'nested': {
    'id': 159,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'fly',
    'chicken',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'mouse',
    'maybe': 'mouse',
    'maybe_null': 'fox',
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
    '21',
    '05',
    '22',
],
    'text_data': 'f021085d60bc4e588f969c4aac423502',
    'rand_digit': 7,
    'rand_number': 0.1477,
    'rand_signed_int': -5,
    'rand_datetime': '2000-01-14 06:30:56.388061',
    'text_array': [
    '4cfb57d427fd490d800ac43bfb8e8743',
    '37d6a370c5ad4eadbf41ec5aef9218d7',
],
    'words': 'mosquito ant',
    'nested': {
    'id': 160,
    'rand_digit': 8,
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
    'word': 'sloth',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ape',
    'lion',
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
    'mixed_type': None,
    'maybe_null': 'giraffe',
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
    '06',
    '20',
    '27',
],
    'text_data': '845142d2ef6c4f7086769e075d293711',
    'rand_digit': 1,
    'rand_number': 0.6737,
    'rand_signed_int': -6,
    'rand_datetime': '2000-05-06T00:02:47.245460-10:00',
    'text_array': [
    '6bdf544567354080918c6fb8c095bcbf',
    '1f26c6a9f92a40d3aa61e5572e39cec9',
],
    'words': 'sheep elephant',
    'nested': {
    'id': 161,
    'rand_digit': 7,
    'array': [
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
    [
    -9,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'crab',
    'lizard',
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
    'mixed_type': False,
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
    'text_data': 'c300c1099efd4c2eb80fae67ecbf9a7a',
    'rand_digit': 0,
    'rand_number': 0.03067,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-16 19:17:25',
    'text_array': [
    'c01cda654e43483abfadc84836c12c24',
    '7361f0b918f7491d8fea1d1653185aaf',
],
    'words': 'bird rabbit',
    'nested': {
    'id': 162,
    'rand_digit': 8,
    'array': [
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
    'word': 'leopard',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'hippo',
    'fox',
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
    'mixed_type': 'hyena',
    'maybe': 'hyena',
    'maybe_null': 'mosquito',
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
    '21',
    '20',
    '02',
    '22',
],
    'text_data': 'c234feca0fbc4339a53c32b4ae2fa919',
    'rand_digit': 9,
    'rand_number': 0.9154,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-21T10:05:02.578818-01:00',
    'text_array': [
    '7e19025eb5514f5db959ac7146387dad',
    '71b7077212f74f76b680981c854140a1',
],
    'words': 'mosquito cat',
    'nested': {
    'id': 163,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 5,
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
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'mosquito',
    'tiger',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe_null': 'deer',
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
    'content-length': '138014',
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
    '06',
    '30',
    '15',
    '24',
],
    'text_data': '2b17b522352240e8a4111b013105ee80',
    'rand_digit': 8,
    'rand_number': 0.74959,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-27 21:03',
    'text_array': [
    '14a58344107b4aaba57e5b2ec3fbf07a',
    '2b356a69edf94b968bd8e578d59f5c08',
],
    'words': 'fox octopus',
    'nested': {
    'id': 100,
    'rand_digit': 9,
    'array': [
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
    'word': 'elephant',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'elephant',
    'rabbit',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 'snail',
    'maybe_null': 'elephant',
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
    '26',
    '04',
],
    'text_data': '9842700b57f144dd93f813526f0dfbb1',
    'rand_digit': 4,
    'rand_number': 0.65,
    'rand_signed_int': 9,
    'rand_datetime': '2000-01-20 18:00',
    'text_array': [
    '6fa498a26150479e8633205a2ca2b79d',
    'fcce8dab1f064f9f82281f76e55b734a',
],
    'words': 'dragonfly lion',
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
    'word': 'turtle',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'duck',
    'fox',
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
    'mixed_type': 7,
    'maybe': 'scorpion',
    'maybe_null': 'hippo',
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
    '23',
    '30',
    '17',
    '07',
],
    'text_data': '333f3a36f11a4295ab0af5352b79b49d',
    'rand_digit': 1,
    'rand_number': 0.04729,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-08T09:05:12.142158',
    'text_array': [
    '80c13e15455a4722865c0054b10c39d8',
    'e1a7e1116b0b4081bcc66d49279d6820',
],
    'words': 'fish mosquito',
    'nested': {
    'id': 102,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'camel',
    'cheetah',
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
    'mixed_type': 9,
    'maybe': 'horse',
    'maybe_null': 'ladybug',
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
    '27',
],
    'text_data': 'e4d1272528514868881ec21d05f55b97',
    'rand_digit': 1,
    'rand_number': 0.88145,
    'rand_signed_int': 2,
    'rand_datetime': '2000-06-11T17:46:43.521148',
    'text_array': [
    '81eacfdb89044a3ea884890cc8dbcd72',
    'a45eddaa2a0342cc83db2d5a822ac8e2',
],
    'words': 'cow shark',
    'nested': {
    'id': 103,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'duck',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'dog',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'hippo',
    'fly',
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
    'mixed_type': 'ape',
    'maybe': 'grasshopper',
    'maybe_null': None,
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
    '12',
],
    'text_data': '48ee63b82a0844d098f55a9773706f8b',
    'rand_digit': 9,
    'rand_number': 0.89576,
    'rand_signed_int': -10,
    'rand_datetime': '2000-02-01 00:37',
    'text_array': [
    'a55b0652e5724dabbc7d8c6fe00a687e',
    '953dddab0f714adbaa561e97e8ff24dc',
],
    'words': 'fox leopard',
    'nested': {
    'id': 104,
    'rand_digit': 7,
    'array': [
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
    'word': 'sloth',
    'number': 7,
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
    'word': 'panda',
    'number': 4,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'frog',
    'pig',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': [
    12,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
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
    '24',
],
    'text_data': '7c27823e59284f33b742f44affd80894',
    'rand_digit': 5,
    'rand_number': 0.37618,
    'rand_signed_int': -3,
    'rand_datetime': '2000-07-11 01:58:36',
    'text_array': [
    'ae02786c95ab49ebb34b7e64940d0148',
    '2685398435d840cdb2ad537af37c455b',
],
    'words': 'sheep camel',
    'nested': {
    'id': 105,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 5,
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
    'hello',
],
    'word': 'bird',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'kangaroo',
    'hippo',
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
    'mixed_type': 'mosquito',
    'maybe_null': 'rhino',
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
    '03',
    '01',
    '25',
],
    'text_data': '72af9f6b1c424d07850021249df21703',
    'rand_digit': 8,
    'rand_number': 0.74421,
    'rand_signed_int': -5,
    'rand_datetime': '2000-10-15T16:14:49.723308-0600',
    'text_array': [
    'e1e54bf318d44651bd2314013f50c77d',
    '45e62241b20942bb92cecd048665a1e0',
],
    'words': 'giraffe zebra',
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
    'word': 'cheetah',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ape',
    'pig',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': [
    7,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'fly',
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
    'text_data': '1242be0f19044b259b6f8f7f24f561c5',
    'rand_digit': 2,
    'rand_number': 0.60093,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-24 09:06',
    'text_array': [
    '2dcb8d0dc70444d8a461bdb03cdb66fc',
    '5a6adb6bbd3748829284fd8de3550cf1',
],
    'words': 'turtle bee',
    'nested': {
    'id': 107,
    'rand_digit': 0,
    'array': [
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
    'word': 'rabbit',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 8,
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
],
},
    'nested_array': [
],
    'two_words': [
    'shark',
    'cheetah',
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
    'mixed_type': 0.86777,
    'maybe_null': 'fish',
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
    '23',
    '10',
    '16',
    '08',
    '08',
],
    'text_data': '8dfe1e95cdd84ddd95eade3c6c6a0659',
    'rand_digit': 3,
    'rand_number': 0.62575,
    'rand_signed_int': -8,
    'rand_datetime': '2000-06-09T14:05:39',
    'text_array': [
    '88f6e2d23ecf4074b15da74a2ff4fc29',
    'ea798541aedb47f7a59264645fd1eb32',
],
    'words': 'camel pig',
    'nested': {
    'id': 108,
    'rand_digit': 4,
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
],
    'word': 'scorpion',
    'number': 9,
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
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'pig',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'cheetah',
    'squid',
],
    'city': {
    'name': 'Kharkiv',
    'geo': {
    'lat': 49.980812,
    'lon': 36.25272,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'crab',
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
    'text_data': 'aab226fb376f4e7582248ac5a28fa903',
    'rand_digit': 1,
    'rand_number': 0.88526,
    'rand_signed_int': -5,
    'rand_datetime': '2000-12-23T15:58:20.889861-0400',
    'text_array': [
    '86af3ac71d7a4d32bd55816554fde92f',
    'ade8c7c0a0e148bcaa93533d670d2c9b',
],
    'words': 'cat hippo',
    'nested': {
    'id': 109,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lion',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'leopard',
    'number': 7,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_3,3__',
    'two_words': [
    'tiger',
    'panda',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': [
    1,
],
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
],
    'text_data': '00254929949845f594c4b31224c6e981',
    'rand_digit': 8,
    'rand_number': 0.84393,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-06T20:15:23.575542+03:00',
    'text_array': [
    '0d74d4cb0d9842469163484071d823e0',
    'f41c38bbcd244cdbacc3e30d44761c50',
],
    'words': 'goat sloth',
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
    'word': 'gorilla',
    'number': 10,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
    [
    -10,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'bird',
    'fish',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': [
    57,
],
    'rand_bool': False,
    'mixed_type': 0.19087,
    'maybe_null': 'snake',
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
    '09',
    '30',
    '05',
],
    'text_data': 'c5d69945b1f641febe058294420a87e2',
    'rand_digit': 0,
    'rand_number': 0.65405,
    'rand_signed_int': -7,
    'rand_datetime': '2000-04-13T12:30:21.199279-0100',
    'text_array': [
    'ba9430f4ed8b4dfc92ab0c6f125b1c4a',
    '00058b2055c24c179ec139c7461b7bad',
],
    'words': 'tiger ladybug',
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
    'word': 'giraffe',
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
    'number': 2,
},
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
    'word': 'rhino',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'rabbit',
    'scorpion',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '27',
    '07',
    '30',
    '14',
],
    'text_data': 'd77a3521516042ec80e591b330fd720e',
    'rand_digit': 9,
    'rand_number': 0.18403,
    'rand_signed_int': 9,
    'rand_datetime': '2000-08-09 07:23:10+0900',
    'text_array': [
    '42ff0d634a5a4cfb80a220d070a79a51',
    '1a9bd4b605ec43a2bc1af39c9bb4bca3',
],
    'words': 'shark lizard',
    'nested': {
    'id': 112,
    'rand_digit': 4,
    'array': [
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
    1,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'monkey',
    'bee',
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
    'maybe_null': None,
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
],
    'text_data': 'b675bca175c048e2ad0481ebc1a45682',
    'rand_digit': 9,
    'rand_number': 0.67845,
    'rand_signed_int': -2,
    'rand_datetime': '2000-08-14T02:31:24.507809',
    'text_array': [
    '8c051a02cae04fa9bb48995fa686ebd3',
    '463275f06f724aa39fd353575901347f',
],
    'words': 'duck sloth',
    'nested': {
    'id': 113,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'turtle',
    'number': 2,
},
],
},
    'nested_array': [
    [
    -5,
],
],
    'two_words': [
    'lion',
    'panda',
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
    'mixed_type': 'elephant',
    'maybe_null': 'chicken',
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
    '04',
],
    'text_data': '4e322c72f675483297a4761222a4a74d',
    'rand_digit': 4,
    'rand_number': 0.35996,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-20T13:02:37.906595+0800',
    'text_array': [
    '1ed2d00added4ad09111fcdd7e9b444f',
    '195be3d373114008bf4c2eaea8d12b19',
],
    'words': 'dog fox',
    'nested': {
    'id': 114,
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
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 7,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 5,
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
],
    'two_words': [
    'monkey',
    'chicken',
],
    'city': {
    'name': 'Athens',
    'geo': {
    'lat': 37.98381,
    'lon': 23.727539,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'butterfly',
    'maybe_null': None,
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
    '09',
    '16',
    '24',
],
    'text_data': '8355913630584cb5901f0fa64943c815',
    'rand_digit': 4,
    'rand_number': 0.92595,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-17T19:48:53.924414',
    'text_array': [
    'f1319ba953fd40149b5fdfd242ec8c6f',
    'b76ec8cb92dd47d8a455a21b0dd0ca15',
],
    'words': 'fox spider',
    'nested': {
    'id': 115,
    'rand_digit': 6,
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
    'word': 'snail',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'dog',
    'mouse',
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
    'maybe': 'koala',
    'maybe_null': 'shark',
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
    '07',
    '16',
    '24',
],
    'text_data': 'b31b689223af4df4b7e3244e70c1708b',
    'rand_digit': 4,
    'rand_number': 0.99494,
    'rand_signed_int': 2,
    'rand_datetime': '2000-04-16 07:32:37',
    'text_array': [
    'e34d40500872430b9bb1aff2462166ca',
    'd93ef126faf044f2b17fea72ac8614b9',
],
    'words': 'scorpion tiger',
    'nested': {
    'id': 116,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'monkey',
    'ape',
],
    'city': {
    'name': 'Frankfurt',
    'geo': {
    'lat': 50.110922,
    'lon': 8.682127,
},
},
    'rand_tuple': [
    7,
],
    'rand_bool': True,
    'mixed_type': 0.37466,
    'maybe_null': 'giraffe',
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
    '06',
    '03',
],
    'text_data': 'd0ef7e32a8a844dd8237552cb2afe1cb',
    'rand_digit': 2,
    'rand_number': 0.03555,
    'rand_signed_int': 3,
    'rand_datetime': '2000-02-16 21:37:00+1100',
    'text_array': [
    '17f0097449e24bdcb8385fb6660460af',
    '8b00193191154538ad0a2064f51cc62e',
],
    'words': 'horse dragonfly',
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
    'word': 'duck',
    'number': 7,
},
    {
    'nested_empty': None,
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
    'word': 'cat',
    'number': 5,
},
],
},
    'nested_array': [
    [
    6,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'koala',
    'lion',
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
    'maybe_null': None,
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
    '17',
],
    'text_data': 'db11b64e65cd42848fb50eab43840424',
    'rand_digit': 1,
    'rand_number': 0.26061,
    'rand_signed_int': 8,
    'rand_datetime': '2000-05-08T19:15:48',
    'text_array': [
    '9b7f4a8107a746a8a9387f75f9d07e2b',
    'fb59c1085e4c41099129a98a742cdc44',
],
    'words': 'fish deer',
    'nested': {
    'id': 118,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    2,
],
],
    'two_words': [
    'bee',
    'bird',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'kangaroo',
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
    '14',
    '27',
],
    'text_data': 'd92f1aacd867440b90ad14e64db6bcab',
    'rand_digit': 8,
    'rand_number': 0.24313,
    'rand_signed_int': -8,
    'rand_datetime': '2000-10-11T05:33:03',
    'text_array': [
    'fea5b3ae844a48d1bf3ac726c3fea19e',
    'f6a7a9dbefd5404e87cd8dead24d673a',
],
    'words': 'lion koala',
    'nested': {
    'id': 119,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'whale',
    'zebra',
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
    'maybe': 'mosquito',
    'maybe_null': 'fly',
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
    '02',
    '13',
    '20',
],
    'text_data': '2dbd4bfdabdb46bb8b2512617d43a7eb',
    'rand_digit': 0,
    'rand_number': 0.99211,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-06 09:47:04',
    'text_array': [
    'c4929490cc13432d82c7e67f43a4103f',
    '5b7e68dede3d4518a4c7cc6c5f028328',
],
    'words': 'goat tiger',
    'nested': {
    'id': 120,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'snake',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '26',
    '23',
    '14',
    '12',
],
    'text_data': 'c46ab6c354de46488501dd15eb8900df',
    'rand_digit': 4,
    'rand_number': 0.49374,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-16T08:40:06.781113',
    'text_array': [
    'ebfd978d37574970a34ef6f3e80fda56',
    '0e20f7e8eb0d4d888236c958e879d84c',
],
    'words': 'grasshopper squid',
    'nested': {
    'id': 121,
    'rand_digit': 2,
    'array': [
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
    'hello',
],
    'word': 'fly',
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
    'horse',
    'snail',
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
    'mixed_type': 0.60067,
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
    '19',
    '20',
    '20',
],
    'text_data': 'c6519abed24f4ad889f29bf12177b278',
    'rand_digit': 6,
    'rand_number': 0.82925,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-23T16:26:16.344918-0700',
    'text_array': [
    '889591d34b684814b496393f419ff763',
    '797f8bd76d514b9fbae29cad50eb219f',
],
    'words': 'giraffe butterfly',
    'nested': {
    'id': 122,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 8,
},
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
    'word': 'lobster',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'monkey',
    'camel',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'ladybug',
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
    '28',
    '16',
    '21',
    '26',
],
    'text_data': 'ace4390aeccf4899931781e1431bba47',
    'rand_digit': 4,
    'rand_number': 0.95681,
    'rand_signed_int': -10,
    'rand_datetime': '2000-02-17T05:22:28.337778-06:00',
    'text_array': [
    '4667bab3378c4e2fb449301fae6e120d',
    '26d049da36294fc78909c8ba3949ed13',
],
    'words': 'sheep bee',
    'nested': {
    'id': 123,
    'rand_digit': 7,
    'array': [
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
    'hello',
],
    'word': 'camel',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'leopard',
    'sloth',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': [
    84,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'grasshopper',
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
    '23',
    '24',
    '27',
    '17',
],
    'text_data': 'b67fd3c19b92489b84a9848ff0d54722',
    'rand_digit': 3,
    'rand_number': 0.32518,
    'rand_signed_int': 7,
    'rand_datetime': '2000-04-27 08:15:30+0700',
    'text_array': [
    '01d5e19103b04a09970a277af423c9f8',
    '2033dd3528614ea5a496f0665198dba2',
],
    'words': 'sloth elephant',
    'nested': {
    'id': 124,
    'rand_digit': 9,
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
    'word': 'goat',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    0,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'ape',
    'zebra',
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
    'mixed_type': 8,
    'maybe': 'hyena',
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
    '23',
],
    'text_data': '67ea77633ead4f6c93b586d4bceaed81',
    'rand_digit': 5,
    'rand_number': 0.26173,
    'rand_signed_int': -8,
    'rand_datetime': '2000-06-24T02:53:55.833489',
    'text_array': [
    '1a768abcd0304882aefc193af7bf9c2b',
    '37b2eeca2e334d4db1bc77323b12c260',
],
    'words': 'lizard gorilla',
    'nested': {
    'id': 125,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'fly',
    'number': 2,
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
    'hello',
],
    'word': 'grasshopper',
    'number': 4,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,3__',
    'two_words': [
    'kangaroo',
    'chicken',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
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
    '10',
    '06',
    '21',
],
    'text_data': '875789be17314045abc7aba4b0f534e4',
    'rand_digit': 0,
    'rand_number': 0.86122,
    'rand_signed_int': 1,
    'rand_datetime': '2001-01-11 11:01:54.421083',
    'text_array': [
    '113bfe280d194aa49b6234b09238836a',
    '35ff8f3f12d542b09e2878b160f4dfb8',
],
    'words': 'mosquito bear',
    'nested': {
    'id': 126,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'duck',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lizard',
    'scorpion',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'hyena',
    'maybe_null': 'scorpion',
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
    '14',
    '06',
    '22',
],
    'text_data': '2bd31537081249bc96709f73379e7a3f',
    'rand_digit': 9,
    'rand_number': 0.23572,
    'rand_signed_int': 10,
    'rand_datetime': '2000-02-09 18:29:35',
    'text_array': [
    'd9978d11bc1142a8bf9c107e404a5cc5',
    'b453c02d9d2644c4a1457e4b89bff32c',
],
    'words': 'dog duck',
    'nested': {
    'id': 127,
    'rand_digit': 3,
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
    'nested_empty': None,
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
    'word': 'wolf',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snail',
    'zebra',
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
    '05',
    '05',
    '08',
    '19',
    '17',
],
    'text_data': '3b8c82cd80284ec392a7f9a391a8463f',
    'rand_digit': 1,
    'rand_number': 0.48369,
    'rand_signed_int': 7,
    'rand_datetime': '2000-09-28 13:55',
    'text_array': [
    'f416148f64f54cc3b90d80f4e34d0333',
    '89ae0b7c38d943f39ae73d24b5576e36',
],
    'words': 'octopus hyena',
    'nested': {
    'id': 128,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'zebra',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'deer',
    'dog',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': [
    49,
],
    'rand_bool': False,
    'mixed_type': 0.20598,
    'maybe': 'butterfly',
    'maybe_null': 'giraffe',
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
    '12',
    '25',
],
    'text_data': '95b7da0320054e9e9317870dcb698148',
    'rand_digit': 5,
    'rand_number': 0.66813,
    'rand_signed_int': -10,
    'rand_datetime': '2000-01-04T03:07:51.985023+0100',
    'text_array': [
    'cc89c868b1274f38b412844c23860621',
    '9f11e9b86aab44a79e52dbf39e4bce62',
],
    'words': 'crab bird',
    'nested': {
    'id': 129,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 9,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ladybug',
    'dolphin',
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
    'mixed_type': 0.48121,
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
    '05',
],
    'text_data': 'c93aab39925b40b79a470ec1126811fa',
    'rand_digit': 6,
    'rand_number': 0.51599,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-12 14:27:59.296023-0600',
    'text_array': [
    'd13fb8df512145aeb62ab836198ca750',
    '1bb337cac98d4c15b6ab5f2db8437a88',
],
    'words': 'ant chicken',
    'nested': {
    'id': 130,
    'rand_digit': 3,
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
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 2,
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
    'word': 'wolf',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'butterfly',
    'cat',
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
    'mixed_type': 6,
    'maybe': 'wolf',
    'maybe_null': 'hyena',
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
],
    'text_data': 'b294dac79e6f4d098fe43b6d383c761f',
    'rand_digit': 4,
    'rand_number': 0.36715,
    'rand_signed_int': 2,
    'rand_datetime': '2000-10-01T23:29:26.901842+06:00',
    'text_array': [
    '7fca991046634ef3b17fac9dfbf0b7a2',
    '0776249d598243bfafa470384b97cd65',
],
    'words': 'mosquito bird',
    'nested': {
    'id': 131,
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
    'number': 6,
},
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'bird',
    'duck',
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
    'mixed_type': False,
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
],
    'text_data': '4cde1b82dfe24ed0940b5a50eda4d22f',
    'rand_digit': 7,
    'rand_number': 0.00907,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-17 15:40:12',
    'text_array': [
    'fe2bbdee613740038780a15c7d6968ed',
    '1fe743c6ad834849b6c779d0c543174b',
],
    'words': 'dragonfly fish',
    'nested': {
    'id': 132,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'mouse',
    'chicken',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
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
    '24',
],
    'text_data': '6415d6dd87c347ab9087b254eab3c596',
    'rand_digit': 2,
    'rand_number': 0.22282,
    'rand_signed_int': -8,
    'rand_datetime': '2000-05-14T08:29:38.030453+0800',
    'text_array': [
    'a189c1e8af3140fdb83d19ad5ccd61fc',
    '422d957f308b4d60aca25c89eea5e190',
],
    'words': 'snake duck',
    'nested': {
    'id': 133,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'sloth',
    'wolf',
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
    'maybe_null': 'lizard',
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
    '14',
],
    'text_data': '5a6891b1f022474e8b45ccf058b099ef',
    'rand_digit': 6,
    'rand_number': 0.1645,
    'rand_signed_int': -7,
    'rand_datetime': '2000-11-25T01:59:49-0900',
    'text_array': [
    '294c6d2861bf4545a97b749b1107815e',
    '4b958b86e91d4e44bdd8bd93237a204f',
],
    'words': 'tiger scorpion',
    'nested': {
    'id': 134,
    'rand_digit': 8,
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
],
},
    'nested_array': [
],
    'two_words': [
    'turtle',
    'ant',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 'fox',
    'maybe_null': 'giraffe',
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
    '22',
    '05',
],
    'text_data': '2c87e37667d84aea806269130ae6e390',
    'rand_digit': 0,
    'rand_number': 0.21277,
    'rand_signed_int': 2,
    'rand_datetime': '2000-01-13T08:26:19.940040',
    'text_array': [
    '31ad89c2c72944b99feef1652df2bee0',
    '6d34966306484206a32420a1a763c4b0',
],
    'words': 'spider bird',
    'nested': {
    'id': 135,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 1,
},
    {
    'nested_empty': None,
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
    'word': 'gorilla',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'gorilla',
    'grasshopper',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': [
    24,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'hippo',
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
    '01',
    '02',
    '06',
    '29',
],
    'text_data': '9f7968f8ba45455ebb97b5d77ca90836',
    'rand_digit': 5,
    'rand_number': 0.79288,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-15 12:17:33-1100',
    'text_array': [
    '74e472b052534d518e13e4ff250e50c9',
    '44c603f4e560421eb5743d515a2bee94',
],
    'words': 'snail frog',
    'nested': {
    'id': 136,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
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
],
    'word': 'hyena',
    'number': 9,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'sheep',
    'dolphin',
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
    'mixed_type': None,
    'maybe_null': None,
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
    '23',
    '09',
    '17',
],
    'text_data': '12449e5685d94005b0d5f7d31032237a',
    'rand_digit': 7,
    'rand_number': 0.81747,
    'rand_signed_int': -7,
    'rand_datetime': '2000-07-23T08:46:22',
    'text_array': [
    'ae2505d34106458abe78f7b05fef3b08',
    '7e1a8418d9fa455bb48c6b3b60907223',
],
    'words': 'giraffe hyena',
    'nested': {
    'id': 137,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dog',
    'snail',
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
    'mixed_type': 'zebra',
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
    '23',
    '22',
],
    'text_data': 'dacb377a5f3046ccaa87e8c8fd40f965',
    'rand_digit': 1,
    'rand_number': 0.61892,
    'rand_signed_int': 0,
    'rand_datetime': '2000-11-19 02:42:35.486137-0800',
    'text_array': [
    'd0e216a7da954f6c8903ddb9d4a0a4ba',
    '92cbfafdac5541c084e91f4c77f256b4',
],
    'words': 'leopard bird',
    'nested': {
    'id': 138,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 8,
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
],
    'word': 'dog',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hyena',
    'fox',
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
    'mixed_type': 'duck',
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
    '27',
    '06',
    '03',
    '27',
],
    'text_data': '28036453b6b445b8b956711f3d576c86',
    'rand_digit': 0,
    'rand_number': 0.97068,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-25 10:40:08+0100',
    'text_array': [
    '786c2066836c462b82473efac0060533',
    '612d9b8719e3427f8ec89d7401ebd568',
],
    'words': 'hyena ant',
    'nested': {
    'id': 139,
    'rand_digit': 9,
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
],
    'word': 'tiger',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'whale',
    'wolf',
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
    'maybe': 'whale',
    'maybe_null': 'squid',
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
    '09',
    '27',
    '20',
    '29',
],
    'text_data': '3a64ebeeae3d4226908fb6f9a86c867d',
    'rand_digit': 0,
    'rand_number': 0.39252,
    'rand_signed_int': 4,
    'rand_datetime': '2000-04-20T21:00:03.413902',
    'text_array': [
    'd43218b574dc40b7ac5df2184975aae4',
    'e0c059ef99a94e6fba3b50b9dc37148d',
],
    'words': 'pig lobster',
    'nested': {
    'id': 140,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    4,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'mosquito',
    'cow',
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
    'mixed_type': 0.25163,
    'maybe': 'horse',
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
],
    'text_data': '01eb2ad692bd4f94803c76214e6fb228',
    'rand_digit': 0,
    'rand_number': 0.8939,
    'rand_signed_int': 7,
    'rand_datetime': '2000-03-08T09:37:18.302688',
    'text_array': [
    '2ad805bb21fc44b4b9d9da9531281423',
    '5a215b45d75d4ae7aed2c57908ce341d',
],
    'words': 'dog camel',
    'nested': {
    'id': 141,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    8,
],
],
    'two_words': [
    'dolphin',
    'deer',
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
    'mixed_type': 0,
    'maybe_null': 'duck',
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
    '02',
],
    'text_data': '61cb7fb785cf48958b8936166a8824b2',
    'rand_digit': 0,
    'rand_number': 0.65184,
    'rand_signed_int': 10,
    'rand_datetime': '2000-10-25',
    'text_array': [
    'd63d459519cf4f58b1a0b1fd607abaeb',
    'a8ac0efb019b4077be0339f9836f6aee',
],
    'words': 'cow spider',
    'nested': {
    'id': 142,
    'rand_digit': 4,
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
    'word': 'monkey',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'tiger',
    'tiger',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    'text_data': '747a1c84bd8c4d23bf9b0faee646805e',
    'rand_digit': 2,
    'rand_number': 0.28185,
    'rand_signed_int': -9,
    'rand_datetime': '2000-11-23',
    'text_array': [
    '3e4a6ac5e7854a3c934c23c265b7506e',
    'e5e2be4c02ad41febefdc470f9810755',
],
    'words': 'ape bird',
    'nested': {
    'id': 143,
    'rand_digit': 1,
    'array': [
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
    'number': 9,
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
],
    'two_words': [
    'ape',
    'ladybug',
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
    'mixed_type': None,
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
    '06',
],
    'text_data': 'f36be0773f9e49ffbe09e8ea9301f2ae',
    'rand_digit': 7,
    'rand_number': 0.9238,
    'rand_signed_int': 4,
    'rand_datetime': '2000-04-02T06:19:42.916132',
    'text_array': [
    '28ceac84baa646b7a9d212084a84652a',
    '7054a2224bd04c5c84d3c389466421b2',
],
    'words': 'dolphin deer',
    'nested': {
    'id': 144,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
],
    [
    -2,
],
    [
    -8,
],
],
    'two_words': [
    'grasshopper',
    'frog',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': [
    5,
],
    'rand_bool': False,
    'mixed_type': 'frog',
    'maybe_null': 'grasshopper',
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
    '08',
    '07',
],
    'text_data': '7007758eedf942b2994eafea2ce17af4',
    'rand_digit': 4,
    'rand_number': 0.41741,
    'rand_signed_int': -7,
    'rand_datetime': '2001-01-10T05:54:15-0900',
    'text_array': [
    'a0dea5e617954a0fbd9272d6aa5397aa',
    '120bc45f05164fc2a6b5681d32ba8c18',
],
    'words': 'scorpion grasshopper',
    'nested': {
    'id': 145,
    'rand_digit': 4,
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
],
    'word': 'squid',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'crab',
    'zebra',
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
    'mixed_type': 'spider',
    'maybe_null': 'panda',
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
    '16',
    '26',
    '26',
    '12',
    '04',
],
    'text_data': 'b264f5e7249b48adbae3379ec04c0e42',
    'rand_digit': 2,
    'rand_number': 0.67449,
    'rand_signed_int': 4,
    'rand_datetime': '2000-11-09T16:29:21.262934-0900',
    'text_array': [
    'dc374212363e4d179c8fbcbdf6e05f8f',
    '6b5a0d9d2e7b4fab8f028dc438508abb',
],
    'words': 'dog tiger',
    'nested': {
    'id': 146,
    'rand_digit': 2,
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
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'bear',
    'fly',
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
    'mixed_type': None,
    'maybe': 'frog',
    'maybe_null': 'leopard',
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
    '11',
],
    'text_data': 'da727f5e03424e5dbb0781039f133ea7',
    'rand_digit': 3,
    'rand_number': 0.05169,
    'rand_signed_int': -6,
    'rand_datetime': '2000-11-22',
    'text_array': [
    '6bb5ead78f844bfab09352178ca7c784',
    'fea017ab52704b4ab7c6480218107dfd',
],
    'words': 'sloth tiger',
    'nested': {
    'id': 147,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
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
],
    'word': 'cat',
    'number': 5,
},
    {
    'nested_empty': None,
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
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'squid',
    'monkey',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': [
    13,
],
    'rand_bool': False,
    'mixed_type': 0.91605,
    'maybe': 'elephant',
    'maybe_null': 'cat',
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
],
    'text_data': 'cfe90d2b472843b1b1787b526620612b',
    'rand_digit': 2,
    'rand_number': 0.7588,
    'rand_signed_int': 9,
    'rand_datetime': '2000-08-20 17:11:34.030238+0300',
    'text_array': [
    'f08a9c051da344ca9280434278dfc3bc',
    'c261230f31564d628cc6c234dc3cb611',
],
    'words': 'ant scorpion',
    'nested': {
    'id': 148,
    'rand_digit': 3,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 2,
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
],
    'word': 'ant',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    6,
],
],
    'two_words': [
    'bee',
    'camel',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': [
    62,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'panda',
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
    '06',
],
    'text_data': 'e2f312451d494b7b80188dced0a77444',
    'rand_digit': 8,
    'rand_number': 0.10705,
    'rand_signed_int': -10,
    'rand_datetime': '2001-01-09 08:46:18',
    'text_array': [
    '30ea1e5c318a4224aa2b08804d1e4223',
    'f12de919c0f64026b59ad9070d4941ec',
],
    'words': 'tiger tiger',
    'nested': {
    'id': 149,
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
    'number': 3,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    8,
],
],
    'two_words': [
    'rhino',
    'fox',
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
    'mixed_type': 0.77668,
    'maybe_null': 'tiger',
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
    '05',
    '17',
    '05',
    '07',
],
    'text_data': '4ec13328c8854550932a93272554cb15',
    'rand_digit': 5,
    'rand_number': 0.40867,
    'rand_signed_int': 3,
    'rand_datetime': '2000-12-23T22:32:37-0400',
    'text_array': [
    'b8ac2aca72dc49e684730ddba53807f4',
    '5e010b0008ec467d88905c87fcc19fcd',
],
    'words': 'zebra horse',
    'nested': {
    'id': 150,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    [
    -10,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hyena',
    'ape',
],
    'city': {
    'name': 'London',
    'geo': {
    'lat': 51.507351,
    'lon': -0.127758,
},
},
    'rand_tuple': [
    86,
],
    'rand_bool': True,
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
    '22',
],
    'text_data': '190768a140ee4ea8b1b5beaca48e0135',
    'rand_digit': 8,
    'rand_number': 0.64595,
    'rand_signed_int': -2,
    'rand_datetime': '2000-01-25',
    'text_array': [
    '92c40b80f46b4ffdab5b808fd9156168',
    '3c3a507f87c8476b83f8f45fa0228e96',
],
    'words': 'mosquito squid',
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
    'word': 'hippo',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'koala',
    'gorilla',
],
    'city': {
    'name': 'Moscow',
    'geo': {
    'lat': 55.755826,
    'lon': 37.6173,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.60266,
    'maybe': 'lobster',
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
    '06',
    '03',
    '11',
    '20',
],
    'text_data': '623be8e6687a49ae947571bfc4a79287',
    'rand_digit': 4,
    'rand_number': 0.44899,
    'rand_signed_int': 5,
    'rand_datetime': '2000-03-17T14:41:16.434287',
    'text_array': [
    '4c0cf8706c7d4772b58a0cfbde1a3e1b',
    'e4487c8966e0441499a1fff80eb1596e',
],
    'words': 'rhino snail',
    'nested': {
    'id': 152,
    'rand_digit': 4,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'chicken',
    'snail',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '28',
    '13',
    '05',
],
    'text_data': 'baea3c386faa4dd69e4afbd1d66161cc',
    'rand_digit': 4,
    'rand_number': 0.35251,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-28T12:20:55.327998',
    'text_array': [
    '34557e9a681f4b748aed504cb516af63',
    '1b3b480e50b34bbb94a0a0f6dcf31308',
],
    'words': 'kangaroo snake',
    'nested': {
    'id': 153,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'wolf',
    'panda',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '06',
    '28',
    '10',
    '12',
],
    'text_data': 'd6f89704593142b6b6c14ff5bf22db71',
    'rand_digit': 8,
    'rand_number': 0.0516,
    'rand_signed_int': 1,
    'rand_datetime': '2001-01-16T23:09:59.810928-1000',
    'text_array': [
    '159e57ffe64f45bda31fb53dfa81222d',
    'ec837576856c4869b0ea090d8e19bfab',
],
    'words': 'panda rhino',
    'nested': {
    'id': 154,
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
    'number': 2,
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
    'word': 'mouse',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dolphin',
    'fish',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
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
],
    'text_data': 'fe4073c8cd524aa685a9c63743badf15',
    'rand_digit': 9,
    'rand_number': 0.89032,
    'rand_signed_int': 5,
    'rand_datetime': '2000-08-02T00:38:00.116739',
    'text_array': [
    '1846c1765d844e56b1377f589a47ff8a',
    'f00256abc44f4d4cb933ed67272d8a2a',
],
    'words': 'cat bee',
    'nested': {
    'id': 155,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
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
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cheetah',
    'cheetah',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': [
    98,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'dragonfly',
    'maybe_null': 'deer',
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
    '13',
    '24',
    '25',
    '17',
    '11',
],
    'text_data': '89b979256a1245549a9815460d45c5c0',
    'rand_digit': 7,
    'rand_number': 0.25194,
    'rand_signed_int': -2,
    'rand_datetime': '2001-01-09T22:28:40.421067+0500',
    'text_array': [
    'dd3604480d24440590d956b50aa1d584',
    '6333057c31904f128437e1c37c430e23',
],
    'words': 'frog camel',
    'nested': {
    'id': 156,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'octopus',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'cow',
    'frog',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '03',
    '07',
    '10',
],
    'text_data': '4c150fa8afb74ae3bc9245ce741926da',
    'rand_digit': 7,
    'rand_number': 0.31273,
    'rand_signed_int': -6,
    'rand_datetime': '2001-01-18 14:47:45+0600',
    'text_array': [
    '3a0b44c46182471e801f0b81bd4e4c60',
    'abfec97659934376a131fd77b548ec34',
],
    'words': 'fox kangaroo',
    'nested': {
    'id': 157,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 2,
},
],
},
    'nested_array': [
    [
    4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'koala',
    'rabbit',
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
    'maybe': 'dragonfly',
    'maybe_null': 'snail',
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
],
    'text_data': '74aee5cd8f2347efa224f568872b9a18',
    'rand_digit': 0,
    'rand_number': 0.83759,
    'rand_signed_int': 7,
    'rand_datetime': '2000-01-12T07:35:34+0700',
    'text_array': [
    '4053669bccae4c7c815f18228c243308',
    '3750f2a1a30f40169809a050fbf85976',
],
    'words': 'fish monkey',
    'nested': {
    'id': 158,
    'rand_digit': 4,
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
    'word': 'dragonfly',
    'number': 1,
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
],
},
    'nested_array': [
    [
    3,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'zebra',
    'goat',
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
    'mixed_type': 1,
    'maybe': 'panda',
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
    '18',
    '05',
],
    'text_data': '48255b784b7e4d018b1f72228f0e543a',
    'rand_digit': 3,
    'rand_number': 0.52284,
    'rand_signed_int': 10,
    'rand_datetime': '2000-11-09T21:01:43.749630+05:00',
    'text_array': [
    '794e777832204c038b2a0849041ad11f',
    'a77d0339e1264534b14cfdb35d5f374c',
],
    'words': 'dolphin turtle',
    'nested': {
    'id': 159,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'fish',
    'pig',
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
    'mixed_type': 0,
    'maybe': 'kangaroo',
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
],
    'text_data': 'fdea19a2763649d8a78549df5dd0a0f9',
    'rand_digit': 9,
    'rand_number': 0.99811,
    'rand_signed_int': -1,
    'rand_datetime': '2000-07-23T18:58:47.440219+0300',
    'text_array': [
    '87031f5d642f44d0b779b2c556a7a052',
    'fea3822a2b7d405eba5ffbbcaf67c189',
],
    'words': 'panda kangaroo',
    'nested': {
    'id': 160,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 5,
},
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
    'word': 'spider',
    'number': 1,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'duck',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
    10,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -4,
],
],
    'two_words': [
    'jaguar',
    'lion',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
],
    'text_data': 'ef068506258542328cc49edf6e3739bf',
    'rand_digit': 0,
    'rand_number': 0.67374,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-23 01:56:37.236674',
    'text_array': [
    '71e0786270da4f13966dd538ca198fb1',
    '9107d8d67f594921a13260eb277ac9d3',
],
    'words': 'turtle koala',
    'nested': {
    'id': 161,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'ape',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 6,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
    4,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'turtle',
    'tiger',
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
    'maybe': 'fox',
    'maybe_null': 'jaguar',
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
    '02',
    '24',
],
    'text_data': '920018b530d348a992621fddf97ef8cb',
    'rand_digit': 6,
    'rand_number': 0.40367,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-19T02:36:23.877832',
    'text_array': [
    '039d226370dd47cfb7479ab115985f36',
    'cdf2995b68b1496b93266cd0687fb44b',
],
    'words': 'mosquito cat',
    'nested': {
    'id': 162,
    'rand_digit': 3,
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'grasshopper',
    'ladybug',
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
    'id': 63,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 163,
    'id_str': [
    '09',
    '15',
    '27',
    '24',
],
    'text_data': 'c35d8aa4ad3746b4b68d005772b8973a',
    'rand_digit': 8,
    'rand_number': 0.93123,
    'rand_signed_int': -5,
    'rand_datetime': '2000-03-08 10:20:40.509870',
    'text_array': [
    '225382b53d4f4b5c841a8b54f2138764',
    '34987545fd15493890484384f98f3257',
],
    'words': 'grasshopper tiger',
    'nested': {
    'id': 163,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'bear',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -5,
],
],
    'two_words': [
    'squid',
    'gorilla',
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
    'mixed_type': 5,
    'maybe': 'shark',
    'maybe_null': 'duck',
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
        """测试请求 4 - POST http://localhost:6333/collections/congruence_test_collection/points/recommend/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/recommend/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/recommend/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '195',
}
        
        # 原始请求内容
        original_content = {
    'positive': [
    10,
],
    'negative': [
],
    'params': {
    'exact': True,
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'using': 'image',
    'group_by': 'rand_digit',
    'group_size': 3,
    'limit': 10,
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
        """测试请求 5 - POST http://localhost:6333/collections/congruence_test_collection/points/recommend/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/recommend/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/recommend/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '219',
}
        
        # 原始请求内容
        original_content = {
    'positive': [
    10,
],
    'negative': [
],
    'strategy': 'best_score',
    'params': {
    'exact': True,
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'using': 'image',
    'group_by': 'rand_digit',
    'group_size': 3,
    'limit': 10,
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
        """测试请求 6 - POST http://localhost:6333/collections/congruence_test_collection/points/recommend/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/recommend/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/recommend/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '279',
}
        
        # 原始请求内容
        original_content = {
    'positive': [
    10,
],
    'negative': self.mutator.generate_float_array(dimension=2, normalized=True),
    'params': {
    'exact': True,
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'using': 'image',
    'lookup_from': {
    'collection': 'congruence_secondary_collection',
    'vector': 'image',
},
    'group_by': 'rand_digit',
    'group_size': 3,
    'limit': 10,
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
        """测试请求 7 - POST http://localhost:6333/collections/congruence_test_collection/points/recommend/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/recommend/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/recommend/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '382',
}
        
        # 原始请求内容
        original_content = {
    'positive': [
    10,
],
    'negative': [
],
    'filter': {
    'min_should': {
    'conditions': [
    {
    'is_empty': {
    'key': 'maybe',
},
},
    {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
    {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
],
    'min_count': 2,
},
},
    'params': {
    'exact': True,
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'using': 'text',
    'group_by': 'rand_digit',
    'group_size': 5,
    'limit': 10,
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
        """测试请求 8 - POST http://localhost:6333/collections/congruence_test_collection/points/recommend/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/recommend/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/recommend/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '310',
}
        
        # 原始请求内容
        original_content = {
    'positive': [
    10,
],
    'negative': [
],
    'filter': {
    'should': {
    'key': 'nested_array[10][1]',
    'range': {
    'lt': -7.0,
},
},
    'must': {
    'key': 'words',
    'match': {
    'text': 'ant',
},
},
},
    'params': {
    'exact': True,
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'using': 'text',
    'group_by': 'rand_digit',
    'group_size': 5,
    'limit': 10,
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
        """测试请求 9 - POST http://localhost:6333/collections/congruence_test_collection/points/recommend/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/recommend/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/recommend/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '322',
}
        
        # 原始请求内容
        original_content = {
    'positive': [
    10,
],
    'negative': [
],
    'filter': {
    'must_not': [
    {
    'key': 'city.geo',
    'geo_radius': {
    'center': {
    'lon': 11.581981,
    'lat': 48.135125,
},
    'radius': 1754136.322308282,
},
},
],
},
    'params': {
    'exact': True,
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'using': 'text',
    'group_by': 'rand_digit',
    'group_size': 5,
    'limit': 10,
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
        """测试请求 10 - POST http://localhost:6333/collections/congruence_test_collection/points/recommend/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/recommend/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/recommend/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '466',
}
        
        # 原始请求内容
        original_content = {
    'positive': [
    10,
],
    'negative': [
],
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
    'value': 'koala',
},
},
],
    'must_not': [
    {
    'key': 'number',
    'range': {
    'lt': 6.0,
},
},
],
},
},
},
    {
    'key': 'city.geo',
    'geo_radius': {
    'center': {
    'lon': -74.005973,
    'lat': 40.712775,
},
    'radius': 1734835.1806958304,
},
},
],
},
    'params': {
    'exact': True,
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'using': 'text',
    'group_by': 'rand_digit',
    'group_size': 5,
    'limit': 10,
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
        """测试请求 11 - POST http://localhost:6333/collections/congruence_test_collection/points/recommend/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/recommend/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/recommend/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '510',
}
        
        # 原始请求内容
        original_content = {
    'positive': [
    10,
],
    'negative': [
],
    'filter': {
    'must': [
    {
    'is_empty': {
    'key': 'nested.array[].nested_empty2',
},
},
    {
    'min_should': {
    'conditions': [
    {
    'key': 'words',
    'match': {
    'text': 'koala',
},
},
    {
    'key': 'city.geo',
    'geo_radius': {
    'center': {
    'lon': 39.7015,
    'lat': 47.235713,
},
    'radius': 1829973.8014289557,
},
},
    {
    'key': 'nested.array[].word',
    'match': {
    'value': 'cat',
},
},
],
    'min_count': 2,
},
},
],
},
    'params': {
    'exact': True,
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'using': 'text',
    'group_by': 'rand_digit',
    'group_size': 5,
    'limit': 10,
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
        """测试请求 12 - POST http://localhost:6333/collections/congruence_test_collection/points/recommend/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/recommend/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/recommend/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '356',
}
        
        # 原始请求内容
        original_content = {
    'positive': [
    10,
],
    'negative': [
],
    'filter': {
    'must': {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'shark',
},
},
],
    'must_not': [
    {
    'key': 'number',
    'range': {
    'lt': 5.0,
},
},
],
},
},
},
},
    'params': {
    'exact': True,
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'using': 'text',
    'group_by': 'rand_digit',
    'group_size': 5,
    'limit': 10,
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
        """测试请求 13 - DELETE http://localhost:6333/collections/congruence_test_collection?timeout=60"""
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_group_recommend.test_simple_recommend_groups')
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
    test = TestGroupRecommendtestSimpleRecommendGroups()
    test.run_tests()
