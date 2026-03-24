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
logger = logging.getLogger('vdb_fuzzer.test.test_qdrant_client_test_records_upload')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_qdrant_client.test_records_upload"
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



class TestQdrantClienttestRecordsUpload:
    """自动生成的VDB模糊测试类 - test_qdrant_client.test_records_upload"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_qdrant_client.test_records_upload"
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
    'content-length': '173766',
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
    '10',
    '22',
    '29',
],
    'text_data': '87c7fc7533724b9e8e512c4e0d3abd72',
    'rand_digit': 3,
    'rand_number': 0.90009,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-09 08:26:31+0500',
    'text_array': [
    'c3bc879957e2443a8d6bcca5607107dc',
    '9dca55c183b54be08a54c6d22e1e57c3',
],
    'words': 'scorpion zebra',
    'nested': {
    'id': 100,
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
    'number': 7,
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
    {
    'nested_empty': None,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lizard',
    'giraffe',
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
    'mixed_type': 1,
    'maybe': 'chicken',
    'maybe_null': 'hyena',
},
},
    {
    'id': 1,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 101,
    'id_str': [
    '15',
    '06',
    '07',
],
    'text_data': '1dfd76dd4c2242ff8c039580132cebec',
    'rand_digit': 6,
    'rand_number': 0.03072,
    'rand_signed_int': -6,
    'rand_datetime': '2000-07-26T15:22:32',
    'text_array': [
    '57f321d0fcc84f5b8294fb3fa8ee092c',
    'c3c1f8ac72b14177ae966eb89234d99d',
],
    'words': 'sloth gorilla',
    'nested': {
    'id': 101,
    'rand_digit': 7,
    'array': [
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
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'rabbit',
    'lizard',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
},
},
    'rand_tuple': [
    84,
],
    'rand_bool': False,
    'mixed_type': 9,
    'maybe_null': 'snail',
},
},
    {
    'id': 2,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 102,
    'id_str': [
    '12',
    '12',
    '21',
    '05',
    '12',
],
    'text_data': '834166e23a5b4a16be4427940e6fa42d',
    'rand_digit': 1,
    'rand_number': 0.08408,
    'rand_signed_int': -1,
    'rand_datetime': '2000-02-22T20:21:47.415848',
    'text_array': [
    '8b066d7b564b4479abd8b485e41be261',
    'dcee76d6e7a846e59eaee6c63aa4f1da',
],
    'words': 'turtle ant',
    'nested': {
    'id': 102,
    'rand_digit': 3,
    'array': [
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
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'mosquito',
    'shark',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': [
    67,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 3,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 103,
    'id_str': [
    '23',
    '08',
    '08',
],
    'text_data': '628f3fc74b264d54bfe8a571c2f843f2',
    'rand_digit': 6,
    'rand_number': 0.4399,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-08T21:51:13+0000',
    'text_array': [
    '8b7af10873f44741abdfae3d4cca8651',
    'f99753ccb0404d5a829506e905d0cd80',
],
    'words': 'fly elephant',
    'nested': {
    'id': 103,
    'rand_digit': 3,
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
    'word': 'sloth',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'crab',
    'frog',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': [
    51,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'horse',
    'maybe_null': 'monkey',
},
},
    {
    'id': 4,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 104,
    'id_str': [
    '16',
    '24',
    '10',
    '26',
    '17',
],
    'text_data': '43c12b59c41e4b5592e0e8cc57d25187',
    'rand_digit': 2,
    'rand_number': 0.55777,
    'rand_signed_int': 7,
    'rand_datetime': '2000-07-30T02:34:37.311531',
    'text_array': [
    'aec591d04e804d7392125df3cba8281c',
    '0aeaf8d108874fc79ac5844d8651385e',
],
    'words': 'dolphin fish',
    'nested': {
    'id': 104,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'leopard',
    'mosquito',
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
    'mixed_type': False,
},
},
    {
    'id': 5,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 105,
    'id_str': [
    '11',
    '13',
    '16',
    '25',
    '22',
],
    'text_data': '24502b0632594a809a0f1c22e536035e',
    'rand_digit': 8,
    'rand_number': 0.43021,
    'rand_signed_int': -5,
    'rand_datetime': '2000-10-08T13:23:46.694831-08:00',
    'text_array': [
    'e139746c5f994624b75c122d62eebb24',
    'faa846125ae24863889834f087ec8467',
],
    'words': 'mouse dragonfly',
    'nested': {
    'id': 105,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 6,
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
    'word': 'hippo',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ant',
    'snail',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 'lobster',
    'maybe_null': 'fox',
},
},
    {
    'id': 6,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 106,
    'id_str': [
    '01',
    '30',
    '25',
    '02',
],
    'text_data': '253f2014f9974568b3d7721330e5c065',
    'rand_digit': 6,
    'rand_number': 0.34825,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-01T00:35:12.873102',
    'text_array': [
    '1ada075475654f0084c31e7b893a1a88',
    'af537aa5506d4112945e3750f28a1a98',
],
    'words': 'octopus rabbit',
    'nested': {
    'id': 106,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'bear',
    'sheep',
],
    'city': {
    'name': 'Moscow',
    'geo': {
    'lat': 55.755826,
    'lon': 37.6173,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'deer',
},
},
    {
    'id': 7,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 107,
    'id_str': [
    '18',
    '08',
    '13',
    '18',
    '10',
],
    'text_data': '65b357a2ecfc47108fcb4f6c7b5230fb',
    'rand_digit': 2,
    'rand_number': 0.66769,
    'rand_signed_int': -6,
    'rand_datetime': '2000-09-28T09:20:09.521179',
    'text_array': [
    '8771a8bf4d1c4976bcaffc79879c556f',
    '5d549bdc3bd041de9f3fbeb76be50db7',
],
    'words': 'butterfly wolf',
    'nested': {
    'id': 107,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'giraffe',
    'zebra',
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
    'mixed_type': 7,
    'maybe': 'hippo',
    'maybe_null': 'panda',
},
},
    {
    'id': 8,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 108,
    'id_str': [
    '30',
    '22',
    '08',
    '02',
    '16',
],
    'text_data': '0bebf2caed64405fb26ce3ae00c42b5e',
    'rand_digit': 9,
    'rand_number': 0.53178,
    'rand_signed_int': -9,
    'rand_datetime': '2000-08-29T19:18:24',
    'text_array': [
    '5ddd1fb9d0f84da6af3818b8f0d23041',
    '6b5818d550964eec9bff9955da14f064',
],
    'words': 'giraffe panda',
    'nested': {
    'id': 108,
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
    'number': 6,
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
    'word': 'ant',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'kangaroo',
    'zebra',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'whale',
},
},
    {
    'id': 9,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 109,
    'id_str': [
    '04',
    '04',
],
    'text_data': '925ade5a1c2c41d5a4191e1d77ece82d',
    'rand_digit': 6,
    'rand_number': 0.42274,
    'rand_signed_int': -3,
    'rand_datetime': '2000-08-04',
    'text_array': [
    '89e27d4894144c4487b846b1e2c1d3ec',
    '7b7e2b4408be474e88e3dcf0042ac391',
],
    'words': 'lion fish',
    'nested': {
    'id': 109,
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
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 8,
},
],
},
    'nested_array': [
    [
    -6,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'whale',
    'giraffe',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'panda',
},
},
    {
    'id': 10,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 110,
    'id_str': [
],
    'text_data': '33b48601c1234ed5acaf1be5fcce6768',
    'rand_digit': 3,
    'rand_number': 0.16788,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-12 14:02:41+0700',
    'text_array': [
    '35466d04421a4612a7be939540fc4671',
    'a50f90074b3f4da19180f4c30a73edca',
],
    'words': 'dog rabbit',
    'nested': {
    'id': 110,
    'rand_digit': 9,
    'array': [
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
    'word': 'panda',
    'number': 7,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'jaguar',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'snail',
    'monkey',
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
    'mixed_type': 'ant',
},
},
    {
    'id': 11,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 111,
    'id_str': [
    '01',
    '11',
],
    'text_data': 'cb285724a15c4aa59c5476cabf21863c',
    'rand_digit': 1,
    'rand_number': 0.53659,
    'rand_signed_int': -10,
    'rand_datetime': '2000-12-12 09:41:19.064093',
    'text_array': [
    '1c0f3ba4668f48b580d58bd32957c3c0',
    '228d971e72e54a6baa64dbb8dee4839d',
],
    'words': 'pig octopus',
    'nested': {
    'id': 111,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'butterfly',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    [
    -3,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lion',
    'cheetah',
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
    'mixed_type': 0.52848,
},
},
    {
    'id': 12,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 112,
    'id_str': [
    '23',
    '11',
    '10',
    '03',
],
    'text_data': 'd7cc5c3b111e4e3691e6385601d77654',
    'rand_digit': 9,
    'rand_number': 0.27839,
    'rand_signed_int': -6,
    'rand_datetime': '2000-05-06 13:05:24.690923',
    'text_array': [
    '9d986f1b7ccf4f9c8b7e0c8eea266c71',
    '1583af3bed5f44b79caaef8e2ac11406',
],
    'words': 'snail squid',
    'nested': {
    'id': 112,
    'rand_digit': 5,
    'array': [
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
    'word': 'hyena',
    'number': 10,
},
],
},
    'nested_array': [
    [
    4,
],
    [
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'wolf',
    'sloth',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'scorpion',
    'maybe_null': 'duck',
},
},
    {
    'id': 13,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 113,
    'id_str': [
    '25',
],
    'text_data': '6bd5010059024989923e0472bd945144',
    'rand_digit': 7,
    'rand_number': 0.46733,
    'rand_signed_int': 1,
    'rand_datetime': '2000-10-16T18:30:54+1100',
    'text_array': [
    'b0b3cb26e958403ba4772e67c3700518',
    '5654bf04f47c4454879848d95a4cb560',
],
    'words': 'ladybug sloth',
    'nested': {
    'id': 113,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'ladybug',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'ape',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
],
    [
    -2,
],
    [
    -9,
],
],
    'two_words': [
    'koala',
    'hippo',
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
    'mixed_type': 'whale',
    'maybe': 'fish',
},
},
    {
    'id': 14,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 114,
    'id_str': [
    '06',
    '18',
    '17',
],
    'text_data': '793a37e95f85413f94ec93bcf0f84c54',
    'rand_digit': 1,
    'rand_number': 0.78361,
    'rand_signed_int': 8,
    'rand_datetime': '2000-01-15',
    'text_array': [
    'b99eab6169f34a5f9145b70b395efdca',
    '0754658e07614bde915f849e94eab398',
],
    'words': 'ladybug horse',
    'nested': {
    'id': 114,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
    4,
],
    [
    3,
],
],
    'two_words': [
    'frog',
    'cat',
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
    'mixed_type': 'dolphin',
    'maybe': 'bear',
    'maybe_null': 'duck',
},
},
    {
    'id': 15,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 115,
    'id_str': [
    '02',
    '26',
    '25',
    '26',
],
    'text_data': 'c6b2f1be5d0740d2b3e90940791a649c',
    'rand_digit': 7,
    'rand_number': 0.46802,
    'rand_signed_int': 0,
    'rand_datetime': '2000-12-29 20:19:07-0500',
    'text_array': [
    '8054ebc85c6046b9bf9fb817bab40a4b',
    '2030530e887341a681ff4c63042e3f74',
],
    'words': 'camel giraffe',
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
    'word': 'spider',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'giraffe',
    'wolf',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
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
    '08',
    '27',
    '28',
    '03',
    '23',
],
    'text_data': '4825c3f834c24ba1964a8a6f83158c33',
    'rand_digit': 0,
    'rand_number': 0.16414,
    'rand_signed_int': 7,
    'rand_datetime': '2000-06-30T01:00:59.840868-1000',
    'text_array': [
    'ccc5298fdc384b24a0449c3be16b1f61',
    'f49e84ebbdbc4612b858a4b5c728c053',
],
    'words': 'ladybug squid',
    'nested': {
    'id': 116,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'duck',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'rabbit',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'frog',
    'frog',
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
    'mixed_type': 0.33788,
    'maybe': 'fox',
    'maybe_null': 'duck',
},
},
    {
    'id': 17,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 117,
    'id_str': [
    '27',
],
    'text_data': 'b0eba2c394dc4e3b8b189aa1a6102d91',
    'rand_digit': 4,
    'rand_number': 0.87291,
    'rand_signed_int': 8,
    'rand_datetime': '2000-03-10 08:43:55+0900',
    'text_array': [
    '9b47bea72bf64b75a3801dba0486c94b',
    '7909e05c2932445ca07eadcbb4f95b96',
],
    'words': 'kangaroo leopard',
    'nested': {
    'id': 117,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'fish',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -4,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'snail',
    'panda',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': [
    100,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'shark',
    'maybe_null': 'rabbit',
},
},
    {
    'id': 18,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 118,
    'id_str': [
],
    'text_data': '5a31b149f1724ca99768571486b610aa',
    'rand_digit': 1,
    'rand_number': 0.95345,
    'rand_signed_int': -5,
    'rand_datetime': '2001-01-04T10:00:25-1100',
    'text_array': [
    '554aea6a92e84699840b2021c9abd34b',
    'cdf2d3e79c0d428caa1d296e4f61b3bb',
],
    'words': 'fly duck',
    'nested': {
    'id': 118,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
    -3,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'ant',
    'dolphin',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'chicken',
    'maybe_null': None,
},
},
    {
    'id': 19,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 119,
    'id_str': [
    '23',
    '09',
],
    'text_data': 'a51e61f3660b402fabbf95ecd9989f4e',
    'rand_digit': 9,
    'rand_number': 0.10533,
    'rand_signed_int': 7,
    'rand_datetime': '2000-08-10T05:42:40.415113',
    'text_array': [
    '084c77a71dc1453f8e793c0757505772',
    '9ea9d5cb6e314edd9084828ff32baf7b',
],
    'words': 'cat scorpion',
    'nested': {
    'id': 119,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'lion',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'koala',
    'jaguar',
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
    'mixed_type': 3,
    'maybe': 'fly',
    'maybe_null': 'tiger',
},
},
    {
    'id': 20,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 120,
    'id_str': [
    '12',
    '11',
    '26',
    '13',
],
    'text_data': '680282cb21b54e37942a5a8faa981533',
    'rand_digit': 0,
    'rand_number': 0.13641,
    'rand_signed_int': 6,
    'rand_datetime': '2000-05-13 11:41:01.842219',
    'text_array': [
    '8c5211c05c8c4d61873e0211537cb8f6',
    'c6ec1fd451a0439c91cf754565c6f559',
],
    'words': 'butterfly sloth',
    'nested': {
    'id': 120,
    'rand_digit': 8,
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
    'turtle',
    'lizard',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'lion',
},
},
    {
    'id': 21,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 121,
    'id_str': [
],
    'text_data': '928a473c10534f10a564736cddbf9188',
    'rand_digit': 3,
    'rand_number': 0.7061,
    'rand_signed_int': 4,
    'rand_datetime': '2000-04-11 15:50:28+0200',
    'text_array': [
    'e911407130df4186bd96a43c6111b31b',
    'd8a0a38966ed4a889569d5a2d7418103',
],
    'words': 'dragonfly butterfly',
    'nested': {
    'id': 121,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
],
    [
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
    'maybe': 'butterfly',
},
},
    {
    'id': 22,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 122,
    'id_str': [
],
    'text_data': 'd8b78fd25f114c9187178371de2681ba',
    'rand_digit': 3,
    'rand_number': 0.30586,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-30T15:25:54.523934',
    'text_array': [
    '0b4ac4f9ae9f40509aa35573d48c8098',
    'c48ea0e42f704ac786fe961e98bebcd5',
],
    'words': 'goat tiger',
    'nested': {
    'id': 122,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'lobster',
    'bee',
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
    'mixed_type': None,
    'maybe_null': 'mosquito',
},
},
    {
    'id': 23,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 123,
    'id_str': [
    '29',
    '16',
    '17',
],
    'text_data': '3ae8c3ecad4945dbbe4d0cf223d4d795',
    'rand_digit': 2,
    'rand_number': 0.4162,
    'rand_signed_int': 7,
    'rand_datetime': '2000-11-22 21:44:03',
    'text_array': [
    'ac4a80817551497ca340fa46b00c352f',
    '91b08cb8bfa94359ba9867bd414fb322',
],
    'words': 'lobster bee',
    'nested': {
    'id': 123,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'crab',
    'panda',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'lion',
    'maybe_null': 'turtle',
},
},
    {
    'id': 24,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 124,
    'id_str': [
],
    'text_data': '0d4e548501bc46b5a2f21785683c097e',
    'rand_digit': 2,
    'rand_number': 0.24261,
    'rand_signed_int': -3,
    'rand_datetime': '2000-02-14',
    'text_array': [
    '042a0ce85d3d402185c83f3f791dc7ec',
    'a4ac6dc08e7f44509c62fa16a3fed0c0',
],
    'words': 'jaguar cat',
    'nested': {
    'id': 124,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 7,
},
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
    'word': 'monkey',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'crab',
    'frog',
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
    'mixed_type': 9,
},
},
    {
    'id': 25,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 125,
    'id_str': [
    '17',
    '27',
    '25',
    '30',
    '16',
],
    'text_data': 'eac52a3ed4ac4a81a13f47c5328cf0c7',
    'rand_digit': 7,
    'rand_number': 0.79106,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-03T21:24:14.824282-01:00',
    'text_array': [
    '3d606f2114724224a19126f16ec829aa',
    '96acc9e4fd0141269c33de96c0cf2965',
],
    'words': 'squid gorilla',
    'nested': {
    'id': 125,
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
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    7,
],
    [
],
],
    'two_words': [
    'turtle',
    'shark',
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
    'mixed_type': None,
    'maybe': 'dragonfly',
    'maybe_null': 'camel',
},
},
    {
    'id': 26,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 126,
    'id_str': [
    '24',
    '20',
],
    'text_data': 'a51a62723ef042aeb42ef59d82c50e0f',
    'rand_digit': 3,
    'rand_number': 0.71439,
    'rand_signed_int': 9,
    'rand_datetime': '2000-03-01T14:45:47.895651-0200',
    'text_array': [
    'f50278b0e7df4c149eee3ac846a4327e',
    'fd838b34bdad445da2702512626e08d2',
],
    'words': 'hippo hippo',
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
    'word': 'rhino',
    'number': 2,
},
],
},
    'nested_array': [
    [
    -4,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'cat',
    'bee',
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
    'mixed_type': False,
    'maybe': 'lobster',
    'maybe_null': None,
},
},
    {
    'id': 27,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 127,
    'id_str': [
    '07',
    '15',
    '11',
],
    'text_data': '1709cea381234d179a77748b6c41fdf8',
    'rand_digit': 5,
    'rand_number': 0.83921,
    'rand_signed_int': 2,
    'rand_datetime': '2000-01-26T13:47:22+0800',
    'text_array': [
    '7b205e04628b4fee92438484ea47b084',
    '5238062faa944131a8c1f36188c404a8',
],
    'words': 'wolf cheetah',
    'nested': {
    'id': 127,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'kangaroo',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'ape',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'koala',
    'squid',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'snail',
    'maybe_null': 'hippo',
},
},
    {
    'id': 28,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 128,
    'id_str': [
],
    'text_data': '9a7690aa0f254b4d8ed72408ac8989f2',
    'rand_digit': 6,
    'rand_number': 0.29736,
    'rand_signed_int': -8,
    'rand_datetime': '2000-04-24',
    'text_array': [
    'be88ba2c9240402f83bc68db051d4501',
    '2d6b1ccf5a704a6ca45513b4e58fa4cd',
],
    'words': 'giraffe mosquito',
    'nested': {
    'id': 128,
    'rand_digit': 0,
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
    'word': 'lobster',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'ladybug',
    'snail',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': [
    17,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'bee',
    'maybe_null': None,
},
},
    {
    'id': 29,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 129,
    'id_str': [
    '14',
],
    'text_data': '4f1484a80a654da283213fd5655027b6',
    'rand_digit': 7,
    'rand_number': 0.13128,
    'rand_signed_int': -2,
    'rand_datetime': '2000-11-16 18:36:45-0300',
    'text_array': [
    '86295ca1d9fe4be3804e8630166861a0',
    '411c4e67bce942c69ae3d9cfd75e3419',
],
    'words': 'cheetah spider',
    'nested': {
    'id': 129,
    'rand_digit': 4,
    'array': [
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
    'number': 1,
},
    {
    'nested_empty': None,
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
    'word': 'scorpion',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'cheetah',
    'lion',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
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
    'id': 30,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 130,
    'id_str': [
    '02',
    '07',
    '26',
    '14',
    '19',
],
    'text_data': '2e677ed80c8a4692b5500e57dcfaa69f',
    'rand_digit': 6,
    'rand_number': 0.6517,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-11 12:11:31+0200',
    'text_array': [
    'e23cd3a4a0994996a07498e526a28dd3',
    'dc9445b6e135426bba42724578e4e7b4',
],
    'words': 'gorilla sheep',
    'nested': {
    'id': 130,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'bee',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'wolf',
    'kangaroo',
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
    'mixed_type': 0.4876,
    'maybe_null': None,
},
},
    {
    'id': 31,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 131,
    'id_str': [
],
    'text_data': '32c66c5dea8f4668b5b64fc152efba4b',
    'rand_digit': 8,
    'rand_number': 0.77535,
    'rand_signed_int': 10,
    'rand_datetime': '2000-08-21 00:44:23.835503-1100',
    'text_array': [
    '0a997658780e421fa677bfa6719af202',
    'feb261f338884041891048654710509f',
],
    'words': 'dog hyena',
    'nested': {
    'id': 131,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'cheetah',
    'whale',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': [
    4,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'shark',
    'maybe_null': 'gorilla',
},
},
    {
    'id': 32,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 132,
    'id_str': [
    '25',
    '12',
],
    'text_data': 'bf172341cb4d47e08aa01b417c4f417e',
    'rand_digit': 9,
    'rand_number': 0.69282,
    'rand_signed_int': -2,
    'rand_datetime': '2000-10-24T05:26:00.397011+1200',
    'text_array': [
    'd1e574c5eb5b42d6906c44f7deaca19b',
    '7aa6718cf625442ca6244a19a7362b7c',
],
    'words': 'cat fox',
    'nested': {
    'id': 132,
    'rand_digit': 6,
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
    'word': 'turtle',
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    5,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'grasshopper',
    'rabbit',
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
    'mixed_type': 0.75441,
    'maybe': 'crab',
    'maybe_null': None,
},
},
    {
    'id': 33,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 133,
    'id_str': [
],
    'text_data': '64548335126e4a4691aac5d3b550cec2',
    'rand_digit': 6,
    'rand_number': 0.72704,
    'rand_signed_int': -1,
    'rand_datetime': '2000-11-18 22:57',
    'text_array': [
    'b6e3f0e5ce3141a9ab347464af167d81',
    'a49128577d64439e82a36e0aad9c53fa',
],
    'words': 'sheep wolf',
    'nested': {
    'id': 133,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'rabbit',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'whale',
    'bee',
],
    'city': {
    'name': 'Johannesburg',
    'geo': {
    'lat': -26.204103,
    'lon': 28.047305,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'cat',
    'maybe_null': 'lobster',
},
},
    {
    'id': 34,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 134,
    'id_str': [
    '09',
    '15',
    '05',
],
    'text_data': '3455c6b6c1a44e7b80e4a402693b0279',
    'rand_digit': 3,
    'rand_number': 0.79938,
    'rand_signed_int': 6,
    'rand_datetime': '2000-05-27 16:22:01+0900',
    'text_array': [
    '5928a7699a564153ba27ce21d2813c78',
    'b79605c9262d4675b880d649817f652f',
],
    'words': 'snail wolf',
    'nested': {
    'id': 134,
    'rand_digit': 4,
    'array': [
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
    'hello',
],
    'word': 'crab',
    'number': 5,
},
    {
    'nested_empty': None,
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
    'word': 'duck',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    5,
],
],
    'two_words': [
    'goat',
    'snail',
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
    'mixed_type': 'elephant',
    'maybe': 'wolf',
},
},
    {
    'id': 35,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 135,
    'id_str': [
    '03',
    '09',
    '07',
    '05',
],
    'text_data': '66223efb6fa74738afd63312538c0815',
    'rand_digit': 6,
    'rand_number': 0.17177,
    'rand_signed_int': -2,
    'rand_datetime': '2001-01-22 20:40:23',
    'text_array': [
    '945734c26fad40f99732a4d352219648',
    '85ca12de2e5649f198d221b00d5035aa',
],
    'words': 'turtle rhino',
    'nested': {
    'id': 135,
    'rand_digit': 4,
    'array': [
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
    'word': 'grasshopper',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -2,
],
],
    'two_words': [
    'crab',
    'cow',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 'ant',
    'maybe': 'rhino',
},
},
    {
    'id': 36,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 136,
    'id_str': [
],
    'text_data': '43849c7e3e9a42bcbc10bf3ebd027c22',
    'rand_digit': 9,
    'rand_number': 0.93936,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-06 21:57:22.132315+0600',
    'text_array': [
    '63e8fa97acfa466e97e09f89c4634c17',
    '0e6c88d22d0e4978a93e1d26ef1a01f2',
],
    'words': 'mouse sloth',
    'nested': {
    'id': 136,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'deer',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 6,
},
],
},
    'nested_array': [
    [
    5,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'wolf',
    'chicken',
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
},
},
    {
    'id': 37,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 137,
    'id_str': [
],
    'text_data': '1dd8fbcf0ce1453d86d3b94a6c1a66c4',
    'rand_digit': 9,
    'rand_number': 0.63064,
    'rand_signed_int': 10,
    'rand_datetime': '2000-09-18T16:09:38.194716-08:00',
    'text_array': [
    'e78b2472e2bf44c88961474d238a617f',
    '399e753442824d49850941d41496a70d',
],
    'words': 'bird fox',
    'nested': {
    'id': 137,
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
    'number': 5,
},
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
    'word': 'giraffe',
    'number': 4,
},
],
},
    'nested_array': [
    [
    -1,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    5,
],
    [
    -9,
],
],
    'two_words': [
    'whale',
    'kangaroo',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 8,
},
},
    {
    'id': 38,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 138,
    'id_str': [
    '12',
    '30',
    '27',
],
    'text_data': '5b74c40640e54a39a4c0b37cc48fc03f',
    'rand_digit': 2,
    'rand_number': 0.93145,
    'rand_signed_int': 8,
    'rand_datetime': '2000-05-27T11:01:54',
    'text_array': [
    '961cb14475a14cfb99637adeaf63636c',
    'aba313215eae45629a47ff2bc08e1845',
],
    'words': 'rabbit spider',
    'nested': {
    'id': 138,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
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
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    6,
],
],
    'two_words': [
    'pig',
    'pig',
],
    'city': {
    'name': 'Seoul',
    'geo': {
    'lat': 37.566535,
    'lon': 126.977969,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
},
},
    {
    'id': 39,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 139,
    'id_str': [
],
    'text_data': 'e661b758fe5b4c0da05af67848c2e8c9',
    'rand_digit': 2,
    'rand_number': 0.69874,
    'rand_signed_int': -8,
    'rand_datetime': '2000-07-12 17:51:55+0200',
    'text_array': [
    'b704da9e75674440b93de381709d99ea',
    'f6b111e537ae450790385cc03c2ace65',
],
    'words': 'butterfly bear',
    'nested': {
    'id': 139,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    10,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'hyena',
    'rhino',
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
    'maybe_null': 'mouse',
},
},
    {
    'id': 40,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 140,
    'id_str': [
    '07',
],
    'text_data': '3806cd30dbfb4ab9a9287fb9cc8e3d0f',
    'rand_digit': 5,
    'rand_number': 0.65654,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-26T01:02:32.467713',
    'text_array': [
    'd9b89eac92b843d488b5a60ecaf2e944',
    '485e7aec83504cf1b088abff6f057acd',
],
    'words': 'fish cheetah',
    'nested': {
    'id': 140,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 6,
},
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
    'hello',
],
    'word': 'bee',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 6,
},
    {
    'nested_empty': None,
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
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'tiger',
    'rabbit',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 6,
    'maybe': 'dragonfly',
    'maybe_null': 'elephant',
},
},
    {
    'id': 41,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 141,
    'id_str': [
    '07',
    '29',
    '11',
    '24',
],
    'text_data': '7e9bd3ef389c466190377fb2253b8669',
    'rand_digit': 6,
    'rand_number': 0.17802,
    'rand_signed_int': 0,
    'rand_datetime': '2000-04-20 17:50:28.285825',
    'text_array': [
    '97f5138cbfe042a18033fb19e28291bd',
    '5660e6a7f3494105a9669452a0daa185',
],
    'words': 'gorilla fox',
    'nested': {
    'id': 141,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'squid',
    'grasshopper',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.70263,
    'maybe': 'mouse',
},
},
    {
    'id': 42,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 142,
    'id_str': [
    '21',
],
    'text_data': '40a915a7d8714474a643b99992dac110',
    'rand_digit': 1,
    'rand_number': 0.27926,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-08T09:29:31.270997',
    'text_array': [
    '896e8a55203c4c2fa4564bf7f3705fb1',
    '319699eb272d4f62825e61c0f25deeff',
],
    'words': 'pig snake',
    'nested': {
    'id': 142,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'goat',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'ladybug',
    'number': 9,
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
    [
    -10,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dog',
    'shark',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 5,
    'maybe_null': 'octopus',
},
},
    {
    'id': 43,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 143,
    'id_str': [
    '05',
    '06',
    '18',
    '14',
],
    'text_data': '3f6fbf07c4eb4be596ef6bed4623bc62',
    'rand_digit': 0,
    'rand_number': 0.92901,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-13 19:17:10',
    'text_array': [
    'a25d25a1d21843c9b52516bc45b7b2cb',
    '928fd63ca44a434d9d79aa4621d27d1f',
],
    'words': 'scorpion cheetah',
    'nested': {
    'id': 143,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 2,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'butterfly',
    'giraffe',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
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
    'id': 44,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 144,
    'id_str': [
    '09',
],
    'text_data': '9d3b1924ff304db8ab614b262df32f2a',
    'rand_digit': 2,
    'rand_number': 0.2885,
    'rand_signed_int': -2,
    'rand_datetime': '2000-11-06T13:01:57.426574-12:00',
    'text_array': [
    '4704991b02f44a519c0440b0b3771bdf',
    'cd164d0ace264fd79b15285c094471bf',
],
    'words': 'camel squid',
    'nested': {
    'id': 144,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'fly',
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
    'hello',
],
    'word': 'hyena',
    'number': 3,
},
],
},
    'nested_array': [
    [
    6,
],
    [
    1,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'grasshopper',
    'sloth',
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
    'mixed_type': 0.85382,
    'maybe_null': None,
},
},
    {
    'id': 45,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 145,
    'id_str': [
    '27',
    '14',
    '29',
    '16',
    '16',
],
    'text_data': '97d36d5fd9224253b31beb495b3d20dd',
    'rand_digit': 2,
    'rand_number': 0.15062,
    'rand_signed_int': 5,
    'rand_datetime': '2000-08-12 18:01:54+1200',
    'text_array': [
    '5c0924ddf9404907829ccf59d0003600',
    '8a5b5d3fc3f4477d8161e82f661b2bba',
],
    'words': 'monkey mosquito',
    'nested': {
    'id': 145,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 8,
},
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'giraffe',
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
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'dragonfly',
},
},
    {
    'id': 46,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 146,
    'id_str': [
    '05',
    '17',
],
    'text_data': '84b44cb0200642e1a566143bb3a6cfaf',
    'rand_digit': 7,
    'rand_number': 0.58574,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-21T11:38:40.808123-0700',
    'text_array': [
    '9881d3eee1104df480e21d98af82782d',
    '885ab82ef6d5414ba2dfbff33861337e',
],
    'words': 'shark sloth',
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
    'word': 'dolphin',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 2,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'ape',
    'koala',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'frog',
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 47,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 147,
    'id_str': [
],
    'text_data': '3ebeef78a304483f8407a6f5296f8b8f',
    'rand_digit': 5,
    'rand_number': 0.12131,
    'rand_signed_int': -3,
    'rand_datetime': '2000-12-14 08:53:42.885162-1200',
    'text_array': [
    '2c8f914e2ba14a8da3c1be62083f4f18',
    '786fd6e901b843c5bd0643be31651e21',
],
    'words': 'frog rhino',
    'nested': {
    'id': 147,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'pig',
    'scorpion',
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
    'mixed_type': False,
    'maybe': 'dog',
    'maybe_null': None,
},
},
    {
    'id': 48,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 148,
    'id_str': [
    '21',
],
    'text_data': '5d8f7655791e43b08409488797194fab',
    'rand_digit': 4,
    'rand_number': 0.72702,
    'rand_signed_int': 9,
    'rand_datetime': '2000-10-22T18:58:06.484083',
    'text_array': [
    '9626023b85db4c27b1f8468de7ddd7e0',
    '7d8c86f0d2804a6aaa03a72838c2bcf1',
],
    'words': 'dragonfly crab',
    'nested': {
    'id': 148,
    'rand_digit': 5,
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
    'word': 'octopus',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'koala',
    'cow',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'squid',
    'maybe_null': 'snail',
},
},
    {
    'id': 49,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 149,
    'id_str': [
    '26',
],
    'text_data': '258d13e0ac68410b82b1fe705dc974ef',
    'rand_digit': 1,
    'rand_number': 0.21956,
    'rand_signed_int': 8,
    'rand_datetime': '2000-04-15T06:19:19-0600',
    'text_array': [
    '562a26227dd1403c98113133a5f09267',
    '4039b5c15cc34f35af53154f50006230',
],
    'words': 'ape horse',
    'nested': {
    'id': 149,
    'rand_digit': 9,
    'array': [
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
    'hello',
],
    'word': 'zebra',
    'number': 8,
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
    'kangaroo',
    'mosquito',
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
    'mixed_type': 'mosquito',
},
},
    {
    'id': 50,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 150,
    'id_str': [
],
    'text_data': '128b42275f4044aaa3b7b853daf733e3',
    'rand_digit': 0,
    'rand_number': 0.35489,
    'rand_signed_int': -10,
    'rand_datetime': '2000-10-18 19:31:15.314142',
    'text_array': [
    '4362d7106aa44d1ca8862ba08b5d16d5',
    '202d2e65daef412e9a6310ac60fbc30a',
],
    'words': 'duck grasshopper',
    'nested': {
    'id': 150,
    'rand_digit': 1,
    'array': [
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
    'hello',
],
    'word': 'koala',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 4,
},
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
    'hello',
],
    'word': 'crab',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -9,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -4,
],
],
    'two_words': [
    'jaguar',
    'elephant',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
},
},
    'rand_tuple': [
    0,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'gorilla',
    'maybe_null': 'jaguar',
},
},
    {
    'id': 51,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 151,
    'id_str': [
    '28',
],
    'text_data': 'b2b56fd10f22474892aff31542e7b3ad',
    'rand_digit': 0,
    'rand_number': 0.83314,
    'rand_signed_int': 2,
    'rand_datetime': '2000-10-31T05:00:53+0000',
    'text_array': [
    '7cc707806ce14533b2f1b6f6a9559a2c',
    '22349169456b454395274c0d0bf9620e',
],
    'words': 'zebra spider',
    'nested': {
    'id': 151,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    3,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    0,
],
],
    'two_words': [
    'horse',
    'sheep',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 52,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 152,
    'id_str': [
    '18',
    '19',
],
    'text_data': '794d917208d645739b06eb30ffd4020a',
    'rand_digit': 3,
    'rand_number': 0.87033,
    'rand_signed_int': 7,
    'rand_datetime': '2000-08-22 04:22:53+0200',
    'text_array': [
    '8df0adc28098489f8cc92ff1c801969a',
    '5bec6a43f06643e09fc2d43e11f87368',
],
    'words': 'bee grasshopper',
    'nested': {
    'id': 152,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lion',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
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
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'giraffe',
    'squid',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'mosquito',
    'maybe_null': 'gorilla',
},
},
    {
    'id': 53,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 153,
    'id_str': [
    '20',
    '29',
    '14',
],
    'text_data': 'fbba8497cfb8498b9f5144b141211722',
    'rand_digit': 8,
    'rand_number': 0.0472,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-11T21:54:27.643817+1200',
    'text_array': [
    '476cdfbbf49441649fa5ccd9d9e4b94c',
    '828b52673fc24290a5670a64f13e77ba',
],
    'words': 'scorpion zebra',
    'nested': {
    'id': 153,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snake',
    'number': 8,
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
],
    'word': 'crab',
    'number': 8,
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
    [
],
],
    'two_words': [
    'sheep',
    'spider',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.97177,
    'maybe': 'fish',
    'maybe_null': 'bird',
},
},
    {
    'id': 54,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 154,
    'id_str': [
    '04',
    '13',
    '02',
],
    'text_data': '907cbce3c6144c1a984c6aa67dd38561',
    'rand_digit': 9,
    'rand_number': 0.49633,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-06T01:33:41.695068+10:00',
    'text_array': [
    '513c748e60b448d2ac2c783cecb1c454',
    'aea6035261174ba9847817e0dedc2365',
],
    'words': 'hyena tiger',
    'nested': {
    'id': 154,
    'rand_digit': 9,
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
    'word': 'tiger',
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
    'number': 1,
},
],
},
    'nested_array': [
    [
    -5,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'giraffe',
    'goat',
],
    'city': {
    'name': 'Seoul',
    'geo': {
    'lat': 37.566535,
    'lon': 126.977969,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 3,
    'maybe': 'shark',
    'maybe_null': 'bee',
},
},
    {
    'id': 55,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 155,
    'id_str': [
    '26',
    '09',
    '20',
    '27',
    '09',
],
    'text_data': 'c2724fed800b414b8a7ca6c0af9bc0b8',
    'rand_digit': 4,
    'rand_number': 0.37359,
    'rand_signed_int': 5,
    'rand_datetime': '2000-04-22T00:43:19.855026+0500',
    'text_array': [
    '61a35b0d16984162aadc33a48857e9e9',
    '6a3ea26fec644f8fbf1dd8f35a37694d',
],
    'words': 'cat squid',
    'nested': {
    'id': 155,
    'rand_digit': 7,
    'array': [
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
    'hello',
],
    'word': 'crab',
    'number': 5,
},
    {
    'nested_empty': None,
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
    'word': 'fox',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dog',
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
    'cat',
    'frog',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'rabbit',
},
},
    {
    'id': 56,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 156,
    'id_str': [
    '07',
    '24',
    '27',
],
    'text_data': 'ea575647bcbc46cd99535fd5fa5a17aa',
    'rand_digit': 2,
    'rand_number': 0.87763,
    'rand_signed_int': -1,
    'rand_datetime': '2001-01-09 19:27',
    'text_array': [
    '25593969f0974aef8e6333ce3fdb3404',
    '26a8b2604f074f94a35e56be3c8ee01d',
],
    'words': 'leopard hyena',
    'nested': {
    'id': 156,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'sheep',
    'chicken',
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
    'mixed_type': 9,
    'maybe': 'butterfly',
    'maybe_null': 'squid',
},
},
    {
    'id': 57,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 157,
    'id_str': [
    '09',
    '02',
],
    'text_data': 'cb3d0ef8313e45faae7e9965ec56c9d5',
    'rand_digit': 4,
    'rand_number': 0.90133,
    'rand_signed_int': 8,
    'rand_datetime': '2000-04-22T02:12:02.076228',
    'text_array': [
    '24fcf8269c354c44ad8a47e0d8e31b45',
    'b5afa8d5c7794817b5a9acbd5bb98cab',
],
    'words': 'leopard scorpion',
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
    'word': 'zebra',
    'number': 3,
},
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
    'word': 'horse',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 2,
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
],
},
    'nested_array': [
],
    'two_words': [
    'cow',
    'bee',
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
    'mixed_type': 'fish',
    'maybe_null': None,
},
},
    {
    'id': 58,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 158,
    'id_str': [
    '07',
    '02',
    '05',
    '03',
    '01',
],
    'text_data': '3f05f94a2fa842d4ae459d35410e859c',
    'rand_digit': 9,
    'rand_number': 0.23878,
    'rand_signed_int': -8,
    'rand_datetime': '2000-09-24T06:11:56',
    'text_array': [
    '12ee21f539cf4f048381a89870955049',
    'a8002c4dde9d42988a4c73829e4fb63e',
],
    'words': 'turtle lizard',
    'nested': {
    'id': 158,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
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
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'hippo',
    'fly',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': [
    12,
],
    'rand_bool': False,
    'mixed_type': 4,
    'maybe_null': 'dog',
},
},
    {
    'id': 59,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 159,
    'id_str': [
    '18',
    '06',
    '12',
    '11',
    '17',
],
    'text_data': 'e4a49947bcc14491b0178b3c70eca71e',
    'rand_digit': 6,
    'rand_number': 0.8924,
    'rand_signed_int': 1,
    'rand_datetime': '2000-10-08 20:35:18+0000',
    'text_array': [
    'c47cb912aeeb49499c46c7f66bcdbea8',
    '661be06abe8c479d815deb15cb9e58ae',
],
    'words': 'mouse duck',
    'nested': {
    'id': 159,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 2,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'mouse',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ape',
    'ant',
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
    'maybe': 'bird',
},
},
    {
    'id': 60,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 160,
    'id_str': [
    '09',
    '25',
    '05',
    '04',
],
    'text_data': 'ac11addb824c42658aa55b3244eae528',
    'rand_digit': 6,
    'rand_number': 0.11352,
    'rand_signed_int': 2,
    'rand_datetime': '2000-01-18',
    'text_array': [
    '425dd1d9b92a41088210c77c0cff39d2',
    '95e7f770469b46548eb58074726bf816',
],
    'words': 'dolphin tiger',
    'nested': {
    'id': 160,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 10,
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
],
},
    'nested_array': [
    [
    10,
],
],
    'two_words': [
    'turtle',
    'elephant',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 61,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 161,
    'id_str': [
    '16',
    '09',
    '26',
    '13',
    '04',
],
    'text_data': 'dc2e35e3f29e476a8b36eec43ee67e36',
    'rand_digit': 1,
    'rand_number': 0.78892,
    'rand_signed_int': 2,
    'rand_datetime': '2000-04-23 20:15',
    'text_array': [
    'f8f5eb747ce2462b9522f7200af0ebd5',
    '03c42b8b25894b1ca2565cb700d4c684',
],
    'words': 'scorpion snail',
    'nested': {
    'id': 161,
    'rand_digit': 9,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'panda',
    'spider',
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
    'maybe_null': None,
},
},
    {
    'id': 62,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 162,
    'id_str': [
    '06',
    '29',
    '01',
    '17',
    '21',
],
    'text_data': '86debec40a2d4fa48376d88a218761f7',
    'rand_digit': 7,
    'rand_number': 0.33159,
    'rand_signed_int': 5,
    'rand_datetime': '2000-05-07 13:04',
    'text_array': [
    'a26e65f7fc0a4d2ba4a9ead79df13b93',
    '5ca62376ce7b4268af628c18c5832bce',
],
    'words': 'dragonfly scorpion',
    'nested': {
    'id': 162,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'deer',
    'sloth',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'dog',
},
},
    {
    'id': 63,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 163,
    'id_str': [
    '25',
    '04',
],
    'text_data': 'a857b6a201a54257bd3ae0873121f411',
    'rand_digit': 3,
    'rand_number': 0.4817,
    'rand_signed_int': -2,
    'rand_datetime': '2000-09-28T22:57:22.444804',
    'text_array': [
    'dbc62806359a418793b526aa3032cfd5',
    '7afa471834224e17b35798f6876b9927',
],
    'words': 'rhino jaguar',
    'nested': {
    'id': 163,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 9,
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
    'nested_array': [
],
    'two_words': [
    'camel',
    'rabbit',
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
    'content-length': '124633',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_qdrant_client.test_records_upload')
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
    test = TestQdrantClienttestRecordsUpload()
    test.run_tests()
