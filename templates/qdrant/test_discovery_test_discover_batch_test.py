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
logger = logging.getLogger('vdb_fuzzer.test.test_discovery_test_discover_batch')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_discovery.test_discover_batch"
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



class TestDiscoverytestDiscoverBatch:
    """自动生成的VDB模糊测试类 - test_discovery.test_discover_batch"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_discovery.test_discover_batch"
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
    'content-length': '137113',
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
    '28',
    '02',
],
    'text_data': '68f003ecfa5e46b698a93eff097fc110',
    'rand_digit': 4,
    'rand_number': 0.65113,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-15T20:02:35.697725',
    'text_array': [
    'cf5e4e4b82e9419fbaa8d4c47925784e',
    '5428172ccb27440287fc7ad80e2df57e',
],
    'words': 'monkey rabbit',
    'nested': {
    'id': 100,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 1,
},
    {
    'nested_empty': None,
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
],
    'word': 'panda',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'sheep',
    'bear',
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
    'mixed_type': 0.28144,
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
    '03',
    '02',
    '17',
    '26',
],
    'text_data': '5e3c9f28b33d4a8d9c571f28e2d899e8',
    'rand_digit': 5,
    'rand_number': 0.31374,
    'rand_signed_int': -10,
    'rand_datetime': '2000-02-14T09:36:39.797733',
    'text_array': [
    'd4593fd8200640c8befdb8471992f462',
    '33b0cbd10e6342b0bb55ee3230090e8e',
],
    'words': 'rabbit giraffe',
    'nested': {
    'id': 101,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'leopard',
    'grasshopper',
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
    'maybe_null': 'dolphin',
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
],
    'text_data': '490f4ea8714d4cd896ed3ba76b77e565',
    'rand_digit': 9,
    'rand_number': 0.35956,
    'rand_signed_int': 8,
    'rand_datetime': '2000-05-12T16:15:49.255473',
    'text_array': [
    '2701af42e2934605b60d6f08c226f5a5',
    '64286e43734b41e7aa89e4d62f2c5788',
],
    'words': 'cheetah hyena',
    'nested': {
    'id': 102,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 8,
},
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    [
    0,
],
],
    'two_words': [
    'octopus',
    'lizard',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bee',
    'maybe_null': 'sheep',
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
    '17',
    '17',
    '06',
],
    'text_data': '2976682780b747139954b6b109ee187f',
    'rand_digit': 5,
    'rand_number': 0.47808,
    'rand_signed_int': -10,
    'rand_datetime': '2000-02-09T18:21:49-0400',
    'text_array': [
    '43c41696448d4286a05ca3f74de40133',
    'd1b7ef1adab64a7799218ebe90479400',
],
    'words': 'scorpion sloth',
    'nested': {
    'id': 103,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'sloth',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 1,
},
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
],
},
    'nested_array': [
    [
],
    [
],
],
    'two_words': [
    'gorilla',
    'mosquito',
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
    'mixed_type': 0.26378,
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
    '19',
    '21',
    '04',
    '14',
],
    'text_data': 'c0e8559798e9404e878019941c06e28e',
    'rand_digit': 3,
    'rand_number': 0.26394,
    'rand_signed_int': -8,
    'rand_datetime': '2000-07-01T16:13:45.353258',
    'text_array': [
    'd038cfb134ef4891b269546c0192a521',
    'e372eecd194c44e4810b03048b0d846d',
],
    'words': 'goat grasshopper',
    'nested': {
    'id': 104,
    'rand_digit': 9,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 2,
},
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'dolphin',
    'tiger',
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
    'mixed_type': None,
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
],
    'text_data': 'd064c3b262af4c809308a51021096730',
    'rand_digit': 6,
    'rand_number': 0.58378,
    'rand_signed_int': -5,
    'rand_datetime': '2001-01-03 04:25:14.468810',
    'text_array': [
    '68aacc0ea51c4d42afe1c405dfd681bf',
    'b377e51a87e24c16b411f2f5f1d75208',
],
    'words': 'cheetah dog',
    'nested': {
    'id': 105,
    'rand_digit': 7,
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
],
    'word': 'cat',
    'number': 6,
},
],
},
    'nested_array': [
    [
    -3,
],
],
    'two_words': [
    'scorpion',
    'cat',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': [
    91,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'grasshopper',
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
    '23',
],
    'text_data': 'dace9fb5b4bd44b1a0b54f6f2ed8484e',
    'rand_digit': 1,
    'rand_number': 0.36941,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-24',
    'text_array': [
    'a5d0344be55e4d65985bbbd30da43374',
    '05c781f21a5845788239e136b0a6ead1',
],
    'words': 'leopard crab',
    'nested': {
    'id': 106,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rhino',
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
    'number': 2,
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
    'chicken',
    'camel',
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
    'mixed_type': True,
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
    '08',
    '01',
    '25',
    '10',
    '14',
],
    'text_data': '698a9c11d1ed4ebeb4bb1cfda5665e50',
    'rand_digit': 8,
    'rand_number': 0.82079,
    'rand_signed_int': 1,
    'rand_datetime': '2000-08-17T17:53:21.858682',
    'text_array': [
    'b12e3749edd24c749b1b7bfad7099f2b',
    '4e4eb043e8db437ea320442798b4dc52',
],
    'words': 'zebra crab',
    'nested': {
    'id': 107,
    'rand_digit': 7,
    'array': [
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
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
    'rand_tuple': [
    82,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'hyena',
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
    '19',
    '30',
],
    'text_data': '89bdf59c057c4a95a7b8e7ca279df32c',
    'rand_digit': 1,
    'rand_number': 0.90779,
    'rand_signed_int': -1,
    'rand_datetime': '2000-03-29T03:20:30.899129-0700',
    'text_array': [
    'a2c7a4c4b3484a09b949e3d99155bd49',
    'd9a3e294d87742bd8f93f2bd81f10ff4',
],
    'words': 'butterfly frog',
    'nested': {
    'id': 108,
    'rand_digit': 6,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lion',
    'number': 6,
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
    'koala',
    'shark',
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
    'maybe_null': 'chicken',
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
    '29',
],
    'text_data': 'a8ea253469d14e69b54898ee048aaaa0',
    'rand_digit': 8,
    'rand_number': 0.63116,
    'rand_signed_int': -6,
    'rand_datetime': '2000-03-20T00:39:36.191770+10:00',
    'text_array': [
    '60d1a5ebe7c54b448bac35086556b451',
    'c7ecf1bbe085434f87c6aa56b3524f2f',
],
    'words': 'cow goat',
    'nested': {
    'id': 109,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 2,
},
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
],
    'word': 'duck',
    'number': 10,
},
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
],
},
    'nested_array': [
],
    'two_words': [
    'cow',
    'cow',
],
    'city': {
    'name': 'Cardiff',
    'geo': {
    'lat': 51.481581,
    'lon': -3.17909,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 9,
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
    '24',
],
    'text_data': '4846e7de5faa416fabcc026888838353',
    'rand_digit': 6,
    'rand_number': 0.93036,
    'rand_signed_int': -6,
    'rand_datetime': '2001-01-13 19:11:14.136162',
    'text_array': [
    '55cc3d558c7c4e2aa58f57a88b8fd3f3',
    '1d5642a5eaf747f3b2b8d07c4d136c3d',
],
    'words': 'fox fish',
    'nested': {
    'id': 110,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'dog',
    'number': 6,
},
    {
    'nested_empty': None,
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
],
    'word': 'wolf',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cat',
    'bird',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'lizard',
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
    '10',
],
    'text_data': '3c1575a570d04243967732ba5b55e2c8',
    'rand_digit': 0,
    'rand_number': 0.04145,
    'rand_signed_int': -5,
    'rand_datetime': '2000-12-20',
    'text_array': [
    'a6451359b2b5478183b251cfa01c823a',
    'ce96929470604407b838ba4e8f519a40',
],
    'words': 'fox sheep',
    'nested': {
    'id': 111,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
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
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bee',
    'gorilla',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'whale',
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
    '22',
    '01',
],
    'text_data': '5f72856d82a1451fba6c11c269ea083a',
    'rand_digit': 4,
    'rand_number': 0.27502,
    'rand_signed_int': -9,
    'rand_datetime': '2000-06-25T13:18:16',
    'text_array': [
    'a7dc20d17ecf4c8993b3f5a34883bda8',
    '4804a64b1d8a4494bfb44638dee45b70',
],
    'words': 'kangaroo panda',
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
    'word': 'dolphin',
    'number': 4,
},
    {
    'nested_empty': None,
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
    'word': 'horse',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -5,
],
],
    'two_words': [
    'dolphin',
    'octopus',
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
    'mixed_type': 0.08547,
    'maybe_null': 'kangaroo',
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
    '12',
    '23',
    '10',
],
    'text_data': '6f26e9278c94403c891bea1ec3b09dfb',
    'rand_digit': 4,
    'rand_number': 0.88921,
    'rand_signed_int': 9,
    'rand_datetime': '2000-01-22T10:26:20.890064-04:00',
    'text_array': [
    'dd02ed9d9da44fdab584a5499258a5c2',
    '38501f162554467a8f75b57e9bee3952',
],
    'words': 'leopard spider',
    'nested': {
    'id': 113,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'gorilla',
    'sloth',
],
    'city': {
    'name': 'London',
    'geo': {
    'lat': 51.507351,
    'lon': -0.127758,
},
},
    'rand_tuple': [
    20,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'ape',
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
    'text_data': 'e1fc7b01d2544aad89887ce8a9258b96',
    'rand_digit': 1,
    'rand_number': 0.36938,
    'rand_signed_int': 8,
    'rand_datetime': '2000-12-21T07:22:11.652325',
    'text_array': [
    '0803e3260f1347faa3805201f6f22c95',
    'f52d313a729045f68989983362250a1a',
],
    'words': 'kangaroo cow',
    'nested': {
    'id': 114,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snail',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 2,
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
    'fox',
    'bear',
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
    'mixed_type': 'dog',
    'maybe': 'cow',
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
    '03',
],
    'text_data': '148eef61d2de4d608a863cb552737521',
    'rand_digit': 8,
    'rand_number': 0.9729,
    'rand_signed_int': 10,
    'rand_datetime': '2000-08-12T12:42:21-1100',
    'text_array': [
    'd8e5b7e5db984375b1c58807ce90a988',
    'a78f613736a94b6db3e3797eb1f7a0bc',
],
    'words': 'koala cat',
    'nested': {
    'id': 115,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'wolf',
    'lobster',
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
    'mixed_type': 'cow',
    'maybe': 'snake',
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
    '01',
    '26',
],
    'text_data': '11b80d11f3b8437fa78a0c7cd9c78511',
    'rand_digit': 2,
    'rand_number': 0.96107,
    'rand_signed_int': -9,
    'rand_datetime': '2000-11-29T23:42:57',
    'text_array': [
    '4d2e7316ae29435cbab16effb3dfb5aa',
    'aabefde86e244a528ad5e8464c0f4554',
],
    'words': 'zebra panda',
    'nested': {
    'id': 116,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
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
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -2,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ant',
    'fox',
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
    'mixed_type': 'hippo',
    'maybe': 'bee',
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
    '13',
    '22',
    '26',
    '04',
    '02',
],
    'text_data': 'ac97f2c9e595410abaa2397384286400',
    'rand_digit': 7,
    'rand_number': 0.46311,
    'rand_signed_int': 3,
    'rand_datetime': '2000-02-09T11:31:53.487868',
    'text_array': [
    '07cb0e40388448038a521a2923bd7852',
    '732fdcf12ef74937aa4ba3d6002d324c',
],
    'words': 'monkey panda',
    'nested': {
    'id': 117,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 8,
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
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'monkey',
    'cow',
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
    'mixed_type': 0.26872,
    'maybe': 'hyena',
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
    '22',
    '14',
    '09',
    '19',
],
    'text_data': 'b1f3796a238a488eb7872a3c76b0b055',
    'rand_digit': 0,
    'rand_number': 0.20818,
    'rand_signed_int': 1,
    'rand_datetime': '2001-01-12T19:51:15.789033-03:00',
    'text_array': [
    'da81d172a235499a816ab4d69b0c1153',
    '3b5bc0be02114a4eba95028a22dd7eb7',
],
    'words': 'cow hippo',
    'nested': {
    'id': 118,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dragonfly',
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
],
},
    'nested_array': [
    [
    1,
],
],
    'two_words': [
    'ladybug',
    'gorilla',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '11',
    '28',
    '16',
    '21',
    '20',
],
    'text_data': '20443979eeb941ff86888fa1dd0b8c0e',
    'rand_digit': 3,
    'rand_number': 0.79116,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-26 20:01:10',
    'text_array': [
    '06bedf129e444ae8813448bd369fcad4',
    '18a3eb2081b143a3bf406815bdc8c7b6',
],
    'words': 'duck gorilla',
    'nested': {
    'id': 119,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'leopard',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ape',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 5,
},
],
},
    'nested_array': [
    [
    3,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dragonfly',
    'cat',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '22',
    '19',
],
    'text_data': 'b2ac2e894d2b429b8ad20ccebb828811',
    'rand_digit': 6,
    'rand_number': 0.00162,
    'rand_signed_int': 8,
    'rand_datetime': '2000-12-19 14:40:09.231191',
    'text_array': [
    '6f2272d8297b418bbfe9a5e9bd2fe5ff',
    '07260c4381a347468be47e0fa427cab9',
],
    'words': 'lion fox',
    'nested': {
    'id': 120,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 5,
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
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'goat',
    'mouse',
],
    'city': {
    'name': 'Athens',
    'geo': {
    'lat': 37.98381,
    'lon': 23.727539,
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
    'id': 21,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 121,
    'id_str': [
    '28',
    '06',
    '05',
    '07',
],
    'text_data': '9920956849c84783b2f462b9f6883761',
    'rand_digit': 9,
    'rand_number': 0.65357,
    'rand_signed_int': -7,
    'rand_datetime': '2000-10-29T00:39:27.358807+06:00',
    'text_array': [
    '75efe17b5dc343f29a6118823400382f',
    '64332163324447ceb889b306a389898f',
],
    'words': 'butterfly ape',
    'nested': {
    'id': 121,
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
    'number': 2,
},
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 7,
},
    {
    'nested_empty': None,
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
    'word': 'fish',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'elephant',
    'elephant',
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
    'mixed_type': 1,
    'maybe_null': 'mouse',
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
    '28',
    '24',
    '06',
    '18',
    '14',
],
    'text_data': '0c91e44dd7a24e8aadbc31ebf1f89176',
    'rand_digit': 1,
    'rand_number': 0.08443,
    'rand_signed_int': -7,
    'rand_datetime': '2000-06-08T01:54:56.892518+0700',
    'text_array': [
    'f882369bd80549d7886a8419b1b25c5e',
    'fc0adb9325544faf91e3c38b41517260',
],
    'words': 'dragonfly camel',
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
    'word': 'frog',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'horse',
    'dolphin',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'dog',
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
    '01',
    '21',
],
    'text_data': 'd2e8da4a7c3e421fb60ebae08b07fa9f',
    'rand_digit': 0,
    'rand_number': 0.17471,
    'rand_signed_int': 0,
    'rand_datetime': '2000-10-07 06:11:33-0600',
    'text_array': [
    'b935e648254b46899bc67f0f0a7b691f',
    'aaade4660a3d469dbe4f29414a5bad85',
],
    'words': 'rabbit cat',
    'nested': {
    'id': 123,
    'rand_digit': 5,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 4,
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
    'word': 'panda',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -6,
],
    [
    -2,
],
],
    'two_words': [
    'snake',
    'lion',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'lobster',
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
    '30',
    '18',
],
    'text_data': '5892b22289a847ac88aa73be59465f11',
    'rand_digit': 9,
    'rand_number': 0.17076,
    'rand_signed_int': 4,
    'rand_datetime': '2000-12-29T16:12:51+0600',
    'text_array': [
    'd84a0dadfe194e069fc57822779a94ef',
    '3eaecdb1dca84c7fb6335536e91982f6',
],
    'words': 'goat dragonfly',
    'nested': {
    'id': 124,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 8,
},
],
},
    'nested_array': [
    [
    -7,
],
],
    'two_words': [
    'fox',
    'shark',
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
    'mixed_type': 0.65122,
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
    'text_data': 'ea963cc7ff5b4241be58c17ec8f99504',
    'rand_digit': 1,
    'rand_number': 0.44631,
    'rand_signed_int': 1,
    'rand_datetime': '2000-12-29T18:37:14.464099+0000',
    'text_array': [
    '98d8e4890fc34c70b6103acf21e53493',
    '076a7f8ca7ee40c5b221636e34412f08',
],
    'words': 'goat squid',
    'nested': {
    'id': 125,
    'rand_digit': 3,
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
    'word': 'ladybug',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'jaguar',
    'number': 5,
},
],
},
    'nested_array': [
    [
    -10,
],
    [
],
],
    'two_words': [
    'sheep',
    'snake',
],
    'city': {
    'name': 'Johannesburg',
    'geo': {
    'lat': -26.204103,
    'lon': 28.047305,
},
},
    'rand_tuple': [
    79,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '28',
    '17',
    '16',
],
    'text_data': 'd451541f46cf45298c23c70d48ab456b',
    'rand_digit': 5,
    'rand_number': 0.50847,
    'rand_signed_int': 9,
    'rand_datetime': '2001-01-06T21:58:13',
    'text_array': [
    'a1d4231dc1c445faa1b38a9fb664c73f',
    '305a0e5cd92d42b8b6cd16e400bafe28',
],
    'words': 'spider mouse',
    'nested': {
    'id': 126,
    'rand_digit': 6,
    'array': [
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
],
    'word': 'shark',
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
    'number': 9,
},
],
},
    'nested_array': [
    [
    -3,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'bird',
    'hippo',
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
    'mixed_type': False,
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
    '29',
    '25',
    '14',
    '15',
],
    'text_data': '6ca2bce684ef459785a9cb69b327d424',
    'rand_digit': 8,
    'rand_number': 0.03225,
    'rand_signed_int': -2,
    'rand_datetime': '2000-12-15 09:34:53.715085',
    'text_array': [
    '6c2069a564b442aa9bf8fc79d41cb514',
    'f6c8dfdfcd114ccca220fb6d23bb676f',
],
    'words': 'goat octopus',
    'nested': {
    'id': 127,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'deer',
    'bear',
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
    'mixed_type': 1,
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
    '24',
],
    'text_data': '4b5b9ece24d74296941e782a3e1356da',
    'rand_digit': 7,
    'rand_number': 0.88365,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-06',
    'text_array': [
    '5bb8612ad1054253bda2f27e7f234287',
    '4dc87188c37f49009da0a174017a07f5',
],
    'words': 'tiger sloth',
    'nested': {
    'id': 128,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'snake',
    'wolf',
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
    'mixed_type': None,
    'maybe_null': 'zebra',
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
    '16',
    '23',
    '20',
    '20',
    '06',
],
    'text_data': '1de48db640aa4a30aaf7190208245bbc',
    'rand_digit': 9,
    'rand_number': 0.98659,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-19 11:12:36+0800',
    'text_array': [
    'fbae3dd17dc94266916ad416ea05a23f',
    '7229e23200064fd5b27b7a92997f2a73',
],
    'words': 'fly cow',
    'nested': {
    'id': 129,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'crab',
    'number': 9,
},
],
},
    'nested_array': [
    [
    -5,
],
],
    'two_words': [
    'giraffe',
    'dragonfly',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'butterfly',
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
    '14',
    '14',
    '29',
],
    'text_data': 'f055d2dcf4eb4605adb27cefde5e6252',
    'rand_digit': 1,
    'rand_number': 0.97957,
    'rand_signed_int': 5,
    'rand_datetime': '2000-05-21T00:58:17+0100',
    'text_array': [
    'cfec684d6d5d4ca6b2f4054456dbfdd4',
    '1f331e2e359d447a85441ec99d194df7',
],
    'words': 'mosquito fly',
    'nested': {
    'id': 130,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 1,
},
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
    'word': 'leopard',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'ladybug',
    'rhino',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '27',
    '24',
    '14',
],
    'text_data': '05d291ab94e34509b45f7cf1c14adbe4',
    'rand_digit': 1,
    'rand_number': 0.56741,
    'rand_signed_int': 6,
    'rand_datetime': '2000-10-13 18:10:12+1100',
    'text_array': [
    '242b35d13f0245599f59d301fc281da7',
    '92dcaea7f0c54e32a88fbc83dab8d1e0',
],
    'words': 'duck jaguar',
    'nested': {
    'id': 131,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'pig',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -10,
],
],
    'two_words': [
    'bear',
    'bird',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'butterfly',
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
    'text_data': 'c2ba5e7e7bab4418a5e645dda4dd0656',
    'rand_digit': 2,
    'rand_number': 0.29143,
    'rand_signed_int': 5,
    'rand_datetime': '2000-04-12T07:29:06.862200',
    'text_array': [
    'e2d3e56f7fe94773b6128d8a95d1621f',
    'a4774d6f3a7542dd90a1f28e6c891d2b',
],
    'words': 'fox ape',
    'nested': {
    'id': 132,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'camel',
    'hippo',
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
    'maybe_null': 'camel',
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
],
    'text_data': '3c1c0f86fe684b259b9ea864af208132',
    'rand_digit': 0,
    'rand_number': 0.82957,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-29T02:58:56.146438+0300',
    'text_array': [
    'd695fb20d2544ea98fc083a901c9580f',
    '9a051402b4cc464390cf42477ef8e4fb',
],
    'words': 'snail wolf',
    'nested': {
    'id': 133,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 5,
},
    {
    'nested_empty': None,
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
    'word': 'horse',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'duck',
    'fox',
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
    'maybe': 'grasshopper',
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
    '30',
    '18',
],
    'text_data': '243ac36adf9242c181b5964d7c620337',
    'rand_digit': 3,
    'rand_number': 0.2586,
    'rand_signed_int': -10,
    'rand_datetime': '2000-04-25 19:48:31',
    'text_array': [
    '4b8776b899f24a0ebf3491476e8eda5a',
    'a3f87c3675b94b64a46e0a4f7842b79c',
],
    'words': 'snail deer',
    'nested': {
    'id': 134,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'scorpion',
    'butterfly',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
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
    '28',
    '09',
    '25',
    '16',
    '30',
],
    'text_data': 'c022a47fcb5e47c49095d50d4a2c9865',
    'rand_digit': 5,
    'rand_number': 0.49886,
    'rand_signed_int': 0,
    'rand_datetime': '2000-05-13T06:43:11.652488+0200',
    'text_array': [
    'f17f1fd88e854a578d95eab8167fa05c',
    '50f68082958b4eb881ce48b7875be227',
],
    'words': 'mouse tiger',
    'nested': {
    'id': 135,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
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
    'dolphin',
    'shark',
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
    'mixed_type': True,
    'maybe': 'leopard',
    'maybe_null': 'fox',
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
],
    'text_data': '4dcd2da6db624c3caf63f784aaa46791',
    'rand_digit': 2,
    'rand_number': 0.47801,
    'rand_signed_int': -6,
    'rand_datetime': '2000-08-23 10:56:58',
    'text_array': [
    'e5bd1e3e46394b90b7604dd0f719dfc1',
    '49d439a1b8824f27af394c435e66a34d',
],
    'words': 'dolphin shark',
    'nested': {
    'id': 136,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -10,
],
],
    'two_words': [
    'camel',
    'panda',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': [
    1,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'gorilla',
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
    '17',
    '21',
],
    'text_data': '3e33f58c8a9b4904ba27bd3ea38691bc',
    'rand_digit': 6,
    'rand_number': 0.41226,
    'rand_signed_int': -4,
    'rand_datetime': '2000-02-18T18:39:02.684309-0700',
    'text_array': [
    '81f109fb50f8435284513df99f4fb8f5',
    '1591fed869e84343a4c20b1b91689b96',
],
    'words': 'hyena sloth',
    'nested': {
    'id': 137,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'bird',
    'grasshopper',
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
    'mixed_type': True,
    'maybe': 'tiger',
    'maybe_null': 'mouse',
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
    '13',
    '23',
],
    'text_data': '85cef7360df341eca9458eae1d9aa76a',
    'rand_digit': 0,
    'rand_number': 0.75769,
    'rand_signed_int': -5,
    'rand_datetime': '2000-02-09 17:30:42',
    'text_array': [
    '43dbbc9205ad455d9e82e21065c2307f',
    'a666ba87eea347b1af7a8d6f4f5c2fd9',
],
    'words': 'lion hyena',
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
    'word': 'sheep',
    'number': 2,
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
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'butterfly',
    'cheetah',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '16',
    '17',
    '29',
    '16',
],
    'text_data': 'e052d7bfcbea4ec48cb2bbadf2460d70',
    'rand_digit': 1,
    'rand_number': 0.6669,
    'rand_signed_int': -1,
    'rand_datetime': '2001-01-24T22:54:57.705470',
    'text_array': [
    '30109711f0ca457eba8ccc7691899ac2',
    'b09bb5eca3854ff9bda9ac147006f100',
],
    'words': 'cheetah camel',
    'nested': {
    'id': 139,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 5,
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
    'word': 'fox',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'shark',
    'octopus',
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
    'mixed_type': 7,
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
    '18',
    '23',
    '04',
    '02',
],
    'text_data': '69be8b2db21e45fb852a6407dc76956c',
    'rand_digit': 9,
    'rand_number': 0.00608,
    'rand_signed_int': 3,
    'rand_datetime': '2000-01-05 16:25:16-0200',
    'text_array': [
    '058000b8ff2c42cab173c27800898df8',
    'dad98329897848b9896ff0e144f93830',
],
    'words': 'lobster wolf',
    'nested': {
    'id': 140,
    'rand_digit': 6,
    'array': [
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
    'hello',
],
    'word': 'dragonfly',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ladybug',
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
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'horse',
    'mouse',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.96776,
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
    '24',
],
    'text_data': 'b0a8d2e1b89a4664a16cc7e215f65cc6',
    'rand_digit': 0,
    'rand_number': 0.72101,
    'rand_signed_int': -9,
    'rand_datetime': '2000-04-18 16:37:38.955292-0600',
    'text_array': [
    'b249525b860646c2b66f5c59647d6f99',
    'a1db84e0212448efab617d2539820d6a',
],
    'words': 'fish wolf',
    'nested': {
    'id': 141,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'hyena',
    'cat',
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
    'mixed_type': 4,
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
    '15',
    '19',
],
    'text_data': '89d6dbb511504b488d6dcdbdf4e8527d',
    'rand_digit': 2,
    'rand_number': 0.20748,
    'rand_signed_int': -5,
    'rand_datetime': '2000-06-29T05:56:23.374902+03:00',
    'text_array': [
    '778b1c9eb90644e090623bfb9ec84aed',
    '690dbb66142641b797dff48693748fc9',
],
    'words': 'dog scorpion',
    'nested': {
    'id': 142,
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
    'word': 'frog',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dragonfly',
    'snail',
],
    'city': {
    'name': 'Dubai',
    'geo': {
    'lat': 25.204849,
    'lon': 55.270783,
},
},
    'rand_tuple': [
    79,
],
    'rand_bool': False,
    'mixed_type': False,
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
    '08',
    '09',
    '20',
],
    'text_data': 'e3edc4114e214b929226dc247808302b',
    'rand_digit': 8,
    'rand_number': 0.00043,
    'rand_signed_int': -3,
    'rand_datetime': '2000-12-24 00:20:02',
    'text_array': [
    'f7e1273dce0843b6b54944e786328a43',
    '35efaf11108543d38d931032b910d15d',
],
    'words': 'bear dragonfly',
    'nested': {
    'id': 143,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    5,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'octopus',
    'sheep',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': [
    88,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'ladybug',
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
    'text_data': '0d75c87137814b7a8030a492c529eed3',
    'rand_digit': 3,
    'rand_number': 0.18396,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-10 10:15:59.689360',
    'text_array': [
    '5bddf4ff5ff64a9f84f32fc04ac15434',
    'b697a2a7ab7740cfba4d5ba9fb86b600',
],
    'words': 'panda shark',
    'nested': {
    'id': 144,
    'rand_digit': 0,
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
    'word': 'tiger',
    'number': 6,
},
],
},
    'nested_array': [
    [
    6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'zebra',
    'cheetah',
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
    'maybe': 'bee',
    'maybe_null': 'ant',
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
    '04',
    '09',
    '03',
],
    'text_data': 'd5f6502729494136a7c1e857032c5553',
    'rand_digit': 3,
    'rand_number': 0.3091,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-25T18:53:02.143689',
    'text_array': [
    'a6f772e42f584847b08bed32f1f47177',
    'af67b134dc9a457195f21b0f4eb1a2e9',
],
    'words': 'leopard sloth',
    'nested': {
    'id': 145,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'mosquito',
    'ape',
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
    'mixed_type': 0.66346,
    'maybe': 'dolphin',
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
    '21',
],
    'text_data': '72a66c1aa0284b15931b0cd9a4ba4f17',
    'rand_digit': 1,
    'rand_number': 0.71805,
    'rand_signed_int': 9,
    'rand_datetime': '2000-02-12T08:31:46.879271',
    'text_array': [
    '2a566303d0ce4a7286eb7e6e1dd803dd',
    '745091f3eef94c7aa6777a635d20c254',
],
    'words': 'ladybug hyena',
    'nested': {
    'id': 146,
    'rand_digit': 4,
    'array': [
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
    'word': 'camel',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cat',
    'cat',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': [
    74,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
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
    '23',
    '16',
],
    'text_data': 'ae2fae6e208b42e9bffe1a49c26f35de',
    'rand_digit': 1,
    'rand_number': 0.24381,
    'rand_signed_int': -8,
    'rand_datetime': '2000-06-11 03:53:03.359550',
    'text_array': [
    '44926b01dd794365b4892d4e6fccbce6',
    '2a79d8ca2ba64d46b5c0349478215f39',
],
    'words': 'hyena bear',
    'nested': {
    'id': 147,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'dragonfly',
    'ant',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '18',
    '29',
    '07',
],
    'text_data': '033ef01271d34c93b6b5bf033ceecd85',
    'rand_digit': 1,
    'rand_number': 0.95466,
    'rand_signed_int': 0,
    'rand_datetime': '2000-10-07T00:51:46.725940',
    'text_array': [
    '94b511d4917d4fbcac5243054063049a',
    '1b462a16951641a4ad339cc292d0526f',
],
    'words': 'lobster turtle',
    'nested': {
    'id': 148,
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
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 8,
},
],
},
    'nested_array': [
    [
    8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'fox',
    'fly',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': [
    26,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'frog',
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
    'text_data': '2741a9c5a0cb4116bd25733de6c52d76',
    'rand_digit': 7,
    'rand_number': 0.6558,
    'rand_signed_int': 5,
    'rand_datetime': '2000-03-05T03:47:11.550496',
    'text_array': [
    '52bb1af3b8464e89b74ce6e3a840762e',
    'd1dc8339b6d349babbff6a3cfd184fcd',
],
    'words': 'cat camel',
    'nested': {
    'id': 149,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 7,
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
],
    'word': 'bird',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'hippo',
    'wolf',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'horse',
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
    '30',
    '06',
    '11',
],
    'text_data': '8a1ec1814772496997f5c6488af9fcd1',
    'rand_digit': 5,
    'rand_number': 0.31521,
    'rand_signed_int': -9,
    'rand_datetime': '2000-07-13 22:51',
    'text_array': [
    'ae6e455e10ee41d2b14c9ea7abe389ae',
    'bf80496eb476483aba3e23fbe9b71071',
],
    'words': 'butterfly panda',
    'nested': {
    'id': 150,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -6,
],
    [
    5,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'bee',
    'grasshopper',
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
    'mixed_type': 'bear',
    'maybe_null': 'monkey',
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
    'text_data': 'ae0ed7d19f634142b3d6a9698efc7ca2',
    'rand_digit': 4,
    'rand_number': 0.68783,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-20T00:42:14-0200',
    'text_array': [
    'c99fb8104c9b4b909f6ff731346d9c62',
    '1c873ad414d44a7ab6eb6b3ddec216f6',
],
    'words': 'duck gorilla',
    'nested': {
    'id': 151,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 8,
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
    'hello',
],
    'word': 'hippo',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'jaguar',
    'whale',
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
    'mixed_type': 9,
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
    '20',
    '06',
    '08',
    '21',
    '12',
],
    'text_data': '154f0d3a4860499aab4a60767027bd5c',
    'rand_digit': 0,
    'rand_number': 0.12948,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-18',
    'text_array': [
    'b107bc90a00745ebbbf374e25d6ef894',
    '06d01ec855bc43dd9e8ce09cb58ebe3f',
],
    'words': 'dog rhino',
    'nested': {
    'id': 152,
    'rand_digit': 0,
    'array': [
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
    'word': 'mosquito',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'shark',
    'kangaroo',
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
    'mixed_type': 9,
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
    '11',
],
    'text_data': '1f2092c3a8224cbab84ba99c10b80830',
    'rand_digit': 7,
    'rand_number': 0.28516,
    'rand_signed_int': -2,
    'rand_datetime': '2000-02-03',
    'text_array': [
    '37eda4cbd2d341d4a0315447b6da900a',
    '2d54385cccb044eab66136e6a1aab15a',
],
    'words': 'monkey ladybug',
    'nested': {
    'id': 153,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 10,
},
    {
    'nested_empty': None,
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
    'word': 'camel',
    'number': 1,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'lizard',
    'jaguar',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': [
    100,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'horse',
    'maybe_null': 'butterfly',
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
    '13',
    '28',
    '02',
    '05',
],
    'text_data': '0c60d9a9a0a645199d455af6c48b6310',
    'rand_digit': 3,
    'rand_number': 0.74548,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-23T18:04:42.541404-06:00',
    'text_array': [
    '60a855a8fa4243da82f6a262cc715677',
    '5fd72a979e6842a4b47f2f8b170a8d24',
],
    'words': 'fish lion',
    'nested': {
    'id': 154,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'frog',
    'tiger',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'shark',
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
    '14',
],
    'text_data': '8339d8b7be5f4941a1687dfafb3eebcc',
    'rand_digit': 3,
    'rand_number': 0.26496,
    'rand_signed_int': -10,
    'rand_datetime': '2000-02-07T06:07:00.957594',
    'text_array': [
    'f586498f6dc74c5e9e23cb35edfc0e19',
    'fb7c8fda7a514cd09f0426b87ca95c99',
],
    'words': 'spider lizard',
    'nested': {
    'id': 155,
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
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'hyena',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 6,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    5,
],
],
    'two_words': [
    'koala',
    'scorpion',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'ladybug',
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
    '28',
    '01',
],
    'text_data': 'e3e9e422ecbb475a96bc8ec542407e07',
    'rand_digit': 6,
    'rand_number': 0.20603,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-14',
    'text_array': [
    '70e16fabb46d43188cad202b3d8337c3',
    'a01a2d1b906140558a79d2482d551cfe',
],
    'words': 'leopard butterfly',
    'nested': {
    'id': 156,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 8,
},
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
    'word': 'camel',
    'number': 5,
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
    'word': 'horse',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'leopard',
    'zebra',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
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
],
    'text_data': 'e8e82ee404eb4ff182f84d94470d3d3a',
    'rand_digit': 4,
    'rand_number': 0.46373,
    'rand_signed_int': 0,
    'rand_datetime': '2000-04-29 08:49:44.591082+0300',
    'text_array': [
    '45dd66cb58e34149a2b793d36de3acc1',
    '86a61cf0feb44422b083097caec3aff6',
],
    'words': 'hyena hyena',
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
    'word': 'cheetah',
    'number': 5,
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
    'word': 'hippo',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 9,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,5__',
    'two_words': [
    'cat',
    'deer',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 'lobster',
    'maybe_null': 'rabbit',
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
    '25',
],
    'text_data': 'ac12d84e147147a9a8238a09b180fd08',
    'rand_digit': 1,
    'rand_number': 0.02983,
    'rand_signed_int': 2,
    'rand_datetime': '2000-09-02T15:27:15.486884+0500',
    'text_array': [
    'eba9010420de4904bd35fc06ceedaee7',
    'fe1ce0f0eee549c9ac34cb0299c04cca',
],
    'words': 'zebra mosquito',
    'nested': {
    'id': 158,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 7,
},
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
    [
    1,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'tiger',
    'giraffe',
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
    'mixed_type': 'panda',
    'maybe': 'zebra',
    'maybe_null': 'zebra',
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
    '10',
    '05',
    '05',
    '04',
],
    'text_data': 'ad96bcb743b3463f8f3822fcc915beb0',
    'rand_digit': 0,
    'rand_number': 0.72283,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-19 00:09:56+0000',
    'text_array': [
    '2c3917808a284b5cae51f1ebd077c716',
    'e7a0fd16a785489e87718d0179a65009',
],
    'words': 'zebra crab',
    'nested': {
    'id': 159,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'duck',
    'ladybug',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.28037,
    'maybe': 'bird',
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
    '21',
],
    'text_data': 'd71b2c0fa14947788d49548596e128cf',
    'rand_digit': 2,
    'rand_number': 0.74336,
    'rand_signed_int': -9,
    'rand_datetime': '2000-02-16T16:54:44.714761',
    'text_array': [
    '7d0c671d39a04f69a9e0fe10543e4460',
    '2311a3fe36d54c40a5931770b315628e',
],
    'words': 'panda lizard',
    'nested': {
    'id': 160,
    'rand_digit': 4,
    'array': [
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'shark',
    'snail',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': [
    93,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'mouse',
    'maybe_null': 'snail',
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
    'text_data': '1c5349b16a494f9c9ea8b6a3c3464974',
    'rand_digit': 2,
    'rand_number': 0.85052,
    'rand_signed_int': 6,
    'rand_datetime': '2001-01-12T11:34:48-0600',
    'text_array': [
    '2eafaa045f034136b5b7e0fc039992f6',
    'bfca7ef8d0cb4c4e93c9daf021f14022',
],
    'words': 'rhino tiger',
    'nested': {
    'id': 161,
    'rand_digit': 4,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 2,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dog',
    'leopard',
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
    'mixed_type': 6,
    'maybe': 'ladybug',
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
    'text_data': '72dbb03cd9594485a3c5514ae45a689e',
    'rand_digit': 0,
    'rand_number': 0.49515,
    'rand_signed_int': 0,
    'rand_datetime': '2000-11-01T11:18:28.126294-03:00',
    'text_array': [
    'f23df622a0d84787806900535207af36',
    'ca30e10e6291421a8cf37db5fc6238ca',
],
    'words': 'bear sheep',
    'nested': {
    'id': 162,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'dragonfly',
    'octopus',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': [
    47,
],
    'rand_bool': True,
    'mixed_type': 1,
    'maybe': 'dolphin',
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
    '02',
    '15',
    '22',
    '18',
    '17',
],
    'text_data': '5a789089574d4e70a9bbce1338597696',
    'rand_digit': 6,
    'rand_number': 0.7184,
    'rand_signed_int': -6,
    'rand_datetime': '2000-11-15 06:08:37-0800',
    'text_array': [
    'c33b578df8724defb34b8b6a50b54d35',
    'aa3269ab2ba04149a9c4f614e09146d6',
],
    'words': 'chicken lion',
    'nested': {
    'id': 163,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'grasshopper',
    'fish',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'dragonfly',
    'maybe_null': 'bee',
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
    'content-length': '137210',
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
],
    'text_data': '24e86022bfb94192b5a9ea72c29f704c',
    'rand_digit': 3,
    'rand_number': 0.29091,
    'rand_signed_int': -10,
    'rand_datetime': '2000-06-09T05:16:54.410969+0600',
    'text_array': [
    '7933af9bd1044ca289772ef34e0e37c6',
    '8ae16c1afd3147958d34e12d900a87c7',
],
    'words': 'goat scorpion',
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
    'word': 'scorpion',
    'number': 7,
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
    {
    'nested_empty': None,
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
    'word': 'turtle',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'jaguar',
    'scorpion',
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
    'mixed_type': 0.43464,
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
    '19',
    '18',
],
    'text_data': '9ffb8a7303c444f3868ccd8a91b71aa9',
    'rand_digit': 7,
    'rand_number': 0.9275,
    'rand_signed_int': 7,
    'rand_datetime': '2000-05-15 21:45:53.480859+0800',
    'text_array': [
    'd227efa78a32465199455a7e4c7feb4a',
    'b9a14cacddc14da6aaeab9d0fb719147',
],
    'words': 'wolf bird',
    'nested': {
    'id': 101,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lion',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    4,
],
],
    'two_words': [
    'monkey',
    'horse',
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
    'mixed_type': 'bear',
    'maybe': 'koala',
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
    '27',
    '14',
],
    'text_data': '403a8f20c54144d0a42aca6365751291',
    'rand_digit': 3,
    'rand_number': 0.70119,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-28T13:07:07.851411',
    'text_array': [
    '41c33025dde6482ebe382773495be7fb',
    '23b3f97463834257826f5dbca5ce0b28',
],
    'words': 'mosquito kangaroo',
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
    'word': 'snail',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'hyena',
    'scorpion',
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
    'mixed_type': None,
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
    '29',
    '09',
    '26',
],
    'text_data': '085f6e02d2db4701b8d46e5576cebf6b',
    'rand_digit': 4,
    'rand_number': 0.48257,
    'rand_signed_int': -4,
    'rand_datetime': '2000-09-24 03:07',
    'text_array': [
    '3dfd7c10ad9740aba010726e00491ee7',
    'dd86e545421a4f298f0a1ab3289fbdf6',
],
    'words': 'rabbit gorilla',
    'nested': {
    'id': 103,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 8,
},
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'fish',
    'horse',
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
    'mixed_type': 0.54131,
    'maybe': 'tiger',
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
    '07',
    '27',
    '27',
],
    'text_data': 'bb6401ddf25e418aaa6ed6311d7755be',
    'rand_digit': 7,
    'rand_number': 0.58567,
    'rand_signed_int': -10,
    'rand_datetime': '2000-03-10 14:05:50',
    'text_array': [
    '50dd0f86f3484dfe922b625a6fb4e920',
    'f757135a48ba41f489f3114da26f4588',
],
    'words': 'dolphin turtle',
    'nested': {
    'id': 104,
    'rand_digit': 5,
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
    'word': 'rhino',
    'number': 1,
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
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'ape',
    'ape',
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
    'mixed_type': False,
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
    '27',
    '08',
    '03',
    '26',
    '02',
],
    'text_data': '0476e8495db14197bd874f1530fa697a',
    'rand_digit': 4,
    'rand_number': 0.61197,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-13 07:28',
    'text_array': [
    '54b49edc61114c26b961a6517d703644',
    'f7d0142288ae4eddbfa7ecd44a46c4da',
],
    'words': 'goat turtle',
    'nested': {
    'id': 105,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'cow',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'rabbit',
    'snake',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': [
    58,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'butterfly',
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
    '21',
    '13',
    '05',
    '16',
    '15',
],
    'text_data': 'acf878c9636a480eb7e3540a215fd558',
    'rand_digit': 4,
    'rand_number': 0.01032,
    'rand_signed_int': -5,
    'rand_datetime': '2000-03-11T14:34:10.121869',
    'text_array': [
    '36ef6442d0524f41bf4f27fd000c2bdf',
    'd1ce163530154985aadd4690ec853c83',
],
    'words': 'bird hyena',
    'nested': {
    'id': 106,
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
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'tiger',
    'scorpion',
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
    'mixed_type': False,
    'maybe_null': 'mouse',
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
    '28',
    '14',
],
    'text_data': 'c9264476857e42a683bf1ed05e2c7daa',
    'rand_digit': 0,
    'rand_number': 0.67905,
    'rand_signed_int': -8,
    'rand_datetime': '2000-10-11T11:34:07-1200',
    'text_array': [
    '40addafe38fb4a74baa1012011f2c16f',
    'd312ee99127a4e09b3e77653c6e8b04c',
],
    'words': 'monkey deer',
    'nested': {
    'id': 107,
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
    'number': 4,
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
],
    'word': 'dog',
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
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'chicken',
    'sloth',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'ant',
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
    '18',
],
    'text_data': '02260b8048d24b40b57d809493f1c223',
    'rand_digit': 8,
    'rand_number': 0.46064,
    'rand_signed_int': 0,
    'rand_datetime': '2000-10-31T03:57:04',
    'text_array': [
    'fac170c05b2e472e908e1b5f6245cd5b',
    '8ea63cd46021448cb1082e733b6fd35c',
],
    'words': 'fox gorilla',
    'nested': {
    'id': 108,
    'rand_digit': 6,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'rhino',
    'fly',
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
    'mixed_type': 2,
    'maybe': 'shark',
    'maybe_null': 'dog',
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
    '19',
],
    'text_data': 'b767841325d845d2a77f03bce8fccbb6',
    'rand_digit': 7,
    'rand_number': 0.75911,
    'rand_signed_int': 3,
    'rand_datetime': '2000-09-03 03:02:13.641787',
    'text_array': [
    'ae13f53cec7941cca5b289e72fce0a9f',
    'f601ac5a3e4a433b8f631bf7145979c6',
],
    'words': 'panda ant',
    'nested': {
    'id': 109,
    'rand_digit': 7,
    'array': [
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'panda',
    'jaguar',
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
    'maybe': 'turtle',
    'maybe_null': 'scorpion',
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
    '07',
    '03',
    '11',
    '30',
],
    'text_data': 'e6a9cc00da824a2dbd6320510aa8dda2',
    'rand_digit': 2,
    'rand_number': 0.45695,
    'rand_signed_int': 1,
    'rand_datetime': '2000-05-26T08:05:23',
    'text_array': [
    '0e38994b345145e0b14f15bb72362195',
    '685e0d1542214a02a37537d6c310d361',
],
    'words': 'squid lion',
    'nested': {
    'id': 110,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 10,
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
    'word': 'camel',
    'number': 8,
},
    {
    'nested_empty': None,
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
],
    'word': 'hyena',
    'number': 6,
},
],
},
    'nested_array': [
    [
    -5,
],
],
    'two_words': [
    'bee',
    'dolphin',
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
    'mixed_type': True,
    'maybe': 'whale',
    'maybe_null': 'shark',
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
],
    'text_data': 'b9187519a17542288d1c73388206f9ca',
    'rand_digit': 3,
    'rand_number': 0.56288,
    'rand_signed_int': 8,
    'rand_datetime': '2000-11-29',
    'text_array': [
    '69fd41bde2994ea584607b85cd3f1942',
    '2f4b2fdfc45949e59eb9f8d73c9635ec',
],
    'words': 'rabbit lion',
    'nested': {
    'id': 111,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
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
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'octopus',
    'bee',
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
    'mixed_type': 0.83787,
    'maybe': 'jaguar',
    'maybe_null': 'whale',
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
    '01',
    '16',
    '08',
],
    'text_data': 'e0b8c6d8a40249be97c0bbbecc350624',
    'rand_digit': 8,
    'rand_number': 0.70362,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-28T09:29:39.911816',
    'text_array': [
    '2ab69c7082004e63a5e0d0917980a217',
    '10d6f9fe11de4a0e83c851a9e761aa97',
],
    'words': 'elephant hyena',
    'nested': {
    'id': 112,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'pig',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '20',
    '26',
    '10',
],
    'text_data': '7e13c03bbade4cd0981df3899bcc5960',
    'rand_digit': 1,
    'rand_number': 0.48093,
    'rand_signed_int': -10,
    'rand_datetime': '2000-07-08 16:01',
    'text_array': [
    'a9c82487e96941e4a38e4ca957a75dbb',
    'a00ab2431a3b4d108deacf73d1ab377c',
],
    'words': 'fish horse',
    'nested': {
    'id': 113,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 9,
},
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
    'hello',
],
    'word': 'ape',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
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
    'butterfly',
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
    'mixed_type': None,
    'maybe': 'fox',
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
],
    'text_data': 'a29678aa8f384a3f9d6fd875167f4c66',
    'rand_digit': 7,
    'rand_number': 0.15782,
    'rand_signed_int': -1,
    'rand_datetime': '2000-05-13 19:28',
    'text_array': [
    '252a143d18574824b276af02c416a637',
    'ad1e3fd78e8343bab1ca8b8ca709f593',
],
    'words': 'elephant hippo',
    'nested': {
    'id': 114,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 4,
},
],
},
    'nested_array': [
    [
    -1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bear',
    'gorilla',
],
    'city': {
    'name': 'Riga',
    'geo': {
    'lat': 56.949649,
    'lon': 24.105186,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'rhino',
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
    '24',
    '12',
    '20',
],
    'text_data': 'f3a11fd5ba2449f4900aa1cce443598b',
    'rand_digit': 0,
    'rand_number': 0.45652,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-19 08:29:05',
    'text_array': [
    '41017e7efb614036a6994c09f7fdf38d',
    '34fc795b0cd94bf8b90493fa31418597',
],
    'words': 'fish ant',
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
    'word': 'zebra',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'scorpion',
    'rabbit',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'scorpion',
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
    '09',
    '05',
    '21',
],
    'text_data': 'c281856c91fd4dada296db689580c47f',
    'rand_digit': 1,
    'rand_number': 0.09712,
    'rand_signed_int': -9,
    'rand_datetime': '2000-11-03T20:56:05.268459+0300',
    'text_array': [
    '78ff920511a34fe8870589f5a7e4e5e3',
    'ae4c8f9cd9fe499c8550047d0931b0dc',
],
    'words': 'dragonfly cheetah',
    'nested': {
    'id': 116,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fly',
    'rhino',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'leopard',
    'maybe_null': 'frog',
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
],
    'text_data': '77d8bdbf446b4045b2529654cce5d487',
    'rand_digit': 1,
    'rand_number': 0.38243,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-02 02:21:40',
    'text_array': [
    'ac945a608dcf454f8e8450d96b4f73db',
    '6808e77f879247c9956ba63b88b50951',
],
    'words': 'hippo snail',
    'nested': {
    'id': 117,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'whale',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 2,
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
    'word': 'rabbit',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -6,
],
],
    'two_words': [
    'snake',
    'rabbit',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'hyena',
    'maybe_null': 'cat',
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
    '22',
    '28',
],
    'text_data': '6b19992ddec0420eb0c478e441498560',
    'rand_digit': 9,
    'rand_number': 0.9597,
    'rand_signed_int': -1,
    'rand_datetime': '2000-02-08 17:05',
    'text_array': [
    '4073d1d599f94e5fba028314de18fb94',
    '3ab29d912ffa41aeb6992cddce55e315',
],
    'words': 'cheetah fox',
    'nested': {
    'id': 118,
    'rand_digit': 4,
    'array': [
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
    'word': 'spider',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 2,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'grasshopper',
    'hippo',
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
    'mixed_type': False,
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
    'text_data': 'e6c719c604fb45a98efcf3d58453fb3c',
    'rand_digit': 8,
    'rand_number': 0.36301,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-26 19:57',
    'text_array': [
    'a929472c8f034b219c5d97e1c8a70020',
    '8e3347edcf2a40eab62763554df450c8',
],
    'words': 'bear whale',
    'nested': {
    'id': 119,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bee',
    'snake',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cow',
    'maybe_null': 'horse',
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
    'text_data': '2fef6f25e77b4280a6f3b3b53d9b12ee',
    'rand_digit': 0,
    'rand_number': 0.1755,
    'rand_signed_int': 7,
    'rand_datetime': '2000-09-09 13:51:55-0300',
    'text_array': [
    '39a5e6c251c445e597e8006d4dd0dfea',
    'cb6061e7e125429aba2f0fcf03f27417',
],
    'words': 'elephant goat',
    'nested': {
    'id': 120,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ape',
    'squid',
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
    'mixed_type': 0.06364,
    'maybe': 'monkey',
    'maybe_null': 'horse',
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
    '22',
    '14',
    '07',
    '25',
],
    'text_data': 'f047260e4a1744ac833e561b3157c296',
    'rand_digit': 0,
    'rand_number': 0.37562,
    'rand_signed_int': 9,
    'rand_datetime': '2001-01-21T06:39:55.710188',
    'text_array': [
    '0e1a862b677c41378871db990408b2e3',
    '78f0b62646c741a2b91e6e2f36505520',
],
    'words': 'octopus leopard',
    'nested': {
    'id': 121,
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
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'grasshopper',
    'elephant',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'cat',
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
    '10',
    '05',
    '20',
],
    'text_data': '651f1a36c7c14587b7f8304c735fa0e7',
    'rand_digit': 1,
    'rand_number': 0.22655,
    'rand_signed_int': 1,
    'rand_datetime': '2000-05-20 13:12:59.895560+0500',
    'text_array': [
    '09bef4cad3884355ac56e18c9f2d401a',
    'a2d72dd00157493288bba6696606bd3d',
],
    'words': 'butterfly zebra',
    'nested': {
    'id': 122,
    'rand_digit': 0,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 9,
},
],
},
    'nested_array': [
    [
    1,
],
    [
    7,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'sheep',
    'monkey',
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
    'mixed_type': 'dolphin',
    'maybe': 'cheetah',
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
    '24',
    '30',
    '10',
    '18',
],
    'text_data': '667b85d909224177abc9ffb1a2bfea88',
    'rand_digit': 3,
    'rand_number': 0.95032,
    'rand_signed_int': -6,
    'rand_datetime': '2000-11-12 21:16',
    'text_array': [
    'edd94685cfc64a38ab25216fd84dbd5d',
    'b0529eb4c6ad4f1e9dd77f1e006db6cf',
],
    'words': 'sloth fly',
    'nested': {
    'id': 123,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'bee',
    'duck',
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
    'mixed_type': 2,
    'maybe_null': 'giraffe',
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
],
    'text_data': 'fc9070daf4854bd59629f79fc672c7fa',
    'rand_digit': 6,
    'rand_number': 0.77522,
    'rand_signed_int': -6,
    'rand_datetime': '2000-08-29T21:39:50-1000',
    'text_array': [
    '13fdec9a61a341deba39e6533e824afe',
    'de40fb1bbb174b2b929a681c91e9c4fc',
],
    'words': 'mouse lizard',
    'nested': {
    'id': 124,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'shark',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'sheep',
    'ape',
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
    'mixed_type': 7,
    'maybe': 'cat',
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
    '09',
    '09',
    '03',
],
    'text_data': '48a698fa36d4492f80fcc38d91951736',
    'rand_digit': 8,
    'rand_number': 0.11889,
    'rand_signed_int': 10,
    'rand_datetime': '2000-03-28T14:15:17.941899',
    'text_array': [
    'fdb43f677e7a4145af4e3d3154c7bdfb',
    '203f47ff802e4ee9ae1cc18700f09f5b',
],
    'words': 'horse octopus',
    'nested': {
    'id': 125,
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
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'bear',
    'number': 9,
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
    -4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'octopus',
    'grasshopper',
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
    'mixed_type': 'hippo',
    'maybe': 'zebra',
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
    '25',
    '12',
    '30',
],
    'text_data': '8ea3906bbb624474a02490b80d599fb8',
    'rand_digit': 4,
    'rand_number': 0.02066,
    'rand_signed_int': 3,
    'rand_datetime': '2000-03-29 21:24:41.668133',
    'text_array': [
    '8eeb7518100a470ba665132a77d10a71',
    '39eac0f635ac4e99bc5d82b06e24bfc4',
],
    'words': 'mouse kangaroo',
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
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
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
    'spider',
    'fly',
],
    'city': {
    'name': 'Zurich',
    'geo': {
    'lat': 47.376887,
    'lon': 8.541694,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'shark',
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
    '13',
    '14',
    '20',
],
    'text_data': '6447a59d941d452286f04a15effa647f',
    'rand_digit': 5,
    'rand_number': 0.35492,
    'rand_signed_int': -7,
    'rand_datetime': '2000-09-02 01:13:50.439173',
    'text_array': [
    'a4a4d2edd044463db89b303128e5dddb',
    '1e36be5207b747888e360b10372401c1',
],
    'words': 'tiger lobster',
    'nested': {
    'id': 127,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -5,
],
],
    'two_words': [
    'ant',
    'duck',
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
    'mixed_type': None,
    'maybe': 'panda',
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
    '26',
    '02',
    '25',
    '23',
    '09',
],
    'text_data': 'afe5d31410fc47749b0ea7baa44a2d08',
    'rand_digit': 7,
    'rand_number': 0.50592,
    'rand_signed_int': -2,
    'rand_datetime': '2000-06-18 18:23',
    'text_array': [
    '9e629d4da74242fcbfa9927991a4409f',
    'b157696072c34eb3b7a83da1b3670eb4',
],
    'words': 'chicken camel',
    'nested': {
    'id': 128,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 2,
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
    [
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'mouse',
    'dragonfly',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'jaguar',
    'maybe_null': 'ladybug',
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
    '17',
    '06',
    '24',
    '04',
    '02',
],
    'text_data': 'b6e51071e85a4b3196e9ea604c10192d',
    'rand_digit': 0,
    'rand_number': 0.54263,
    'rand_signed_int': 9,
    'rand_datetime': '2000-03-06',
    'text_array': [
    'e16de41acd66400982e07aebb370b27a',
    '3072e9462b5d45978b04a606f601d6ce',
],
    'words': 'dragonfly lizard',
    'nested': {
    'id': 129,
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
    'word': 'monkey',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'monkey',
    'bee',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': [
    31,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '17',
    '07',
    '13',
],
    'text_data': '50b1019614c34e9d9d2e6dd21ac8b277',
    'rand_digit': 6,
    'rand_number': 0.12678,
    'rand_signed_int': 5,
    'rand_datetime': '2000-05-28T22:38:47',
    'text_array': [
    '6951a5c790a542dda18e102d87226e77',
    '4f5f586dd6b742d1a62f2c21f8773589',
],
    'words': 'horse dragonfly',
    'nested': {
    'id': 130,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    [
],
    [
    0,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'snail',
    'tiger',
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
    'mixed_type': True,
    'maybe': 'dolphin',
    'maybe_null': 'bee',
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
    'text_data': '322b372136524c67a219ad943f3bc048',
    'rand_digit': 9,
    'rand_number': 0.87143,
    'rand_signed_int': -10,
    'rand_datetime': '2000-11-01 00:09:44',
    'text_array': [
    'fe624b0ef8964e56baa1a854f0ce282a',
    '8842c4d749a8416996f0ed0d07bf616e',
],
    'words': 'squid monkey',
    'nested': {
    'id': 131,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -2,
],
    [
],
],
    'two_words': [
    'cow',
    'bee',
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
],
    'text_data': '9868fe18dc684f80bb79866cd4788fbe',
    'rand_digit': 5,
    'rand_number': 0.33321,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-03T07:45:46.925777',
    'text_array': [
    'ea177a37188843ecad8e328d1a26d026',
    '4fb5665b524b4720b624643171faf668',
],
    'words': 'rhino whale',
    'nested': {
    'id': 132,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'fly',
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
],
],
    'two_words': [
    'dog',
    'bear',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': [
    92,
],
    'rand_bool': False,
    'mixed_type': 'ape',
    'maybe': 'shark',
    'maybe_null': 'tiger',
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
    '17',
    '14',
    '14',
    '25',
],
    'text_data': 'dc4900d4c4714661ad8c33ea0e9dd199',
    'rand_digit': 6,
    'rand_number': 0.48294,
    'rand_signed_int': -6,
    'rand_datetime': '2000-11-11 23:59:45',
    'text_array': [
    'b82ad4fe3fa24a43a762e4b51ad4b895',
    '9d210d7597b04e1ab112c3bf48f67d51',
],
    'words': 'cheetah bird',
    'nested': {
    'id': 133,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'mouse',
    'spider',
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
    'mixed_type': 5,
    'maybe': 'zebra',
    'maybe_null': 'hippo',
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
    '01',
],
    'text_data': 'f6a62020f894426986017bdf8127763f',
    'rand_digit': 6,
    'rand_number': 0.5842,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-28 05:31:49',
    'text_array': [
    '513e53d828294b88b631440de612a14d',
    '894bc41a60c0453b99cd620f2dfba926',
],
    'words': 'snail hyena',
    'nested': {
    'id': 134,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 8,
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
    'nested_array': [
    [
    7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'sheep',
    'mosquito',
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
    'mixed_type': 0,
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
    '06',
    '04',
    '09',
],
    'text_data': '7b7a64a1750a4d47af31c501f9a5d710',
    'rand_digit': 7,
    'rand_number': 0.13375,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-14T01:55:42',
    'text_array': [
    '1c47dd9808e9403cadebf1ba9409d432',
    'b81fc18b2f87478da6369a5dd48f08c3',
],
    'words': 'octopus fox',
    'nested': {
    'id': 135,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 9,
},
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    9,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    4,
],
],
    'two_words': [
    'horse',
    'duck',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': [
    94,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'zebra',
    'maybe_null': 'panda',
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
],
    'text_data': '51a79e7197274c68b5eda9fe7557afb7',
    'rand_digit': 3,
    'rand_number': 0.50216,
    'rand_signed_int': -6,
    'rand_datetime': '2001-01-27T04:35:01',
    'text_array': [
    '5276506d4e3941b4b18ac27cd8f68f4b',
    'ad68712bb9a8404393e6b51102880538',
],
    'words': 'giraffe ladybug',
    'nested': {
    'id': 136,
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
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    7,
],
],
    'two_words': [
    'lion',
    'hippo',
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
    'mixed_type': 0.61171,
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
    'text_data': 'cc044388714948b9ba081c285e79296e',
    'rand_digit': 0,
    'rand_number': 0.16984,
    'rand_signed_int': -9,
    'rand_datetime': '2000-11-01 10:11:04.549365-1200',
    'text_array': [
    'b1baba8346974277b4feebad078625c9',
    '717e087b738e4e0f98d0f3186c188694',
],
    'words': 'bee chicken',
    'nested': {
    'id': 137,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'wolf',
    'horse',
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
    'mixed_type': None,
    'maybe_null': 'deer',
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
    '28',
],
    'text_data': 'f02ed901d9f04a0097d4ef87899420aa',
    'rand_digit': 6,
    'rand_number': 0.21116,
    'rand_signed_int': 7,
    'rand_datetime': '2000-12-20',
    'text_array': [
    'a30cbeb3739149089e69a76f7f8eaa80',
    '7afa31c593a14726979fda5aeaca9afe',
],
    'words': 'jaguar sheep',
    'nested': {
    'id': 138,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 7,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lizard',
    'wolf',
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
    'mixed_type': 'rabbit',
    'maybe': 'hyena',
    'maybe_null': 'shark',
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
    '21',
],
    'text_data': 'c580ecb14ba74ac089c2c65bacfc8277',
    'rand_digit': 3,
    'rand_number': 0.07475,
    'rand_signed_int': -3,
    'rand_datetime': '2000-01-15 01:56:35-0300',
    'text_array': [
    '3861b5bc50044348bcb7f2c59601db65',
    '400f92047c1b4a3eb1bafddf737134c0',
],
    'words': 'sloth ant',
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
    'word': 'turtle',
    'number': 2,
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
],
    'word': 'octopus',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -4,
],
],
    'two_words': [
    'wolf',
    'pig',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': [
    3,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
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
    '12',
    '16',
    '16',
    '26',
],
    'text_data': '0fe3a98940b94ed788a3f619a51c390b',
    'rand_digit': 2,
    'rand_number': 0.08351,
    'rand_signed_int': -10,
    'rand_datetime': '2000-01-21T03:15:33.935057',
    'text_array': [
    '8353c825b1c848bdb29f234e68d706c6',
    'cecead51a1814e2399566db4c374b8e9',
],
    'words': 'crab butterfly',
    'nested': {
    'id': 140,
    'rand_digit': 5,
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
    'word': 'dog',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'squid',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'camel',
    'camel',
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
    'mixed_type': 'grasshopper',
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
    '18',
    '20',
    '16',
    '27',
],
    'text_data': '1547ff09b5b5414fa88827f850c83a5f',
    'rand_digit': 7,
    'rand_number': 0.68473,
    'rand_signed_int': 7,
    'rand_datetime': '2000-03-24T02:59:57.738146',
    'text_array': [
    'cf10d9cfe8eb40099b432e73e2dc86d1',
    '11f25680ec9d4803a0de3a67064a1d4c',
],
    'words': 'fox horse',
    'nested': {
    'id': 141,
    'rand_digit': 9,
    'array': [
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lion',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    8,
],
    [
],
],
    'two_words': [
    'bird',
    'deer',
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
    'mixed_type': 'bee',
    'maybe': 'lizard',
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
    '03',
    '29',
    '22',
    '08',
    '01',
],
    'text_data': 'e997f04524384c5380a72d2056e95f72',
    'rand_digit': 1,
    'rand_number': 0.72558,
    'rand_signed_int': -5,
    'rand_datetime': '2000-06-26 11:37:09.640433',
    'text_array': [
    '14fa5a2cd2d84befa9798ed681dbfa5d',
    '81679b7873394f0ea11f2cf39b5202d7',
],
    'words': 'gorilla bear',
    'nested': {
    'id': 142,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lobster',
    'fly',
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
    'maybe': 'deer',
    'maybe_null': 'scorpion',
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
    '09',
    '27',
    '16',
    '01',
],
    'text_data': '877f62e6d98847e2879a99439b48c3b7',
    'rand_digit': 7,
    'rand_number': 0.09564,
    'rand_signed_int': 10,
    'rand_datetime': '2000-09-17T17:53:58-0300',
    'text_array': [
    'a1f2614a35034e698a3143c91ba5b93b',
    '4ee22b70d7784ebf95f8f90722473217',
],
    'words': 'zebra fox',
    'nested': {
    'id': 143,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'jaguar',
    'ant',
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
    'mixed_type': False,
    'maybe_null': 'koala',
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
    '19',
    '13',
],
    'text_data': '2f79eb693f8144298f4c6f6ec0aa5e44',
    'rand_digit': 5,
    'rand_number': 0.25064,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-22',
    'text_array': [
    'e2ba8906c49c4fc09393f5cbd3d74d2f',
    'f5c0fcc5b73343478e13dc7035c7a157',
],
    'words': 'cat sloth',
    'nested': {
    'id': 144,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'crab',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cow',
    'spider',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': [
    59,
],
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'turtle',
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
],
    'text_data': '1355d92a5b9e4d20b8f909a0ee911cb3',
    'rand_digit': 8,
    'rand_number': 0.2143,
    'rand_signed_int': 0,
    'rand_datetime': '2000-02-05T06:10:25-0100',
    'text_array': [
    'ed99b46686e5498cb5e672480477c422',
    '58494fe32df649b4855689489ac0516b',
],
    'words': 'dragonfly cheetah',
    'nested': {
    'id': 145,
    'rand_digit': 6,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'crab',
    'number': 10,
},
],
},
    'nested_array': [
    [
    -8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    5,
],
    [
],
    [
],
],
    'two_words': [
    'butterfly',
    'goat',
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
    'mixed_type': 9,
    'maybe_null': 'lizard',
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
    '10',
    '02',
    '11',
    '26',
],
    'text_data': 'e1bd792f9bcb49d4884140d85c04b267',
    'rand_digit': 7,
    'rand_number': 0.71013,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-25 09:29:02',
    'text_array': [
    'ebb8e42de682492ca33715b86a63cf2e',
    '5c621fc153ea4e4783c38020858a4b48',
],
    'words': 'shark monkey',
    'nested': {
    'id': 146,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'bear',
    'number': 4,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'koala',
    'mosquito',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': [
    67,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'duck',
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
    '27',
    '30',
    '13',
    '13',
],
    'text_data': 'b7a7798495f14317af428a07b133c919',
    'rand_digit': 4,
    'rand_number': 0.79573,
    'rand_signed_int': 7,
    'rand_datetime': '2000-05-24T05:54:22.381334-10:00',
    'text_array': [
    'b9c2e6f4d9454872ab3bbefc365411a2',
    '37e1ea968c2d43bfa0dc886f7d12ee87',
],
    'words': 'panda cat',
    'nested': {
    'id': 147,
    'rand_digit': 0,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 7,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'wolf',
    'fish',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '29',
    '10',
    '05',
    '03',
],
    'text_data': 'ae51a7a7a1b346f9a73a497d982a8f85',
    'rand_digit': 6,
    'rand_number': 0.03948,
    'rand_signed_int': 2,
    'rand_datetime': '2000-06-26 00:07:49.320105',
    'text_array': [
    'abf00a0a37c1443f8ccebca9e7b6234e',
    '239b66be17b54224af2c7716b48e2f8f',
],
    'words': 'lizard leopard',
    'nested': {
    'id': 148,
    'rand_digit': 7,
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
    'hello',
],
    'word': 'horse',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 9,
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
],
    'two_words': [
    'snake',
    'lobster',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': [
    13,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': 'sloth',
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
    '25',
    '06',
    '08',
    '07',
],
    'text_data': 'ef20ce1f962e470082ea3e509f75f086',
    'rand_digit': 3,
    'rand_number': 0.28836,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-24 15:05:10+0600',
    'text_array': [
    'b84f6cf5eb7a4b8bb9b7ec6fe1d8977a',
    '8a1df528de6b44f783e1ab3d527a378b',
],
    'words': 'ant pig',
    'nested': {
    'id': 149,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
    -8,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    7,
],
],
    'two_words': [
    'fish',
    'fox',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'zebra',
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
    '14',
    '24',
],
    'text_data': '241f1071fd004a41b05acd91b2e7a3ba',
    'rand_digit': 9,
    'rand_number': 0.29496,
    'rand_signed_int': 8,
    'rand_datetime': '2000-03-22T08:28:46.084377+0200',
    'text_array': [
    'c4c4bb15a1054cd18d8b964fb37e8316',
    'b4a84da84311470db0d2b071933d646f',
],
    'words': 'crab butterfly',
    'nested': {
    'id': 150,
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
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -4,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'dragonfly',
    'leopard',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': [
    90,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'octopus',
    'maybe_null': 'cheetah',
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
    '08',
    '27',
    '07',
],
    'text_data': 'e92057817a294582a65b3694b40a024b',
    'rand_digit': 6,
    'rand_number': 0.76636,
    'rand_signed_int': 2,
    'rand_datetime': '2000-04-26T14:51:56.202746',
    'text_array': [
    '866afc4226f745dfa72c5498e8399eaa',
    'b16495c06d2c496b8ade62dee77a36ac',
],
    'words': 'mosquito sloth',
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
    'word': 'wolf',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 5,
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
    'koala',
    'tiger',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
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
    '07',
    '12',
],
    'text_data': '83b4221315b34ea0a8c71ed754b84212',
    'rand_digit': 9,
    'rand_number': 0.3961,
    'rand_signed_int': -4,
    'rand_datetime': '2000-11-07T08:27:04.076084-0300',
    'text_array': [
    '27bdcaa25b03459c80a852a603508a62',
    '151e179172b74958ae2aa3fc5e56401f',
],
    'words': 'dolphin fish',
    'nested': {
    'id': 152,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'camel',
    'number': 6,
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
    -5,
],
    [
],
],
    'two_words': [
    'tiger',
    'horse',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 3,
    'maybe': 'hippo',
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
    '03',
    '13',
    '23',
    '22',
    '16',
],
    'text_data': '319b72f0bfe84780ace4cd2cafba029e',
    'rand_digit': 0,
    'rand_number': 0.78685,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-27 07:10:09.278448',
    'text_array': [
    '76e78f07572e4435b87eb358ec767abe',
    '74ed6739ad95414b84952fd29736a7c9',
],
    'words': 'dragonfly mosquito',
    'nested': {
    'id': 153,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'shark',
    'goat',
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
    'maybe': 'kangaroo',
    'maybe_null': 'bee',
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
    '03',
    '21',
    '20',
    '21',
    '17',
],
    'text_data': '8144b70a3d6346deb076208bf405209a',
    'rand_digit': 6,
    'rand_number': 0.50496,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-10T00:02:12.182335-0600',
    'text_array': [
    '663fa233b62442a18ddd4ec7512e9c18',
    'a484dacaf96f4d59b454c741019a4abe',
],
    'words': 'goat ladybug',
    'nested': {
    'id': 154,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 3,
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
    'word': 'hyena',
    'number': 1,
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
    'word': 'cheetah',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snail',
    'wolf',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'crab',
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
    '25',
    '26',
],
    'text_data': 'ad65afdcd5954d7cb114ff0e82a5469e',
    'rand_digit': 2,
    'rand_number': 0.66602,
    'rand_signed_int': 7,
    'rand_datetime': '2000-12-08T07:30:40.750559-11:00',
    'text_array': [
    '0ed428c7eb4046808f18a2b92afdc4bd',
    'e1bc244971b8469386ec51759495ec3f',
],
    'words': 'dog sheep',
    'nested': {
    'id': 155,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    8,
],
],
    'two_words': [
    'dragonfly',
    'rabbit',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.86659,
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
    '17',
],
    'text_data': 'd2c4f42c690f45ab8299cc4dddd1a4ba',
    'rand_digit': 4,
    'rand_number': 0.25957,
    'rand_signed_int': 7,
    'rand_datetime': '2000-08-25 00:55:40.824081',
    'text_array': [
    '95777e56ce57406b845a27e5d95890f3',
    'a25981bcb3ce46d99cbd0934d7e30699',
],
    'words': 'rabbit crab',
    'nested': {
    'id': 156,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'scorpion',
    'mosquito',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 1,
    'maybe': 'goat',
    'maybe_null': 'hyena',
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
    '24',
    '30',
],
    'text_data': 'b5de2d2cdf60488a847a1da9371dd039',
    'rand_digit': 6,
    'rand_number': 0.09247,
    'rand_signed_int': 7,
    'rand_datetime': '2000-01-27T11:22:56',
    'text_array': [
    'b67b2f6729a841a8ae3e8dc852385bd7',
    '7207f7ef6fe7437bb5711c7904455c21',
],
    'words': 'scorpion crab',
    'nested': {
    'id': 157,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 10,
},
],
},
    'nested_array': [
    [
    2,
],
],
    'two_words': [
    'deer',
    'elephant',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 'scorpion',
    'maybe': 'octopus',
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
],
    'text_data': 'dc8e96a59bd442a586fb430a4116f000',
    'rand_digit': 1,
    'rand_number': 0.08733,
    'rand_signed_int': 4,
    'rand_datetime': '2000-10-26T21:07:14.439941',
    'text_array': [
    '1599a056339544529d5e1f84763ca825',
    '2408b2bba15a4ef48ef63d5d1d9acc8c',
],
    'words': 'giraffe squid',
    'nested': {
    'id': 158,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
    7,
],
    [
    10,
],
],
    'two_words': [
    'snake',
    'goat',
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
    'mixed_type': 'hyena',
    'maybe_null': 'cat',
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
    '02',
    '23',
],
    'text_data': 'a7daf1cedef14206817fc87cd3fb3483',
    'rand_digit': 3,
    'rand_number': 0.95885,
    'rand_signed_int': 8,
    'rand_datetime': '2000-12-28T17:29:22.653275+01:00',
    'text_array': [
    '68556921dcde4a998a8066032041e31e',
    'af65e3756dd241358e436efa35d317cd',
],
    'words': 'duck cat',
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
    'word': 'dragonfly',
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
    'word': 'hippo',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -1,
],
    [
    2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dolphin',
    'dog',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'snake',
    'maybe_null': 'lion',
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
    '07',
    '23',
    '20',
    '06',
],
    'text_data': 'e69546ebfeb148d2808eae7ef8bffa37',
    'rand_digit': 6,
    'rand_number': 0.61476,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-03T17:18:40.047943+0900',
    'text_array': [
    'd449514c958c45a5a0682d0eda060398',
    'c825d8658b8e4c45bc2a55ecf24c68eb',
],
    'words': 'giraffe goat',
    'nested': {
    'id': 160,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'frog',
    'lizard',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'dog',
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
    '23',
    '10',
],
    'text_data': '15e346e8544549b483def4bedddc9480',
    'rand_digit': 8,
    'rand_number': 0.637,
    'rand_signed_int': -4,
    'rand_datetime': '2000-05-31 16:59',
    'text_array': [
    '9ff163167f5d4e86add8ce1e99042c24',
    '466421ef3a8c4552914a338e23dbacfb',
],
    'words': 'dog zebra',
    'nested': {
    'id': 161,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 2,
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
    'snail',
    'camel',
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
    'mixed_type': True,
    'maybe': 'hippo',
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
    '27',
    '13',
    '15',
],
    'text_data': '015dd49a8c55400abb3d3980107934f6',
    'rand_digit': 9,
    'rand_number': 0.62144,
    'rand_signed_int': 2,
    'rand_datetime': '2000-01-18T01:06:44.066426+0000',
    'text_array': [
    '75fb2e0111264fa0bef59983ecb503c3',
    '759d50fa0e9748409346e87ec3c236c4',
],
    'words': 'snail mosquito',
    'nested': {
    'id': 162,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    [
    7,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'cheetah',
    'sloth',
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
    'mixed_type': None,
    'maybe': 'sloth',
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
    '04',
    '16',
    '09',
    '17',
],
    'text_data': '9f4f01c8f19644ff9622b28812192a0c',
    'rand_digit': 8,
    'rand_number': 0.58881,
    'rand_signed_int': 4,
    'rand_datetime': '2000-04-21 15:00:11-0800',
    'text_array': [
    'cb74a401e1524cc1bc001213401ff352',
    '614be6a78a2d484d882e02383cfe3e59',
],
    'words': 'spider koala',
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
    'word': 'lobster',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'shark',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'snail',
    'sheep',
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
    'mixed_type': True,
    'maybe': 'ape',
    'maybe_null': 'rabbit',
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
        """测试请求 4 - POST http://localhost:6333/collections/congruence_test_collection/points/discover/batch"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/discover/batch")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/discover/batch'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '257',
}
        
        # 原始请求内容
        original_content = {
    'searches': [
    {
    'target': 10,
    'context': [
    {
    'positive': 15,
    'negative': 7,
},
],
    'limit': 5,
    'using': 'image',
},
    {
    'target': 11,
    'context': [
    {
    'positive': 15,
    'negative': 17,
},
],
    'limit': 6,
    'using': 'image',
    'lookup_from': {
    'collection': 'congruence_secondary_collection',
    'vector': 'image',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_discovery.test_discover_batch')
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
    test = TestDiscoverytestDiscoverBatch()
    test.run_tests()
