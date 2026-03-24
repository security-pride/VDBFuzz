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
logger = logging.getLogger('vdb_fuzzer.test.test_group_search_test_single_vector')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_group_search.test_single_vector"
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



class TestGroupSearchtestSingleVector:
    """自动生成的VDB模糊测试类 - test_group_search.test_single_vector"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_group_search.test_single_vector"
        self.test_count = 63  # 测试方法数量
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
    'content-length': '68001',
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
],
    'text_data': '9be4b82a5a374b5f9e73b5f5146af669',
    'rand_digit': 5,
    'rand_number': 0.71272,
    'rand_signed_int': -5,
    'rand_datetime': '2001-01-27T23:36:45+0000',
    'text_array': [
    '283e82fad7af43eeaf6f3070ccadf438',
    '4aa8a4d2e9e345fe84ff0a4f087aaab1',
],
    'words': 'goat elephant',
    'nested': {
    'id': 100,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    6,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'camel',
    'duck',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 0,
    'maybe': 'whale',
},
},
    {
    'id': 1,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 101,
    'id_str': [
],
    'text_data': '96416c326a3f4158af791f9b532aadaa',
    'rand_digit': 4,
    'rand_number': 0.96466,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-05 05:53:41+0700',
    'text_array': [
    '25ff32bfc8494a7db6a7598239e9877e',
    'a590bf0c267a468d9c20dd6074f15a24',
],
    'words': 'whale mosquito',
    'nested': {
    'id': 101,
    'rand_digit': 0,
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
],
    'word': 'hippo',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'rabbit',
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
    'mixed_type': 'crab',
    'maybe': 'ladybug',
    'maybe_null': None,
},
},
    {
    'id': 2,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 102,
    'id_str': [
    '08',
    '30',
    '01',
    '01',
],
    'text_data': 'a5565ba9313745c0b629e099465863ef',
    'rand_digit': 5,
    'rand_number': 0.37257,
    'rand_signed_int': 4,
    'rand_datetime': '2000-10-13 17:04:02.789477',
    'text_array': [
    '05f82212edc74c0086c5fecc715ad678',
    '5972182000124345a8de57b58a709e3a',
],
    'words': 'fly jaguar',
    'nested': {
    'id': 102,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'mosquito',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'deer',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'hyena',
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
    'mixed_type': 'dolphin',
    'maybe_null': 'kangaroo',
},
},
    {
    'id': 3,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 103,
    'id_str': [
    '04',
    '08',
],
    'text_data': '7ed9ede1d4464a8d86b74266ebd7f1df',
    'rand_digit': 8,
    'rand_number': 0.83985,
    'rand_signed_int': -9,
    'rand_datetime': '2000-12-05',
    'text_array': [
    '6e34990775d1430fac7f4913083ca473',
    'bb93610c56744fffa959c02ed48f0beb',
],
    'words': 'fly ladybug',
    'nested': {
    'id': 103,
    'rand_digit': 5,
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
    'hello',
],
    'word': 'gorilla',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 4,
},
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
],
    'word': 'panda',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -9,
],
],
    'two_words': [
    'lobster',
    'zebra',
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
    'mixed_type': 0.53948,
    'maybe_null': 'grasshopper',
},
},
    {
    'id': 4,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 104,
    'id_str': [
    '07',
    '23',
    '02',
    '07',
    '26',
],
    'text_data': '28c2a8a4c6d9468fa8c2509d3d26877e',
    'rand_digit': 9,
    'rand_number': 0.63974,
    'rand_signed_int': 8,
    'rand_datetime': '2000-12-17 11:34:46+1200',
    'text_array': [
    '3e1a478f3e864fe8a2d9feec5a3c03b2',
    '0181aabadf4f4c2bb612a5efe2f75986',
],
    'words': 'ant gorilla',
    'nested': {
    'id': 104,
    'rand_digit': 9,
    'array': [
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
    'word': 'shark',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'bird',
    'turtle',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'frog',
},
},
    {
    'id': 5,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 105,
    'id_str': [
    '08',
    '15',
],
    'text_data': '14bb2d60887a4439a14dc5e69564bd6f',
    'rand_digit': 7,
    'rand_number': 0.88754,
    'rand_signed_int': -10,
    'rand_datetime': '2000-02-07T19:22:58.424316-1200',
    'text_array': [
    '17747a42b48842fd9c6a41809658a1ef',
    'a8be4a7ffd9740848ca4b8e610876082',
],
    'words': 'sheep elephant',
    'nested': {
    'id': 105,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'fly',
    'fly',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'koala',
},
},
    {
    'id': 6,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 106,
    'id_str': [
    '20',
    '02',
    '05',
],
    'text_data': '43b677b06d8a4b79b13c49faad011e35',
    'rand_digit': 9,
    'rand_number': 0.56454,
    'rand_signed_int': 8,
    'rand_datetime': '2000-06-12 17:52:04.791781-0500',
    'text_array': [
    'e00769252f424387b05427415fe349bb',
    'ae508ef74e15489b800106b81557c0a5',
],
    'words': 'bee monkey',
    'nested': {
    'id': 106,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 10,
},
],
},
    'nested_array': [
    [
    4,
],
],
    'two_words': [
    'deer',
    'lobster',
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
    'mixed_type': 2,
},
},
    {
    'id': 7,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 107,
    'id_str': [
    '12',
    '06',
    '26',
    '16',
],
    'text_data': '6ff5508f655f4c1e8c479f21b19a06fb',
    'rand_digit': 3,
    'rand_number': 0.37387,
    'rand_signed_int': -9,
    'rand_datetime': '2000-03-08 01:42',
    'text_array': [
    '748122b2dfec4faa9920b1c03645fb15',
    '7fadaa9a242d44fe88ebfd468a047114',
],
    'words': 'lion snake',
    'nested': {
    'id': 107,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    [
    -6,
],
],
    'two_words': [
    'shark',
    'crab',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'squid',
    'maybe_null': None,
},
},
    {
    'id': 8,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 108,
    'id_str': [
    '30',
],
    'text_data': '61b7d10ec8654fbc849a2ef0de62d0f8',
    'rand_digit': 4,
    'rand_number': 0.89928,
    'rand_signed_int': 3,
    'rand_datetime': '2000-09-14T20:04:16.908275+1200',
    'text_array': [
    '236c5941a1bd4758ac1c6015aec5731f',
    'c0b13e37455a4da7879e5c0df03377b4',
],
    'words': 'dragonfly hippo',
    'nested': {
    'id': 108,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    [
    -4,
],
    [
],
    [
],
],
    'two_words': [
    'rabbit',
    'spider',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'whale',
    'maybe_null': None,
},
},
    {
    'id': 9,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 109,
    'id_str': [
    '04',
    '08',
    '23',
    '21',
],
    'text_data': '0ac2b76e3567478e9be127c4adbd6465',
    'rand_digit': 9,
    'rand_number': 0.2045,
    'rand_signed_int': -9,
    'rand_datetime': '2000-04-22T08:26:27.403812',
    'text_array': [
    'a304add13f94434fba07f491be5a8a79',
    '47ae72a10749469a98e346269c48b93f',
],
    'words': 'sloth rhino',
    'nested': {
    'id': 109,
    'rand_digit': 2,
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
    'hello',
],
    'word': 'jaguar',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'monkey',
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
    'mixed_type': False,
    'maybe_null': 'fish',
},
},
    {
    'id': 10,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 110,
    'id_str': [
    '14',
    '07',
    '23',
    '16',
],
    'text_data': '0e27f236c7f045d1a4caf775da05dece',
    'rand_digit': 0,
    'rand_number': 0.74838,
    'rand_signed_int': -4,
    'rand_datetime': '2000-06-05 02:05:29.505558',
    'text_array': [
    '86a19cad22a14ad0b825cee65d6949e9',
    '931a1a404acd4cddb2afb787f0ca1fee',
],
    'words': 'goat ladybug',
    'nested': {
    'id': 110,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'ant',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fly',
    'wolf',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 11,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 111,
    'id_str': [
    '27',
    '18',
    '22',
    '25',
    '28',
],
    'text_data': '5e029402cd084762830e336d15c8f4e4',
    'rand_digit': 1,
    'rand_number': 0.53455,
    'rand_signed_int': 0,
    'rand_datetime': '2000-03-05T01:25:49.070285-09:00',
    'text_array': [
    '2ef331292e184a6a8c1a499d0b12a204',
    '1e981a991d0249cc85ff1caa18dfdfe9',
],
    'words': 'fish tiger',
    'nested': {
    'id': 111,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 9,
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
    'word': 'fish',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 5,
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'wolf',
    'ladybug',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': [
    89,
],
    'rand_bool': True,
    'mixed_type': 'rabbit',
    'maybe_null': 'deer',
},
},
    {
    'id': 12,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 112,
    'id_str': [
    '09',
    '27',
    '17',
    '20',
],
    'text_data': 'fa894eafef674f5ea1f5303e4ff7d204',
    'rand_digit': 3,
    'rand_number': 0.58172,
    'rand_signed_int': -7,
    'rand_datetime': '2000-02-08T01:43:56.452076',
    'text_array': [
    '069ed94c66fe4a3bba2667d13a6afae7',
    'cee2455697d04ea58f87d2d036a82b8c',
],
    'words': 'mosquito lobster',
    'nested': {
    'id': 112,
    'rand_digit': 7,
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
    'hello',
],
    'word': 'gorilla',
    'number': 1,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'cat',
    'lion',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'leopard',
},
},
    {
    'id': 13,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 113,
    'id_str': [
    '04',
    '12',
    '10',
    '19',
],
    'text_data': '29202f0a8e1743488fe9fdd9156cfd7d',
    'rand_digit': 1,
    'rand_number': 0.65246,
    'rand_signed_int': 10,
    'rand_datetime': '2000-12-14 20:31:36.414554',
    'text_array': [
    '4bb86388f1dc4fa1957e8c5fb24d65a6',
    'ef7b9b46b50749ac801e2aa3e34c4594',
],
    'words': 'leopard horse',
    'nested': {
    'id': 113,
    'rand_digit': 0,
    'array': [
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
],
    'word': 'rhino',
    'number': 2,
},
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'fox',
    'ape',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': [
    24,
],
    'rand_bool': False,
    'mixed_type': 0.22598,
    'maybe_null': 'ape',
},
},
    {
    'id': 14,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 114,
    'id_str': [
],
    'text_data': 'fe86d665e4cd4c76b6628006f5204944',
    'rand_digit': 4,
    'rand_number': 0.70652,
    'rand_signed_int': 8,
    'rand_datetime': '2000-03-15 19:11:47.592446',
    'text_array': [
    '5e61bac5b4984733892983515f1b86dd',
    '251c142df196487d924f78ce37a51e96',
],
    'words': 'pig ladybug',
    'nested': {
    'id': 114,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dog',
    'pig',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'bee',
    'maybe': 'cheetah',
    'maybe_null': 'sheep',
},
},
    {
    'id': 15,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 115,
    'id_str': [
    '26',
],
    'text_data': 'e5098bf59c504cffa1e6ebfe1bbd457b',
    'rand_digit': 0,
    'rand_number': 0.84742,
    'rand_signed_int': -7,
    'rand_datetime': '2000-01-28T12:33:50',
    'text_array': [
    '3ddac9a4bf0f4c2885ab0e9652775d1b',
    'e224f30135444c6ebb5c5cb7e2f93064',
],
    'words': 'lobster dolphin',
    'nested': {
    'id': 115,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
],
    [
    -4,
],
],
    'two_words': [
    'dog',
    'giraffe',
],
    'city': {
    'name': 'Kuala Lumpur',
    'geo': {
    'lat': 3.139003,
    'lon': 101.686855,
},
},
    'rand_tuple': [
    59,
],
    'rand_bool': False,
    'mixed_type': 'sloth',
    'maybe': 'crab',
    'maybe_null': 'dog',
},
},
    {
    'id': 16,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 116,
    'id_str': [
],
    'text_data': 'c2fdeacbe6514230a2c070daf813c2d8',
    'rand_digit': 1,
    'rand_number': 0.87175,
    'rand_signed_int': -5,
    'rand_datetime': '2000-12-04T06:23:10.888362+02:00',
    'text_array': [
    'ff1edc78326e472b96d74e4860018ef1',
    'd9718db227e443698d36aa7b836e9b79',
],
    'words': 'zebra whale',
    'nested': {
    'id': 116,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
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
    'number': 7,
},
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
    'hello',
],
    'word': 'pig',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'hippo',
    'lion',
],
    'city': {
    'name': 'Cardiff',
    'geo': {
    'lat': 51.481581,
    'lon': -3.17909,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'chicken',
    'maybe_null': None,
},
},
    {
    'id': 17,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 117,
    'id_str': [
    '11',
],
    'text_data': 'fe9e85e179ce4008a5752248b6fbde88',
    'rand_digit': 5,
    'rand_number': 0.00518,
    'rand_signed_int': 2,
    'rand_datetime': '2000-03-20 15:13:33.768341-1200',
    'text_array': [
    'aad519dc6e6a433ca04603ce6513cbb7',
    '680651ba7d06455a979a5fe882bfde41',
],
    'words': 'snake elephant',
    'nested': {
    'id': 117,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'lion',
    'butterfly',
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
    'maybe_null': None,
},
},
    {
    'id': 18,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 118,
    'id_str': [
    '24',
    '30',
    '14',
],
    'text_data': '137f2fd99e574b3f8bedc61089f73511',
    'rand_digit': 7,
    'rand_number': 0.0465,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-13T19:20:10.434123-0700',
    'text_array': [
    '5e8e0deb90484c0f97e1db1058f06d73',
    '0311ce48a7a4496f8bedf7629ce8636f',
],
    'words': 'frog camel',
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
    'word': 'kangaroo',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 3,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    6,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hyena',
    'lobster',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.73626,
    'maybe': 'octopus',
},
},
    {
    'id': 19,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 119,
    'id_str': [
    '24',
    '25',
    '13',
    '18',
    '12',
],
    'text_data': 'd1a321cbcd1748409c71aca1766cf592',
    'rand_digit': 9,
    'rand_number': 0.68965,
    'rand_signed_int': 9,
    'rand_datetime': '2001-01-03 10:25:18.303136',
    'text_array': [
    '4cdb8837b8ac42d880626ee87dd4eefa',
    'cbcc340b2cbc455192e06917b834fe77',
],
    'words': 'mosquito chicken',
    'nested': {
    'id': 119,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'lizard',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'rabbit',
    'cow',
],
    'city': {
    'name': 'Dubai',
    'geo': {
    'lat': 25.204849,
    'lon': 55.270783,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bee',
    'maybe_null': 'sheep',
},
},
    {
    'id': 20,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 120,
    'id_str': [
    '17',
    '17',
],
    'text_data': 'e74cbad0009e436da24765dd4d483406',
    'rand_digit': 0,
    'rand_number': 0.28115,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-13T07:20:51-0700',
    'text_array': [
    'a3deda8fb3444f638be4a603d637ebf2',
    '252df763291849559961cd0d9c23e123',
],
    'words': 'ant snake',
    'nested': {
    'id': 120,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'chicken',
    'bee',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'cat',
},
},
    {
    'id': 21,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 121,
    'id_str': [
],
    'text_data': '79d978cf0ed94e34b8a4a1e74db56fe9',
    'rand_digit': 2,
    'rand_number': 0.8404,
    'rand_signed_int': 1,
    'rand_datetime': '2000-08-13 19:17:58.542204-1000',
    'text_array': [
    'd73ee66cabe1476582056222729b3752',
    '1ad62be6ea5a4453ba7324ad14103879',
],
    'words': 'duck turtle',
    'nested': {
    'id': 121,
    'rand_digit': 3,
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fish',
    'ladybug',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cat',
    'maybe_null': None,
},
},
    {
    'id': 22,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 122,
    'id_str': [
    '29',
    '12',
    '10',
    '24',
],
    'text_data': 'bcee51dbac1646abbe520a24a78be708',
    'rand_digit': 1,
    'rand_number': 0.12582,
    'rand_signed_int': -3,
    'rand_datetime': '2000-12-13T04:44:36',
    'text_array': [
    '96bbeaaeb2e84cfc9c2dfa749525810b',
    'a821047fb33b4b5a901030ccb2007e6e',
],
    'words': 'sheep lobster',
    'nested': {
    'id': 122,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 1,
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
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'wolf',
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
    30,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 23,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 123,
    'id_str': [
    '29',
],
    'text_data': 'b2d0b23e65b24befae0df784b5572366',
    'rand_digit': 1,
    'rand_number': 0.43396,
    'rand_signed_int': 10,
    'rand_datetime': '2000-12-31T11:29:05.646713',
    'text_array': [
    'bf34021ec9ca4df0adb97d65fcfaf28e',
    '199184d4e4b54d9e86bb2c944d7ae395',
],
    'words': 'lizard crab',
    'nested': {
    'id': 123,
    'rand_digit': 1,
    'array': [
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
    'word': 'zebra',
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
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'ladybug',
    'crab',
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
    'maybe_null': 'turtle',
},
},
    {
    'id': 24,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 124,
    'id_str': [
    '21',
    '01',
    '18',
    '18',
    '25',
],
    'text_data': 'b690a304b2064f44b417790dc2a5ca1d',
    'rand_digit': 3,
    'rand_number': 0.43829,
    'rand_signed_int': -4,
    'rand_datetime': '2000-01-24T11:53:02.087742',
    'text_array': [
    'faee0b8f5fb540e588e54ac2e3ac44a9',
    '408c10e29d3e4340aac3e7504727f7e7',
],
    'words': 'cheetah bear',
    'nested': {
    'id': 124,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'ladybug',
    'number': 7,
},
],
},
    'nested_array': [
    [
    -3,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'shark',
    'ant',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 'squid',
    'maybe': 'dolphin',
},
},
    {
    'id': 25,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 125,
    'id_str': [
    '10',
    '06',
],
    'text_data': '01d6d05a58c249f2b2a66036f65ff505',
    'rand_digit': 6,
    'rand_number': 0.34057,
    'rand_signed_int': 10,
    'rand_datetime': '2000-06-08 11:19:58-0500',
    'text_array': [
    'fbdd0d7f4dd644e7b13a622ceba31cef',
    'ffcccbbf494d416fb3079d45a8f3d5d2',
],
    'words': 'sheep sheep',
    'nested': {
    'id': 125,
    'rand_digit': 0,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snail',
    'cow',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'octopus',
    'maybe_null': 'wolf',
},
},
    {
    'id': 26,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 126,
    'id_str': [
    '11',
    '30',
    '19',
    '28',
],
    'text_data': 'f844298a83504f72b84d460b812ee12f',
    'rand_digit': 6,
    'rand_number': 0.33594,
    'rand_signed_int': 2,
    'rand_datetime': '2000-10-11T17:39:48',
    'text_array': [
    'db429cce98f24a3898ec88f5c723f0ea',
    'e1cfd3d26d4a4e15a4b2044706cb15d5',
],
    'words': 'scorpion giraffe',
    'nested': {
    'id': 126,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
    7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fox',
    'rhino',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 27,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 127,
    'id_str': [
    '22',
    '17',
    '03',
],
    'text_data': '6fcf0285ed5c498bba87cdd2bbe19327',
    'rand_digit': 5,
    'rand_number': 0.90703,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-20 00:01',
    'text_array': [
    'ec0d3e30ead24a37be7d4f2d8eb42bd3',
    '7228a96ea18b44eb8d9304689ea31ad0',
],
    'words': 'lion crab',
    'nested': {
    'id': 127,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 10,
},
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
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'mosquito',
    'bear',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 'cat',
    'maybe': 'butterfly',
},
},
    {
    'id': 28,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 128,
    'id_str': [
    '22',
    '18',
    '14',
    '25',
    '30',
],
    'text_data': 'f53f3cb5ef814633b7d2ea13964e5c59',
    'rand_digit': 6,
    'rand_number': 0.99382,
    'rand_signed_int': 4,
    'rand_datetime': '2000-07-03T06:29:22+1200',
    'text_array': [
    'ad2e6d16217641388140987b7097c44f',
    '86d90387d3874b22afa7709a986afdbe',
],
    'words': 'wolf spider',
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
    'word': 'panda',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'lobster',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -2,
],
    [
    5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dog',
    'squid',
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
    'mixed_type': 0.88789,
    'maybe': 'cheetah',
},
},
    {
    'id': 29,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 129,
    'id_str': [
],
    'text_data': '7b9f2242f7ef44f798245811d0052abc',
    'rand_digit': 6,
    'rand_number': 0.95616,
    'rand_signed_int': 2,
    'rand_datetime': '2000-06-08',
    'text_array': [
    'd2c8925c68e0492b8df02490c0b1c23a',
    '527fb6153b3f43f087b58bad8c96fe0a',
],
    'words': 'ladybug spider',
    'nested': {
    'id': 129,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lion',
    'shark',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 30,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 130,
    'id_str': [
    '30',
    '06',
    '11',
    '20',
],
    'text_data': 'e962b6c17ce848e18aae611875011180',
    'rand_digit': 8,
    'rand_number': 0.15257,
    'rand_signed_int': 10,
    'rand_datetime': '2000-11-06T22:06:55',
    'text_array': [
    '7daf1edf1a15452ab63806b4f0abd196',
    '0edbb5a9af144ac88bd8e22cbdc981dc',
],
    'words': 'horse zebra',
    'nested': {
    'id': 130,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'duck',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 2,
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    9,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bear',
    'elephant',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'ape',
},
},
    {
    'id': 31,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 131,
    'id_str': [
    '11',
    '11',
],
    'text_data': 'f5242f93cca34d04b022a69feba3211b',
    'rand_digit': 8,
    'rand_number': 0.79066,
    'rand_signed_int': 8,
    'rand_datetime': '2000-01-10T23:39:39-0800',
    'text_array': [
    'c8e7b0f1acfd45a2855a213dba29b23f',
    '5255a38b800448a08880507c90195a52',
],
    'words': 'chicken elephant',
    'nested': {
    'id': 131,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'panda',
    'dolphin',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 32,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 132,
    'id_str': [
    '10',
    '09',
    '08',
    '05',
    '25',
],
    'text_data': 'dfb18d88abbf411faf2c0a7f0bcf7d52',
    'rand_digit': 5,
    'rand_number': 0.54637,
    'rand_signed_int': 5,
    'rand_datetime': '2000-05-26 01:48:40.732036+0500',
    'text_array': [
    '0f013b9c32934a2b8498dcce7b09549b',
    '597d3c90fb7e41bf8ce62a1e25bc9737',
],
    'words': 'koala dolphin',
    'nested': {
    'id': 132,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'leopard',
    'shark',
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
    'mixed_type': True,
    'maybe_null': 'spider',
},
},
    {
    'id': 33,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 133,
    'id_str': [
],
    'text_data': '1dadc760951a445ab8de4c68e1a8395b',
    'rand_digit': 5,
    'rand_number': 0.51031,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-19 04:39:01',
    'text_array': [
    'c964cc9b931a4cb9a401830fcd453c9c',
    '27712f89e4a34a8b8e38a1c5df1d1478',
],
    'words': 'fly wolf',
    'nested': {
    'id': 133,
    'rand_digit': 0,
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
    'hello',
],
    'word': 'dolphin',
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
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 10,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'bear',
    'mosquito',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': [
    30,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 34,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 134,
    'id_str': [
    '12',
    '19',
    '06',
],
    'text_data': '73a53761d7454fb9a65a5c36656eac3c',
    'rand_digit': 1,
    'rand_number': 0.93244,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-06T08:14:36.185346',
    'text_array': [
    '9cf7dc6e506d48f9b01752bd409adfed',
    'd5440f50479d4ab0a961e40972e37e0f',
],
    'words': 'horse leopard',
    'nested': {
    'id': 134,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'ape',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 7,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'butterfly',
    'bear',
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
    'mixed_type': 'snake',
    'maybe': 'dragonfly',
    'maybe_null': 'leopard',
},
},
    {
    'id': 35,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 135,
    'id_str': [
    '13',
    '07',
    '11',
    '16',
    '24',
],
    'text_data': 'b40213513a2c41f4bf757d4aee5930c6',
    'rand_digit': 0,
    'rand_number': 0.58934,
    'rand_signed_int': 2,
    'rand_datetime': '2000-05-02T10:45:05.961189',
    'text_array': [
    '5692a9164a7a48cbaab6361649084a12',
    '5041346bf847416691a5d441ce425632',
],
    'words': 'snail grasshopper',
    'nested': {
    'id': 135,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'sloth',
    'bird',
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
    'mixed_type': 'snail',
},
},
    {
    'id': 36,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 136,
    'id_str': [
    '21',
],
    'text_data': 'd42106528a68422183a9f4cbd91343d3',
    'rand_digit': 4,
    'rand_number': 0.64408,
    'rand_signed_int': 9,
    'rand_datetime': '2000-07-29T07:47:50.783923+0000',
    'text_array': [
    'b2ee4420fb074a22ae00ce1d6dc5ca96',
    'c0750c9c8aef444d8fd10d1251dda323',
],
    'words': 'sloth snake',
    'nested': {
    'id': 136,
    'rand_digit': 2,
    'array': [
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
    'word': 'bird',
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
    'hello',
],
    'word': 'goat',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'butterfly',
    'lizard',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 37,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 137,
    'id_str': [
    '03',
    '11',
],
    'text_data': '61cd943a3c7a44aea39d82742a2b0fc0',
    'rand_digit': 3,
    'rand_number': 0.84675,
    'rand_signed_int': 1,
    'rand_datetime': '2000-09-26 06:04',
    'text_array': [
    'efa671b0ea064e998c25db04317f73fc',
    'c40de6d40a1d40c49ede0d3d4f4f42d4',
],
    'words': 'ape ant',
    'nested': {
    'id': 137,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'rhino',
    'snake',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'fly',
},
},
    {
    'id': 38,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 138,
    'id_str': [
    '29',
    '12',
    '23',
    '06',
    '10',
],
    'text_data': '2b4cd40d76b64317b1b488a33f1dbee3',
    'rand_digit': 8,
    'rand_number': 0.29169,
    'rand_signed_int': -10,
    'rand_datetime': '2000-06-25 05:04:09.735616',
    'text_array': [
    '4cfcefc2613b40dcb53ef3436aa7f36a',
    'b0653c0cc29e48328fed88e4d2328b72',
],
    'words': 'lion panda',
    'nested': {
    'id': 138,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'horse',
    'horse',
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
    'mixed_type': 0.99689,
    'maybe': 'lobster',
},
},
    {
    'id': 39,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 139,
    'id_str': [
    '25',
    '05',
    '10',
],
    'text_data': '625cd482a2f74fca99b08fa414f77027',
    'rand_digit': 7,
    'rand_number': 0.65746,
    'rand_signed_int': 7,
    'rand_datetime': '2000-05-21T14:20:18.432920',
    'text_array': [
    'd627163ccdfa48f89644e051c644fa40',
    '41ee1f682cf3499fbed1719dc82b6582',
],
    'words': 'bird dragonfly',
    'nested': {
    'id': 139,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    5,
],
],
    'two_words': [
    'whale',
    'fox',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'sheep',
},
},
    {
    'id': 40,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 140,
    'id_str': [
    '20',
    '15',
],
    'text_data': '2615e1f381ef419fb8a9db18233c994e',
    'rand_digit': 9,
    'rand_number': 0.56654,
    'rand_signed_int': 4,
    'rand_datetime': '2000-10-27T20:33:56',
    'text_array': [
    '3247b22083ee43efbb17205acce18129',
    '5128e6df65744a55a625e8d38ca44112',
],
    'words': 'elephant chicken',
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
    'word': 'koala',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'hyena',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'whale',
    'dolphin',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'jaguar',
    'maybe_null': 'bird',
},
},
    {
    'id': 41,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 141,
    'id_str': [
    '28',
    '24',
],
    'text_data': '0ceb7f21f5c94107bf26756c757f061d',
    'rand_digit': 7,
    'rand_number': 0.63834,
    'rand_signed_int': -5,
    'rand_datetime': '2000-03-04T00:06:54.832531',
    'text_array': [
    '4a65a1e948334307b83e19592530b4e7',
    '259d7c594f0443e1bd3d281549e453ff',
],
    'words': 'cat snail',
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
    'word': 'crab',
    'number': 9,
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
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'giraffe',
    'spider',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'koala',
    'maybe_null': None,
},
},
    {
    'id': 42,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 142,
    'id_str': [
    '10',
    '05',
    '24',
    '10',
],
    'text_data': '26d5a3870b8a48bb85d23c5a0f068481',
    'rand_digit': 6,
    'rand_number': 0.83533,
    'rand_signed_int': 2,
    'rand_datetime': '2000-03-27T14:16:23.534383',
    'text_array': [
    'a44d60916ad148dba9acc549f781d5f7',
    'c177e1823f894ff0a72cbb8eb6ea55e0',
],
    'words': 'gorilla bird',
    'nested': {
    'id': 142,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'lobster',
    'chicken',
],
    'city': {
    'name': 'Copenhagen',
    'geo': {
    'lat': 55.676097,
    'lon': 12.568337,
},
},
    'rand_tuple': [
    6,
],
    'rand_bool': True,
    'mixed_type': 9,
},
},
    {
    'id': 43,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 143,
    'id_str': [
    '29',
    '25',
],
    'text_data': '58bff5b072704f2a872f3498f2dff3ba',
    'rand_digit': 5,
    'rand_number': 0.30554,
    'rand_signed_int': -7,
    'rand_datetime': '2000-01-25T22:53:59-0800',
    'text_array': [
    '48232d21331544f19a852ebd064baf83',
    '0734a3ba004c478ba4063eab1024d85a',
],
    'words': 'turtle cow',
    'nested': {
    'id': 143,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'grasshopper',
    'lizard',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': [
    1,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': 'dolphin',
},
},
    {
    'id': 44,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 144,
    'id_str': [
    '13',
    '01',
    '20',
    '17',
],
    'text_data': '14c32756b37646ea94b0605c2f9512d4',
    'rand_digit': 9,
    'rand_number': 0.30677,
    'rand_signed_int': 3,
    'rand_datetime': '2000-04-26 10:22:14.084909',
    'text_array': [
    '9eadecebc1e740e0bf21b7cffc1605f1',
    'f8971b0833fc49e3b5acb78e3596079c',
],
    'words': 'crab monkey',
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
    'word': 'snail',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 1,
},
],
},
    'nested_array': [
    [
    5,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'grasshopper',
    'frog',
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
    'mixed_type': None,
},
},
    {
    'id': 45,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 145,
    'id_str': [
],
    'text_data': '8c29de4af59148c2b9a78df5bfbcac3b',
    'rand_digit': 6,
    'rand_number': 0.5,
    'rand_signed_int': -3,
    'rand_datetime': '2000-12-01',
    'text_array': [
    '7d00bc0190da48dbad6dcd20a7be41ab',
    '9874c622790242b898a493f05b88556e',
],
    'words': 'shark cheetah',
    'nested': {
    'id': 145,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'butterfly',
    'pig',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': [
    72,
],
    'rand_bool': False,
    'mixed_type': 0.71506,
    'maybe': 'whale',
},
},
    {
    'id': 46,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 146,
    'id_str': [
],
    'text_data': '35920228747e42189e9a56c581c7129b',
    'rand_digit': 4,
    'rand_number': 0.2665,
    'rand_signed_int': 9,
    'rand_datetime': '2000-08-25 19:40:02.381246',
    'text_array': [
    'eaad6ab0e42442549a9f4524cefdcf3a',
    '36b22d52482b47139f9eaf219bb652f3',
],
    'words': 'octopus hyena',
    'nested': {
    'id': 146,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'leopard',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'grasshopper',
    'butterfly',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'fly',
},
},
    {
    'id': 47,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 147,
    'id_str': [
    '02',
],
    'text_data': '5e353975aa3b46bba3462f87b422011c',
    'rand_digit': 3,
    'rand_number': 0.17743,
    'rand_signed_int': 8,
    'rand_datetime': '2000-09-22',
    'text_array': [
    'd5fedd6003ef43d48d5e47e2c23c6b48',
    '4548c3402f8d46cebcfe94f4e0212dde',
],
    'words': 'sheep cow',
    'nested': {
    'id': 147,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 4,
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
    'word': 'giraffe',
    'number': 5,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'panda',
    'lizard',
],
    'city': {
    'name': 'Kharkiv',
    'geo': {
    'lat': 49.980812,
    'lon': 36.25272,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': None,
},
},
    {
    'id': 48,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 148,
    'id_str': [
    '29',
    '19',
    '04',
],
    'text_data': 'e8d1456bd45c4c8f880b8aa7e9cfba82',
    'rand_digit': 8,
    'rand_number': 0.79127,
    'rand_signed_int': -4,
    'rand_datetime': '2000-06-29T11:58:39.192176',
    'text_array': [
    '0e02a47cd47a41068ffb68064335a150',
    '847b066baeff460cb03c5997b817d17f',
],
    'words': 'bird elephant',
    'nested': {
    'id': 148,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snail',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cat',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
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
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    0,
],
],
    'two_words': [
    'panda',
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
    3,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'camel',
    'maybe_null': None,
},
},
    {
    'id': 49,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 149,
    'id_str': [
    '26',
    '25',
    '06',
    '05',
    '09',
],
    'text_data': 'c7982b7344bf4febab6a700c725b0325',
    'rand_digit': 1,
    'rand_number': 0.78955,
    'rand_signed_int': -4,
    'rand_datetime': '2000-01-16T06:21:11',
    'text_array': [
    'b3532e6d7c934cbe96f28d045dffbab2',
    'ea7ff583dbed4896a1558b98c960991b',
],
    'words': 'sloth hippo',
    'nested': {
    'id': 149,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 4,
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
    'crab',
    'ladybug',
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
    'mixed_type': False,
    'maybe': 'bird',
    'maybe_null': 'rabbit',
},
},
    {
    'id': 50,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 150,
    'id_str': [
    '17',
    '28',
    '27',
    '03',
],
    'text_data': '77479ad6587f42ed8acc36638ee64cf9',
    'rand_digit': 5,
    'rand_number': 0.11774,
    'rand_signed_int': 1,
    'rand_datetime': '2000-05-22T16:29:28.972916-09:00',
    'text_array': [
    '4284877243844a5d89e93d17908da962',
    '5ba57a8d76cf4c488892aaa568e6a559',
],
    'words': 'deer koala',
    'nested': {
    'id': 150,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'wolf',
    'squid',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'horse',
    'maybe_null': 'crab',
},
},
    {
    'id': 51,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 151,
    'id_str': [
    '03',
    '02',
],
    'text_data': 'bf01b8eebe5540eb90737bb4d84c9e60',
    'rand_digit': 5,
    'rand_number': 0.6184,
    'rand_signed_int': -2,
    'rand_datetime': '2000-04-08T14:15:16.239324',
    'text_array': [
    '7960c44eda6a43c9a02a6bc9ea88edf1',
    'a2e90451b98342e691b57d507d6273df',
],
    'words': 'mosquito ant',
    'nested': {
    'id': 151,
    'rand_digit': 7,
    'array': [
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'crab',
    'kangaroo',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'ape',
    'maybe_null': 'spider',
},
},
    {
    'id': 52,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 152,
    'id_str': [
    '09',
    '12',
],
    'text_data': 'a6bb855a366745569be65cf9eb63746a',
    'rand_digit': 3,
    'rand_number': 0.94077,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-04 21:51:46.576499',
    'text_array': [
    'fae3e4f2a8f34b758cedbc4803a016eb',
    'c71fea7bc1514f6b88d0fbdb7cc212a7',
],
    'words': 'ladybug horse',
    'nested': {
    'id': 152,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'koala',
    'number': 2,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'wolf',
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
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'duck',
    'maybe_null': None,
},
},
    {
    'id': 53,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 153,
    'id_str': [
    '28',
    '12',
],
    'text_data': '7272f39eefc9480ea28a189d2305fbf2',
    'rand_digit': 2,
    'rand_number': 0.2839,
    'rand_signed_int': -8,
    'rand_datetime': '2000-04-26T15:35:36.040179',
    'text_array': [
    'a5347a853b7743008f2f6dda71818c74',
    'd19980f1274940d585121a3d802e2e65',
],
    'words': 'bird giraffe',
    'nested': {
    'id': 153,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'leopard',
    'hyena',
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
    'mixed_type': 8,
    'maybe': 'hyena',
    'maybe_null': None,
},
},
    {
    'id': 54,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 154,
    'id_str': [
    '23',
    '25',
],
    'text_data': 'fc734185768a42669b67273bb29a363f',
    'rand_digit': 6,
    'rand_number': 0.08513,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-15T08:02:24-0700',
    'text_array': [
    '758e4c8fd87d4c33b874b229180c07ae',
    '199145f60e14475fb15dc37029a39e83',
],
    'words': 'snail spider',
    'nested': {
    'id': 154,
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
    'number': 5,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
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
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -10,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'horse',
    'elephant',
],
    'city': {
    'name': 'Seoul',
    'geo': {
    'lat': 37.566535,
    'lon': 126.977969,
},
},
    'rand_tuple': [
    72,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'dog',
    'maybe_null': 'octopus',
},
},
    {
    'id': 55,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 155,
    'id_str': [
    '15',
    '30',
    '04',
],
    'text_data': 'e4d1b9951e684fdcbbba14e6f2ef982d',
    'rand_digit': 5,
    'rand_number': 0.86451,
    'rand_signed_int': 6,
    'rand_datetime': '2000-10-14 10:22:46.483763-0900',
    'text_array': [
    'e4f9015ec55e453b84391e506de9bab2',
    '0d68b96a73fa4585bf55aefe39e0e588',
],
    'words': 'pig cat',
    'nested': {
    'id': 155,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'duck',
    'jaguar',
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
    'mixed_type': 'cat',
    'maybe_null': 'ladybug',
},
},
    {
    'id': 56,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 156,
    'id_str': [
    '30',
    '02',
],
    'text_data': 'ffbadccffc3d492ebb1530ee887d7f6d',
    'rand_digit': 2,
    'rand_number': 0.099,
    'rand_signed_int': 10,
    'rand_datetime': '2000-05-29 21:48:31-0600',
    'text_array': [
    'a6e3cb0924ee488a9bac5caa6232edb5',
    '8f10eabe6cc3458db08da96031375de9',
],
    'words': 'gorilla turtle',
    'nested': {
    'id': 156,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'dragonfly',
    'number': 10,
},
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
    'hello',
],
    'word': 'gorilla',
    'number': 8,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hyena',
    'octopus',
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
    'maybe': 'sloth',
    'maybe_null': 'dog',
},
},
    {
    'id': 57,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 157,
    'id_str': [
    '25',
    '09',
    '24',
],
    'text_data': 'cee19d957d174f228c1e7f581042489b',
    'rand_digit': 6,
    'rand_number': 0.22301,
    'rand_signed_int': -7,
    'rand_datetime': '2000-04-30 22:09:08.693875',
    'text_array': [
    '7cdaa6b6a09c49a8b19c22349cb8b8ee',
    'd157c26461e944e3adf27e3ad226d94e',
],
    'words': 'grasshopper cat',
    'nested': {
    'id': 157,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    [
],
    [
    -9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    10,
],
    [
    -2,
],
],
    'two_words': [
    'bird',
    'lizard',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': [
    32,
],
    'rand_bool': True,
    'mixed_type': None,
},
},
    {
    'id': 58,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 158,
    'id_str': [
    '27',
    '24',
],
    'text_data': 'a4f594bdc0184d9684491621428dd384',
    'rand_digit': 8,
    'rand_number': 0.75352,
    'rand_signed_int': -4,
    'rand_datetime': '2000-05-28 08:00:40.716405',
    'text_array': [
    '3681ff18f26649b490481b7ae81a22bf',
    'a0e7c38b09d34a3291fa6f44f7ccca2f',
],
    'words': 'snake whale',
    'nested': {
    'id': 158,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -3,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'gorilla',
    'bee',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'hippo',
},
},
    {
    'id': 59,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 159,
    'id_str': [
    '09',
    '24',
    '26',
],
    'text_data': '10a117cbadc348b3965fb58fd1b5593a',
    'rand_digit': 3,
    'rand_number': 0.96013,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-01 20:31:59+0400',
    'text_array': [
    'eacaa7d92d3b445d859681fc58fece19',
    '4cb240b0078a4017957cd1ec606e04ed',
],
    'words': 'kangaroo panda',
    'nested': {
    'id': 159,
    'rand_digit': 2,
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
    'word': 'squid',
    'number': 10,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'mosquito',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    6,
],
],
    'two_words': [
    'gorilla',
    'squid',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 60,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 160,
    'id_str': [
    '22',
    '06',
    '02',
    '07',
    '29',
],
    'text_data': '49824a24e3af4d9e857aa1d2180da7c2',
    'rand_digit': 5,
    'rand_number': 0.35079,
    'rand_signed_int': 7,
    'rand_datetime': '2000-06-28 23:52:51+0100',
    'text_array': [
    '40194f3c2a8c459da40b1dc9c195d8b1',
    'cbe19cd08de749b18cbbc69248213ab4',
],
    'words': 'goat elephant',
    'nested': {
    'id': 160,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'pig',
    'scorpion',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': [
    95,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'ladybug',
},
},
    {
    'id': 61,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 161,
    'id_str': [
],
    'text_data': 'ef39c161163540a8a9ff0068505b9984',
    'rand_digit': 9,
    'rand_number': 0.86778,
    'rand_signed_int': 9,
    'rand_datetime': '2000-07-29 10:09:17+0300',
    'text_array': [
    '921ac9dc2d4f4aab9e5be98dccc401a9',
    '3c44a2c1f9834b6ead6856b1ccbd445a',
],
    'words': 'fly lobster',
    'nested': {
    'id': 161,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    10,
],
    [
    0,
],
],
    'two_words': [
    'monkey',
    'turtle',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 62,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 162,
    'id_str': [
    '01',
    '18',
],
    'text_data': '8afdc143f8d54989b87b8b51516a8509',
    'rand_digit': 3,
    'rand_number': 0.03146,
    'rand_signed_int': -2,
    'rand_datetime': '2001-01-27T09:26:42',
    'text_array': [
    '46d7c61e87e74c4eba7642bc3dd449b7',
    'b86c196714ef49fea969de7801014648',
],
    'words': 'octopus rabbit',
    'nested': {
    'id': 162,
    'rand_digit': 0,
    'array': [
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
    'nested_array': '__FLOAT_MULTI_DIM_2,2__',
    'two_words': [
    'sheep',
    'koala',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'horse',
},
},
    {
    'id': 63,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 163,
    'id_str': [
    '20',
],
    'text_data': '4c7627405fef432b933e585c2ca30700',
    'rand_digit': 9,
    'rand_number': 0.82995,
    'rand_signed_int': -3,
    'rand_datetime': '2000-06-02T01:11:38-0500',
    'text_array': [
    '6708be250ca6487989125b841d293193',
    '0fcb78ccbecd44dd8cf42e6239dd6709',
],
    'words': 'octopus dragonfly',
    'nested': {
    'id': 163,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 2,
},
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'squid',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'mouse',
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
        """测试请求 2 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1166',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_3(self):
        """测试请求 3 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1367',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'min_should': {
    'conditions': [
    {
    'key': 'city.geo',
    'geo_bounding_box': {
    'top_left': {
    'lon': 141.31418909625808,
    'lat': 32.004603599158145,
},
    'bottom_right': {
    'lon': -60.73231150091286,
    'lat': -34.59471354752484,
},
},
},
    {
    'key': 'nested_array[10][]',
    'range': {
    'lt': -3.0,
},
},
],
    'min_count': 1,
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_4(self):
        """测试请求 4 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1321',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': [
    {
    'key': 'city.geo',
    'geo_bounding_box': {
    'top_left': {
    'lon': 176.74127185822522,
    'lat': 22.34971190886337,
},
    'bottom_right': {
    'lon': -39.770466543869674,
    'lat': -31.813618499375472,
},
},
},
    {
    'is_null': {
    'key': 'maybe_null',
},
},
],
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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
        """测试请求 5 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1306',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must': [
    {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'panda',
},
},
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
    {
    'key': 'rand_datetime',
    'range': {
    'gt': '2000-12-30T00:00:00Z',
},
},
],
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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
        """测试请求 6 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1285',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': [
    {
    'key': 'city.geo',
    'geo_bounding_box': {
    'top_left': {
    'lon': 128.1489558288897,
    'lat': -14.934312186202007,
},
    'bottom_right': {
    'lon': 133.22879392151953,
    'lat': -13.39327850414196,
},
},
},
],
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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
        """测试请求 7 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1316',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'nested_array[10][10]',
    'range': {
    'lt': 5.0,
},
},
    'must': {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'leopard',
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
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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
        """测试请求 8 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1243',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'duck',
},
},
    {
    'key': 'number',
    'range': {
    'lt': 4.0,
},
},
],
},
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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
        """测试请求 9 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1168',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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
        """测试请求 10 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1163',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': {
    'key': 'nested_array[1][0]',
    'range': {
    'lt': 0.0,
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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
        """测试请求 11 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1142',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'is_empty': {
    'key': 'maybe',
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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
        """测试请求 12 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1214',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': [
    {
    'key': 'id_str',
    'match': {
    'any': [
    '21',
    '06',
    '12',
],
},
},
],
    'must': {
    'key': 'words',
    'match': {
    'text': 'spider',
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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
        """测试请求 13 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1338',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'nested_array[1][1]',
    'range': {
    'lt': -9.0,
},
},
    'must': {
    'key': 'city.geo',
    'geo_bounding_box': {
    'top_left': {
    'lon': -44.04509199247147,
    'lat': 53.44675673981186,
},
    'bottom_right': {
    'lon': 44.924186485045595,
    'lat': -88.81556288258108,
},
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_14(self):
        """测试请求 14 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
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
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': [
    {
    'should': [
    {
    'key': 'words',
    'match': {
    'text': 'mouse',
},
},
],
},
],
    'must': {
    'is_null': {
    'key': 'maybe_null',
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_15(self):
        """测试请求 15 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1260',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'dolphin',
},
},
],
    'must_not': [
    {
    'key': 'number',
    'range': {
    'lt': 10.0,
},
},
],
},
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_16(self):
        """测试请求 16 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1217',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'city.geo',
    'geo_radius': {
    'center': {
    'lon': 19.040235,
    'lat': 47.497912,
},
    'radius': 1269362.456227461,
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_17(self):
        """测试请求 17 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1313',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'scorpion',
},
},
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
    'must': [
    {
    'key': 'rand_number',
    'range': {
    'lt': 0.31280992758961657,
},
},
],
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_18(self):
        """测试请求 18 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1204',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'two_words',
    'match': {
    'except': [
    '11',
    '06',
    '29',
    '12',
    '11',
    '21',
    '25',
    '24',
    '20',
    '14',
],
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_19(self):
        """测试请求 19 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1231',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'nested.array[].word',
    'match': {
    'value': 'snail',
},
},
    'must': {
    'key': 'nested.array[].word',
    'match': {
    'value': 'bird',
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_20(self):
        """测试请求 20 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1421',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'city.geo',
    'geo_bounding_box': {
    'top_left': {
    'lon': 150.0344209390217,
    'lat': -77.47746561325842,
},
    'bottom_right': {
    'lon': -9.06045291410635,
    'lat': 8.172211928266961,
},
},
},
    'must': {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'mosquito',
},
},
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
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_21(self):
        """测试请求 21 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1264',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'two_words',
    'match': {
    'except': [
    '01',
    '10',
    '08',
    '06',
    '15',
    '03',
    '29',
    '10',
    '22',
    '06',
],
},
},
    'must': {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_22(self):
        """测试请求 22 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1217',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
    'must': {
    'key': 'words',
    'match': {
    'text': 'kangaroo',
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_23(self):
        """测试请求 23 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1168',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must': {
    'key': 'rand_number',
    'range': {
    'gt': 0.37838529474518456,
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_24(self):
        """测试请求 24 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1255',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must': {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'hyena',
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
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_25(self):
        """测试请求 25 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
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
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': {
    'key': 'words',
    'match': {
    'text': 'wolf',
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_26(self):
        """测试请求 26 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1203',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'is_null': {
    'key': 'maybe_null',
},
},
    'must': [
    {
    'key': 'id_str',
    'values_count': {
    'lt': 4,
    'gt': 6,
},
},
],
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_27(self):
        """测试请求 27 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1281',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'city.geo',
    'geo_bounding_box': {
    'top_left': {
    'lon': -109.04204744553991,
    'lat': 54.660387360270306,
},
    'bottom_right': {
    'lon': 48.49962377683332,
    'lat': 70.7987814412813,
},
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_28(self):
        """测试请求 28 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1255',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': [
    {
    'key': 'id_str',
    'match': {
    'value': '21',
},
},
],
    'must': [
    {
    'key': 'two_words',
    'match': {
    'except': [
    '20',
    '20',
    '08',
    '16',
    '15',
    '06',
    '10',
    '20',
    '30',
    '05',
],
},
},
],
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_29(self):
        """测试请求 29 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1253',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'id_str',
    'match': {
    'value': '05',
},
},
    'must': [
    {
    'key': 'two_words',
    'match': {
    'except': [
    '06',
    '27',
    '07',
    '17',
    '15',
    '09',
    '21',
    '27',
    '27',
    '27',
],
},
},
],
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_30(self):
        """测试请求 30 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1275',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'id_str',
    'match': {
    'any': [
    '25',
    '06',
    '25',
],
},
},
    'must': [
    {
    'key': 'city.geo',
    'geo_radius': {
    'center': {
    'lon': -80.19179,
    'lat': 25.76168,
},
    'radius': 925778.2005931683,
},
},
],
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_31(self):
        """测试请求 31 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1220',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': {
    'key': 'city.geo',
    'geo_radius': {
    'center': {
    'lon': -74.072092,
    'lat': 4.710989,
},
    'radius': 1969786.5383177383,
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_32(self):
        """测试请求 32 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1205',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'is_null': {
    'key': 'maybe_null',
},
},
    'must': {
    'is_empty': {
    'key': 'nested.array[].nested_empty2',
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_33(self):
        """测试请求 33 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1228',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'rand_number',
    'range': {
    'gt': 0.02837178143581509,
},
},
    'must': {
    'is_empty': {
    'key': 'nested.array[].nested_empty',
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
    'group_by': 'rand_digit',
    'group_size': 1,
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



    def test_request_34(self):
        """测试请求 34 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1262',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'is_empty': {
    'key': 'nested.array[].nested_empty',
},
},
    'must': {
    'key': 'two_words',
    'match': {
    'except': [
    '06',
    '30',
    '08',
    '22',
    '23',
    '01',
    '27',
    '19',
    '28',
    '09',
],
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_35(self):
        """测试请求 35 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1259',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'city.geo',
    'geo_radius': {
    'center': {
    'lon': 21.012229,
    'lat': 52.229676,
},
    'radius': 1102567.111693526,
},
},
    'must': [
    {
    'is_null': {
    'key': 'maybe_null',
},
},
],
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_36(self):
        """测试请求 36 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1258',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'bird',
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
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_37(self):
        """测试请求 37 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
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
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must': {
    'is_empty': {
    'key': 'nested.array[].nested_empty',
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_38(self):
        """测试请求 38 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '2014',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'words',
    'match': {
    'text': 'rhino',
},
},
    'must': {
    'min_should': {
    'conditions': [
    {
    'key': 'city.geo',
    'geo_bounding_box': {
    'top_left': {
    'lon': -56.670275025529946,
    'lat': -78.24146947175585,
},
    'bottom_right': {
    'lon': -3.2249959534490245,
    'lat': 78.03554018002075,
},
},
},
    {
    'key': 'city.geo',
    'geo_bounding_box': {
    'top_left': {
    'lon': -70.63817388564733,
    'lat': 54.8473971275487,
},
    'bottom_right': {
    'lon': -23.640492423120634,
    'lat': -9.771604481534155,
},
},
},
    {
    'key': 'city.geo',
    'geo_radius': {
    'center': {
    'lon': -1.61778,
    'lat': 54.978252,
},
    'radius': 1983954.269827895,
},
},
    {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'elephant',
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
    {
    'key': 'city.geo',
    'geo_bounding_box': {
    'top_left': {
    'lon': 91.66549137364808,
    'lat': 0.007172749679540402,
},
    'bottom_right': {
    'lon': 151.81704796650877,
    'lat': 27.2132498717408,
},
},
},
    {
    'key': 'id_str',
    'values_count': {
    'lt': 1,
    'gt': 5,
},
},
],
    'min_count': 3,
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_39(self):
        """测试请求 39 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1339',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': [
    {
    'key': 'id_str',
    'values_count': {
    'lt': 4,
    'gt': 7,
},
},
],
    'must': {
    'key': 'city.geo',
    'geo_bounding_box': {
    'top_left': {
    'lon': -109.79254107711708,
    'lat': 4.276479682196424,
},
    'bottom_right': {
    'lon': 6.138539753331912,
    'lat': -20.44899289039735,
},
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_40(self):
        """测试请求 40 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1330',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'must': [
    {
    'key': 'id_str',
    'values_count': {
    'lt': 2,
    'gt': 2,
},
},
    {
    'must_not': [
    {
    'is_empty': {
    'key': 'nested.array[].nested_empty2',
},
},
    {
    'key': 'two_words',
    'match': {
    'except': [
    '20',
    '10',
    '26',
    '18',
    '17',
    '22',
    '06',
    '19',
    '29',
    '23',
],
},
},
],
},
],
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_41(self):
        """测试请求 41 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1152',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must': {
    'key': 'id_str',
    'values_count': {
    'gt': 2,
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_42(self):
        """测试请求 42 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1269',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'words',
    'match': {
    'text': 'jaguar',
},
},
    'must': [
    {
    'key': 'city.geo',
    'geo_radius': {
    'center': {
    'lon': 126.977969,
    'lat': 37.566535,
},
    'radius': 347879.8109576895,
},
},
],
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_43(self):
        """测试请求 43 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1170',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'rand_number',
    'range': {
    'lt': 0.24093710836412396,
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_44(self):
        """测试请求 44 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
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
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must': {
    'key': 'nested_array[10][10]',
    'range': {
    'lt': -5.0,
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_45(self):
        """测试请求 45 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1230',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': [
    {
    'key': 'rand_number',
    'range': {
    'gt': 0.6432910309832413,
},
},
],
    'must': {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_46(self):
        """测试请求 46 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1325',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'city.geo',
    'geo_bounding_box': {
    'top_left': {
    'lon': -22.721894118215744,
    'lat': -53.20228640741446,
},
    'bottom_right': {
    'lon': 121.58600755851319,
    'lat': 50.56128873096401,
},
},
},
    'must': [
    {
    'is_null': {
    'key': 'maybe_null',
},
},
],
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_47(self):
        """测试请求 47 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1206',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': {
    'key': 'two_words',
    'match': {
    'except': [
    '18',
    '11',
    '29',
    '02',
    '08',
    '10',
    '16',
    '12',
    '13',
    '14',
],
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_48(self):
        """测试请求 48 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1297',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'min_should': {
    'conditions': [
    {
    'is_empty': {
    'key': 'nested.array[].nested_empty',
},
},
],
    'min_count': 1,
},
},
    'must': {
    'key': 'rand_number',
    'range': {
    'lt': 0.3883680173807774,
    'gt': 0.8198745668029306,
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_49(self):
        """测试请求 49 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1249',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': [
    {
    'key': 'rand_number',
    'range': {
    'lt': 0.314919533297326,
    'gt': 0.7665502717859485,
},
},
],
    'must': {
    'key': 'id_str',
    'values_count': {
    'lt': 3,
    'gt': 6,
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_50(self):
        """测试请求 50 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1392',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'city.geo',
    'geo_bounding_box': {
    'top_left': {
    'lon': 138.26250173387155,
    'lat': -5.7756474806396625,
},
    'bottom_right': {
    'lon': -36.02959903767044,
    'lat': 32.09654816819257,
},
},
},
    'must': {
    'key': 'rand_datetime',
    'range': {
    'lt': '2000-04-06T21:13:52.709364+07:00',
    'gt': '2000-10-28T00:00:00Z',
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_51(self):
        """测试请求 51 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1298',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'bird',
},
},
    {
    'key': 'number',
    'range': {
    'lt': 4.0,
},
},
],
},
},
},
    'must': {
    'must_not': [
    {
    'is_null': {
    'key': 'maybe_null',
},
},
],
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_52(self):
        """测试请求 52 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1297',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'is_null': {
    'key': 'maybe_null',
},
},
    'must': {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'snake',
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
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_53(self):
        """测试请求 53 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
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
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'rand_datetime',
    'range': {
    'gt': '2001-01-14T03:10:33.525215-02:00',
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_54(self):
        """测试请求 54 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1241',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must': {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'wolf',
},
},
    {
    'key': 'number',
    'range': {
    'lt': 4.0,
},
},
],
},
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_55(self):
        """测试请求 55 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1195',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': {
    'key': 'rand_number',
    'range': {
    'lt': 0.2918794153077685,
    'gt': 0.5812990970933966,
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_56(self):
        """测试请求 56 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
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
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': {
    'key': 'maybe',
    'match': {
    'value': 'dog',
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_57(self):
        """测试请求 57 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
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
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must': {
    'key': 'rand_number',
    'range': {
    'lt': 0.35828005131522356,
    'gt': 0.5742740578421657,
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_58(self):
        """测试请求 58 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
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
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'rand_number',
    'range': {
    'lt': 0.1367570550750823,
    'gt': 0.7307640735519333,
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_59(self):
        """测试请求 59 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1161',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'id_str',
    'values_count': {
    'lt': 2,
    'gt': 5,
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_60(self):
        """测试请求 60 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1202',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must': {
    'key': 'two_words',
    'match': {
    'except': [
    '20',
    '18',
    '15',
    '09',
    '12',
    '19',
    '17',
    '23',
    '30',
    '06',
],
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_61(self):
        """测试请求 61 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
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
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': {
    'is_empty': {
    'key': 'maybe',
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': True,
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



    def test_request_62(self):
        """测试请求 62 - DELETE http://localhost:6333/collections/congruence_test_collection?timeout=60"""
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_group_search.test_single_vector')
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
    test = TestGroupSearchtestSingleVector()
    test.run_tests()
