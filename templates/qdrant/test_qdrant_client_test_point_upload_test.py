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
logger = logging.getLogger('vdb_fuzzer.test.test_qdrant_client_test_point_upload')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_qdrant_client.test_point_upload"
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


def send_request(content, request_type="PUT", url_path="http://localhost:6333/collections/client_test?timeout=60", custom_headers=None):
    """
    发送请求到目标服务器

    Args:
        content: 请求内容
        request_type: 请求方法，默认为"PUT"
        url_path: URL路径，默认为"http://localhost:6333/collections/client_test?timeout=60"
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



class TestQdrantClienttestPointUpload:
    """自动生成的VDB模糊测试类 - test_qdrant_client.test_point_upload"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_qdrant_client.test_point_upload"
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
        """测试请求 0 - PUT http://localhost:6333/collections/client_test?timeout=60"""
        logger.info(f"跳过非写请求或无内容请求: PUT http://localhost:6333/collections/client_test?timeout=60")
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/client_test?timeout=60'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '41',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'size': 100,
    'distance': 'Dot',
},
}


        send_request(original_content, method, url_path, headers)
        return True



    def test_request_1(self):
        """测试请求 1 - PUT http://localhost:6333/collections/client_test/points?wait=false"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/client_test/points?wait=false")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/client_test/points?wait=false'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '172828',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 100,
    'id_str': [
    '15',
    '03',
    '06',
    '23',
    '27',
],
    'text_data': '3a999b8fd6cf4189bf86c0d600760b41',
    'rand_digit': 9,
    'rand_number': 0.37529,
    'rand_signed_int': -1,
    'rand_datetime': '2000-09-06 06:46:21.800064-0400',
    'text_array': [
    'a5f9fe4b7d0b465388d75a5adab1ea80',
    '1b33afc713044367b613a5454e2d2911',
],
    'words': 'deer dolphin',
    'nested': {
    'id': 100,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
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
    'number': 8,
},
],
},
    'nested_array': [
    [
    4,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bear',
    'tiger',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': [
    96,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'sloth',
},
},
    {
    'id': 1,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 101,
    'id_str': [
    '23',
    '26',
],
    'text_data': '5696b1fc8eb34d639ee330bf3a28aad3',
    'rand_digit': 4,
    'rand_number': 0.7206,
    'rand_signed_int': 0,
    'rand_datetime': '2000-09-05 02:04:44.040190',
    'text_array': [
    'efb208a0d72341349f7490714c963a4f',
    'f1132334189a46178e4d607bf2a9c90f',
],
    'words': 'mouse whale',
    'nested': {
    'id': 101,
    'rand_digit': 6,
    'array': [
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
    'word': 'duck',
    'number': 2,
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
    'word': 'mouse',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 4,
},
],
},
    'nested_array': [
    [
    -4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'monkey',
    'ant',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': [
    63,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 2,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 102,
    'id_str': [
    '21',
    '24',
],
    'text_data': 'b761b1057bcb4c3e86798bd4a27cb271',
    'rand_digit': 5,
    'rand_number': 0.72897,
    'rand_signed_int': -8,
    'rand_datetime': '2000-02-08 14:38:44.051105-0600',
    'text_array': [
    'f99509a371934f94a84e18763b1b868d',
    '3d829c75ea854fb999724a6ba6a0b07e',
],
    'words': 'snail gorilla',
    'nested': {
    'id': 102,
    'rand_digit': 6,
    'array': [
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'bee',
    'wolf',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': [
    91,
],
    'rand_bool': False,
    'mixed_type': 4,
},
},
    {
    'id': 3,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 103,
    'id_str': [
    '07',
],
    'text_data': '4da28ad94714427eadfe9e50b68c67c8',
    'rand_digit': 7,
    'rand_number': 0.87815,
    'rand_signed_int': 6,
    'rand_datetime': '2000-08-30T04:18:21.940505',
    'text_array': [
    '7c8e6bd90b344237bf5e1638e0c72b1e',
    'ddbbba3d8de546b7833e98f663987b95',
],
    'words': 'bird crab',
    'nested': {
    'id': 103,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'monkey',
    'tiger',
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
    'mixed_type': False,
    'maybe': 'hyena',
},
},
    {
    'id': 4,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 104,
    'id_str': [
],
    'text_data': '8f190e8944db4e6388b74ef42e75a8d4',
    'rand_digit': 6,
    'rand_number': 0.77002,
    'rand_signed_int': -9,
    'rand_datetime': '2000-04-03 07:36:40',
    'text_array': [
    'd491f57c478543d3924565f9a107481e',
    'e86f9ecb77e54708be5256eced67d240',
],
    'words': 'panda kangaroo',
    'nested': {
    'id': 104,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'spider',
    'leopard',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cheetah',
    'maybe_null': None,
},
},
    {
    'id': 5,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 105,
    'id_str': [
    '15',
    '20',
    '06',
    '14',
],
    'text_data': '4281000093a34dbc80c81f880938362d',
    'rand_digit': 9,
    'rand_number': 0.42665,
    'rand_signed_int': -5,
    'rand_datetime': '2000-06-17T19:29:55.991108-05:00',
    'text_array': [
    '73f98f53b8774bbb8304da4beed0ac08',
    'b60d0f3550b244d5afd63d9b5d7230b3',
],
    'words': 'lizard fish',
    'nested': {
    'id': 105,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'lion',
    'number': 1,
},
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'dolphin',
    'hippo',
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
    'mixed_type': 0.88911,
},
},
    {
    'id': 6,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 106,
    'id_str': [
    '27',
    '24',
    '09',
    '17',
],
    'text_data': '17ae81e014fe444e8538bca059a4fe4b',
    'rand_digit': 9,
    'rand_number': 0.02095,
    'rand_signed_int': 6,
    'rand_datetime': '2000-10-21T11:08:37.343061+0600',
    'text_array': [
    'd4ab7bc646b344bca8e009ec96d92005',
    '8f5cf23592b949b589af10764cbc00f9',
],
    'words': 'chicken kangaroo',
    'nested': {
    'id': 106,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fox',
    'number': 2,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'wolf',
    'jaguar',
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
    'mixed_type': None,
    'maybe_null': 'whale',
},
},
    {
    'id': 7,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 107,
    'id_str': [
    '25',
    '17',
    '10',
],
    'text_data': '468d0a6b4a304eaf8e2d61c72c823131',
    'rand_digit': 4,
    'rand_number': 0.56435,
    'rand_signed_int': -8,
    'rand_datetime': '2000-04-30T12:54:12',
    'text_array': [
    '4dc514b370ba4fea83fae593dea26d4e',
    '953a1568192647c69998133f6e504e45',
],
    'words': 'ape kangaroo',
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
    'word': 'dragonfly',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 7,
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
    'word': 'wolf',
    'number': 8,
},
],
},
    'nested_array': [
    [
    -5,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -9,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lobster',
    'fly',
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
    'mixed_type': 1,
},
},
    {
    'id': 8,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 108,
    'id_str': [
    '03',
],
    'text_data': '18953dc1ecbe4af0a4afcdf6d6323325',
    'rand_digit': 6,
    'rand_number': 0.04608,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-14 16:26:32-0200',
    'text_array': [
    '3cb896969ce94f3aa40debcc991579f1',
    '87784c29cc3b4ef58018f30eb1f4ca14',
],
    'words': 'bear chicken',
    'nested': {
    'id': 108,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'duck',
    'shark',
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
    'mixed_type': True,
    'maybe': 'turtle',
},
},
    {
    'id': 9,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 109,
    'id_str': [
    '29',
    '24',
    '15',
],
    'text_data': '41e9e372a2c04e56a04a62fb83a38d01',
    'rand_digit': 7,
    'rand_number': 0.47723,
    'rand_signed_int': -2,
    'rand_datetime': '2000-06-09',
    'text_array': [
    'cbf4121625904ae787fdc4f7f453dab8',
    '274134903ce943f0a966c260f7df16c0',
],
    'words': 'horse goat',
    'nested': {
    'id': 109,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'elephant',
    'ape',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 9,
    'maybe': 'zebra',
},
},
    {
    'id': 10,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 110,
    'id_str': [
    '23',
    '05',
    '08',
    '11',
],
    'text_data': 'db696f2b1d384a0180b97ac222a2ee38',
    'rand_digit': 7,
    'rand_number': 0.31639,
    'rand_signed_int': -1,
    'rand_datetime': '2000-09-25T05:31:08.400216+09:00',
    'text_array': [
    '60d9d949ec874d1d8f5441e7b7a2eb60',
    'fd075ca1e5454a8b972ea86b55ca005d',
],
    'words': 'panda rhino',
    'nested': {
    'id': 110,
    'rand_digit': 4,
    'array': [
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'lizard',
    'bear',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': [
    21,
],
    'rand_bool': False,
    'mixed_type': True,
},
},
    {
    'id': 11,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 111,
    'id_str': [
    '28',
    '28',
    '06',
],
    'text_data': '953da6f24b234ea1879c1cbbaeb9438f',
    'rand_digit': 6,
    'rand_number': 0.86409,
    'rand_signed_int': 3,
    'rand_datetime': '2000-01-26T01:45:02',
    'text_array': [
    'acf352e181d54d748a7d320f992ecdf0',
    '0c3d461bb229485fb6c38bebc814624a',
],
    'words': 'butterfly sheep',
    'nested': {
    'id': 111,
    'rand_digit': 4,
    'array': [
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'bear',
    'scorpion',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 'fish',
},
},
    {
    'id': 12,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 112,
    'id_str': [
    '08',
    '13',
    '02',
],
    'text_data': 'eb5d7458148d414b95b6c0f7781aa6a9',
    'rand_digit': 7,
    'rand_number': 0.86596,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-01T04:07:20.552565',
    'text_array': [
    '81267a387cff4e3caba4d0fed4655fc1',
    '5526b8aaab7543da90795cc0868fb708',
],
    'words': 'fish dolphin',
    'nested': {
    'id': 112,
    'rand_digit': 9,
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
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'scorpion',
    'number': 8,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,3__',
    'two_words': [
    'ape',
    'hyena',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': [
    48,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'duck',
},
},
    {
    'id': 13,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 113,
    'id_str': [
    '15',
    '12',
],
    'text_data': 'e0c2e6aa985d4145902a11f1da76aa50',
    'rand_digit': 2,
    'rand_number': 0.66432,
    'rand_signed_int': -7,
    'rand_datetime': '2000-05-26T08:22:58-0900',
    'text_array': [
    '9673b169dbf04377bf38e064c53bac12',
    '640c7b8c2de84653b267597e12c6a61f',
],
    'words': 'goat cow',
    'nested': {
    'id': 113,
    'rand_digit': 3,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
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
    'leopard',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'leopard',
    'maybe_null': None,
},
},
    {
    'id': 14,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 114,
    'id_str': [
    '21',
],
    'text_data': 'fa6ad4ae9c63420dbf1aa7f80d541de8',
    'rand_digit': 2,
    'rand_number': 0.91362,
    'rand_signed_int': -2,
    'rand_datetime': '2000-05-30T02:49:37.696893',
    'text_array': [
    '64b5042f24764edd8f6f563a2fc8ec6b',
    '9e6e34716b114fb69fa067e5eef7bf56',
],
    'words': 'butterfly frog',
    'nested': {
    'id': 114,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'tiger',
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
],
    'two_words': [
    'fish',
    'mosquito',
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
    'maybe_null': 'spider',
},
},
    {
    'id': 15,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 115,
    'id_str': [
    '08',
    '13',
],
    'text_data': '45167384109d4410b200c7da337e97d8',
    'rand_digit': 8,
    'rand_number': 0.57363,
    'rand_signed_int': -10,
    'rand_datetime': '2000-05-08 09:09:04.337312-0700',
    'text_array': [
    'b30507a4713742efa8541a47e2cbd93f',
    '10d3e8ccda3f490f92dcf3e7ccaee01d',
],
    'words': 'ladybug scorpion',
    'nested': {
    'id': 115,
    'rand_digit': 5,
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
    'word': 'monkey',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'bird',
    'lion',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 16,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 116,
    'id_str': [
    '25',
    '14',
],
    'text_data': '7e23a25927d94b03a999425423afd7aa',
    'rand_digit': 5,
    'rand_number': 0.79954,
    'rand_signed_int': 10,
    'rand_datetime': '2000-09-11 20:25:07.644190+0200',
    'text_array': [
    '03d237a9fb134242a305eda1479877f7',
    '0a4ae0329693409c8c316b25e4c3c2e1',
],
    'words': 'lobster camel',
    'nested': {
    'id': 116,
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
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    2,
],
],
    'two_words': [
    'fish',
    'kangaroo',
],
    'city': {
    'name': 'Kuala Lumpur',
    'geo': {
    'lat': 3.139003,
    'lon': 101.686855,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 9,
},
},
    {
    'id': 17,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 117,
    'id_str': [
    '24',
],
    'text_data': '0f78f4981b1e4dbe9a8e9ae5e06f2f5a',
    'rand_digit': 0,
    'rand_number': 0.73236,
    'rand_signed_int': -1,
    'rand_datetime': '2000-02-06T10:02:02.065524-1000',
    'text_array': [
    '9fb3b2f42cde40c28bfdb19589180ebd',
    'a64cbd5d2325429287500cc2aefaf969',
],
    'words': 'duck duck',
    'nested': {
    'id': 117,
    'rand_digit': 5,
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
    'panda',
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
    'mixed_type': None,
    'maybe_null': 'ant',
},
},
    {
    'id': 18,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 118,
    'id_str': [
    '01',
    '16',
    '22',
    '22',
],
    'text_data': '2b1b939f802646a8b78cd31b146cfb00',
    'rand_digit': 3,
    'rand_number': 0.33209,
    'rand_signed_int': -10,
    'rand_datetime': '2000-09-17T12:02:58.168025',
    'text_array': [
    '8826cb2a430f48b38d227c601b0660ec',
    '491313ba56904797999c496be32ee837',
],
    'words': 'snail panda',
    'nested': {
    'id': 118,
    'rand_digit': 4,
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
    'word': 'sheep',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fox',
    'ant',
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
    'mixed_type': 0.54859,
    'maybe_null': 'chicken',
},
},
    {
    'id': 19,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 119,
    'id_str': [
    '25',
    '17',
],
    'text_data': 'db421ade486d42e1b35b78c2a7b299a4',
    'rand_digit': 4,
    'rand_number': 0.40912,
    'rand_signed_int': 9,
    'rand_datetime': '2000-06-05T21:38:52.425605',
    'text_array': [
    'be050d3870f246aca7bccd9516716e0a',
    'bc04ab5be79748d08898bcf1fd9b1509',
],
    'words': 'rhino duck',
    'nested': {
    'id': 119,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
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
    'word': 'camel',
    'number': 6,
},
    {
    'nested_empty': None,
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
],
    'word': 'zebra',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'goat',
    'fox',
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
    'mixed_type': True,
    'maybe': 'snail',
    'maybe_null': 'jaguar',
},
},
    {
    'id': 20,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 120,
    'id_str': [
    '08',
    '24',
    '21',
    '11',
],
    'text_data': 'd561349f1f4f4430aa82894d31d01337',
    'rand_digit': 2,
    'rand_number': 0.42817,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-22T04:06:11.996384+0900',
    'text_array': [
    '2701e3c4a6594f82bba1b46f83821250',
    '34b7beea46a24ab9b1f3694c01f2b24b',
],
    'words': 'mouse scorpion',
    'nested': {
    'id': 120,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 8,
},
    {
    'nested_empty': None,
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
],
    'word': 'jaguar',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 8,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cat',
    'monkey',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': [
    53,
],
    'rand_bool': False,
    'mixed_type': 'pig',
    'maybe_null': None,
},
},
    {
    'id': 21,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 121,
    'id_str': [
    '27',
    '06',
    '01',
    '28',
],
    'text_data': '69c849e4cb08425e902a53ae7ab1238b',
    'rand_digit': 9,
    'rand_number': 0.3996,
    'rand_signed_int': -6,
    'rand_datetime': '2000-05-27T02:07:44.841068+08:00',
    'text_array': [
    '6de57bcaeba84ef1a3b97996a7cc8ff8',
    '19eae2b4fbd948318fddb725106866f9',
],
    'words': 'turtle dolphin',
    'nested': {
    'id': 121,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dog',
    'bird',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'fox',
},
},
    {
    'id': 22,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 122,
    'id_str': [
    '14',
    '16',
    '17',
],
    'text_data': '8ce0ab21734f43b5ad21e5da7933abfb',
    'rand_digit': 8,
    'rand_number': 0.40025,
    'rand_signed_int': -8,
    'rand_datetime': '2000-02-19T17:34:42.240808+1000',
    'text_array': [
    'a0f20a9304264f16ba0d03e0bfcb684e',
    '5daac4d9204b4a4fb4d524dfc0576bbb',
],
    'words': 'turtle squid',
    'nested': {
    'id': 122,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'pig',
    'number': 7,
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
    'word': 'mosquito',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'goat',
    'dog',
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
    'mixed_type': 0.90816,
    'maybe': 'duck',
    'maybe_null': None,
},
},
    {
    'id': 23,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 123,
    'id_str': [
    '01',
    '22',
    '05',
    '04',
    '06',
],
    'text_data': '69e7eabd6368491681718f042997f883',
    'rand_digit': 8,
    'rand_number': 0.80015,
    'rand_signed_int': -2,
    'rand_datetime': '2000-11-08 07:07:35',
    'text_array': [
    '10786e4f1c494dd88cc49ff78833324d',
    'aca5c85f079a4d4ebc7a0b13f1a3da67',
],
    'words': 'jaguar duck',
    'nested': {
    'id': 123,
    'rand_digit': 4,
    'array': [
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
    'word': 'kangaroo',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fly',
    'number': 3,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    9,
],
],
    'two_words': [
    'spider',
    'rhino',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'cat',
    'maybe_null': 'ape',
},
},
    {
    'id': 24,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 124,
    'id_str': [
    '20',
    '03',
    '27',
    '22',
],
    'text_data': '8017b7f3c3464cde98a9535e49745641',
    'rand_digit': 6,
    'rand_number': 0.80432,
    'rand_signed_int': -6,
    'rand_datetime': '2000-08-21T09:46:21.937550',
    'text_array': [
    '72cb86d4592144e88c18f3d332d090d1',
    'f893f637ccfa42d09368884d656b7984',
],
    'words': 'deer ape',
    'nested': {
    'id': 124,
    'rand_digit': 3,
    'array': [
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -5,
],
    [
    -1,
],
],
    'two_words': [
    'dragonfly',
    'kangaroo',
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
    'mixed_type': 4,
    'maybe': 'scorpion',
    'maybe_null': 'goat',
},
},
    {
    'id': 25,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 125,
    'id_str': [
    '25',
    '15',
    '27',
    '07',
],
    'text_data': '042621df9fd64d1485571d179478d419',
    'rand_digit': 7,
    'rand_number': 0.0712,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-04T01:34:02.198195',
    'text_array': [
    '8eedde07f8f740c9b8f3aff9993d9f3e',
    '0ba8f305ed184688b04b1ec1aec41bf0',
],
    'words': 'elephant bear',
    'nested': {
    'id': 125,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 1,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ant',
    'camel',
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
    'mixed_type': 0,
    'maybe': 'sheep',
    'maybe_null': None,
},
},
    {
    'id': 26,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 126,
    'id_str': [
    '18',
    '09',
    '27',
    '13',
],
    'text_data': '670601be21a64926a604ef98393035ca',
    'rand_digit': 1,
    'rand_number': 0.32849,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-22 19:29:34.786196+0400',
    'text_array': [
    'bf6e5c4fa2674b75b34e28f467abd293',
    '3cef29c13f6140d093746ecfaf0b38a8',
],
    'words': 'grasshopper spider',
    'nested': {
    'id': 126,
    'rand_digit': 6,
    'array': [
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
    'hello',
],
    'word': 'chicken',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'goat',
    'monkey',
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
    'maybe_null': 'giraffe',
},
},
    {
    'id': 27,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 127,
    'id_str': [
    '25',
],
    'text_data': 'b45fd472fb1f481b8f7c3869c980c53a',
    'rand_digit': 9,
    'rand_number': 0.50628,
    'rand_signed_int': -9,
    'rand_datetime': '2000-12-14',
    'text_array': [
    '656a656e2031491b9e660755b96bc5b2',
    'c4dc8b372b51463b8e31ae9d29763945',
],
    'words': 'horse shark',
    'nested': {
    'id': 127,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'tiger',
    'sheep',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 5,
    'maybe': 'shark',
    'maybe_null': 'frog',
},
},
    {
    'id': 28,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 128,
    'id_str': [
    '08',
    '19',
    '10',
],
    'text_data': '6bac004d015c4a66a7627a3e95303715',
    'rand_digit': 2,
    'rand_number': 0.03948,
    'rand_signed_int': 9,
    'rand_datetime': '2000-08-14 05:18:38.134465',
    'text_array': [
    'dd71a51e09d1411b995b5e0ba245d5f7',
    'a01a2eb4d27b485eb5b76c4a4704b52d',
],
    'words': 'lizard monkey',
    'nested': {
    'id': 128,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'deer',
    'frog',
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
    'mixed_type': True,
    'maybe_null': 'rabbit',
},
},
    {
    'id': 29,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 129,
    'id_str': [
    '24',
    '28',
    '05',
    '10',
],
    'text_data': 'cf9be029bc6d454d990d04204adea03d',
    'rand_digit': 2,
    'rand_number': 0.62881,
    'rand_signed_int': 1,
    'rand_datetime': '2001-01-19 13:53:04+0900',
    'text_array': [
    '98f124d85b7344449c4b59ac6be914a0',
    '6e6848949407468eb863a90ee70b1609',
],
    'words': 'snail lizard',
    'nested': {
    'id': 129,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
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
    -4,
],
],
    'two_words': [
    'ape',
    'mosquito',
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
    'mixed_type': 0,
    'maybe_null': 'koala',
},
},
    {
    'id': 30,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 130,
    'id_str': [
    '25',
    '21',
    '29',
    '15',
    '08',
],
    'text_data': '76d56a07e29c4bfb9022a696110d9db7',
    'rand_digit': 5,
    'rand_number': 0.10238,
    'rand_signed_int': 1,
    'rand_datetime': '2000-04-16 08:24:25',
    'text_array': [
    '0037cb03e9e74abf81f05e9a83c0caf8',
    '7aa1fc52f9034bac8055fc36375ac744',
],
    'words': 'dragonfly rabbit',
    'nested': {
    'id': 130,
    'rand_digit': 2,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
    -6,
],
],
    'two_words': [
    'frog',
    'koala',
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
    'mixed_type': None,
    'maybe': 'scorpion',
    'maybe_null': 'koala',
},
},
    {
    'id': 31,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 131,
    'id_str': [
    '19',
],
    'text_data': '5d42aaa5c114447a858832f64796a0e3',
    'rand_digit': 2,
    'rand_number': 0.24519,
    'rand_signed_int': 3,
    'rand_datetime': '2000-12-22 12:15:23.868200',
    'text_array': [
    '0aabaca15aa5422cb89ea3bb16b35264',
    '098b722fbe4247d693720028dee6d035',
],
    'words': 'octopus tiger',
    'nested': {
    'id': 131,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 5,
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
    'word': 'crab',
    'number': 10,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'cat',
    'panda',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'whale',
    'maybe_null': 'turtle',
},
},
    {
    'id': 32,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 132,
    'id_str': [
    '05',
    '20',
    '23',
    '02',
],
    'text_data': '0b3f68222c274219ae974314644c2aad',
    'rand_digit': 1,
    'rand_number': 0.81618,
    'rand_signed_int': -10,
    'rand_datetime': '2000-05-20',
    'text_array': [
    '193fbec0c36441458d68814bdc2a7584',
    '63012af2817c42b480d1735a0dd5e553',
],
    'words': 'bear scorpion',
    'nested': {
    'id': 132,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'cheetah',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'gorilla',
    'elephant',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': [
    73,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'octopus',
},
},
    {
    'id': 33,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 133,
    'id_str': [
    '27',
],
    'text_data': '104cd0a192954f78a8482b053f80cbd5',
    'rand_digit': 1,
    'rand_number': 0.62715,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-09T01:10:08.975638-11:00',
    'text_array': [
    '50bbc5fc55994b28b6eba3d6ef121d27',
    'f7f2e3dcace842aaa27a23c57acf0195',
],
    'words': 'lizard snail',
    'nested': {
    'id': 133,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 8,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'wolf',
    'hippo',
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
    'mixed_type': 'hyena',
},
},
    {
    'id': 34,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 134,
    'id_str': [
    '22',
    '25',
],
    'text_data': '330fd00898a842049c6a58713d5623df',
    'rand_digit': 6,
    'rand_number': 0.55972,
    'rand_signed_int': -5,
    'rand_datetime': '2000-02-28T07:25:12.622002',
    'text_array': [
    '75ce5e41e1e748259005e08d24a40f18',
    '3fa8fcbc1aad4e1cbe26eb7bb907f010',
],
    'words': 'dog spider',
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
    'word': 'bird',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 10,
},
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
    'word': 'hyena',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
    [
],
    [
    3,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'grasshopper',
    'bird',
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
    'mixed_type': 1,
},
},
    {
    'id': 35,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 135,
    'id_str': [
    '30',
    '29',
    '09',
    '04',
],
    'text_data': 'aae138e008154008abd066f7f7c82444',
    'rand_digit': 5,
    'rand_number': 0.34953,
    'rand_signed_int': -6,
    'rand_datetime': '2000-08-22',
    'text_array': [
    'aab6d5cc385a457ca8df6683e389f4f5',
    '23f4dfb940bf4d94bb60a5f9419412d9',
],
    'words': 'rhino turtle',
    'nested': {
    'id': 135,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
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
    [
    -2,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    4,
],
],
    'two_words': [
    'rhino',
    'rabbit',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': [
    34,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'monkey',
},
},
    {
    'id': 36,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 136,
    'id_str': [
    '27',
    '25',
    '20',
    '09',
    '24',
],
    'text_data': 'b566bf98d1284000a52cb82a2e121c0b',
    'rand_digit': 3,
    'rand_number': 0.23999,
    'rand_signed_int': 1,
    'rand_datetime': '2000-08-09T16:30:57.541698',
    'text_array': [
    '58c1d12f74e74830967d94f0412bc394',
    'ea17f61f21ee4c48a8decaee487b8e8e',
],
    'words': 'crab crab',
    'nested': {
    'id': 136,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 7,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dog',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'leopard',
    'crab',
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
    'mixed_type': None,
    'maybe': 'butterfly',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 37,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 137,
    'id_str': [
    '15',
    '11',
],
    'text_data': 'ab1d133e8b40424fbd79201340f18fd6',
    'rand_digit': 7,
    'rand_number': 0.14944,
    'rand_signed_int': 7,
    'rand_datetime': '2000-02-11 08:49:15.099430',
    'text_array': [
    '77c3d151e3af4b1cb8c9c6406bd8795c',
    '89b4e4be594449519dae4ffa0a513bfd',
],
    'words': 'sloth squid',
    'nested': {
    'id': 137,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'tiger',
    'butterfly',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': [
    16,
],
    'rand_bool': False,
    'mixed_type': True,
},
},
    {
    'id': 38,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 138,
    'id_str': [
    '11',
    '05',
],
    'text_data': 'a05700cdb9394d709b8bb3df90fb8c93',
    'rand_digit': 0,
    'rand_number': 0.8552,
    'rand_signed_int': -6,
    'rand_datetime': '2000-06-15',
    'text_array': [
    'c99b3ea8f23547e991ecb8e9d602e087',
    '8d06b63c24354d77b4c1e791bf1b4f2c',
],
    'words': 'kangaroo turtle',
    'nested': {
    'id': 138,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'gorilla',
    'panda',
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
    'maybe': 'octopus',
    'maybe_null': None,
},
},
    {
    'id': 39,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 139,
    'id_str': [
    '25',
    '20',
    '03',
    '15',
],
    'text_data': '51e1be09833245b18072c6bdb06480f1',
    'rand_digit': 5,
    'rand_number': 0.25365,
    'rand_signed_int': 10,
    'rand_datetime': '2000-12-02T07:26:04',
    'text_array': [
    '4cbda12f72be4d4c93cc2548c7a1a776',
    '25a9442ae742456db096f3184a5de6d2',
],
    'words': 'chicken lobster',
    'nested': {
    'id': 139,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'duck',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'lion',
    'whale',
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
    'mixed_type': True,
    'maybe_null': None,
},
},
    {
    'id': 40,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 140,
    'id_str': [
    '28',
    '19',
    '03',
    '05',
],
    'text_data': '7df46827b8154ac682987b4a1543e611',
    'rand_digit': 5,
    'rand_number': 0.26484,
    'rand_signed_int': -6,
    'rand_datetime': '2000-09-01T20:13:18',
    'text_array': [
    '74b06123bff142228eb91998746140cd',
    'b07b1ec6e83645ef9eec79a01c5a5e5b',
],
    'words': 'dragonfly lion',
    'nested': {
    'id': 140,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 1,
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
],
    'two_words': [
    'ladybug',
    'bird',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': [
    79,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'sheep',
},
},
    {
    'id': 41,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 141,
    'id_str': [
    '25',
],
    'text_data': '6c082b5082e34b40b4bca27f27201813',
    'rand_digit': 6,
    'rand_number': 0.40434,
    'rand_signed_int': 2,
    'rand_datetime': '2001-01-21T11:35:14.349875',
    'text_array': [
    '0e56afafa4124a9baccbc970ee30e1c3',
    'e2369eae2ec044419d50a8a1c73c08ba',
],
    'words': 'lion pig',
    'nested': {
    'id': 141,
    'rand_digit': 4,
    'array': [
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
    'word': 'deer',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'koala',
    'number': 9,
},
],
},
    'nested_array': [
    [
    -10,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dragonfly',
    'kangaroo',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': [
    92,
],
    'rand_bool': False,
    'mixed_type': 8,
    'maybe_null': None,
},
},
    {
    'id': 42,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 142,
    'id_str': [
    '15',
    '03',
    '18',
],
    'text_data': 'a770cbe7a2054b76b58c0a916a39c278',
    'rand_digit': 0,
    'rand_number': 0.64115,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-27 15:17:01-1100',
    'text_array': [
    '814aebed7a814e8e84d790661d9c6e0c',
    '8c03e13d946c4a1c952ed3caaee0984e',
],
    'words': 'dolphin bear',
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
    'word': 'spider',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 7,
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
    'word': 'sheep',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'squid',
    'duck',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.36998,
    'maybe': 'rhino',
    'maybe_null': 'cheetah',
},
},
    {
    'id': 43,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 143,
    'id_str': [
    '18',
],
    'text_data': '9be382be38d94b9caf30590764c69728',
    'rand_digit': 2,
    'rand_number': 0.55213,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-26 23:31:31.920109-0600',
    'text_array': [
    'c929b8b4e0f945ebb3997c0883ce8775',
    '7d8d562e93784d3d81721b13863bb793',
],
    'words': 'dragonfly grasshopper',
    'nested': {
    'id': 143,
    'rand_digit': 4,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'panda',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'tiger',
    'dolphin',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.20881,
},
},
    {
    'id': 44,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 144,
    'id_str': [
    '24',
    '08',
    '13',
],
    'text_data': '26dbf7b483704304a6d638d17578bd8d',
    'rand_digit': 4,
    'rand_number': 0.73945,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-08 18:06:30+0500',
    'text_array': [
    'fc4c1737b0f549cbb1bf9fb8e17ebf8c',
    '248044b7aac24dadaee6c1556df5f98e',
],
    'words': 'ape lobster',
    'nested': {
    'id': 144,
    'rand_digit': 5,
    'array': [
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
    'hello',
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
    'word': 'snake',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dolphin',
    'rabbit',
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
    'mixed_type': 'pig',
    'maybe_null': 'ant',
},
},
    {
    'id': 45,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 145,
    'id_str': [
    '02',
    '14',
],
    'text_data': '6e2e7d10b1554345a223542e50e4723b',
    'rand_digit': 9,
    'rand_number': 0.86869,
    'rand_signed_int': 8,
    'rand_datetime': '2000-11-20 03:54:32',
    'text_array': [
    '73d23c2c17114530b013454d265068e6',
    'f848e68537c64ff08d2eed6e9a058aad',
],
    'words': 'ladybug lion',
    'nested': {
    'id': 145,
    'rand_digit': 9,
    'array': [
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
],
    'word': 'giraffe',
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
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
    8,
],
    [
],
],
    'two_words': [
    'horse',
    'camel',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'goat',
    'maybe_null': None,
},
},
    {
    'id': 46,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 146,
    'id_str': [
    '14',
    '17',
    '15',
    '05',
],
    'text_data': '4a323242be334d219b58c803eab561f8',
    'rand_digit': 6,
    'rand_number': 0.17783,
    'rand_signed_int': 6,
    'rand_datetime': '2001-01-08 06:13:19.677823-0500',
    'text_array': [
    '048257416193441f997d405360e3a987',
    'c6843d46ff584a03ab511a85f95038bd',
],
    'words': 'gorilla whale',
    'nested': {
    'id': 146,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    0,
],
],
    'two_words': [
    'mouse',
    'bird',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'fish',
    'maybe_null': 'lobster',
},
},
    {
    'id': 47,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 147,
    'id_str': [
    '29',
],
    'text_data': 'd11e1902719849a8884789d13929a134',
    'rand_digit': 6,
    'rand_number': 0.41225,
    'rand_signed_int': -9,
    'rand_datetime': '2000-03-11T00:44:40.376018-0800',
    'text_array': [
    'f6ee87982a1343ae91c7db24f529be0a',
    '51b35749c2884172b536398741bbbb6e',
],
    'words': 'mosquito duck',
    'nested': {
    'id': 147,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
    -4,
],
],
    'two_words': [
    'fish',
    'bird',
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
    'mixed_type': True,
},
},
    {
    'id': 48,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 148,
    'id_str': [
    '26',
    '20',
],
    'text_data': '068571762469417f87ab11a80da19a57',
    'rand_digit': 8,
    'rand_number': 0.02908,
    'rand_signed_int': 10,
    'rand_datetime': '2000-05-29T12:27:37.838272-0800',
    'text_array': [
    '1276ba741c6c474594e5006f1f60c508',
    '56ba7218412f4448b38c5b41f11fe575',
],
    'words': 'wolf wolf',
    'nested': {
    'id': 148,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'sheep',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'duck',
    'bird',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': [
    49,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'jaguar',
},
},
    {
    'id': 49,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 149,
    'id_str': [
    '05',
    '17',
    '25',
    '01',
    '20',
],
    'text_data': '09638b0cefc04d57a128508f90e8968a',
    'rand_digit': 6,
    'rand_number': 0.81197,
    'rand_signed_int': 8,
    'rand_datetime': '2000-03-29 06:55:31.581040-0500',
    'text_array': [
    '7f9906e1f0af45149b1d9c9803c38462',
    'b32052e51a3d4fc6ab4e8c008c86258c',
],
    'words': 'bee rhino',
    'nested': {
    'id': 149,
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
    'number': 6,
},
],
},
    'nested_array': [
    [
    2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'bee',
    'snake',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': [
    16,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'whale',
    'maybe_null': 'kangaroo',
},
},
    {
    'id': 50,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 150,
    'id_str': [
    '10',
],
    'text_data': '33d878dd834241a9924c70c608d4a2a0',
    'rand_digit': 9,
    'rand_number': 0.08079,
    'rand_signed_int': 8,
    'rand_datetime': '2000-04-01 17:45:25.492615',
    'text_array': [
    '8e39b5a02dc44b40a2699b0bfe047a3c',
    '08899f6856ed4c6f901be0882d6f1da3',
],
    'words': 'bird ape',
    'nested': {
    'id': 150,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'shark',
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
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 1,
},
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
    'word': 'cow',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'elephant',
    'snake',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': [
    9,
],
    'rand_bool': False,
    'mixed_type': 'cow',
},
},
    {
    'id': 51,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 151,
    'id_str': [
    '03',
    '12',
    '23',
    '10',
],
    'text_data': '08151995633d4b0aa16e9c2d0c4b04d3',
    'rand_digit': 5,
    'rand_number': 0.50145,
    'rand_signed_int': 4,
    'rand_datetime': '2000-02-03 06:29:46-0300',
    'text_array': [
    '889f2bd0adaf453fbb4cb327b76bc807',
    '59de85c868594233968f6599ab802a9a',
],
    'words': 'chicken tiger',
    'nested': {
    'id': 151,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'whale',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'shark',
    'bee',
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
    'mixed_type': 0.41786,
    'maybe_null': 'zebra',
},
},
    {
    'id': 52,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 152,
    'id_str': [
    '10',
    '16',
    '07',
    '29',
    '06',
],
    'text_data': '9c0508f2eb9d491ea5cfe66d67222b0a',
    'rand_digit': 8,
    'rand_number': 0.70997,
    'rand_signed_int': -3,
    'rand_datetime': '2001-01-28T02:50:12-0300',
    'text_array': [
    '5c6587757e4b4da2846065173f6dbef6',
    '9ee8ac246f1948cd9161ecd9f9462ac7',
],
    'words': 'spider snake',
    'nested': {
    'id': 152,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'frog',
    'mouse',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 53,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 153,
    'id_str': [
    '22',
],
    'text_data': '3d7a3b7b71a54782ab7e50d336d04905',
    'rand_digit': 7,
    'rand_number': 0.17437,
    'rand_signed_int': -10,
    'rand_datetime': '2000-09-13',
    'text_array': [
    '0d508b972fe246b1b065bf62d69e9d2a',
    'ba7ba2c0d3464c28a5a4ae3d42d7bff3',
],
    'words': 'lizard bird',
    'nested': {
    'id': 153,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'ladybug',
    'wolf',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'hippo',
},
},
    {
    'id': 54,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 154,
    'id_str': [
    '01',
    '17',
    '17',
],
    'text_data': '9484fe17ffd9423bafdd5253a41d00e9',
    'rand_digit': 0,
    'rand_number': 0.64966,
    'rand_signed_int': 7,
    'rand_datetime': '2001-01-16 21:15',
    'text_array': [
    'f10123cac2244ec79f8eda2f13a5f7a2',
    'f7717fac6b504567a88c75e8c214af79',
],
    'words': 'mouse hyena',
    'nested': {
    'id': 154,
    'rand_digit': 8,
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
],
    [
],
],
    'two_words': [
    'hippo',
    'tiger',
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
    'maybe': 'fish',
},
},
    {
    'id': 55,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 155,
    'id_str': [
    '04',
    '07',
    '14',
    '16',
    '06',
],
    'text_data': '88a48e88d1264242a640dcd3dd191f45',
    'rand_digit': 0,
    'rand_number': 0.48239,
    'rand_signed_int': -4,
    'rand_datetime': '2000-01-06T02:09:31.888628+0000',
    'text_array': [
    '53fcbf82776b44a280721faaff0a2063',
    'fae68a2e20c2405f8905ae55018d2f08',
],
    'words': 'dragonfly leopard',
    'nested': {
    'id': 155,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'mouse',
    'sloth',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'zebra',
    'maybe_null': 'jaguar',
},
},
    {
    'id': 56,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 156,
    'id_str': [
    '02',
],
    'text_data': '2cf35e87ddc0435fa2e19a3d14867a58',
    'rand_digit': 6,
    'rand_number': 0.53693,
    'rand_signed_int': 6,
    'rand_datetime': '2000-05-18 14:39:25.010844',
    'text_array': [
    '95faff60c3e547429b6973e2ac096f33',
    '940c00fc6e0d4dac9cddcbf6826f58e7',
],
    'words': 'bird tiger',
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
    'word': 'dragonfly',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bee',
    'number': 5,
},
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fish',
    'mouse',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 'bear',
    'maybe': 'bird',
},
},
    {
    'id': 57,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 157,
    'id_str': [
    '28',
    '06',
    '18',
],
    'text_data': '7c70eb75f0ec46f283127e8e804e0019',
    'rand_digit': 6,
    'rand_number': 0.85386,
    'rand_signed_int': 3,
    'rand_datetime': '2000-07-17',
    'text_array': [
    '75e8301db7084263ab3f0bdf2fd07bc3',
    'c698e0e64c4c42d1ab264cab8d403cb4',
],
    'words': 'elephant rhino',
    'nested': {
    'id': 157,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 5,
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
    'panda',
    'monkey',
],
    'city': {
    'name': 'Seoul',
    'geo': {
    'lat': 37.566535,
    'lon': 126.977969,
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
    'id': 58,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 158,
    'id_str': [
    '06',
],
    'text_data': '58e23ad69ae84d2a8386cc7ec493388e',
    'rand_digit': 6,
    'rand_number': 0.26679,
    'rand_signed_int': -5,
    'rand_datetime': '2000-03-29T22:16:30',
    'text_array': [
    'c3568c1866f34d6c91d405d747b9570c',
    '04eed9f3338b41259e809354f69f5c56',
],
    'words': 'scorpion camel',
    'nested': {
    'id': 158,
    'rand_digit': 7,
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
    'hello',
],
    'word': 'bee',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'wolf',
    'grasshopper',
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
    'mixed_type': True,
    'maybe_null': 'rhino',
},
},
    {
    'id': 59,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 159,
    'id_str': [
    '28',
    '17',
    '27',
    '25',
],
    'text_data': '995a12b15fe04315b27a9690d932424b',
    'rand_digit': 6,
    'rand_number': 0.81177,
    'rand_signed_int': -9,
    'rand_datetime': '2001-01-07',
    'text_array': [
    'd6c27d90749d45c3b6ce721280085e45',
    '5d85705d8dfc44648d6b6b7ef659e74c',
],
    'words': 'deer giraffe',
    'nested': {
    'id': 159,
    'rand_digit': 6,
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
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'scorpion',
    'camel',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'cat',
},
},
    {
    'id': 60,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 160,
    'id_str': [
    '09',
    '04',
    '13',
],
    'text_data': 'fb1d44914fee42d984ee40a4b2fee215',
    'rand_digit': 2,
    'rand_number': 0.58319,
    'rand_signed_int': -8,
    'rand_datetime': '2000-09-21 23:49:10.175142',
    'text_array': [
    '81cc4fe1e8af434b806e39fa263742cd',
    '21f6029ab2784ed99a3f158ab207f76a',
],
    'words': 'panda hyena',
    'nested': {
    'id': 160,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'sloth',
    'fox',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'sloth',
},
},
    {
    'id': 61,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 161,
    'id_str': [
    '13',
    '10',
    '16',
    '12',
],
    'text_data': '72c3fbffdc574404b13abb5e6efd7337',
    'rand_digit': 4,
    'rand_number': 0.86229,
    'rand_signed_int': -3,
    'rand_datetime': '2000-08-08T19:38:49',
    'text_array': [
    '259dd9bec8d64812a13fe6a9409ccd47',
    'dd67f9d211b64698afb96164b0dd4224',
],
    'words': 'frog snake',
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
    'word': 'ape',
    'number': 3,
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
    'word': 'zebra',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'camel',
    'jaguar',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
    'maybe_null': None,
},
},
    {
    'id': 62,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 162,
    'id_str': [
    '20',
],
    'text_data': '4ba545dbe4e54e94ab65cfc74ffdabea',
    'rand_digit': 3,
    'rand_number': 0.04867,
    'rand_signed_int': -1,
    'rand_datetime': '2000-05-30',
    'text_array': [
    '199bff389a234236b7817d28edde9511',
    '3803c75532ae4dfabcc08c27738632bf',
],
    'words': 'panda lizard',
    'nested': {
    'id': 162,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
    -5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'koala',
    'ladybug',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'mosquito',
},
},
    {
    'id': 63,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 163,
    'id_str': [
    '27',
    '23',
    '04',
],
    'text_data': '182f5b6258e442a692263cd7ccb80282',
    'rand_digit': 1,
    'rand_number': 0.94564,
    'rand_signed_int': 0,
    'rand_datetime': '2000-03-05T05:17:02+0100',
    'text_array': [
    '074e4769a75445e8a95a8d7beebe4401',
    'd7c7a9950812424ea5a1b0d684de13e9',
],
    'words': 'lizard giraffe',
    'nested': {
    'id': 163,
    'rand_digit': 1,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lion',
    'lobster',
],
    'city': {
    'name': 'Athens',
    'geo': {
    'lat': 37.98381,
    'lon': 23.727539,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.31975,
    'maybe': 'pig',
    'maybe_null': 'ape',
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
        """测试请求 2 - POST http://localhost:6333/collections/client_test/points/count"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/client_test/points/count")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/client_test/points/count'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '76',
}
        
        # 原始请求内容
        original_content = {
    'filter': {
    'must': [
    {
    'key': 'rand_number',
    'range': {
    'gte': 0.5,
},
},
],
},
    'exact': True,
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
        """测试请求 3 - PUT http://localhost:6333/collections/client_test/points?wait=true"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/client_test/points?wait=true")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/client_test/points?wait=true'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '124632',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 1,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 2,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 3,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 4,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 5,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 6,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 7,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 8,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 9,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 10,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 11,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 12,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 13,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 14,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 15,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 16,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 17,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 18,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 19,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 20,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 21,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 22,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 23,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 24,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 25,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 26,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 27,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 28,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 29,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 30,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 31,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 32,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 33,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 34,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 35,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 36,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 37,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 38,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 39,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 40,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 41,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 42,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 43,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 44,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 45,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 46,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 47,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 48,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 49,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 50,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 51,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 52,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 53,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 54,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 55,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 56,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 57,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 58,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 59,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 60,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 61,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 62,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    {
    'id': 63,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
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
        """测试请求 4 - DELETE http://localhost:6333/collections/client_test?timeout=60"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://localhost:6333/collections/client_test?timeout=60")
        method = 'DELETE'
        url_path = 'http://localhost:6333/collections/client_test?timeout=60'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '41',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'size': 100,
    'distance': 'Dot',
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_qdrant_client.test_point_upload')
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
    test = TestQdrantClienttestPointUpload()
    test.run_tests()
