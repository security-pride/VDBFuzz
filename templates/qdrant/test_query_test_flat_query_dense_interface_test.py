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
logger = logging.getLogger('vdb_fuzzer.test.test_query_test_flat_query_dense_interface')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_query.test_flat_query_dense_interface"
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



class TestQuerytestFlatQueryDenseInterface:
    """自动生成的VDB模糊测试类 - test_query.test_flat_query_dense_interface"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_query.test_flat_query_dense_interface"
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
    'content-length': '138543',
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
    '16',
],
    'text_data': 'b22fc1196ff74cebaedc580d8b537b28',
    'rand_digit': 8,
    'rand_number': 0.07528,
    'rand_signed_int': -5,
    'rand_datetime': '2000-06-16 15:09:53',
    'text_array': [
    '600b063e8ce84026afd8ec804634289d',
    '56f719942b8342828bc87df3e3feb5b8',
],
    'words': 'crab deer',
    'nested': {
    'id': 100,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 6,
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
    'word': 'mouse',
    'number': 9,
},
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
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'crab',
    'hippo',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': [
    25,
],
    'rand_bool': False,
    'mixed_type': 'mosquito',
    'maybe': 'turtle',
    'maybe_null': 'mouse',
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
    '11',
    '27',
],
    'text_data': '63d344bed53d40cda0a3bb47c39a0375',
    'rand_digit': 2,
    'rand_number': 0.22503,
    'rand_signed_int': 2,
    'rand_datetime': '2000-11-12 10:12:34+0100',
    'text_array': [
    '037beaf6adbc48c792b81b78fc21ae78',
    'a534ef65a67f414b8eab96086b3401bb',
],
    'words': 'frog zebra',
    'nested': {
    'id': 101,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -4,
],
],
    'two_words': [
    'sloth',
    'hippo',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': [
    25,
],
    'rand_bool': False,
    'mixed_type': 'ladybug',
    'maybe': 'butterfly',
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
    '15',
],
    'text_data': 'fdf614e5c9f348219a358bee1feb7c4e',
    'rand_digit': 3,
    'rand_number': 0.7247,
    'rand_signed_int': -7,
    'rand_datetime': '2000-11-27 16:56',
    'text_array': [
    '1f2eeb600a76428aa27f81e0aa0f2780',
    '162c149cf8724566ab2211743cb4d5e2',
],
    'words': 'octopus shark',
    'nested': {
    'id': 102,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'elephant',
    'pig',
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
    '08',
    '21',
    '30',
    '04',
],
    'text_data': 'e5b2ee1172ee43a2aad71c0cc467cb56',
    'rand_digit': 8,
    'rand_number': 0.04293,
    'rand_signed_int': 8,
    'rand_datetime': '2000-08-19T04:23:34.277346',
    'text_array': [
    '0849b10a48e1445d904259f1c500fc8d',
    'e0a87e6350c64afb93ca2236773d0e4d',
],
    'words': 'hippo duck',
    'nested': {
    'id': 103,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'pig',
    'deer',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'sloth',
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
    '27',
    '26',
    '11',
    '28',
    '12',
],
    'text_data': '9f2c5d9a21aa46c7aed9896b601d2d64',
    'rand_digit': 8,
    'rand_number': 0.66849,
    'rand_signed_int': -10,
    'rand_datetime': '2001-01-19 08:44:31',
    'text_array': [
    '043292e472cd442b946cd1880dee3eb7',
    '43ed9eeef6ad40f9a81652094406da19',
],
    'words': 'squid gorilla',
    'nested': {
    'id': 104,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 2,
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
],
},
    'nested_array': [
    [
],
    [
    1,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'panda',
    'panda',
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
    'mixed_type': True,
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
    '06',
    '30',
    '06',
    '18',
    '03',
],
    'text_data': 'bfcafdf0151241cea1e55f3266098b7b',
    'rand_digit': 6,
    'rand_number': 0.6208,
    'rand_signed_int': 7,
    'rand_datetime': '2000-07-05',
    'text_array': [
    'f4fb404040f241d98a417687b0cc8996',
    'c588c31d5d5943b7bb63d53b8d5cbca9',
],
    'words': 'sheep crab',
    'nested': {
    'id': 105,
    'rand_digit': 9,
    'array': [
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
    'hello',
],
    'word': 'leopard',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 1,
},
    {
    'nested_empty': None,
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
],
    [
],
],
    'two_words': [
    'bear',
    'bird',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': [
    3,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'bird',
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
    '25',
    '11',
    '22',
    '18',
],
    'text_data': '3edeb354e9bb4b44bdbd0d603325f915',
    'rand_digit': 4,
    'rand_number': 0.30531,
    'rand_signed_int': -4,
    'rand_datetime': '2000-11-05 23:19:16',
    'text_array': [
    '4b8a85b7c1c24c7698e707a2bfb7b50a',
    '876cd2b8639b4ffab2bf68876497acb3',
],
    'words': 'bear ant',
    'nested': {
    'id': 106,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'zebra',
    'dog',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.30448,
    'maybe': 'rabbit',
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
    '11',
],
    'text_data': '8fb08f7ba3054b45b4dead81195f230e',
    'rand_digit': 7,
    'rand_number': 0.28303,
    'rand_signed_int': -5,
    'rand_datetime': '2000-12-11 18:47:37-0300',
    'text_array': [
    '2457083116734995afd31f986d484111',
    '0644bfa1c71a498aade5e23001e31809',
],
    'words': 'rhino whale',
    'nested': {
    'id': 107,
    'rand_digit': 9,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fish',
    'lobster',
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
    'mixed_type': 0.32286,
    'maybe': 'chicken',
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
],
    'text_data': '249b6e96577a43dabd6038b9e0f46148',
    'rand_digit': 2,
    'rand_number': 0.28814,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-13 17:19',
    'text_array': [
    'a85be076aead42d2b2285ae6f8258dc4',
    '98739d0812134cffa27e8508208fdeec',
],
    'words': 'bear spider',
    'nested': {
    'id': 108,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'shark',
    'number': 1,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snake',
    'mosquito',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': [
    40,
],
    'rand_bool': False,
    'mixed_type': 0.49293,
    'maybe_null': 'kangaroo',
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
    'text_data': 'da1fd906163744c985a52d55f35ac69f',
    'rand_digit': 2,
    'rand_number': 0.8358,
    'rand_signed_int': -7,
    'rand_datetime': '2000-07-14',
    'text_array': [
    'bfc53f46405940d4ad98a77f3aefbf80',
    '76cd9bff661447b9afd6085eab2859b6',
],
    'words': 'rhino frog',
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
    'word': 'butterfly',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
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
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'shark',
    'lion',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': [
    74,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '20',
],
    'text_data': 'd6071028524c4d28a115416d6ad9a70c',
    'rand_digit': 9,
    'rand_number': 0.51699,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-12T02:39:05-1200',
    'text_array': [
    '9d559b9e90674e7bb9687e86b51a1a5b',
    '95157ca7ebb942cfabbbaa2ed76a829b',
],
    'words': 'camel leopard',
    'nested': {
    'id': 110,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'gorilla',
    'bird',
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
    'mixed_type': 'dog',
    'maybe': 'fox',
    'maybe_null': None,
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
    '27',
    '28',
    '20',
    '11',
],
    'text_data': '5370905246924042a6aff5970590309c',
    'rand_digit': 3,
    'rand_number': 0.88777,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-07 20:01',
    'text_array': [
    'cbe11a2534cf4e458f47e0e507a161f1',
    '7f05e09295d040e5b98cce818a9424df',
],
    'words': 'dragonfly mouse',
    'nested': {
    'id': 111,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    10,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'lobster',
    'dragonfly',
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
    'mixed_type': 0.37362,
    'maybe': 'sloth',
    'maybe_null': 'sheep',
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
    'text_data': '2d7608acd7e4404cbcc3f51b673f5725',
    'rand_digit': 4,
    'rand_number': 0.57202,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-25T20:38:37',
    'text_array': [
    '2a1b073967aa47c0a0ef0ef37f101320',
    'da546ff377b24ebc91bf39b7bef5b770',
],
    'words': 'lizard cow',
    'nested': {
    'id': 112,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'wolf',
    'number': 7,
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
],
    'word': 'wolf',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    [
],
    [
    -5,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ape',
    'dog',
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
    '04',
    '04',
    '21',
    '13',
],
    'text_data': '00dcf102afdd4ca98cabcef4335a6fa9',
    'rand_digit': 1,
    'rand_number': 0.42615,
    'rand_signed_int': 5,
    'rand_datetime': '2001-01-06T18:17:54-1200',
    'text_array': [
    '7de01f275e4a43a297896f4f3391887d',
    'ebf350b3e66041bd9f3f16c2303e4258',
],
    'words': 'crab crab',
    'nested': {
    'id': 113,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'jaguar',
    'lizard',
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
    'mixed_type': 'scorpion',
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
    '11',
    '18',
    '12',
],
    'text_data': '23f5fc2e0e0340489f9e497955ce5ce9',
    'rand_digit': 1,
    'rand_number': 0.53885,
    'rand_signed_int': 10,
    'rand_datetime': '2000-08-15 15:41:05-0700',
    'text_array': [
    '666d2e57f47b4155bf8754ea2cbe2e07',
    'eefe75dcaaa94bb2b893c75bda1cb6e2',
],
    'words': 'zebra dog',
    'nested': {
    'id': 114,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    [
    -8,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'cow',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'mouse',
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
    'text_data': 'd5cd74975178475c9df24136ca80a8f8',
    'rand_digit': 8,
    'rand_number': 0.24432,
    'rand_signed_int': 1,
    'rand_datetime': '2000-12-21T01:24:07.430839',
    'text_array': [
    '34827eaa83034cc18b8f043d425641b5',
    'af7fb58d643b41ceb13dd44662666e1f',
],
    'words': 'whale frog',
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
    'word': 'ladybug',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'lobster',
    'snake',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': [
    22,
],
    'rand_bool': False,
    'mixed_type': 'dog',
    'maybe_null': 'elephant',
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
    '19',
],
    'text_data': '97f2d08654de423b8e18a5470a851c41',
    'rand_digit': 3,
    'rand_number': 0.32431,
    'rand_signed_int': -1,
    'rand_datetime': '2000-01-20',
    'text_array': [
    'ea8f79deabd24dc399e1af991a2e1a28',
    'a578b8404e214418bb7bee275ac6a0a7',
],
    'words': 'mosquito duck',
    'nested': {
    'id': 116,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'horse',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'zebra',
    'camel',
],
    'city': {
    'name': 'Riga',
    'geo': {
    'lat': 56.949649,
    'lon': 24.105186,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'bird',
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
    '23',
    '02',
],
    'text_data': '94fa61c973d24589a00f721772fa7bb9',
    'rand_digit': 3,
    'rand_number': 0.54603,
    'rand_signed_int': 5,
    'rand_datetime': '2000-04-27T12:45:34.176634',
    'text_array': [
    '33b49de072724702a687cbdffbfe31da',
    'c84da56ca81f4639a6cf46bb293d645b',
],
    'words': 'elephant pig',
    'nested': {
    'id': 117,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'grasshopper',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'camel',
    'sloth',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'ant',
    'maybe_null': 'giraffe',
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
    '24',
    '26',
    '20',
    '23',
],
    'text_data': '37601dec66fe47588c9a28ef1a260afe',
    'rand_digit': 4,
    'rand_number': 0.7743,
    'rand_signed_int': -5,
    'rand_datetime': '2000-11-08 13:45:03.644282+0400',
    'text_array': [
    '86c4662c1ea44a0d859ece76c8de9558',
    'e013586cedc448bda4c9c92c695a6f41',
],
    'words': 'grasshopper camel',
    'nested': {
    'id': 118,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 8,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'shark',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 9,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -8,
],
],
    'two_words': [
    'mosquito',
    'wolf',
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
    'maybe_null': 'lizard',
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
    '26',
    '14',
],
    'text_data': '68586921ddf74175883539da57142887',
    'rand_digit': 5,
    'rand_number': 0.4116,
    'rand_signed_int': 1,
    'rand_datetime': '2000-08-02T16:19:36.631860-0900',
    'text_array': [
    'e3d358c2bf89496ba154c507ae785983',
    '1182f8225f0348c59f32d371032193f9',
],
    'words': 'horse whale',
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
    'word': 'giraffe',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lobster',
    'fox',
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
    'mixed_type': 8,
    'maybe_null': 'hyena',
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
    '30',
    '23',
    '01',
],
    'text_data': 'd50b08475aa444749926cc153322c3aa',
    'rand_digit': 0,
    'rand_number': 0.0816,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-23T22:20:54.451172',
    'text_array': [
    '17c8095b55004b1889fdca0fc5350f83',
    'dfc8cc947fcf4450b8b62b035c2ff302',
],
    'words': 'cheetah kangaroo',
    'nested': {
    'id': 120,
    'rand_digit': 3,
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
    'hello',
],
    'word': 'whale',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 6,
},
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
    [
],
],
    'two_words': [
    'duck',
    'lion',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': [
    35,
],
    'rand_bool': False,
    'mixed_type': 'leopard',
    'maybe': 'cow',
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
    '20',
    '17',
],
    'text_data': 'a231d686388b4e5b86e27c0fabf65888',
    'rand_digit': 7,
    'rand_number': 0.83211,
    'rand_signed_int': -3,
    'rand_datetime': '2000-08-06T10:33:04.710948-0900',
    'text_array': [
    '7b590ee7e26a4090be0180b1c04b54ca',
    '911b7a46b9294664be9252053e230bf1',
],
    'words': 'ant butterfly',
    'nested': {
    'id': 121,
    'rand_digit': 7,
    'array': [
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
    'word': 'lizard',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dog',
    'leopard',
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
    'mixed_type': True,
    'maybe': 'fly',
    'maybe_null': 'hippo',
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
    '12',
    '13',
    '02',
    '06',
],
    'text_data': '77ebb4f180b24d53a7fc68509a1d14e8',
    'rand_digit': 2,
    'rand_number': 0.0948,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-24 08:24:52.603505',
    'text_array': [
    'ac04d5b7727a486aa875b60a34a6b230',
    '2db7afc5b47c4eddaa9a54f42a0cb8a0',
],
    'words': 'sheep zebra',
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
    'word': 'hyena',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mouse',
    'lizard',
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
    'mixed_type': 8,
    'maybe': 'butterfly',
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
],
    'text_data': '1db15f5c42434981967f8d451722a962',
    'rand_digit': 8,
    'rand_number': 0.19582,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-15T15:57:48.042404-0400',
    'text_array': [
    '337759ffc89f4b43a1e2a4906bd48c05',
    'e306de13ab934515a97445f0f139c059',
],
    'words': 'turtle pig',
    'nested': {
    'id': 123,
    'rand_digit': 4,
    'array': [
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -4,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snake',
    'duck',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': [
    48,
],
    'rand_bool': False,
    'mixed_type': 'sloth',
    'maybe_null': 'lizard',
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
    '07',
],
    'text_data': 'd8271fd1421140ef92cd254877ee154f',
    'rand_digit': 4,
    'rand_number': 0.40337,
    'rand_signed_int': 7,
    'rand_datetime': '2000-02-25 15:20:12+1100',
    'text_array': [
    '35046bd7e4c44599a02cdf7ee181a4dc',
    'f4f2872643b545478730381dc4b9e678',
],
    'words': 'dolphin goat',
    'nested': {
    'id': 124,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 8,
},
    {
    'nested_empty': None,
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
],
    'word': 'dragonfly',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
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
],
},
    'nested_array': [
    [
],
    [
],
    [
    -9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    2,
],
],
    'two_words': [
    'hippo',
    'fish',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'shark',
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
    '18',
],
    'text_data': '34c391b1fc1c4e42be2133edcae923b3',
    'rand_digit': 7,
    'rand_number': 0.21609,
    'rand_signed_int': -9,
    'rand_datetime': '2000-06-17T20:07:45.781559',
    'text_array': [
    '2f3a8e41587a481189d8179c1fcffec7',
    'f71ea6301a8747ca81397f0515ea0b4b',
],
    'words': 'cow ant',
    'nested': {
    'id': 125,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'bear',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -4,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'deer',
    'sloth',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'monkey',
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
],
    'text_data': '3d8a691099824bd19f6fdc4526bba826',
    'rand_digit': 0,
    'rand_number': 0.37052,
    'rand_signed_int': -2,
    'rand_datetime': '2000-08-27 00:12:32',
    'text_array': [
    '27aab0558c3a400da87c44f3ac964e66',
    'cf8d69ef0b82439daab121c7454bc154',
],
    'words': 'mosquito sloth',
    'nested': {
    'id': 126,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    5,
],
],
    'two_words': [
    'zebra',
    'snake',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'spider',
    'maybe_null': 'octopus',
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
    'text_data': 'b3dec449a182420abc82503aa288623c',
    'rand_digit': 7,
    'rand_number': 0.90806,
    'rand_signed_int': -1,
    'rand_datetime': '2001-01-17 19:37:55.557020-1000',
    'text_array': [
    '9b6fcb840d59438c8b1f521bf2c655a4',
    'e44f3e8d68cd4288a23b6ab4285d12e1',
],
    'words': 'pig duck',
    'nested': {
    'id': 127,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 8,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_4,5__',
    'two_words': [
    'pig',
    'frog',
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
    'mixed_type': None,
    'maybe_null': 'spider',
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
    '11',
    '06',
    '09',
    '25',
    '03',
],
    'text_data': 'be9e0046edd44bedbec1c7ad5810e137',
    'rand_digit': 4,
    'rand_number': 0.72072,
    'rand_signed_int': 5,
    'rand_datetime': '2001-01-12 14:55:09+1100',
    'text_array': [
    'dad5175b860b41fc8c849fb374bc203a',
    '8e5e199144ae4069b474b68f6ba22cab',
],
    'words': 'rhino dragonfly',
    'nested': {
    'id': 128,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'koala',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'gorilla',
    'octopus',
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
    'mixed_type': 'hippo',
    'maybe_null': 'gorilla',
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
    '25',
    '06',
    '30',
    '27',
],
    'text_data': 'd08666ac9a144f81b3e48ad01f29a133',
    'rand_digit': 9,
    'rand_number': 0.67302,
    'rand_signed_int': 0,
    'rand_datetime': '2000-05-21 08:09:28+0900',
    'text_array': [
    'c8c6191627d544439fde32eeb7d66a50',
    '08283315552d434394b5499f9a07a7f8',
],
    'words': 'deer rhino',
    'nested': {
    'id': 129,
    'rand_digit': 2,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'wolf',
    'fox',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 4,
    'maybe_null': 'giraffe',
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
],
    'text_data': '75d6f17321de4a8b8ee43383efe2953a',
    'rand_digit': 7,
    'rand_number': 0.14341,
    'rand_signed_int': 6,
    'rand_datetime': '2000-08-23',
    'text_array': [
    '73ea2254e1754f9ba09a79d22084a4c0',
    '25023f95d5974bf5a10edeee7df44263',
],
    'words': 'chicken panda',
    'nested': {
    'id': 130,
    'rand_digit': 8,
    'array': [
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
    'word': 'mosquito',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 3,
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dolphin',
    'scorpion',
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
    'maybe': 'horse',
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
    '11',
    '29',
    '25',
    '07',
],
    'text_data': '088bc165582c4ae09dca1886587b3a8d',
    'rand_digit': 9,
    'rand_number': 0.54077,
    'rand_signed_int': 8,
    'rand_datetime': '2000-05-23 00:37:10.125888',
    'text_array': [
    'd0a18b43319944a1939bd6af9e99b932',
    'b62fcd20f48f469d90ee75c99158df36',
],
    'words': 'snake rabbit',
    'nested': {
    'id': 131,
    'rand_digit': 3,
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
    'word': 'scorpion',
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
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 1,
},
],
},
    'nested_array': [
    [
    -2,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'snail',
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
    38,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'goat',
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
    '08',
    '22',
    '24',
],
    'text_data': '51bd4f3a9d114d148810a0229273b5bf',
    'rand_digit': 1,
    'rand_number': 0.23872,
    'rand_signed_int': 6,
    'rand_datetime': '2000-10-12T02:32:47-0400',
    'text_array': [
    '2ecc09e805274e2aa5c803470972290a',
    '3119cf5ae3d949798d12bf072f4c67be',
],
    'words': 'tiger leopard',
    'nested': {
    'id': 132,
    'rand_digit': 9,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 6,
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
    'word': 'bird',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'horse',
    'tiger',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': [
    8,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
],
    'text_data': 'e246b9595d47448a89fa462edaaa4680',
    'rand_digit': 3,
    'rand_number': 0.14757,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-10T09:42:59.421448',
    'text_array': [
    '03c4c4d9074d472d960f7441255b58c6',
    'f07eb8894bc44c859e3fbb02007f1254',
],
    'words': 'lion cat',
    'nested': {
    'id': 133,
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
    'goat',
    'jaguar',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.73537,
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
    '15',
    '08',
],
    'text_data': 'f7e577d3847e4ff0893143701f57bdca',
    'rand_digit': 2,
    'rand_number': 0.61867,
    'rand_signed_int': 0,
    'rand_datetime': '2001-01-11 13:54:00',
    'text_array': [
    '58ca29c30c984d7e9bcba26b6fbd11a6',
    '623fdcaa8db94cc58de11adc3cc30f8f',
],
    'words': 'zebra leopard',
    'nested': {
    'id': 134,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'chicken',
    'fish',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': [
    77,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'jaguar',
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
    '16',
    '03',
    '11',
    '15',
    '04',
],
    'text_data': 'b557e6b476ac4bada527de492ba9a43f',
    'rand_digit': 3,
    'rand_number': 0.37696,
    'rand_signed_int': 0,
    'rand_datetime': '2000-06-05T03:04:51+0900',
    'text_array': [
    '60a191a1829e46ceb674ae424d20a663',
    'e1b2b51d15b84575a9a10228530dd12b',
],
    'words': 'mosquito butterfly',
    'nested': {
    'id': 135,
    'rand_digit': 7,
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
    'word': 'lion',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'leopard',
    'fish',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': [
    55,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'horse',
    'maybe_null': 'crab',
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
    '24',
],
    'text_data': '0ef1a6ad942d46a3bff59b68564f6359',
    'rand_digit': 9,
    'rand_number': 0.96529,
    'rand_signed_int': 3,
    'rand_datetime': '2000-09-18T18:27:09',
    'text_array': [
    '4454eba800ab4774b4fe276ab4c8cc0b',
    '51843d22e3ff4083a534cd779d669395',
],
    'words': 'kangaroo lizard',
    'nested': {
    'id': 136,
    'rand_digit': 4,
    'array': [
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
    'word': 'snail',
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
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    10,
],
],
    'two_words': [
    'hyena',
    'cat',
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
    'mixed_type': 'kangaroo',
    'maybe': 'octopus',
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
    '06',
    '10',
],
    'text_data': '35000c3960d14b5c9a2a0ec52aca3ff1',
    'rand_digit': 6,
    'rand_number': 0.24136,
    'rand_signed_int': 8,
    'rand_datetime': '2000-03-12T17:13:26.064075',
    'text_array': [
    '53e70b65258d4392b52d25cbef79987e',
    'e5ac575f9c8d4c879e654e73dd4a7b5b',
],
    'words': 'mouse bee',
    'nested': {
    'id': 137,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'bear',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 4,
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
    'hippo',
    'horse',
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
    'mixed_type': {
    'key': 'value',
},
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
],
    'text_data': '4edf26c9c8bb47f5a3aebc88567a624c',
    'rand_digit': 6,
    'rand_number': 0.57597,
    'rand_signed_int': 7,
    'rand_datetime': '2000-10-05',
    'text_array': [
    '656f6d9c896a4560a3fe2fdc8b82a085',
    'ba2e0d9a70354840863aeb918d401071',
],
    'words': 'octopus sheep',
    'nested': {
    'id': 138,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'pig',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'octopus',
    'scorpion',
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
    'mixed_type': 7,
    'maybe': 'fish',
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
    '15',
    '09',
    '12',
],
    'text_data': 'e8f684fc6cc148a3887a03cc6f290c46',
    'rand_digit': 1,
    'rand_number': 0.09186,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-21T16:36:38+1200',
    'text_array': [
    'f013a1bb3b2342da88236724cab89fc3',
    '9df1a40f26d0409e8c2e804a8d8d5994',
],
    'words': 'kangaroo grasshopper',
    'nested': {
    'id': 139,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 8,
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
    'word': 'ant',
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'pig',
    'dolphin',
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
    'mixed_type': True,
    'maybe': 'deer',
    'maybe_null': 'tiger',
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
],
    'text_data': '38c7d89f65064018b15184e384c737ff',
    'rand_digit': 6,
    'rand_number': 0.66848,
    'rand_signed_int': 7,
    'rand_datetime': '2000-07-12T17:37:58.758406',
    'text_array': [
    '1c7c56fd9fcb4fd280da18345363373c',
    'edcedb2611b848e88df11a1ffe586c83',
],
    'words': 'rabbit koala',
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
    'word': 'monkey',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'panda',
    'number': 5,
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
],
},
    'nested_array': [
],
    'two_words': [
    'ape',
    'leopard',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': [
    61,
],
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'wolf',
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
    '22',
],
    'text_data': '29610f8b50144c0abd91ff81ff8f0f05',
    'rand_digit': 2,
    'rand_number': 0.52918,
    'rand_signed_int': -4,
    'rand_datetime': '2000-06-04 23:16:53',
    'text_array': [
    '4d7cff679e1d498e9fd4f9011ea822e4',
    '673529fd725d48be8812c25a78f444d2',
],
    'words': 'deer frog',
    'nested': {
    'id': 141,
    'rand_digit': 9,
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
],
    'word': 'squid',
    'number': 1,
},
],
},
    'nested_array': [
    [
    5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'gorilla',
    'ladybug',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': [
    56,
],
    'rand_bool': True,
    'mixed_type': True,
    'maybe_null': 'cheetah',
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
    '23',
    '29',
],
    'text_data': 'e49bd5164ce24d0db76e04e6d27fa4b4',
    'rand_digit': 5,
    'rand_number': 0.4185,
    'rand_signed_int': -5,
    'rand_datetime': '2000-12-14 09:47',
    'text_array': [
    'a6a0309a7a304160930a0cc75ca2530d',
    'f5238f29d9a444a1857955d27010ad6d',
],
    'words': 'giraffe fish',
    'nested': {
    'id': 142,
    'rand_digit': 8,
    'array': [
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
    'dragonfly',
    'scorpion',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': [
    50,
],
    'rand_bool': True,
    'mixed_type': 'gorilla',
    'maybe_null': 'cheetah',
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
    '03',
    '27',
    '30',
    '02',
    '18',
],
    'text_data': '7bf54dfe24c8467386c4b66030108dda',
    'rand_digit': 7,
    'rand_number': 0.12128,
    'rand_signed_int': -3,
    'rand_datetime': '2000-02-11',
    'text_array': [
    '9f4d742bcb6844469480d9bbec979b4e',
    'a57fe6bb40234e7198e3847551c13d74',
],
    'words': 'gorilla elephant',
    'nested': {
    'id': 143,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'dolphin',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 2,
},
],
},
    'nested_array': [
    [
    2,
],
],
    'two_words': [
    'dog',
    'camel',
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
    'mixed_type': None,
    'maybe': 'bird',
    'maybe_null': 'cow',
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
    'text_data': '5ed9b4bac2ae452c951e00e59873543e',
    'rand_digit': 4,
    'rand_number': 0.09164,
    'rand_signed_int': -6,
    'rand_datetime': '2000-06-14 04:07:28.376702-1000',
    'text_array': [
    'be6717733560483fbc539b276f72fd56',
    '67a01d804ea74943932237ecda966709',
],
    'words': 'mosquito crab',
    'nested': {
    'id': 144,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'fish',
    'number': 1,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'leopard',
    'dolphin',
],
    'city': {
    'name': 'Johannesburg',
    'geo': {
    'lat': -26.204103,
    'lon': 28.047305,
},
},
    'rand_tuple': [
    16,
],
    'rand_bool': False,
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
    '15',
    '08',
    '25',
    '29',
    '01',
],
    'text_data': '1b5fffc8f7404b2b98334091dfe1b0ed',
    'rand_digit': 8,
    'rand_number': 0.90942,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-10T14:51:27',
    'text_array': [
    '940750e94ab144fba3c56a44144a8002',
    '96d563e31f144051a87e4c34dde03fe7',
],
    'words': 'ladybug goat',
    'nested': {
    'id': 145,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 3,
},
    {
    'nested_empty': None,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'grasshopper',
    'butterfly',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': [
    31,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'dog',
    'maybe_null': 'horse',
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
    '25',
    '06',
    '14',
],
    'text_data': 'c66d1a0b913341afa4320900ef62907b',
    'rand_digit': 5,
    'rand_number': 0.20387,
    'rand_signed_int': -1,
    'rand_datetime': '2001-01-05 16:03',
    'text_array': [
    'de07dd4fcf034e07842c0e73115011dd',
    '5d64173766db4ac8a609c592a774dde0',
],
    'words': 'crab giraffe',
    'nested': {
    'id': 146,
    'rand_digit': 8,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'whale',
    'cat',
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
    'maybe_null': 'butterfly',
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
    '17',
    '04',
    '18',
    '25',
    '27',
],
    'text_data': '6a891f58837744a6819a23be6f84ec6f',
    'rand_digit': 6,
    'rand_number': 0.25777,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-15 08:42:43+0000',
    'text_array': [
    '5cea60a21f0f4226bac4b0afd5acf641',
    'f27a28ccdfe148aca47626ba63030851',
],
    'words': 'spider turtle',
    'nested': {
    'id': 147,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 3,
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
    'word': 'rhino',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'squid',
    'ant',
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
    'mixed_type': 4,
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
    '06',
    '06',
    '29',
    '28',
],
    'text_data': '85fec3ac63314ccab79d691b30bfa3e1',
    'rand_digit': 6,
    'rand_number': 0.60487,
    'rand_signed_int': 6,
    'rand_datetime': '2000-11-18 16:49:29.412567+0300',
    'text_array': [
    '9ed5a5d69a804ed49cf7fb866eedca9a',
    '26f49570ca9e45058a84c3011c11fe48',
],
    'words': 'goat bird',
    'nested': {
    'id': 148,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 8,
},
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
],
},
    'nested_array': [
],
    'two_words': [
    'dolphin',
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
    'mixed_type': False,
    'maybe': 'frog',
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
    '24',
    '22',
    '25',
],
    'text_data': '2c0256b7a59a466a8f08dec47d2948da',
    'rand_digit': 3,
    'rand_number': 0.22309,
    'rand_signed_int': -7,
    'rand_datetime': '2000-03-26T07:54:28',
    'text_array': [
    '5f52b8c758fa46f7a947cfb7e95359c1',
    '86e63d7179004cc5b3e621484571cc56',
],
    'words': 'lizard hyena',
    'nested': {
    'id': 149,
    'rand_digit': 6,
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
    'hello',
],
    'word': 'ape',
    'number': 9,
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
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'snake',
    'jaguar',
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
    'mixed_type': 0.56345,
    'maybe_null': 'grasshopper',
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
    '22',
    '07',
    '22',
    '26',
    '21',
],
    'text_data': 'bc6dae3df8a64b9486d49e4163d4af04',
    'rand_digit': 4,
    'rand_number': 0.02033,
    'rand_signed_int': -1,
    'rand_datetime': '2000-05-15T12:05:23.186106',
    'text_array': [
    'a5aebdcbd25343e3a2fa83d65e581b82',
    'fa499616fd1749859e814637cbd68d6d',
],
    'words': 'hippo pig',
    'nested': {
    'id': 150,
    'rand_digit': 4,
    'array': [
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
    'word': 'elephant',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'pig',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'whale',
    'duck',
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
    'mixed_type': None,
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
    '27',
    '27',
    '09',
    '24',
],
    'text_data': '47fd4063620c4aaba94248b74846fcd4',
    'rand_digit': 7,
    'rand_number': 0.26794,
    'rand_signed_int': 3,
    'rand_datetime': '2000-12-09T23:24:27.719487',
    'text_array': [
    '158690dabba64bf398764e6f82b64d95',
    'cf95f85628434025861056f9d4e4f069',
],
    'words': 'ladybug ant',
    'nested': {
    'id': 151,
    'rand_digit': 7,
    'array': [
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
],
    'word': 'turtle',
    'number': 3,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'hyena',
    'bear',
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
    'mixed_type': 'cheetah',
    'maybe': 'mouse',
    'maybe_null': 'chicken',
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
    '04',
    '06',
    '14',
    '30',
],
    'text_data': 'c8b5e07884c54b5585d5670cc212d1ae',
    'rand_digit': 8,
    'rand_number': 0.54591,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-22',
    'text_array': [
    '3363a521fc2f4a1c9b8860921622e53e',
    '3bf0a57e2d4843daaaeab19762b78b2b',
],
    'words': 'lion jaguar',
    'nested': {
    'id': 152,
    'rand_digit': 5,
    'array': [
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
    'word': 'cheetah',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fox',
    'gorilla',
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
    'mixed_type': 'leopard',
    'maybe_null': 'lizard',
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
    '15',
    '09',
    '15',
    '06',
],
    'text_data': 'f953b57d64ce4345b8b0b22d2c6cd733',
    'rand_digit': 8,
    'rand_number': 0.8367,
    'rand_signed_int': -10,
    'rand_datetime': '2000-11-25T20:12:28.947987-06:00',
    'text_array': [
    '5c451941bfb34495b1cb35a2796f0b77',
    '8ff428cb2fc3452fac9ea46443562c54',
],
    'words': 'wolf lizard',
    'nested': {
    'id': 153,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 5,
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
    'word': 'dragonfly',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    5,
],
],
    'two_words': [
    'mouse',
    'spider',
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
    'maybe_null': 'koala',
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
    '13',
    '21',
],
    'text_data': '06f79bc6d294469ea62e6022ba5309e5',
    'rand_digit': 3,
    'rand_number': 0.94701,
    'rand_signed_int': -6,
    'rand_datetime': '2000-02-05T00:03:18.018354+12:00',
    'text_array': [
    '09f6f9a675624990b1ce199941a1e861',
    '56e02b910ab04c7587c01b6cdd49e45c',
],
    'words': 'ant horse',
    'nested': {
    'id': 154,
    'rand_digit': 1,
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
    'word': 'grasshopper',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snail',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'octopus',
    'lobster',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': [
    9,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
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
    '01',
    '02',
    '12',
],
    'text_data': '191389babcd5449ebf9b1a025bd8bdf5',
    'rand_digit': 0,
    'rand_number': 0.70589,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-21T12:14:14',
    'text_array': [
    'd7baaf22bf3d408ba577d94bd3f5390a',
    'ada2c3d93b804af1abd13408034def6d',
],
    'words': 'jaguar gorilla',
    'nested': {
    'id': 155,
    'rand_digit': 4,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 3,
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
    'lion',
    'leopard',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'zebra',
    'maybe_null': 'scorpion',
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
    '07',
    '17',
    '04',
    '04',
    '27',
],
    'text_data': 'eb66137543064de2a02147bcc1e8b31d',
    'rand_digit': 4,
    'rand_number': 0.61546,
    'rand_signed_int': -2,
    'rand_datetime': '2000-04-19T07:20:46',
    'text_array': [
    '33aea618eef04afc96c84b2d5cb2b04c',
    'ec6310565fe646bab0729903cf9afb7b',
],
    'words': 'zebra sloth',
    'nested': {
    'id': 156,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'camel',
    'turtle',
],
    'city': {
    'name': 'Frankfurt',
    'geo': {
    'lat': 50.110922,
    'lon': 8.682127,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
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
    '12',
    '11',
],
    'text_data': '05f313acdbbc4a4f9f87f305e28f325f',
    'rand_digit': 3,
    'rand_number': 0.10543,
    'rand_signed_int': -2,
    'rand_datetime': '2000-08-30T12:27:56',
    'text_array': [
    '4bbc81e0af8846828c645f2f60e99a27',
    '0ac66b1c84704785934f9c40865a3ce7',
],
    'words': 'lizard giraffe',
    'nested': {
    'id': 157,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 8,
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
    'name': 'Kuala Lumpur',
    'geo': {
    'lat': 3.139003,
    'lon': 101.686855,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'lizard',
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
    '20',
    '23',
    '29',
],
    'text_data': 'b13357ce679f4839bff6e8b3f386a850',
    'rand_digit': 1,
    'rand_number': 0.1679,
    'rand_signed_int': -10,
    'rand_datetime': '2000-12-28 23:48',
    'text_array': [
    'baeccd2f90cd48a0a7e32b74c6d0cca3',
    'ebdb55bab6e04c298958ccd69bce4f4a',
],
    'words': 'butterfly panda',
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
    'word': 'bear',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 1,
},
    {
    'nested_empty': None,
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
    'word': 'frog',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lion',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    8,
],
],
    'two_words': [
    'ant',
    'rhino',
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
    'mixed_type': None,
    'maybe': 'bee',
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
    '20',
    '17',
    '02',
    '27',
    '30',
],
    'text_data': '72e9b7d608c446e2a8f77581c650caec',
    'rand_digit': 8,
    'rand_number': 0.73998,
    'rand_signed_int': -5,
    'rand_datetime': '2000-02-16T10:43:44.241635',
    'text_array': [
    '2f7f79b60b1448d69a4e47016204cfa5',
    '9cc2e2fe28c242899f8378732245ab95',
],
    'words': 'bird lion',
    'nested': {
    'id': 159,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'turtle',
    'horse',
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
    'maybe': 'bear',
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
    '08',
    '11',
    '15',
    '16',
],
    'text_data': '9de072cf56a54271b658326461945499',
    'rand_digit': 8,
    'rand_number': 0.23937,
    'rand_signed_int': -10,
    'rand_datetime': '2000-12-24T12:49:52',
    'text_array': [
    '59a74c558a504dce9db34844db72f03b',
    'cf1cb3ee6a1c4c7aa3dc02ddfceb05f3',
],
    'words': 'chicken shark',
    'nested': {
    'id': 160,
    'rand_digit': 3,
    'array': [
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
],
    'word': 'turtle',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
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
    'number': 7,
},
],
},
    'nested_array': [
    [
    3,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'cow',
    'fox',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
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
    '12',
    '09',
    '13',
    '27',
],
    'text_data': '7c0ebf6d6a8848c69fb45ced928ee90e',
    'rand_digit': 3,
    'rand_number': 0.89266,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-29T21:25:32+0400',
    'text_array': [
    '3e41b5d8ef834ddbac0038bc5c732ef4',
    'ea5fa19576a048d8807db90013b963d2',
],
    'words': 'ant snail',
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
    'word': 'ape',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'frog',
    'leopard',
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
    'mixed_type': 'lion',
    'maybe': 'frog',
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
    '10',
    '10',
    '07',
    '02',
],
    'text_data': '28314c0b4fe748c78da941f6ac4458a7',
    'rand_digit': 8,
    'rand_number': 0.27687,
    'rand_signed_int': 6,
    'rand_datetime': '2000-10-29T22:23:27.011439',
    'text_array': [
    'b0048dbfb23c474893360912ee566d9c',
    'cd96389b6aa9443db6e5d8a5329ddb66',
],
    'words': 'monkey zebra',
    'nested': {
    'id': 162,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'zebra',
    'fly',
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
    'mixed_type': 0.21765,
    'maybe': 'zebra',
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
],
    'text_data': '471f89c889d84d61b4b0a5ca8fd2a37b',
    'rand_digit': 0,
    'rand_number': 0.21972,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-13 15:35',
    'text_array': [
    'd52a58aa8c39490d80ce0e9b70fefeb2',
    '772be4bbace148aba9734703a63558cf',
],
    'words': 'turtle octopus',
    'nested': {
    'id': 163,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'butterfly',
    'chicken',
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
    'mixed_type': 0.7981,
    'maybe': 'fox',
    'maybe_null': 'scorpion',
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
    'content-length': '1052',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'using': 'text',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_query.test_flat_query_dense_interface')
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
    test = TestQuerytestFlatQueryDenseInterface()
    test.run_tests()
