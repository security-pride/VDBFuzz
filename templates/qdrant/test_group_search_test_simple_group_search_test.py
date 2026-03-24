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
logger = logging.getLogger('vdb_fuzzer.test.test_group_search_test_simple_group_search')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_group_search.test_simple_group_search"
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



class TestGroupSearchtestSimpleGroupSearch:
    """自动生成的VDB模糊测试类 - test_group_search.test_simple_group_search"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_group_search.test_simple_group_search"
        self.test_count = 35  # 测试方法数量
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
    'content-length': '137668',
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
    '24',
],
    'text_data': '075546d0bca14c0790e55ff6afcd1d2a',
    'rand_digit': 5,
    'rand_number': 0.77074,
    'rand_signed_int': -2,
    'rand_datetime': '2000-09-15 09:25:56.506988',
    'text_array': [
    '56524629fcb3486b9d5c04e77fd5a94a',
    '6f0b3edaae4645619d6a72bcc5d5af82',
],
    'words': 'bee lizard',
    'nested': {
    'id': 100,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'ant',
    'bird',
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
    'maybe': 'squid',
    'maybe_null': 'whale',
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
    '13',
    '24',
    '03',
],
    'text_data': 'c85a717f29ee455da0d1f302504ef9b5',
    'rand_digit': 7,
    'rand_number': 0.62396,
    'rand_signed_int': -4,
    'rand_datetime': '2000-07-15T07:05:30.964347+05:00',
    'text_array': [
    'ede73a8cf8b545ce8e03c1f403de6b9f',
    '1d547123b894491b9aa3d4b0f11da882',
],
    'words': 'bird butterfly',
    'nested': {
    'id': 101,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bear',
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'gorilla',
    'chicken',
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
    'mixed_type': 'fox',
    'maybe': 'sheep',
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
    '16',
    '09',
    '19',
    '08',
],
    'text_data': 'a75225bbb6904ac6a8529c6e9bd96e42',
    'rand_digit': 7,
    'rand_number': 0.71291,
    'rand_signed_int': -1,
    'rand_datetime': '2000-09-16T21:00:44.674335-06:00',
    'text_array': [
    '0151be017aa8463f8985c632413544fc',
    '9929d33abe734148be47e46f223d7caa',
],
    'words': 'squid grasshopper',
    'nested': {
    'id': 102,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
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
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
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
    'leopard',
    'monkey',
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
    'mixed_type': 'duck',
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
    '02',
],
    'text_data': '2da0f10537854271acbac1bd9bc3ed3c',
    'rand_digit': 0,
    'rand_number': 0.79511,
    'rand_signed_int': 9,
    'rand_datetime': '2000-02-12T14:51:38.379345+04:00',
    'text_array': [
    'f42a2032cd934c579c9fc5cd45f995d2',
    '22e20ca24b3847bb97d7148cf6e28536',
],
    'words': 'elephant bear',
    'nested': {
    'id': 103,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'ladybug',
    'pig',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': [
    22,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'sloth',
    'maybe_null': 'rabbit',
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
    '25',
    '16',
],
    'text_data': 'c3e40dca95ff4ab38e01895ad5a721fe',
    'rand_digit': 1,
    'rand_number': 0.11397,
    'rand_signed_int': 2,
    'rand_datetime': '2001-01-25T02:16:00.123762+01:00',
    'text_array': [
    'cf8c213d4ed444c1b72d8cda833ee417',
    'ce7291df9c654c4b9a05ca146af2c00b',
],
    'words': 'giraffe lobster',
    'nested': {
    'id': 104,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'hippo',
    'dog',
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
    'mixed_type': 'shark',
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
    '08',
    '15',
    '03',
    '25',
    '25',
],
    'text_data': '237fcedd3ef6401ab3747242b54f6981',
    'rand_digit': 3,
    'rand_number': 0.65182,
    'rand_signed_int': 1,
    'rand_datetime': '2000-02-02 09:33',
    'text_array': [
    'b50423f6b9374fb09a9f6ff607762147',
    '27200faefb8a45649fdab916b10e397f',
],
    'words': 'dragonfly rhino',
    'nested': {
    'id': 105,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 1,
},
    {
    'nested_empty': None,
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
    'word': 'dolphin',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'frog',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -10,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    1,
],
],
    'two_words': [
    'frog',
    'goat',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'leopard',
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
    '01',
    '16',
    '09',
],
    'text_data': '8c977559af8f45259aa5f68ef68fd849',
    'rand_digit': 4,
    'rand_number': 0.05241,
    'rand_signed_int': -1,
    'rand_datetime': '2000-05-13 16:20:06.054961+0800',
    'text_array': [
    '37640c267bc34cb5b0b88f806043944c',
    '708f63c8cba34299a221f9637ce2a4b2',
],
    'words': 'pig shark',
    'nested': {
    'id': 106,
    'rand_digit': 4,
    'array': [
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
    'word': 'grasshopper',
    'number': 10,
},
    {
    'nested_empty': None,
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
    'word': 'snail',
    'number': 7,
},
],
},
    'nested_array': [
    [
    -7,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    6,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'mosquito',
    'bird',
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
    'mixed_type': 4,
    'maybe': 'turtle',
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
    '26',
    '10',
    '14',
],
    'text_data': '4a210ca1117444d9a9943e056643a7bc',
    'rand_digit': 1,
    'rand_number': 0.4188,
    'rand_signed_int': -7,
    'rand_datetime': '2000-06-19',
    'text_array': [
    '43d93ba206524004ae7e07b20060c9b8',
    '8866aa6d77e04857bb090b8cd4f02544',
],
    'words': 'bee bear',
    'nested': {
    'id': 107,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 4,
},
    {
    'nested_empty': None,
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
    'zebra',
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
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'monkey',
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
    '24',
    '09',
    '05',
],
    'text_data': '72c982c6d5ac46058f14913cf6701ac5',
    'rand_digit': 9,
    'rand_number': 0.44051,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-05 07:26:42.830866+1100',
    'text_array': [
    'f2b15f13cb9544c79c9c3045e967debc',
    '393adb14dbc14b74a23d9a2f5dd23c1d',
],
    'words': 'zebra mosquito',
    'nested': {
    'id': 108,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
    2,
],
],
    'two_words': [
    'ant',
    'jaguar',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'chicken',
    'maybe_null': 'gorilla',
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
    '18',
    '16',
    '16',
    '05',
],
    'text_data': '1bf436b304ab489e98fbe22861e5cc3a',
    'rand_digit': 6,
    'rand_number': 0.90954,
    'rand_signed_int': -4,
    'rand_datetime': '2000-11-14 16:18:17.858261',
    'text_array': [
    '20b16baf1c4f4ad6973e401a73d8f4aa',
    '3bce16f8255f4ce1a2ac7d5b6428bc04',
],
    'words': 'bird lobster',
    'nested': {
    'id': 109,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'squid',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fish',
    'turtle',
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
    'mixed_type': 0.88568,
    'maybe_null': 'gorilla',
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
    '09',
    '19',
    '18',
    '08',
    '12',
],
    'text_data': '93be2108aae240fcbcbbb76d71309acb',
    'rand_digit': 3,
    'rand_number': 0.15856,
    'rand_signed_int': -9,
    'rand_datetime': '2000-09-13 04:30',
    'text_array': [
    'ddc31e7513154604b929f00069a8e500',
    '738c577f3b3c47bfb27630dacf396cbd',
],
    'words': 'sheep ladybug',
    'nested': {
    'id': 110,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 4,
},
],
},
    'nested_array': [
    [
    1,
],
    [
],
],
    'two_words': [
    'hippo',
    'hippo',
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
    'mixed_type': 9,
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
    '08',
    '26',
],
    'text_data': '853ad7982044415381c8189efd0453c5',
    'rand_digit': 3,
    'rand_number': 0.70911,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-11 01:18',
    'text_array': [
    'f549fc4f42d94a189c033f95ede00dd1',
    '85a90979b6a94cc8bad13ce8fa475266',
],
    'words': 'cow scorpion',
    'nested': {
    'id': 111,
    'rand_digit': 5,
    'array': [
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
    'hello',
],
    'word': 'lizard',
    'number': 4,
},
],
},
    'nested_array': [
    [
    9,
],
],
    'two_words': [
    'snake',
    'hyena',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'dolphin',
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
    '06',
    '30',
],
    'text_data': 'f13c75c1f7734412b7ff1417c922dfd7',
    'rand_digit': 1,
    'rand_number': 0.2375,
    'rand_signed_int': 4,
    'rand_datetime': '2000-07-06T01:29:30.568300',
    'text_array': [
    '63e2a22f8c9a46ca81a26e7dfcd9559d',
    'fee02980c4ba4ae883d20738089806d6',
],
    'words': 'kangaroo butterfly',
    'nested': {
    'id': 112,
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
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -4,
],
    [
    -1,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'monkey',
    'wolf',
],
    'city': {
    'name': 'Zurich',
    'geo': {
    'lat': 47.376887,
    'lon': 8.541694,
},
},
    'rand_tuple': [
    35,
],
    'rand_bool': False,
    'mixed_type': None,
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
    '26',
    '10',
],
    'text_data': '8c840a868dff4a68b271cba3d589e1dc',
    'rand_digit': 0,
    'rand_number': 0.52828,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-09 21:20:34+0300',
    'text_array': [
    '16d3fa2407644b6c9fcac77fc7887636',
    'db1fe8806b5c4faaa11401793de6653f',
],
    'words': 'ant rabbit',
    'nested': {
    'id': 113,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mouse',
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
],
    'word': 'bee',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    [
    -2,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dragonfly',
    'rhino',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': [
    86,
],
    'rand_bool': False,
    'mixed_type': 0.89125,
    'maybe_null': 'squid',
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
    '07',
    '22',
],
    'text_data': 'a7e1d505ff8f49ae958803dc0a15a481',
    'rand_digit': 6,
    'rand_number': 0.80187,
    'rand_signed_int': 5,
    'rand_datetime': '2000-06-26T08:03:49.308325+0900',
    'text_array': [
    'c1505302def84492a22af8083b8fd547',
    '25b9a386d0f64c65b61d88ba5c8f8623',
],
    'words': 'pig sheep',
    'nested': {
    'id': 114,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'cow',
    'zebra',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': [
    35,
],
    'rand_bool': False,
    'mixed_type': 0.724,
    'maybe': 'ape',
    'maybe_null': 'lizard',
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
    'text_data': '4f55ab1dcc9a4d688f9763ac40f33fd5',
    'rand_digit': 4,
    'rand_number': 0.174,
    'rand_signed_int': 6,
    'rand_datetime': '2000-11-07T11:49:21',
    'text_array': [
    '6610fb2f0bbc44c08ae23fd489496c8e',
    '9e42b70c8f6f45f2bcf6a25075819877',
],
    'words': 'sheep elephant',
    'nested': {
    'id': 115,
    'rand_digit': 4,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 2,
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
],
    'word': 'duck',
    'number': 3,
},
    {
    'nested_empty': None,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    0,
],
],
    'two_words': [
    'ant',
    'cat',
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
    'mixed_type': 0.54335,
    'maybe_null': 'ape',
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
    '26',
    '18',
    '04',
],
    'text_data': '8d803883a16a4a0a9500f3c20ba2f9ed',
    'rand_digit': 0,
    'rand_number': 0.41616,
    'rand_signed_int': 1,
    'rand_datetime': '2000-08-18',
    'text_array': [
    'd8a65b0730924039ae483677b26ea297',
    '6fcd6be6721f440b9354bb43504cc452',
],
    'words': 'duck crab',
    'nested': {
    'id': 116,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bee',
    'number': 9,
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
    2,
],
],
    'two_words': [
    'snake',
    'dog',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': [
    52,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'cat',
    'maybe_null': 'tiger',
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
    '08',
],
    'text_data': '01b09e249f0e4f859476d26d07958779',
    'rand_digit': 7,
    'rand_number': 0.47319,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-14 03:48',
    'text_array': [
    '6f71d343b81f49e68d0a3182d63ff6d4',
    'd90e228289ab43cfad51007531555b36',
],
    'words': 'duck cat',
    'nested': {
    'id': 117,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
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
    'number': 8,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'panda',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'dragonfly',
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
    27,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'grasshopper',
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
    '11',
    '06',
    '25',
    '20',
    '28',
],
    'text_data': '4638484156714f9a8aafc0b9fa34f5fd',
    'rand_digit': 2,
    'rand_number': 0.30654,
    'rand_signed_int': -4,
    'rand_datetime': '2000-01-01T16:04:50.448576-0600',
    'text_array': [
    '6c10650bd3af4b70a7e95e506cf07af2',
    '0c29fd6dcb5447db9f7a02f633479272',
],
    'words': 'wolf sheep',
    'nested': {
    'id': 118,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'grasshopper',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'jaguar',
    'hippo',
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
    'maybe_null': 'shark',
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
    '29',
    '17',
    '02',
],
    'text_data': '45b83ec389074c7db8ae3d485a8a977d',
    'rand_digit': 5,
    'rand_number': 0.33627,
    'rand_signed_int': -3,
    'rand_datetime': '2000-12-13T06:18:34.026096-0100',
    'text_array': [
    '97e44ce0bc6f4808a78f19f98bfdd137',
    'cec55dd17efc492481254fee22ca810c',
],
    'words': 'crab dragonfly',
    'nested': {
    'id': 119,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 3,
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
],
    'word': 'hippo',
    'number': 8,
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
    -1,
],
    [
    -3,
],
],
    'two_words': [
    'deer',
    'dog',
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
    'mixed_type': 1,
    'maybe': 'shark',
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
],
    'text_data': 'e4bdccfa9c2741938d83e5ec08e1be89',
    'rand_digit': 6,
    'rand_number': 0.62872,
    'rand_signed_int': 10,
    'rand_datetime': '2000-11-02T03:15:28-0300',
    'text_array': [
    '05c582599f634851bc41f71eeced2ea9',
    '5b99290d049943d9bc57393b56ffd212',
],
    'words': 'ladybug chicken',
    'nested': {
    'id': 120,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snail',
    'elephant',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'giraffe',
    'maybe_null': 'rhino',
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
    '05',
    '10',
],
    'text_data': '01173540c2cc4049879cb8f0c970f896',
    'rand_digit': 8,
    'rand_number': 0.68068,
    'rand_signed_int': 2,
    'rand_datetime': '2000-06-23T15:57:38',
    'text_array': [
    '1c2a1327183d4a1db53b1d35dec0a328',
    'f4a951ea7de246d38afdce5f9b883487',
],
    'words': 'deer rabbit',
    'nested': {
    'id': 121,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bear',
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
    'number': 1,
},
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
    'word': 'ant',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'hippo',
    'ant',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': [
    29,
],
    'rand_bool': False,
    'mixed_type': 0.04337,
    'maybe': 'monkey',
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
    '17',
],
    'text_data': 'bbdbc02db19b4238ba8afa26791e9476',
    'rand_digit': 9,
    'rand_number': 0.41368,
    'rand_signed_int': -7,
    'rand_datetime': '2000-03-08 14:15:49',
    'text_array': [
    '2bb743057b26486ea7438a69321fe7e6',
    '11047fe99fb54d488a9fbae8490ccfe8',
],
    'words': 'dragonfly lizard',
    'nested': {
    'id': 122,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'shark',
    'crab',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': [
    14,
],
    'rand_bool': True,
    'mixed_type': 6,
    'maybe': 'butterfly',
    'maybe_null': 'octopus',
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
    'text_data': 'a72bdece232d4982a9e4f104a393cb22',
    'rand_digit': 5,
    'rand_number': 0.69144,
    'rand_signed_int': -1,
    'rand_datetime': '2000-05-28 11:43',
    'text_array': [
    'd1c21e42400c465abb8a65be08cac822',
    'a06861bbd7a840eb96bfc79e9097b62d',
],
    'words': 'camel bird',
    'nested': {
    'id': 123,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 6,
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
    'nested_array': '__FLOAT_MULTI_DIM_2,2__',
    'two_words': [
    'camel',
    'deer',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
},
},
    'rand_tuple': [
    58,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '18',
    '05',
    '07',
    '22',
    '11',
],
    'text_data': 'e2bf5e215fde403f9cefea9b37a01c91',
    'rand_digit': 3,
    'rand_number': 0.09373,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-13 15:06:17.767849+0200',
    'text_array': [
    '47e7e658c7e44646b13821e791c3bf17',
    '85405c59959b477f8a0ff7bbeae945d5',
],
    'words': 'dog horse',
    'nested': {
    'id': 124,
    'rand_digit': 1,
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
    'word': 'dolphin',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    0,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'chicken',
    'zebra',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
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
    'id': 25,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 125,
    'id_str': [
    '26',
    '07',
    '06',
    '27',
],
    'text_data': '3171c28c75b640c1a00042e9b4349945',
    'rand_digit': 2,
    'rand_number': 0.31551,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-15T07:56:49-0300',
    'text_array': [
    '1a67718f152f490c9cbf9630101658d6',
    'c848f6122d1b4c4ca5676e5bac5b73ea',
],
    'words': 'rhino wolf',
    'nested': {
    'id': 125,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'panda',
    'hippo',
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
    'mixed_type': False,
    'maybe': 'zebra',
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
    '17',
    '30',
    '28',
    '21',
    '14',
],
    'text_data': 'd775b964b5474eeaaf0a50f40ea2038e',
    'rand_digit': 7,
    'rand_number': 0.15477,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-25T11:15:16.615271-0200',
    'text_array': [
    '3db14d318e294e5f905e9462daaaacee',
    '10ffd254e4fc4d5b9f3a25bf2486a005',
],
    'words': 'snail horse',
    'nested': {
    'id': 126,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'sheep',
    'rhino',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
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
    '12',
],
    'text_data': '930625ceb4234ec0b5a97f833632d921',
    'rand_digit': 9,
    'rand_number': 0.68945,
    'rand_signed_int': -1,
    'rand_datetime': '2000-03-21T10:45:59.252826+0300',
    'text_array': [
    'aeb474d382b245b9ab013a62de94c53b',
    '1cecb01b457e41919bfb4baef7cca035',
],
    'words': 'snail ladybug',
    'nested': {
    'id': 127,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'goat',
    'number': 4,
},
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
    'word': 'ladybug',
    'number': 7,
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
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'octopus',
    'dolphin',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 'cheetah',
    'maybe': 'rhino',
    'maybe_null': 'crab',
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
    '17',
    '29',
    '23',
    '16',
],
    'text_data': 'ded1ba5a5ddb42f9971eb0ef8ac847f1',
    'rand_digit': 9,
    'rand_number': 0.42436,
    'rand_signed_int': 5,
    'rand_datetime': '2000-03-26 09:45:00',
    'text_array': [
    '3cbe14753d3d4367b98f2dff900d081a',
    '38800971aeaa4429aa85af518bad0ebb',
],
    'words': 'dog scorpion',
    'nested': {
    'id': 128,
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
    'number': 6,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cheetah',
    'butterfly',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'jaguar',
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
    'text_data': '04b1e771ff8c4008b5daf246590434f6',
    'rand_digit': 2,
    'rand_number': 0.63053,
    'rand_signed_int': 5,
    'rand_datetime': '2000-08-19T11:52:01.752547+08:00',
    'text_array': [
    '7fcae7b9b6b8404ba5766c7499dae500',
    '16c2a1ea49a443ee9fb263d892bb557b',
],
    'words': 'tiger rabbit',
    'nested': {
    'id': 129,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'fox',
    'dog',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': [
    54,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'monkey',
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
],
    'text_data': '36414826e6c444e0ad2189e8a6f07585',
    'rand_digit': 9,
    'rand_number': 0.24239,
    'rand_signed_int': -8,
    'rand_datetime': '2000-07-18 06:20:29+0400',
    'text_array': [
    '8662ba3ce0a5444bb0fd17c5a70201c2',
    '5213367561304972b186ba22cf905a3c',
],
    'words': 'crab sheep',
    'nested': {
    'id': 130,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'octopus',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'lobster',
    'goat',
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
    'mixed_type': None,
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
],
    'text_data': '769f13ecb4434374bc3d1d84b7754c3f',
    'rand_digit': 0,
    'rand_number': 0.87794,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-20T16:09:37.920734-12:00',
    'text_array': [
    'e5bfc78279c94144a554390425ccbbc7',
    '112a179f8ce249b7ad260e8eadf2a9de',
],
    'words': 'bear jaguar',
    'nested': {
    'id': 131,
    'rand_digit': 0,
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
    'word': 'chicken',
    'number': 7,
},
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'mouse',
    'dolphin',
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
    'mixed_type': 'fly',
    'maybe': 'frog',
    'maybe_null': 'sloth',
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
    '06',
    '02',
    '15',
    '04',
],
    'text_data': '3684e111b9fa4b65885ddb84bfbe3426',
    'rand_digit': 5,
    'rand_number': 0.81076,
    'rand_signed_int': -1,
    'rand_datetime': '2000-01-05 19:22:15.530480-0100',
    'text_array': [
    'b05a8583f395459c95c5d4248bc4f437',
    '8fa8b16f03d24b50b584a30b77efafd3',
],
    'words': 'cow octopus',
    'nested': {
    'id': 132,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    [
    -10,
],
    [
    2,
],
],
    'two_words': [
    'cheetah',
    'fish',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '26',
    '23',
    '27',
],
    'text_data': '9d3ce19d408c412ab8521a516d769a38',
    'rand_digit': 9,
    'rand_number': 0.03464,
    'rand_signed_int': -6,
    'rand_datetime': '2000-04-03',
    'text_array': [
    '43a3ba857a47466f809c0c5458916d80',
    'c4f663211d6e4d888a3d219aea180531',
],
    'words': 'cheetah squid',
    'nested': {
    'id': 133,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
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
    'number': 5,
},
],
},
    'nested_array': [
    [
    8,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'dragonfly',
    'horse',
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
    'mixed_type': False,
    'maybe_null': 'gorilla',
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
    '04',
],
    'text_data': '5b65541c72ad46a9b351c00185f67237',
    'rand_digit': 0,
    'rand_number': 0.21825,
    'rand_signed_int': -1,
    'rand_datetime': '2000-05-23T18:45:58.789754+05:00',
    'text_array': [
    'cc896171b49648649ce7fe1ecd942d7e',
    '94a81559f96e4506ac74c1875c50018b',
],
    'words': 'duck giraffe',
    'nested': {
    'id': 134,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'spider',
    'scorpion',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cheetah',
    'maybe_null': 'fly',
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
],
    'text_data': '5b0820b91fe8441b8d3621166a117042',
    'rand_digit': 7,
    'rand_number': 0.20181,
    'rand_signed_int': -5,
    'rand_datetime': '2000-03-28T07:21:09.008825',
    'text_array': [
    'c314e8cbce6949d2ba28dfd0cf0f77da',
    'eb6078bc9e974dfbb33e55b03429f835',
],
    'words': 'dolphin dog',
    'nested': {
    'id': 135,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 4,
},
    {
    'nested_empty': None,
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
    'word': 'bear',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snail',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'elephant',
    'rabbit',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': [
    23,
],
    'rand_bool': True,
    'mixed_type': 'deer',
    'maybe_null': None,
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
    '06',
    '26',
    '17',
    '26',
    '11',
],
    'text_data': 'bd27fef970e6406ebdedea8e08fc9e32',
    'rand_digit': 9,
    'rand_number': 0.67838,
    'rand_signed_int': -3,
    'rand_datetime': '2000-07-13 07:52',
    'text_array': [
    'fdad35ce1e70438d8dece099efc11c33',
    '4a2cebfcc36c4b8093ffa4cf43f50204',
],
    'words': 'cow goat',
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
    'word': 'lizard',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'lobster',
    'rabbit',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 9,
    'maybe': 'frog',
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
    '02',
],
    'text_data': '66cd27d5a1754238b5a54bdeeff99bb9',
    'rand_digit': 1,
    'rand_number': 0.5679,
    'rand_signed_int': -5,
    'rand_datetime': '2000-03-09T09:38:32.864479',
    'text_array': [
    '514f05641c354d319bc9a111631fad9f',
    'd67b0867ef534e1eb2bd9096fd601dc1',
],
    'words': 'bear frog',
    'nested': {
    'id': 137,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    [
    9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'ladybug',
    'koala',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 'bee',
    'maybe': 'dog',
    'maybe_null': 'sheep',
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
    '25',
    '18',
    '27',
],
    'text_data': '55c416c65e254afb912b96dd291f728e',
    'rand_digit': 3,
    'rand_number': 0.55252,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-09 04:22:51.575580',
    'text_array': [
    '18bb7a9e3dca4e3284d00b14288ce72f',
    '470828afebdd44b98b17c3566bc0e6fa',
],
    'words': 'monkey lizard',
    'nested': {
    'id': 138,
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
    'number': 5,
},
    {
    'nested_empty': None,
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
    'word': 'rhino',
    'number': 7,
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
    [
    2,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    3,
],
],
    'two_words': [
    'mosquito',
    'snail',
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
    'mixed_type': 'hippo',
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
    '24',
    '13',
    '20',
    '25',
],
    'text_data': '2f8d0b75734a41b8a00346c567c916bc',
    'rand_digit': 6,
    'rand_number': 0.23127,
    'rand_signed_int': 1,
    'rand_datetime': '2000-09-19T14:44:54+0400',
    'text_array': [
    'd7b056be061248519a9531b788195af3',
    'c3e2b67d70a44042819aa880f8734890',
],
    'words': 'jaguar grasshopper',
    'nested': {
    'id': 139,
    'rand_digit': 3,
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
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
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
],
    'text_data': '7511ae8924934d8b99590070f5053567',
    'rand_digit': 9,
    'rand_number': 0.87517,
    'rand_signed_int': -6,
    'rand_datetime': '2000-11-14 04:06:18+0900',
    'text_array': [
    '8315bb7fc99b4719bfa835778ffd0757',
    '3c2ae5efe6b04c15aae76b2c28070b13',
],
    'words': 'leopard horse',
    'nested': {
    'id': 140,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 6,
},
],
},
    'nested_array': [
    [
    8,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -4,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'whale',
    'leopard',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'giraffe',
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
    '19',
],
    'text_data': '9e20a6fcd36f4a3a8ee1d01095227699',
    'rand_digit': 6,
    'rand_number': 0.63678,
    'rand_signed_int': 9,
    'rand_datetime': '2000-08-31T11:35:28-0900',
    'text_array': [
    'cdd53b98381d41f48e2cdaa9af069a94',
    '6ed8dc329ca248a98b359b0ac114e236',
],
    'words': 'pig spider',
    'nested': {
    'id': 141,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'number': 4,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'giraffe',
    'crab',
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
    'maybe': 'fox',
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
    '12',
],
    'text_data': 'ed8cf50e46cd42439ea1198e37550f29',
    'rand_digit': 7,
    'rand_number': 0.47616,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-13 07:37:31.648580',
    'text_array': [
    '90ee5891751f4d748fe9199890c3bedc',
    '72f6f4a18320464ea9e0fccda268ea9b',
],
    'words': 'mouse octopus',
    'nested': {
    'id': 142,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'squid',
    'number': 8,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cheetah',
    'butterfly',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'turtle',
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
    'text_data': 'f8f45387bc214aa78f7b0ce4f5afe737',
    'rand_digit': 9,
    'rand_number': 0.71365,
    'rand_signed_int': 1,
    'rand_datetime': '2000-03-06 23:24:49.516337',
    'text_array': [
    '52a80902346a45db829eb6660a3afb1f',
    'cab9d843f1ee45e68500a6229d358a7b',
],
    'words': 'lion spider',
    'nested': {
    'id': 143,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
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
],
    'word': 'leopard',
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
    'bee',
    'sloth',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cow',
    'maybe_null': 'bear',
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
    '07',
    '29',
],
    'text_data': '567766769ae94feebae15066b0309f7c',
    'rand_digit': 1,
    'rand_number': 0.74061,
    'rand_signed_int': -5,
    'rand_datetime': '2000-10-02 05:45:59',
    'text_array': [
    '0c3706dfb8284d5ea089b6b2d1a79b40',
    '1366ddb7fb5a4957980cf2e125f6a2f8',
],
    'words': 'whale leopard',
    'nested': {
    'id': 144,
    'rand_digit': 0,
    'array': [
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
    'hello',
],
    'word': 'kangaroo',
    'number': 5,
},
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
    'word': 'mouse',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
    [
],
    [
    -10,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ape',
    'snake',
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
    'maybe': 'butterfly',
    'maybe_null': 'bird',
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
],
    'text_data': 'fb1700340bae4d90bde8335feece64cf',
    'rand_digit': 9,
    'rand_number': 0.28594,
    'rand_signed_int': 1,
    'rand_datetime': '2000-10-28 14:02:39.691518',
    'text_array': [
    'd3313b05026548a2b949868c71ecaa5c',
    'cedda0e9ad9c4fb79cd40cd3d3527574',
],
    'words': 'whale bird',
    'nested': {
    'id': 145,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 5,
},
    {
    'nested_empty': None,
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
    'word': 'elephant',
    'number': 3,
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'fox',
    'horse',
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
    'mixed_type': 0,
    'maybe': 'bear',
    'maybe_null': 'tiger',
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
    '03',
],
    'text_data': '82b2a13315fc41219cd4dcc1819a2bd9',
    'rand_digit': 2,
    'rand_number': 0.36154,
    'rand_signed_int': 10,
    'rand_datetime': '2001-01-28 07:35:02-0900',
    'text_array': [
    'c3f594529a1b4ebf920d1739657e000d',
    '608a2a96689942ee812b96e60a6f324c',
],
    'words': 'deer turtle',
    'nested': {
    'id': 146,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 2,
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
    'number': 1,
},
],
},
    'nested_array': [
    [
    5,
],
    [
    -3,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'fox',
    'lobster',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'whale',
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
    '14',
    '13',
    '09',
],
    'text_data': '3eb29f5405f04fff8817c5adb795c70e',
    'rand_digit': 1,
    'rand_number': 0.97271,
    'rand_signed_int': 5,
    'rand_datetime': '2000-01-18T03:24:02',
    'text_array': [
    'a5a6a82d36f4498b929be4a64208b913',
    '0c75fbe5d0c14f50a2eae3c66cb1be5a',
],
    'words': 'mosquito goat',
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
    'word': 'frog',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 1,
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
    [
],
],
    'two_words': [
    'leopard',
    'leopard',
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
    'mixed_type': 'turtle',
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
    '04',
    '09',
],
    'text_data': '5e73a91510a6401f8b30d78c0f9c8dff',
    'rand_digit': 7,
    'rand_number': 0.84681,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-06 12:47:17.004025',
    'text_array': [
    '448cf54524484dbb8a726210b26fd2fc',
    '2161dd65386e43a7825eb4776cc1bcc1',
],
    'words': 'turtle lobster',
    'nested': {
    'id': 148,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'cheetah',
    'ant',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': [
    91,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'camel',
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
    '28',
    '01',
    '18',
],
    'text_data': '82e28e972eea4c4491e25ce6996de9dc',
    'rand_digit': 2,
    'rand_number': 0.66196,
    'rand_signed_int': -2,
    'rand_datetime': '2000-03-08T12:50:41.279729',
    'text_array': [
    'f2cd1f6380a34997bfe7e7563bc1beb1',
    '477775741db643828a9580181de2c145',
],
    'words': 'bee cheetah',
    'nested': {
    'id': 149,
    'rand_digit': 8,
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
],
    'word': 'snail',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'horse',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bee',
    'shark',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fish',
    'maybe_null': 'panda',
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
    'text_data': '555b1f0853a74a6287209161e6cfc5c7',
    'rand_digit': 0,
    'rand_number': 0.56153,
    'rand_signed_int': 3,
    'rand_datetime': '2000-12-09 08:53:01-0800',
    'text_array': [
    '3a6387cfac2c4328ad93f03949b05365',
    '7e702a21973d4d79bcb9a72905344a22',
],
    'words': 'spider giraffe',
    'nested': {
    'id': 150,
    'rand_digit': 1,
    'array': [
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
    'word': 'jaguar',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 3,
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
    [
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hyena',
    'mouse',
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
    'mixed_type': 8,
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
    '03',
    '11',
    '30',
],
    'text_data': '550330fab318403687a4d3faa1817284',
    'rand_digit': 2,
    'rand_number': 0.20017,
    'rand_signed_int': 3,
    'rand_datetime': '2000-02-18',
    'text_array': [
    '8ae3272b37e949de80e24bd5e6c034ab',
    '59628a8386054d93ac560f2437723c79',
],
    'words': 'cat chicken',
    'nested': {
    'id': 151,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'whale',
    'rabbit',
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
    'mixed_type': 7,
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
    '04',
    '04',
    '28',
],
    'text_data': '344c3bb6d5b8470488a38d4672517895',
    'rand_digit': 4,
    'rand_number': 0.81073,
    'rand_signed_int': -10,
    'rand_datetime': '2000-09-20 10:48:35+0800',
    'text_array': [
    '5fbae9fc48734f618c5b9a39c3352e7a',
    '55f977810040473ca92fbca702b158c5',
],
    'words': 'bear leopard',
    'nested': {
    'id': 152,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'giraffe',
    'butterfly',
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
    'mixed_type': 'elephant',
    'maybe': 'shark',
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
    '08',
],
    'text_data': '78cfd0e3b9e34deca12c9e0eaad91805',
    'rand_digit': 5,
    'rand_number': 0.54125,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-19 12:43:27',
    'text_array': [
    '3f2518ca2f864e19bdd0d05cd2f72372',
    'b736b7581fe54312b5f5fd4409796570',
],
    'words': 'fish crab',
    'nested': {
    'id': 153,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'dolphin',
    'bird',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': [
    9,
],
    'rand_bool': False,
    'mixed_type': 'elephant',
    'maybe_null': 'fly',
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
    '25',
],
    'text_data': '5d89da7ebf41478a8ba82b9f853665da',
    'rand_digit': 6,
    'rand_number': 0.41414,
    'rand_signed_int': 3,
    'rand_datetime': '2000-02-18 12:53:40-0900',
    'text_array': [
    '4a3c4d8ac6cf4441bcf0e8cff6e691f3',
    'a793b028a56246119d72ab3d9036b633',
],
    'words': 'camel sheep',
    'nested': {
    'id': 154,
    'rand_digit': 7,
    'array': [
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
],
    'word': 'ant',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'jaguar',
    'ant',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'squid',
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
    '18',
    '04',
    '16',
    '14',
],
    'text_data': 'a40ad440c76b48b793fbbc5c505ad872',
    'rand_digit': 7,
    'rand_number': 0.65535,
    'rand_signed_int': -3,
    'rand_datetime': '2000-05-05 05:06:44.938165-0500',
    'text_array': [
    'f70c67b1970c4fc09c273c99b3a1bdb8',
    'bcdb122478894c209f25ef34da17a5e1',
],
    'words': 'sloth mosquito',
    'nested': {
    'id': 155,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 9,
},
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'leopard',
    'squid',
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
    'maybe_null': 'cow',
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
    '17',
],
    'text_data': 'e14d07593f53463aa21699744d82054f',
    'rand_digit': 2,
    'rand_number': 0.22739,
    'rand_signed_int': -1,
    'rand_datetime': '2000-09-11 19:41:42.775873-0500',
    'text_array': [
    '8852db23132c4479987c86cc9620b6ad',
    '54406da2805a490ab62e4b3df22a732f',
],
    'words': 'jaguar deer',
    'nested': {
    'id': 156,
    'rand_digit': 1,
    'array': [
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
],
    'word': 'duck',
    'number': 1,
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
    [
    -8,
],
],
    'two_words': [
    'octopus',
    'wolf',
],
    'city': {
    'name': 'Riga',
    'geo': {
    'lat': 56.949649,
    'lon': 24.105186,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'ant',
    'maybe_null': 'snake',
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
    '11',
    '08',
    '22',
    '10',
    '21',
],
    'text_data': '48d3fff168af45499b8cb3bc75cd00df',
    'rand_digit': 0,
    'rand_number': 0.12512,
    'rand_signed_int': -5,
    'rand_datetime': '2000-11-05T08:58:29.778387+01:00',
    'text_array': [
    'e821698ae7814a578d2eb365e2396045',
    'd811d0998f22406996173ddc3ec6f623',
],
    'words': 'lizard fox',
    'nested': {
    'id': 157,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 1,
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
    'word': 'snake',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'mouse',
    'deer',
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
    'mixed_type': 0.48479,
    'maybe': 'goat',
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
    '11',
    '05',
    '27',
    '25',
],
    'text_data': 'eec5d0f7fc55440085d877b801aaab09',
    'rand_digit': 8,
    'rand_number': 0.01606,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-07T23:26:18.771834',
    'text_array': [
    'caf62f67056d46859927e6edc5583129',
    'd231f24f7de44ea19863dc94d14a2367',
],
    'words': 'snail cheetah',
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
    'word': 'dragonfly',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'fish',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'frog',
    'fish',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    '22',
],
    'text_data': 'b8859a3a775047668db9b8af2633d31c',
    'rand_digit': 0,
    'rand_number': 0.27775,
    'rand_signed_int': 5,
    'rand_datetime': '2001-01-09 18:01:37.279407+0000',
    'text_array': [
    '3491d01bc4134e94a46c52e8eef6435c',
    '7de1c8ded96547cd960b5dafd468aa03',
],
    'words': 'whale fish',
    'nested': {
    'id': 159,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    6,
],
    [
    0,
],
],
    'two_words': [
    'hippo',
    'butterfly',
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
    'mixed_type': 7,
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
    '09',
    '11',
],
    'text_data': 'f9805fc221104add8a4ce46983b12612',
    'rand_digit': 6,
    'rand_number': 0.3753,
    'rand_signed_int': -10,
    'rand_datetime': '2000-12-04 03:03:44.711094+0200',
    'text_array': [
    'a327b4bade8b40928e5c92125884049a',
    'f2555a663f7f45cca56059e7c68ea887',
],
    'words': 'koala dragonfly',
    'nested': {
    'id': 160,
    'rand_digit': 8,
    'array': [
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
    'word': 'bee',
    'number': 5,
},
],
},
    'nested_array': [
    [
    6,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'squid',
    'turtle',
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
    'mixed_type': 2,
    'maybe': 'wolf',
    'maybe_null': 'cheetah',
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
    '27',
    '10',
    '24',
    '04',
    '22',
],
    'text_data': 'd0615c37a7b4457fad2065a69a8a79b3',
    'rand_digit': 3,
    'rand_number': 0.96845,
    'rand_signed_int': -6,
    'rand_datetime': '2000-08-23 05:28:53.649580+0300',
    'text_array': [
    'bb15dc27585e48c8a8eee47cc40e78a6',
    'c16cdb30f1a5499d940178188f68488c',
],
    'words': 'sloth frog',
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
    'word': 'deer',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fox',
    'bird',
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
    'mixed_type': 0,
    'maybe': 'bee',
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
    '12',
    '22',
],
    'text_data': '64732c9ebd28469a80f34ee4fe9ee5bf',
    'rand_digit': 6,
    'rand_number': 0.58893,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-06T10:57:14.641534',
    'text_array': [
    'a01bf16b04b445a58332574dfba76d6d',
    'f29ad180d929465abd194b37f23397b5',
],
    'words': 'tiger octopus',
    'nested': {
    'id': 162,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'pig',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lizard',
    'leopard',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': [
    68,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'hyena',
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
    '25',
],
    'text_data': 'f18627af04ab4f838bea5418088d1ce3',
    'rand_digit': 3,
    'rand_number': 0.04564,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-31T02:51:09+0400',
    'text_array': [
    'ea62601e93d94381a0d828175f7df9bb',
    '37cb570ce0db43628cfb5535d52bead4',
],
    'words': 'cheetah grasshopper',
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
    'word': 'chicken',
    'number': 2,
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
],
    'word': 'frog',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fox',
    'crab',
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
    'mixed_type': 'lizard',
    'maybe': 'pig',
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



    def test_request_2(self):
        """测试请求 2 - PUT http://localhost:6333/collections/lookup_collection?timeout=60"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/lookup_collection?timeout=60")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/lookup_collection?timeout=60'
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
        """测试请求 3 - PUT http://localhost:6333/collections/lookup_collection/points?wait=true"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/lookup_collection/points?wait=true")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/lookup_collection/points?wait=true'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '14927',
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
    '25',
    '04',
    '18',
    '22',
    '07',
],
    'text_data': '3e5ccf3b7a1445b3900f5829ec7187d5',
    'rand_digit': 4,
    'rand_number': 0.75574,
    'rand_signed_int': 1,
    'rand_datetime': '2000-10-04T02:29:25.107490-0600',
    'text_array': [
    'c27a0e1f1f8a405bb618bdcf693705bf',
    '744ca33abcd34f539ada631f385cd8f4',
],
    'words': 'deer gorilla',
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
    'word': 'ant',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'goat',
    'jaguar',
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
    'mixed_type': True,
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
    '21',
    '25',
    '13',
    '20',
],
    'text_data': '680642693ea44820ba0603db37c83273',
    'rand_digit': 2,
    'rand_number': 0.98105,
    'rand_signed_int': 0,
    'rand_datetime': '2000-02-22T03:03:36.324621',
    'text_array': [
    '379f6725a3704d3fb4dcdf7e5b2fcc1f',
    'afa872604abe4304a2f937897f4f9f4b',
],
    'words': 'grasshopper shark',
    'nested': {
    'id': 101,
    'rand_digit': 8,
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
],
    'word': 'camel',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'rhino',
    'number': 2,
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
    [
    9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'hyena',
    'monkey',
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
    'mixed_type': 'lobster',
    'maybe_null': 'gorilla',
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
    '26',
    '24',
    '11',
    '02',
],
    'text_data': '877ebb2347344e3e9f30a16725462f8f',
    'rand_digit': 5,
    'rand_number': 0.77696,
    'rand_signed_int': 5,
    'rand_datetime': '2000-01-20T20:44:18.762587',
    'text_array': [
    '8aaa2c1c582541db9fed74e83ca1682e',
    'fe4d7305b614454f9b0357406de53f2c',
],
    'words': 'tiger cow',
    'nested': {
    'id': 102,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
],
    [
    5,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'tiger',
    'bear',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': [
    82,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'fox',
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
    '07',
    '03',
    '26',
    '10',
],
    'text_data': '148c8a37c95a4f89bec84950dea0c608',
    'rand_digit': 1,
    'rand_number': 0.71855,
    'rand_signed_int': 7,
    'rand_datetime': '2000-04-11',
    'text_array': [
    '5aeb3521c5924624bb21a19b4e285b8d',
    'd20503bc396c4102a8ddbb38d27cf017',
],
    'words': 'ape octopus',
    'nested': {
    'id': 103,
    'rand_digit': 1,
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
    'hello',
],
    'word': 'lobster',
    'number': 2,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'grasshopper',
    'number': 1,
},
],
},
    'nested_array': [
    [
    4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
    3,
],
],
    'two_words': [
    'bird',
    'pig',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'elephant',
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
    '17',
    '10',
    '02',
    '19',
],
    'text_data': 'bd3c46023e6546c6b36203b4103c402d',
    'rand_digit': 4,
    'rand_number': 0.92186,
    'rand_signed_int': -6,
    'rand_datetime': '2000-01-15 06:55:34',
    'text_array': [
    'd3ede0138a3c41388635ec6a04d02811',
    '98eb858c18544444b9e236e757416948',
],
    'words': 'octopus crab',
    'nested': {
    'id': 104,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'camel',
    'bear',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cow',
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
    'text_data': '9043c8683963403aaa048dee590d3ba0',
    'rand_digit': 3,
    'rand_number': 0.60348,
    'rand_signed_int': -10,
    'rand_datetime': '2000-11-17T03:52:37.389514',
    'text_array': [
    '65006019a2764f11bf3e87f09f5d352d',
    '3ebf800021604285aa245f78fb4880fd',
],
    'words': 'scorpion bee',
    'nested': {
    'id': 105,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'hippo',
    'elephant',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'snail',
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
],
    'text_data': 'e8083502779c4ff9a1d8ebfc2f817850',
    'rand_digit': 2,
    'rand_number': 0.68488,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-22 14:44:16',
    'text_array': [
    '11fb93696b214599b73cce136e7b9c5e',
    '06905845481048c88acc304aa20ae089',
],
    'words': 'fly spider',
    'nested': {
    'id': 106,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'wolf',
    'pig',
],
    'city': {
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': [
    60,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'scorpion',
    'maybe_null': 'fox',
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
    'content-length': '1110',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'group_by': 'id',
    'group_size': 1,
    'limit': 2,
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
    'content-length': '2122',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'image',
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
    'with_lookup': 'lookup_collection',
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
    'content-length': '2216',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'image',
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
    'with_lookup': {
    'collection': 'lookup_collection',
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vectors': [
    'image',
],
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
    'content-length': '1140',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'score_threshold': 0.9,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1106',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'with_payload': [
    'text_array',
    'nested.id',
],
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1285',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
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
    'value': 'monkey',
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
],
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1508',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must': [
    {
    'key': 'rand_number',
    'range': {
    'lt': 0.11911974832923977,
    'gt': 0.8178256781689195,
},
},
    {
    'must_not': [
    {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'hippo',
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
    {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'deer',
},
},
],
    'must_not': [
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
],
},
],
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1362',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'min_should': {
    'conditions': [
    {
    'key': 'id_str',
    'match': {
    'any': [
    '23',
    '18',
    '30',
],
},
},
    {
    'key': 'words',
    'match': {
    'text': 'zebra',
},
},
    {
    'key': 'id_str',
    'values_count': {
    'lt': 5,
    'gt': 5,
},
},
    {
    'key': 'id_str',
    'match': {
    'any': [
    '04',
    '28',
    '19',
],
},
},
],
    'min_count': 2,
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1453',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must_not': [
    {
    'should': [
    {
    'key': 'rand_datetime',
    'range': {
    'lt': '2000-03-25T05:46:03.845283-12:00',
    'gt': '2000-01-10T16:14:13.046254-11:00',
},
},
    {
    'key': 'id_str',
    'match': {
    'value': '17',
},
},
],
},
    {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'rhino',
},
},
],
    'must_not': [
    {
    'key': 'number',
    'range': {
    'lt': 3.0,
},
},
],
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
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1333',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must_not': {
    'min_should': {
    'conditions': [
    {
    'key': 'rand_number',
    'range': {
    'lt': 0.4626813127058459,
},
},
    {
    'key': 'two_words',
    'match': {
    'except': [
    '26',
    '23',
    '14',
    '04',
    '25',
    '14',
    '25',
    '02',
    '19',
    '19',
],
},
},
],
    'min_count': 2,
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1280',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
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
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1314',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
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
    'value': 'spider',
},
},
    {
    'key': 'number',
    'range': {
    'lt': 3.0,
},
},
],
},
},
},
],
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
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1180',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must_not': {
    'key': 'id_str',
    'match': {
    'value': '25',
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1231',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': {
    'is_null': {
    'key': 'maybe_null',
},
},
    'must': [
    {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
],
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1262',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': [
    {
    'key': 'rand_datetime',
    'range': {
    'gt': '2000-04-25T00:00:00Z',
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
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1280',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': {
    'key': 'maybe',
    'match': {
    'value': 'leopard',
},
},
    'must': {
    'key': 'two_words',
    'match': {
    'except': [
    '21',
    '15',
    '28',
    '23',
    '21',
    '05',
    '14',
    '25',
    '28',
    '21',
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
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1306',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': {
    'key': 'city.geo',
    'geo_bounding_box': {
    'top_left': {
    'lon': -2.073966696934491,
    'lat': 57.895566472381745,
},
    'bottom_right': {
    'lon': 78.57929111801195,
    'lat': 9.579015756602061,
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
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1236',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': [
    {
    'key': 'maybe',
    'match': {
    'value': 'giraffe',
},
},
],
    'must': {
    'key': 'words',
    'match': {
    'text': 'butterfly',
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1182',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': {
    'key': 'words',
    'match': {
    'text': 'scorpion',
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1210',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must': {
    'key': 'rand_datetime',
    'range': {
    'gt': '2000-10-29T03:41:08.433110+07:00',
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1311',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': {
    'key': 'id_str',
    'match': {
    'any': [
    '08',
    '21',
    '20',
],
},
},
    'must': [
    {
    'key': 'rand_datetime',
    'range': {
    'lt': '2000-10-31T05:50:23.654288-11:00',
    'gt': '2000-04-09T01:49:28.170267+08:00',
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
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1190',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must_not': {
    'key': 'nested_array[1][10]',
    'range': {
    'lt': 10.0,
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1184',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must': {
    'key': 'id_str',
    'values_count': {
    'lt': 2,
    'gt': 3,
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1244',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': {
    'is_empty': {
    'key': 'nested.array[].nested_empty',
},
},
    'must': {
    'key': 'id_str',
    'values_count': {
    'lt': 4,
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
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1318',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': [
    {
    'key': 'rand_datetime',
    'range': {
    'lt': '2000-01-21T05:55:47.372152+01:00',
    'gt': '2000-07-19T00:30:15.276567-12:00',
},
},
],
    'must': {
    'key': 'rand_number',
    'range': {
    'gt': 0.19455172535556298,
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1186',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must': {
    'key': 'id_str',
    'match': {
    'any': [
    '04',
    '30',
    '29',
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
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1176',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must': {
    'key': 'id_str',
    'match': {
    'value': '14',
},
},
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1307',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must': {
    'key': 'city.geo',
    'geo_bounding_box': {
    'top_left': {
    'lon': -20.022688625431385,
    'lat': -54.82405034046417,
},
    'bottom_right': {
    'lon': 105.88332819241128,
    'lat': 7.1186318200314815,
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
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1271',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'must_not': {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'tiger',
},
},
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
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
    'content-length': '1476',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'filter': {
    'should': [
    {
    'must_not': [
    {
    'key': 'id_str',
    'match': {
    'any': [
    '07',
    '18',
    '13',
],
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
    'value': 'rhino',
},
},
],
    'must_not': [
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
],
},
],
    'must': {
    'should': [
    {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
    {
    'key': 'nested.array[].word',
    'match': {
    'value': 'panda',
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
    'with_vector': False,
    'group_by': 'maybe_null',
    'group_size': 3,
    'limit': 2,
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
        """测试请求 34 - DELETE http://localhost:6333/collections/congruence_test_collection?timeout=60"""
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_group_search.test_simple_group_search')
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
    test = TestGroupSearchtestSimpleGroupSearch()
    test.run_tests()
