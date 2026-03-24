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
logger = logging.getLogger('vdb_fuzzer.test.test_multivector_discovery_queries_test_context_dot')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_multivector_discovery_queries.test_context_dot"
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



class TestMultivectorDiscoveryQueriestestContextDot:
    """自动生成的VDB模糊测试类 - test_multivector_discovery_queries.test_context_dot"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_multivector_discovery_queries.test_context_dot"
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
    'content-length': '510502',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 100,
    'id_str': [
    '24',
    '09',
    '07',
    '12',
    '22',
],
    'text_data': '1350af5a26914155a89631b7b7cb2951',
    'rand_digit': 7,
    'rand_number': 0.7984,
    'rand_signed_int': 0,
    'rand_datetime': '2000-10-09T01:16:41.118474',
    'text_array': [
    '8a7ddf3b6b4043d1b03c1b56d2076896',
    'f1ca234c63b34c439549354d6cc76992',
],
    'words': 'ant frog',
    'nested': {
    'id': 100,
    'rand_digit': 7,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'kangaroo',
    'jaguar',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': [
    82,
],
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'bear',
    'maybe_null': 'cheetah',
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 101,
    'id_str': [
    '17',
    '19',
],
    'text_data': '5e6e213d5c7e4759b48ec66017888c97',
    'rand_digit': 9,
    'rand_number': 0.56696,
    'rand_signed_int': 9,
    'rand_datetime': '2000-12-25T01:48:12.385086-1200',
    'text_array': [
    '75cd129bac784b8fb0a7cc0b91e451b0',
    'ae79387f42a84d43aadf6544b1445c03',
],
    'words': 'snake monkey',
    'nested': {
    'id': 101,
    'rand_digit': 4,
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
    'word': 'panda',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snake',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lion',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 3,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,5__',
    'two_words': [
    'goat',
    'giraffe',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': [
    22,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'lion',
    'maybe_null': 'fox',
},
},
    {
    'id': 2,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 102,
    'id_str': [
],
    'text_data': '7e91189467b54f56bc5e89ba19d5155d',
    'rand_digit': 7,
    'rand_number': 0.44057,
    'rand_signed_int': -6,
    'rand_datetime': '2000-04-01 19:29:05.747436',
    'text_array': [
    '25637e6641084535916efc720cb1575a',
    'ef96c5fc260a4f10967480b8edd7c954',
],
    'words': 'crab hyena',
    'nested': {
    'id': 102,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
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
    4,
],
],
    'two_words': [
    'giraffe',
    'dragonfly',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'gorilla',
    'maybe_null': 'deer',
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 103,
    'id_str': [
    '25',
    '16',
    '25',
],
    'text_data': '776d0c4c18374bd2a8c32fc16553aeaf',
    'rand_digit': 3,
    'rand_number': 0.37937,
    'rand_signed_int': 8,
    'rand_datetime': '2000-07-09T08:01:34+0100',
    'text_array': [
    'eb6a206f7ee34c69a793335540cf25d1',
    'b93a7836170e4883b385d597ecc06ff6',
],
    'words': 'spider ant',
    'nested': {
    'id': 103,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    0,
],
],
    'two_words': [
    'goat',
    'panda',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'jaguar',
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 104,
    'id_str': [
    '12',
    '21',
    '10',
],
    'text_data': 'ee646136bfaa4c3eb6e8f6224abcc1eb',
    'rand_digit': 0,
    'rand_number': 0.15568,
    'rand_signed_int': 0,
    'rand_datetime': '2001-01-24 23:09:00',
    'text_array': [
    'f99f86c476d74ced9e695018904b85d8',
    '8b8e573f26724808bc66ec65bc0dbe00',
],
    'words': 'mosquito panda',
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
    'word': 'snail',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dolphin',
    'hyena',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': [
    44,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'deer',
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 105,
    'id_str': [
    '22',
    '06',
    '29',
    '28',
    '24',
],
    'text_data': '078d8548321349dbafbe52a79c04ac75',
    'rand_digit': 4,
    'rand_number': 0.40918,
    'rand_signed_int': 0,
    'rand_datetime': '2000-04-21 06:35:15.194210',
    'text_array': [
    'f38388318dfc4ee9a1beba5336288cbc',
    'ab33ccbce74c44f1bc013e248fb8c408',
],
    'words': 'zebra horse',
    'nested': {
    'id': 105,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    8,
],
],
    'two_words': [
    'camel',
    'mosquito',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'jaguar',
    'maybe_null': 'shark',
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 106,
    'id_str': [
    '11',
    '23',
    '13',
    '08',
],
    'text_data': '83c8feb14a884128b67b88c561db78ea',
    'rand_digit': 1,
    'rand_number': 0.55898,
    'rand_signed_int': 6,
    'rand_datetime': '2000-05-25T17:59:08+0700',
    'text_array': [
    '2846447f1c5d4887b6a605ed67bfd192',
    '673e844a88cb412980b72f60abb2ea09',
],
    'words': 'duck grasshopper',
    'nested': {
    'id': 106,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'crab',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'spider',
    'kangaroo',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 107,
    'id_str': [
    '27',
    '05',
    '27',
    '27',
],
    'text_data': '8cf427f3baf44f1fab0b51618eac501f',
    'rand_digit': 8,
    'rand_number': 0.20056,
    'rand_signed_int': 8,
    'rand_datetime': '2000-01-19T11:55:30-0100',
    'text_array': [
    'd62edae151a949b5a23648d55656bd43',
    'c79bcc0805524704a16d2d857fc66871',
],
    'words': 'hippo leopard',
    'nested': {
    'id': 107,
    'rand_digit': 4,
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
],
},
    'nested_array': [
],
    'two_words': [
    'cow',
    'leopard',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'tiger',
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 108,
    'id_str': [
    '04',
    '07',
],
    'text_data': 'b594f4bd0c1b4bd789943d20024d480e',
    'rand_digit': 1,
    'rand_number': 0.91561,
    'rand_signed_int': 0,
    'rand_datetime': '2000-02-11 10:10:24',
    'text_array': [
    'aeae68163423406dbc62488b42ac5958',
    'ec6e91e840c5418f8efe9cebca1ad430',
],
    'words': 'duck bee',
    'nested': {
    'id': 108,
    'rand_digit': 0,
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
],
    'word': 'duck',
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
],
},
    'nested_array': [
],
    'two_words': [
    'elephant',
    'dog',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 'fish',
    'maybe': 'panda',
    'maybe_null': 'koala',
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 109,
    'id_str': [
    '30',
    '27',
    '30',
    '19',
],
    'text_data': 'e9b6470fabb74a7f9a1408b1221d66f8',
    'rand_digit': 4,
    'rand_number': 0.59641,
    'rand_signed_int': -1,
    'rand_datetime': '2000-06-17T23:03:08',
    'text_array': [
    '6aefeaa6602443f0924073b1561d6011',
    '4e91ef0ed260478ab20a4908104bb774',
],
    'words': 'lion chicken',
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
    'word': 'grasshopper',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'deer',
    'camel',
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
    'maybe': 'scorpion',
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 110,
    'id_str': [
    '29',
    '10',
    '05',
    '19',
    '08',
],
    'text_data': '135642fa8db64b2c9e209909b8c12b53',
    'rand_digit': 6,
    'rand_number': 0.65724,
    'rand_signed_int': 10,
    'rand_datetime': '2000-11-26 05:05:46',
    'text_array': [
    '97c2ba44d3a549b9ac804f3a94ffe9d5',
    'b2571bf94ca64c409564742df0352241',
],
    'words': 'panda snake',
    'nested': {
    'id': 110,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    9,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'giraffe',
    'elephant',
],
    'city': {
    'name': 'Frankfurt',
    'geo': {
    'lat': 50.110922,
    'lon': 8.682127,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'giraffe',
    'maybe_null': 'tiger',
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 111,
    'id_str': [
    '18',
    '29',
],
    'text_data': '940bd0d7798548acaedbf18f54bc4990',
    'rand_digit': 1,
    'rand_number': 0.56522,
    'rand_signed_int': 6,
    'rand_datetime': '2000-08-05 00:56:17-0900',
    'text_array': [
    'f32647195049480eb1dce71ad2339616',
    '144e75926743483dbcb6eb7ac8c0eef5',
],
    'words': 'cow fish',
    'nested': {
    'id': 111,
    'rand_digit': 3,
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
    'hello',
],
    'word': 'bee',
    'number': 10,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'squid',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'panda',
    'cow',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'snail',
    'maybe_null': None,
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 112,
    'id_str': [
],
    'text_data': 'cd02e47edd774e16815eeccf37d51a11',
    'rand_digit': 5,
    'rand_number': 0.23225,
    'rand_signed_int': -8,
    'rand_datetime': '2000-01-10 04:44:56',
    'text_array': [
    'ee9f48cb2a294bb193bfca9da48aed48',
    '6566a14f371b40fcb0df8af867cec1d3',
],
    'words': 'gorilla ape',
    'nested': {
    'id': 112,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'hyena',
    'frog',
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
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 113,
    'id_str': [
    '18',
    '24',
],
    'text_data': '3f4e13116a5c411194062cdb8c0cf87a',
    'rand_digit': 4,
    'rand_number': 0.59886,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-25 15:17:10.929094',
    'text_array': [
    '85d95d84f1d544aca144e28d1bd87563',
    'ebcd8cd78db8465b925f40689ceff39f',
],
    'words': 'crab elephant',
    'nested': {
    'id': 113,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'panda',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'fox',
    'zebra',
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
    'mixed_type': 0.2394,
    'maybe_null': None,
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 114,
    'id_str': [
    '20',
    '13',
    '14',
],
    'text_data': 'a78e25acc63c4c5cae11fb6d5b8f075c',
    'rand_digit': 0,
    'rand_number': 0.17532,
    'rand_signed_int': 8,
    'rand_datetime': '2000-03-19 17:45',
    'text_array': [
    'e1a06f021ac34321aa7e16b45a770da8',
    '6d59e8f10a0b4b6f883bf203d1bc2eca',
],
    'words': 'cow sloth',
    'nested': {
    'id': 114,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bear',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
    -9,
],
],
    'two_words': [
    'grasshopper',
    'fox',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'turtle',
    'maybe_null': 'mouse',
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 115,
    'id_str': [
    '22',
    '10',
    '06',
],
    'text_data': '34884f3470af4964883faa2a82d53a72',
    'rand_digit': 3,
    'rand_number': 0.39186,
    'rand_signed_int': -2,
    'rand_datetime': '2000-01-02 17:33',
    'text_array': [
    'a21506ce5e694322b272dd681a7df325',
    'a29fb09d04ef43a58b1dbc59bbb03e08',
],
    'words': 'cat bear',
    'nested': {
    'id': 115,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -4,
],
    [
],
],
    'two_words': [
    'leopard',
    'rabbit',
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
    'mixed_type': False,
    'maybe_null': 'bird',
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 116,
    'id_str': [
    '28',
    '02',
    '17',
],
    'text_data': 'fbb10edc6aee49768ec1455d655987e3',
    'rand_digit': 7,
    'rand_number': 0.79591,
    'rand_signed_int': -1,
    'rand_datetime': '2000-01-28T15:34:39',
    'text_array': [
    '7f9bb502cdfd46b4875783cfb8a855c1',
    '8b098027c1414cef9fdaeec2a870e3c4',
],
    'words': 'spider ape',
    'nested': {
    'id': 116,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    0,
],
    [
],
],
    'two_words': [
    'ladybug',
    'chicken',
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
    'maybe_null': 'ape',
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 117,
    'id_str': [
    '01',
    '04',
    '26',
    '03',
    '01',
],
    'text_data': '03789d6db6ad432ebef4faa8673a8dfe',
    'rand_digit': 5,
    'rand_number': 0.78431,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-19 19:55:30.813855-0700',
    'text_array': [
    '5cda8d0971494fd3a1aa338e4cb8d924',
    'abd452f2b80041fab7a8ae72394789d5',
],
    'words': 'elephant octopus',
    'nested': {
    'id': 117,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 5,
},
],
},
    'nested_array': [
    [
    0,
],
    [
    10,
],
],
    'two_words': [
    'deer',
    'dragonfly',
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
    'maybe': 'goat',
    'maybe_null': 'whale',
},
},
    {
    'id': 18,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 118,
    'id_str': [
],
    'text_data': '7213c80b938044deb53752a6438eb788',
    'rand_digit': 0,
    'rand_number': 0.22729,
    'rand_signed_int': 0,
    'rand_datetime': '2000-01-19 07:02:33',
    'text_array': [
    'd3e588b2ecfa48c99eeba763f0d38976',
    'c40652207cf14b17a0e71138286908e2',
],
    'words': 'octopus ape',
    'nested': {
    'id': 118,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
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
],
    'word': 'dog',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'bee',
    'scorpion',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cheetah',
    'maybe_null': 'snake',
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
    '19',
],
    'text_data': '289ede809c3140359cb8d9c081cbfdc5',
    'rand_digit': 5,
    'rand_number': 0.60405,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-16T02:01:06',
    'text_array': [
    '529e32db5d2249639940101c03326815',
    'c576e0892f6d4a37838f3f06c9aeeebd',
],
    'words': 'goat rabbit',
    'nested': {
    'id': 119,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fly',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 4,
},
],
},
    'nested_array': [
    [
    -5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    8,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'giraffe',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'dog',
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 120,
    'id_str': [
    '11',
],
    'text_data': 'ba476abdaeeb4957ac4295490cabfd1e',
    'rand_digit': 3,
    'rand_number': 0.51922,
    'rand_signed_int': 7,
    'rand_datetime': '2000-10-31 16:01:36.143060+0800',
    'text_array': [
    '04bc54690fc546a787d4af2e74385023',
    '3b514db0d9544aa5baf76f9c6b374a88',
],
    'words': 'deer elephant',
    'nested': {
    'id': 120,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
    -3,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'grasshopper',
    'kangaroo',
],
    'city': {
    'name': 'Seoul',
    'geo': {
    'lat': 37.566535,
    'lon': 126.977969,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 121,
    'id_str': [
    '23',
    '24',
    '08',
    '23',
    '23',
],
    'text_data': '4cf517ef2f83431aa576fc6b25ac1ad8',
    'rand_digit': 3,
    'rand_number': 0.41461,
    'rand_signed_int': -4,
    'rand_datetime': '2000-03-04 19:09:49.404682+1200',
    'text_array': [
    'ad0fb10fe36d4dc1aecffeef8c679f23',
    'e78de2cd05894a168be300057aa16ee1',
],
    'words': 'dragonfly bear',
    'nested': {
    'id': 121,
    'rand_digit': 3,
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
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dolphin',
    'ape',
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
    'mixed_type': True,
    'maybe': 'frog',
    'maybe_null': 'sloth',
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
    '05',
    '20',
],
    'text_data': 'f5b1a6b42e7249658733ef31ede9793f',
    'rand_digit': 2,
    'rand_number': 0.75588,
    'rand_signed_int': 9,
    'rand_datetime': '2001-01-18T20:40:57.678627+0400',
    'text_array': [
    '8121bce9dd8e41ca8b5d206b8f00ff7d',
    '6324c7f869a54d63a1aea5b4f93df3d4',
],
    'words': 'deer cow',
    'nested': {
    'id': 122,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 1,
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
    'word': 'scorpion',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'rabbit',
    'monkey',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': [
    59,
],
    'rand_bool': False,
    'mixed_type': 'tiger',
    'maybe_null': 'lobster',
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 123,
    'id_str': [
    '28',
    '10',
    '25',
    '09',
    '04',
],
    'text_data': '8a683e651b974ffda72ca072cb69f82a',
    'rand_digit': 3,
    'rand_number': 0.82147,
    'rand_signed_int': -7,
    'rand_datetime': '2000-11-02 04:34:47.013527+0600',
    'text_array': [
    '093d6384523a44d4a4d45e9c205acfc1',
    '6843868864b14077ac44f92dc405cd36',
],
    'words': 'shark scorpion',
    'nested': {
    'id': 123,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'crab',
    'snail',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': [
    27,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'sheep',
    'maybe_null': 'fly',
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 124,
    'id_str': [
    '09',
    '21',
    '15',
    '13',
    '03',
],
    'text_data': 'ffb29ee412b34342983c1df1c4403040',
    'rand_digit': 8,
    'rand_number': 0.95997,
    'rand_signed_int': -2,
    'rand_datetime': '2000-06-12 00:42:55.815091',
    'text_array': [
    'a99fe978c2fe4b5e832f506fd8f3c4f0',
    '5e5aa35e240345f3af00d467faf48f8f',
],
    'words': 'lobster duck',
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
    'word': 'goat',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'kangaroo',
    'tiger',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 'ape',
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
],
    'text_data': 'a26012a4fcfa4c26b2d1aa1c634e57b2',
    'rand_digit': 5,
    'rand_number': 0.12333,
    'rand_signed_int': -7,
    'rand_datetime': '2000-06-20T00:45:41.705781',
    'text_array': [
    '888ed6972d504b05ae9bde9b0e71828f',
    '28d1766df8f04578a2cc2baa96294329',
],
    'words': 'elephant pig',
    'nested': {
    'id': 125,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'ape',
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    6,
],
],
    'two_words': [
    'sloth',
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
    'mixed_type': 'lobster',
    'maybe_null': None,
},
},
    {
    'id': 26,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 126,
    'id_str': [
    '24',
    '26',
],
    'text_data': 'fc8d6cb0393a42549a1ec4ae8de72a94',
    'rand_digit': 5,
    'rand_number': 0.23745,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-09 10:22:24.865884+1100',
    'text_array': [
    '2de154a0e0bc4c6fb59447f9d3fb8f28',
    '4280da22c0f1435bb1623a50e939ee5f',
],
    'words': 'koala spider',
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
    'word': 'snail',
    'number': 7,
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
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    9,
],
],
    'two_words': [
    'frog',
    'frog',
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
    'maybe': 'fox',
    'maybe_null': None,
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 127,
    'id_str': [
],
    'text_data': '63c4b337ac6c4fd09aa95f7b837de9a0',
    'rand_digit': 0,
    'rand_number': 0.08899,
    'rand_signed_int': -6,
    'rand_datetime': '2000-04-15 00:08:53',
    'text_array': [
    '4c0dbf3dbab7438aabd32d13c4ff554a',
    '073321eef848436187f4f6092f3023a8',
],
    'words': 'bee dog',
    'nested': {
    'id': 127,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'wolf',
    'rabbit',
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
    'mixed_type': 'lizard',
    'maybe_null': 'jaguar',
},
},
    {
    'id': 28,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 128,
    'id_str': [
    '28',
    '21',
    '09',
    '19',
    '10',
],
    'text_data': 'c2b0e5ca14f94461940407d95ac1c3cf',
    'rand_digit': 2,
    'rand_number': 0.60617,
    'rand_signed_int': 3,
    'rand_datetime': '2000-04-24 10:47:25.151486-0100',
    'text_array': [
    '5f9f1a90648f429c867b5e1fa645da66',
    '45f16a0c0ba54610922dc4e7b54e33af',
],
    'words': 'cheetah fox',
    'nested': {
    'id': 128,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 4,
},
    {
    'nested_empty': None,
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
],
    'word': 'ant',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
    -9,
],
],
    'two_words': [
    'camel',
    'bird',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
    '13',
],
    'text_data': '3bf876bec18e4a26a1fac8c122672bc4',
    'rand_digit': 2,
    'rand_number': 0.74366,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-13 17:41:34.388080',
    'text_array': [
    '648414572ce44d06ac7fa1f1c94623d4',
    'dbfa2eadb2be4cbcb6616fd4176effad',
],
    'words': 'fox deer',
    'nested': {
    'id': 129,
    'rand_digit': 4,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bear',
    'hyena',
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
    'mixed_type': None,
    'maybe_null': 'fly',
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 130,
    'id_str': [
    '27',
    '01',
    '12',
],
    'text_data': '6c9e26c9490c4c4d97e2239d53848628',
    'rand_digit': 5,
    'rand_number': 0.26842,
    'rand_signed_int': -2,
    'rand_datetime': '2000-05-23 13:08:40.657246+0200',
    'text_array': [
    '7c05329956ac49ed839858af7cb28fe2',
    '21ce05c3af474edf8f2bfacb291723e1',
],
    'words': 'dolphin frog',
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
    'word': 'ant',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'jaguar',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'fox',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'dolphin',
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
    'mixed_type': False,
    'maybe_null': 'ladybug',
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 131,
    'id_str': [
    '09',
    '12',
    '27',
    '24',
    '23',
],
    'text_data': '5b95f47105394814a3b3558f9f590465',
    'rand_digit': 6,
    'rand_number': 0.31932,
    'rand_signed_int': -8,
    'rand_datetime': '2000-08-31 03:12:23.001524',
    'text_array': [
    '01ec5c527da94748beb3ea078c3c5998',
    '55093c9c6692451ba5303837e98aabac',
],
    'words': 'spider jaguar',
    'nested': {
    'id': 131,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'chicken',
    'fish',
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
    'mixed_type': False,
    'maybe': 'panda',
    'maybe_null': 'dog',
},
},
    {
    'id': 32,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 132,
    'id_str': [
],
    'text_data': '69bf9a79c575464bb3e977830e100cf8',
    'rand_digit': 9,
    'rand_number': 0.00527,
    'rand_signed_int': -7,
    'rand_datetime': '2000-10-06T10:57:58.461740-11:00',
    'text_array': [
    '92f3db4531c44e4397324cccd554f0b1',
    '7d5aa605b2b64b0e9858d9ee4f044d2a',
],
    'words': 'crab butterfly',
    'nested': {
    'id': 132,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -4,
],
    [
    -10,
],
],
    'two_words': [
    'koala',
    'lizard',
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
    'mixed_type': 0,
    'maybe_null': 'fish',
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 133,
    'id_str': [
    '25',
    '21',
],
    'text_data': '4c228b7b105e412d86d628ca8f115f88',
    'rand_digit': 1,
    'rand_number': 0.55718,
    'rand_signed_int': 5,
    'rand_datetime': '2000-03-01T11:13:13.129511',
    'text_array': [
    '9261b5a1c1f244fdb76de476282f25ea',
    '0fccf117374848a6821828db01782cad',
],
    'words': 'bear rhino',
    'nested': {
    'id': 133,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'frog',
    'turtle',
],
    'city': {
    'name': 'Kharkiv',
    'geo': {
    'lat': 49.980812,
    'lon': 36.25272,
},
},
    'rand_tuple': [
    57,
],
    'rand_bool': True,
    'mixed_type': 'ape',
    'maybe': 'scorpion',
    'maybe_null': None,
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 134,
    'id_str': [
    '20',
    '02',
],
    'text_data': 'b4d391f73e3c4831ba2670628894dbb0',
    'rand_digit': 7,
    'rand_number': 0.33478,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-24',
    'text_array': [
    'e2c53fe6db0f4cc9aee6c517bca3444e',
    '0c8db62f2088419eb1096fc2732849f9',
],
    'words': 'sheep goat',
    'nested': {
    'id': 134,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    [
    -7,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'sheep',
    'butterfly',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 7,
    'maybe_null': 'lizard',
},
},
    {
    'id': 35,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 135,
    'id_str': [
    '28',
    '28',
],
    'text_data': '6179a49f2209430f936a9cb89385b7ea',
    'rand_digit': 8,
    'rand_number': 0.95039,
    'rand_signed_int': 10,
    'rand_datetime': '2000-06-30 08:37:19+1000',
    'text_array': [
    '4951a42752d1400897e8c149c0969fb4',
    '579f7608b18643ce93ac0064193472c1',
],
    'words': 'ape lion',
    'nested': {
    'id': 135,
    'rand_digit': 7,
    'array': [
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
],
},
    'nested_array': [
    [
],
    [
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fish',
    'ape',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 36,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 136,
    'id_str': [
    '14',
    '09',
],
    'text_data': 'bddd9aade03e415ea6b1c5e97145aaed',
    'rand_digit': 7,
    'rand_number': 0.6047,
    'rand_signed_int': 2,
    'rand_datetime': '2000-08-30 10:09:17+0900',
    'text_array': [
    '37d503f6bab44c9b96b6c4b25f578ab6',
    '93126fd097a4454687e2b324bcfdc0b8',
],
    'words': 'lizard pig',
    'nested': {
    'id': 136,
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
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'crab',
    'bird',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
],
    'text_data': 'cb7d773c996043e49a89f82d30952f7b',
    'rand_digit': 8,
    'rand_number': 0.27266,
    'rand_signed_int': -4,
    'rand_datetime': '2000-08-01T00:10:59.537822+0400',
    'text_array': [
    'e9e8a033b33e44118443b7a15bfa0837',
    'caaf0922a3e4478baf96bdaa2e77c475',
],
    'words': 'butterfly elephant',
    'nested': {
    'id': 137,
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
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 6,
},
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 10,
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
    'zebra',
    'pig',
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
    'mixed_type': False,
    'maybe': 'duck',
    'maybe_null': None,
},
},
    {
    'id': 38,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 138,
    'id_str': [
    '28',
    '05',
    '19',
    '27',
],
    'text_data': '00565959a1eb4bb09db989c2d77f4a85',
    'rand_digit': 6,
    'rand_number': 0.21925,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-12 06:54:56-0300',
    'text_array': [
    '0a981fac00f74188861acbea1f34a90f',
    '255e7cd6480f415eb0a696c208910e29',
],
    'words': 'zebra sheep',
    'nested': {
    'id': 138,
    'rand_digit': 3,
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
    'word': 'wolf',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 5,
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
],
    'two_words': [
    'panda',
    'cat',
],
    'city': {
    'name': 'Kharkiv',
    'geo': {
    'lat': 49.980812,
    'lon': 36.25272,
},
},
    'rand_tuple': [
    73,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'jaguar',
    'maybe_null': 'lobster',
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 139,
    'id_str': [
],
    'text_data': '8d8be476dfef403f9757e39e60819abe',
    'rand_digit': 9,
    'rand_number': 0.89831,
    'rand_signed_int': -10,
    'rand_datetime': '2000-12-09 15:31:26.710892',
    'text_array': [
    '05a97a332f63497980418df7ee2c7dfb',
    '2e27809fa94041a9b7c635d7f29fbb5e',
],
    'words': 'giraffe chicken',
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
    'word': 'snail',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -1,
],
    [
    5,
],
],
    'two_words': [
    'bear',
    'squid',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': [
    89,
],
    'rand_bool': False,
    'mixed_type': 3,
    'maybe': 'sloth',
    'maybe_null': 'lizard',
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 140,
    'id_str': [
],
    'text_data': '4d78f1372fa547a4bdc05a883df44ba7',
    'rand_digit': 5,
    'rand_number': 0.89572,
    'rand_signed_int': -8,
    'rand_datetime': '2000-04-10T00:26:44.908121',
    'text_array': [
    '5de5f207689143d899e2d55a74e0c3c6',
    '5cd5d1f013794bab96efd8b04fb19159',
],
    'words': 'duck fly',
    'nested': {
    'id': 140,
    'rand_digit': 6,
    'array': [
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
    'hello',
],
    'word': 'dolphin',
    'number': 4,
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
    'word': 'dog',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'squid',
    'dragonfly',
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
    'mixed_type': 'hyena',
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 141,
    'id_str': [
    '20',
    '01',
    '28',
],
    'text_data': '2dc5b784c76d4244a69f1365b4c33d6c',
    'rand_digit': 7,
    'rand_number': 0.25491,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-28 05:14:25-1100',
    'text_array': [
    '4711f0c56e834e0e9d439f845bbe311d',
    '1d937596756b41eead590598102be550',
],
    'words': 'scorpion lizard',
    'nested': {
    'id': 141,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'squid',
    'cheetah',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.49657,
    'maybe_null': 'whale',
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 142,
    'id_str': [
    '27',
    '16',
    '26',
    '15',
    '26',
],
    'text_data': '4a481816bee342e8a2570acd9653b4ee',
    'rand_digit': 8,
    'rand_number': 0.95607,
    'rand_signed_int': -3,
    'rand_datetime': '2000-04-23 19:40:40-0300',
    'text_array': [
    '1fb3108fdadd4f8797c5fc481ce9f239',
    'a52a5d17bfd54e40916002a181121e07',
],
    'words': 'zebra whale',
    'nested': {
    'id': 142,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'shark',
    'cat',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
},
},
    {
    'id': 43,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 143,
    'id_str': [
    '15',
],
    'text_data': 'd020a83dfa794b64aa877f79d45309d5',
    'rand_digit': 0,
    'rand_number': 0.84156,
    'rand_signed_int': -2,
    'rand_datetime': '2000-06-13 17:32',
    'text_array': [
    'd55711c4034c4065bc7580f4438ebf5d',
    '87b9f7ff698e40d8a8b03a85f41c65a6',
],
    'words': 'lizard pig',
    'nested': {
    'id': 143,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -5,
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'mosquito',
    'cheetah',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': [
    65,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'rhino',
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 144,
    'id_str': [
    '30',
    '24',
    '29',
],
    'text_data': 'e2249c7faa1d4997b477bfd00018352d',
    'rand_digit': 4,
    'rand_number': 0.82696,
    'rand_signed_int': 9,
    'rand_datetime': '2000-06-22 18:15:24.008577-1100',
    'text_array': [
    'b69778030f51457583c5fb98709f3dd9',
    '451051a67a4a4be19d6e34edf0ec26e1',
],
    'words': 'squid fox',
    'nested': {
    'id': 144,
    'rand_digit': 5,
    'array': [
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
    'shark',
    'mosquito',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': [
    22,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'cat',
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 145,
    'id_str': [
    '05',
    '13',
    '20',
    '25',
],
    'text_data': '4c8226640f9e4e73978e374932d18d85',
    'rand_digit': 1,
    'rand_number': 0.58819,
    'rand_signed_int': -1,
    'rand_datetime': '2000-07-05T07:55:56',
    'text_array': [
    '137f055d6336423ba3f5307fb4cde1fc',
    '83eff03ccb874277bb2ff73de0b5c7ac',
],
    'words': 'scorpion dragonfly',
    'nested': {
    'id': 145,
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
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
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
    'word': 'cow',
    'number': 8,
},
],
},
    'nested_array': [
    [
    7,
],
    [
    -2,
],
],
    'two_words': [
    'frog',
    'mouse',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': [
    74,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'scorpion',
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
    '10',
    '22',
    '02',
    '19',
    '15',
],
    'text_data': '6a8a001792e447ef8d5a58aee0557078',
    'rand_digit': 2,
    'rand_number': 0.5243,
    'rand_signed_int': 1,
    'rand_datetime': '2000-12-23T07:41:02+0200',
    'text_array': [
    'ff30175e183f421cb597136fffcd8380',
    'd814b238596f41e5be4e209b49eaf9e8',
],
    'words': 'turtle lobster',
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
    'word': 'bee',
    'number': 7,
},
    {
    'nested_empty': None,
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
    'word': 'tiger',
    'number': 4,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    3,
],
],
    'two_words': [
    'cheetah',
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
    'mixed_type': False,
    'maybe_null': 'fox',
},
},
    {
    'id': 47,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 147,
    'id_str': [
    '28',
    '09',
    '30',
    '04',
    '10',
],
    'text_data': 'f5897e713109440a97ba6ab98249321d',
    'rand_digit': 7,
    'rand_number': 0.14107,
    'rand_signed_int': -2,
    'rand_datetime': '2000-12-09',
    'text_array': [
    '3924ab9c55c1464bb2ed2415db1cfebf',
    '5db3c1d12b6e42aaa0fc3130425e9212',
],
    'words': 'fox duck',
    'nested': {
    'id': 147,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 1,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,5__',
    'two_words': [
    'deer',
    'turtle',
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
    'maybe': 'cheetah',
    'maybe_null': 'monkey',
},
},
    {
    'id': 48,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 148,
    'id_str': [
    '30',
    '09',
    '29',
],
    'text_data': 'eba603d75b1e4c24a76d626b7ac6c0c5',
    'rand_digit': 3,
    'rand_number': 0.13651,
    'rand_signed_int': 7,
    'rand_datetime': '2000-08-23 00:46:03',
    'text_array': [
    '5a8c61f7a2e1484eaac099816d59af2b',
    '1525c67e9f6c4ebfbf4d0b62eda6c127',
],
    'words': 'butterfly fly',
    'nested': {
    'id': 148,
    'rand_digit': 6,
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
    'word': 'grasshopper',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ant',
    'ant',
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
    'mixed_type': 0.02871,
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 149,
    'id_str': [
    '09',
    '16',
    '01',
],
    'text_data': 'c85f4df1f0d9453ca244b226abccc268',
    'rand_digit': 1,
    'rand_number': 0.25452,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-17T08:02:49',
    'text_array': [
    '9a44234b1ec342f1934f2e27a3d4cb3c',
    'a3cb3c7f816e4915b01fcc92c3f03dc0',
],
    'words': 'sloth bear',
    'nested': {
    'id': 149,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'wolf',
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
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cow',
    'tiger',
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
    'mixed_type': 0.29283,
    'maybe_null': None,
},
},
    {
    'id': 50,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 150,
    'id_str': [
    '17',
    '15',
    '27',
    '27',
],
    'text_data': 'ee00af57b093403bac8d870984a35809',
    'rand_digit': 0,
    'rand_number': 0.7615,
    'rand_signed_int': 1,
    'rand_datetime': '2000-02-09T05:42:11.812651+0200',
    'text_array': [
    'fe33f11fef4d49afbc5212f967625295',
    'e0cbb3d4b2d843048f9a1333953b28fd',
],
    'words': 'grasshopper wolf',
    'nested': {
    'id': 150,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ladybug',
    'squid',
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
    'mixed_type': None,
    'maybe': 'cheetah',
    'maybe_null': 'fox',
},
},
    {
    'id': 51,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 151,
    'id_str': [
    '06',
    '18',
    '15',
],
    'text_data': '67ab47e5880141429e45ff016df17ae9',
    'rand_digit': 4,
    'rand_number': 0.88348,
    'rand_signed_int': -5,
    'rand_datetime': '2000-07-21 00:41:25',
    'text_array': [
    '2c2efaa093ef4a7f80661b93574597fa',
    'e5a87e1bfff446799b971269c6ebc368',
],
    'words': 'hyena sloth',
    'nested': {
    'id': 151,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'bear',
    'lizard',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'mosquito',
    'maybe_null': 'shark',
},
},
    {
    'id': 52,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 152,
    'id_str': [
    '01',
    '04',
    '05',
],
    'text_data': 'a4a5828ed5834c62802635da5388c34e',
    'rand_digit': 0,
    'rand_number': 0.62864,
    'rand_signed_int': -6,
    'rand_datetime': '2000-06-11 01:49:47+0100',
    'text_array': [
    'c2f068db7a704490aa1b7bdaba252772',
    'c83a632f27cd40c3adf1160d82ffaae1',
],
    'words': 'turtle ant',
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
    'word': 'leopard',
    'number': 5,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'frog',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'squid',
    'koala',
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
    'mixed_type': 5,
    'maybe_null': 'grasshopper',
},
},
    {
    'id': 53,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 153,
    'id_str': [
    '01',
],
    'text_data': 'e442d14725b240eeb377d45beaa86cd4',
    'rand_digit': 1,
    'rand_number': 0.91787,
    'rand_signed_int': -8,
    'rand_datetime': '2000-10-22T02:19:38.852314-03:00',
    'text_array': [
    '6528d5ef12554cafa37903d22b14da76',
    '158e3455fbc741aaa561ca59ee553b77',
],
    'words': 'dragonfly gorilla',
    'nested': {
    'id': 153,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,5__',
    'two_words': [
    'mouse',
    'sloth',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
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
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 154,
    'id_str': [
],
    'text_data': 'a9eba6e9a8e54d57a469ac32cb4d4c2d',
    'rand_digit': 9,
    'rand_number': 0.29611,
    'rand_signed_int': -8,
    'rand_datetime': '2000-08-29T20:48:54',
    'text_array': [
    'a21dc1fe121d4bbfbef69e83311df2a4',
    'e46bfa5031824980a0432f175406f500',
],
    'words': 'dolphin frog',
    'nested': {
    'id': 154,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
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
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'lobster',
    'ape',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 55,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 155,
    'id_str': [
    '13',
    '08',
    '16',
    '19',
],
    'text_data': '9368991acd564a0f98bba0aa077601c1',
    'rand_digit': 2,
    'rand_number': 0.50283,
    'rand_signed_int': 7,
    'rand_datetime': '2000-01-29T00:01:33+1200',
    'text_array': [
    '9261c16f033f4ed0a4086cf5a2c5492a',
    'af60825fa5f1424385ec6ccea76cbd02',
],
    'words': 'monkey gorilla',
    'nested': {
    'id': 155,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'octopus',
    'hippo',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'goat',
    'maybe_null': 'cow',
},
},
    {
    'id': 56,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 156,
    'id_str': [
    '03',
    '06',
],
    'text_data': 'ea03b89199ac4c8ab81a383767f853e1',
    'rand_digit': 4,
    'rand_number': 0.1119,
    'rand_signed_int': -9,
    'rand_datetime': '2000-02-10 02:44:51.584282',
    'text_array': [
    '7de751cebb63470bb82bce510aa87cce',
    '67bc29ac466640cc95033bec0368d3f8',
],
    'words': 'koala hyena',
    'nested': {
    'id': 156,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snake',
    'pig',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': [
    7,
],
    'rand_bool': False,
    'mixed_type': 0.92763,
    'maybe': 'bear',
    'maybe_null': 'hippo',
},
},
    {
    'id': 57,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 157,
    'id_str': [
    '03',
],
    'text_data': '8541b33785b5434f8a8d77d0ee401e2b',
    'rand_digit': 6,
    'rand_number': 0.93925,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-20T13:41:14.051557',
    'text_array': [
    '328d8355cf2f4af7895d6f7ab3b99b93',
    'eb23bbf32c8d48b8ba7c1c7688d4511e',
],
    'words': 'frog butterfly',
    'nested': {
    'id': 157,
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
    'word': 'fox',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ant',
    'gorilla',
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
    'maybe_null': 'frog',
},
},
    {
    'id': 58,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 158,
    'id_str': [
    '15',
    '02',
],
    'text_data': '3adf2e3a634f4417997e3a86a8925135',
    'rand_digit': 7,
    'rand_number': 0.26502,
    'rand_signed_int': -8,
    'rand_datetime': '2000-03-01T01:49:07.378108-0600',
    'text_array': [
    '17c0ede83f2a4fe7b5ddceba566ed114',
    '78b4b34cd5c74a6cba51356690ba5326',
],
    'words': 'rhino dog',
    'nested': {
    'id': 158,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 4,
},
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
    'hello',
],
    'word': 'grasshopper',
    'number': 8,
},
    {
    'nested_empty': None,
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
    10,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'turtle',
    'dog',
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
    'mixed_type': False,
    'maybe_null': 'gorilla',
},
},
    {
    'id': 59,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 159,
    'id_str': [
    '21',
    '04',
    '09',
    '22',
    '26',
],
    'text_data': 'c3bfdcf1d4014098bb49c10197093163',
    'rand_digit': 6,
    'rand_number': 0.60271,
    'rand_signed_int': 7,
    'rand_datetime': '2000-01-28T01:07:06-0400',
    'text_array': [
    'd8a6a322063d4b359c214634250483ef',
    '6d79275b837648c9922e8dc364f77578',
],
    'words': 'crab duck',
    'nested': {
    'id': 159,
    'rand_digit': 2,
    'array': [
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'rabbit',
    'zebra',
],
    'city': {
    'name': 'Copenhagen',
    'geo': {
    'lat': 55.676097,
    'lon': 12.568337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bird',
},
},
    {
    'id': 60,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 160,
    'id_str': [
],
    'text_data': '403a77c078f54e8593cee0771b86beea',
    'rand_digit': 4,
    'rand_number': 0.73739,
    'rand_signed_int': 7,
    'rand_datetime': '2000-02-17 09:19:56',
    'text_array': [
    '28fa8841878e40119fc500f3025a6b7c',
    'bd6929a0f76e45968b7e156e1d2b5158',
],
    'words': 'crab hippo',
    'nested': {
    'id': 160,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 8,
},
],
},
    'nested_array': [
    [
    -2,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -1,
],
],
    'two_words': [
    'bee',
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
    'maybe_null': None,
},
},
    {
    'id': 61,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 161,
    'id_str': [
    '20',
    '24',
    '07',
],
    'text_data': '3f7296721b2444c6bfe7bf1ad9dbeaf7',
    'rand_digit': 0,
    'rand_number': 0.52425,
    'rand_signed_int': -10,
    'rand_datetime': '2000-07-10T14:10:11+0700',
    'text_array': [
    'd8cf93569d8c4e84848ce2d60fed05ca',
    '65baf1ea4b364cb3bf935f5d686b134a',
],
    'words': 'ladybug duck',
    'nested': {
    'id': 161,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 9,
},
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
],
    'word': 'crab',
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
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lizard',
    'snake',
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
    'mixed_type': 0.79013,
    'maybe': 'cheetah',
},
},
    {
    'id': 62,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 162,
    'id_str': [
    '18',
],
    'text_data': '189cc6f3bf8a420db91501b40ee86503',
    'rand_digit': 0,
    'rand_number': 0.96576,
    'rand_signed_int': 0,
    'rand_datetime': '2000-09-03T08:56:17+0200',
    'text_array': [
    '3ab09a583f414df09044801f806e3f17',
    '2da6cf5fd9d94859aac9354fb7d4beb2',
],
    'words': 'grasshopper rabbit',
    'nested': {
    'id': 162,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'snail',
    'whale',
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
    'mixed_type': 6,
},
},
    {
    'id': 63,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 163,
    'id_str': [
    '06',
    '16',
],
    'text_data': '92bf6c8891a849dab2895fe48031f408',
    'rand_digit': 9,
    'rand_number': 0.62508,
    'rand_signed_int': -1,
    'rand_datetime': '2000-01-10T21:57:12+0400',
    'text_array': [
    'e30bc2aeb0a34a149745aba2b842edb2',
    '3fd9d8de7cf741eb911de45e55d8c53d',
],
    'words': 'camel lizard',
    'nested': {
    'id': 163,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'jaguar',
    'goat',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': [
    64,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'cat',
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
    'content-length': '419504',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 100,
    'id_str': [
    '09',
],
    'text_data': '460241ef19a34f1292f4bea0528db48a',
    'rand_digit': 8,
    'rand_number': 0.88333,
    'rand_signed_int': -5,
    'rand_datetime': '2000-07-08T16:58:13.991013-1200',
    'text_array': [
    'f2d7f45724d1461ca9c1bbecbd22aaef',
    '638c0ee6aa5b4767ba8ff9b247a696bd',
],
    'words': 'grasshopper tiger',
    'nested': {
    'id': 100,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    [
    -10,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'chicken',
    'lizard',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'sloth',
    'maybe': 'fly',
    'maybe_null': 'deer',
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 101,
    'id_str': [
    '20',
    '08',
    '02',
    '29',
    '27',
],
    'text_data': '90c8db55db254933ba63c21c175baabe',
    'rand_digit': 3,
    'rand_number': 0.64882,
    'rand_signed_int': 10,
    'rand_datetime': '2000-12-01 15:18:45.999693-0300',
    'text_array': [
    'fb615f7496c3466a802f209cefb3acff',
    '118d4b3da9f34743877d17dda22e9224',
],
    'words': 'hyena tiger',
    'nested': {
    'id': 101,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 2,
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
    'word': 'lion',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'camel',
    'pig',
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
    'mixed_type': True,
},
},
    {
    'id': 2,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 102,
    'id_str': [
    '21',
    '04',
    '24',
    '24',
    '02',
],
    'text_data': 'a8a6a648524049dbafabad7a7fc3888e',
    'rand_digit': 3,
    'rand_number': 0.5245,
    'rand_signed_int': -7,
    'rand_datetime': '2000-05-10T15:08:20.007311-11:00',
    'text_array': [
    'cf0d1ae52e5249819e6ed9be7182cfa9',
    '9134eb9af7594f31a2741be00ab721a3',
],
    'words': 'dog horse',
    'nested': {
    'id': 102,
    'rand_digit': 6,
    'array': [
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
    'word': 'butterfly',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ant',
    'dog',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cow',
    'maybe_null': None,
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 103,
    'id_str': [
    '03',
],
    'text_data': '7c64c5befad5498bb23711b1df781b55',
    'rand_digit': 7,
    'rand_number': 0.23619,
    'rand_signed_int': 3,
    'rand_datetime': '2000-12-22T00:10:08.420063+0400',
    'text_array': [
    'ff97a337a8ce4cc888751729a41241fb',
    'f40d3c95060a447683d603200e8c4c87',
],
    'words': 'bee shark',
    'nested': {
    'id': 103,
    'rand_digit': 9,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
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
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
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
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'leopard',
    'snake',
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
    'mixed_type': 3,
    'maybe_null': 'rhino',
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 104,
    'id_str': [
    '07',
    '19',
],
    'text_data': 'd48cf6ec657d4793a701986b8f9f3d75',
    'rand_digit': 5,
    'rand_number': 0.06429,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-06T18:43:25.452785-1200',
    'text_array': [
    '2d45d66832da4cc3bacc70da84ab0abb',
    '176899b98b3342169fa8d95563865936',
],
    'words': 'whale wolf',
    'nested': {
    'id': 104,
    'rand_digit': 8,
    'array': [
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
    'hello',
],
    'word': 'dolphin',
    'number': 6,
},
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
],
    'word': 'monkey',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    7,
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lion',
    'tiger',
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
    'mixed_type': 0.65963,
    'maybe': 'elephant',
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 105,
    'id_str': [
    '17',
    '17',
    '17',
    '21',
    '11',
],
    'text_data': '50c1b7a8bbb1420e84ccb073239bf26e',
    'rand_digit': 4,
    'rand_number': 0.45662,
    'rand_signed_int': 2,
    'rand_datetime': '2001-01-22 00:10',
    'text_array': [
    '460ebed9be43488181bd03bd974dafa0',
    '470afe551ce54e60b185b48e3e3189c3',
],
    'words': 'whale cat',
    'nested': {
    'id': 105,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'dog',
    'number': 8,
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
    'word': 'ape',
    'number': 6,
},
],
},
    'nested_array': [
    [
    -3,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'ant',
    'koala',
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
    'mixed_type': 'bird',
    'maybe': 'dragonfly',
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 106,
    'id_str': [
    '19',
    '04',
],
    'text_data': '99e2fce1bb434d43aae1d1716286dafd',
    'rand_digit': 4,
    'rand_number': 0.52155,
    'rand_signed_int': 4,
    'rand_datetime': '2000-07-30T13:27:33.929886-1200',
    'text_array': [
    '8c13b05177364b3584af8100b3aeb881',
    'cba603e2cf6d4a29a309ab1840d31d13',
],
    'words': 'kangaroo duck',
    'nested': {
    'id': 106,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'hyena',
    'dog',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cheetah',
    'maybe_null': 'bear',
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 107,
    'id_str': [
    '27',
    '27',
],
    'text_data': '196f3936681649e5b37f48852c7f4109',
    'rand_digit': 9,
    'rand_number': 0.42934,
    'rand_signed_int': -8,
    'rand_datetime': '2000-03-02 23:15:40.078271',
    'text_array': [
    'edb0470f1800437e871a78361edc3160',
    '8e6517f32f944f6aaa2d03df2985f6bc',
],
    'words': 'lion gorilla',
    'nested': {
    'id': 107,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lobster',
    'tiger',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': [
    39,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'hyena',
    'maybe_null': 'hippo',
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 108,
    'id_str': [
    '27',
    '24',
    '01',
],
    'text_data': 'e6e8d8be5baa441cb9ef99bb61c3f2cf',
    'rand_digit': 1,
    'rand_number': 0.06049,
    'rand_signed_int': -8,
    'rand_datetime': '2000-03-24 01:28',
    'text_array': [
    'd23cc04955a943d09163193d7ccca2ba',
    'd90aa26f7ff74263b06a594a537d3c18',
],
    'words': 'koala whale',
    'nested': {
    'id': 108,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'fox',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'grasshopper',
    'sheep',
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
    'mixed_type': 'lizard',
    'maybe_null': None,
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 109,
    'id_str': [
    '03',
    '28',
    '18',
    '28',
    '16',
],
    'text_data': '26b9bbcdce0240f0b62310db285afeb2',
    'rand_digit': 8,
    'rand_number': 0.22233,
    'rand_signed_int': 10,
    'rand_datetime': '2000-07-17 22:13',
    'text_array': [
    '903af94ab4944ec295336408d63ecff2',
    '12b47da0781640978e4ef358ff833039',
],
    'words': 'crab kangaroo',
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
    'word': 'whale',
    'number': 1,
},
],
},
    'nested_array': [
    [
    2,
],
    [
    2,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ladybug',
    'snake',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': [
    43,
],
    'rand_bool': False,
    'mixed_type': 'mouse',
    'maybe': 'sloth',
    'maybe_null': None,
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 110,
    'id_str': [
],
    'text_data': '7ae1dcac5a1745b897f7c8c7b897b5ea',
    'rand_digit': 4,
    'rand_number': 0.2002,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-02',
    'text_array': [
    '260c4a5fe019490bb6433cc5e84d40b3',
    'b3700dbcab1b4b5a8feaef4f082d94d5',
],
    'words': 'jaguar dragonfly',
    'nested': {
    'id': 110,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'grasshopper',
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
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'rhino',
    'grasshopper',
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
    'mixed_type': 0.97713,
    'maybe': 'butterfly',
    'maybe_null': 'crab',
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 111,
    'id_str': [
    '14',
    '04',
],
    'text_data': 'b7fac6395630487da5726d1b3e1b8707',
    'rand_digit': 9,
    'rand_number': 0.36219,
    'rand_signed_int': 3,
    'rand_datetime': '2000-03-24T11:35:38.862043+0800',
    'text_array': [
    '2db8d56129aa4857ab83dfb12a943991',
    'f22b70cec0e949cca90379fc20481f6d',
],
    'words': 'hyena mouse',
    'nested': {
    'id': 111,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 1,
},
    {
    'nested_empty': None,
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
    'word': 'ape',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'cow',
    'elephant',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.1432,
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 112,
    'id_str': [
    '15',
    '09',
    '16',
],
    'text_data': '69a243b33de84826a0a22e9eca005e00',
    'rand_digit': 7,
    'rand_number': 0.65264,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-03 01:25:44.791521',
    'text_array': [
    'f6553b004672402b82537c65cf552f37',
    '859189e22a46454c8fb7447a853a7d06',
],
    'words': 'octopus turtle',
    'nested': {
    'id': 112,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'cheetah',
    'cheetah',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'ladybug',
    'maybe_null': None,
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 113,
    'id_str': [
    '29',
    '30',
    '11',
],
    'text_data': '760b92e86cda4d0795fedcb3a098d60d',
    'rand_digit': 7,
    'rand_number': 0.70063,
    'rand_signed_int': 7,
    'rand_datetime': '2000-07-23 06:45:58.362968',
    'text_array': [
    '13860ff213a74665841fe3467fd2a0b5',
    '2f026e387a8841eb9f23569e349f0d09',
],
    'words': 'scorpion squid',
    'nested': {
    'id': 113,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'whale',
    'number': 7,
},
    {
    'nested_empty': None,
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
    'word': 'bird',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dolphin',
    'fox',
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
    'mixed_type': False,
    'maybe_null': 'fly',
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 114,
    'id_str': [
    '30',
    '10',
    '12',
    '02',
],
    'text_data': 'c1d46635efa54566a3f1ea976c97ef01',
    'rand_digit': 7,
    'rand_number': 0.81309,
    'rand_signed_int': -6,
    'rand_datetime': '2000-05-10 10:01:21',
    'text_array': [
    '088184f162a444d58594e901e82c567d',
    '791e2d8dd4a84b889505581b888ca850',
],
    'words': 'giraffe spider',
    'nested': {
    'id': 114,
    'rand_digit': 0,
    'array': [
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
    'word': 'crab',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'spider',
    'ape',
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
    'maybe': 'grasshopper',
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 115,
    'id_str': [
    '04',
    '21',
],
    'text_data': '5a563b81bf464dd8aa8dbc4ce9773c3d',
    'rand_digit': 2,
    'rand_number': 0.87224,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-08T19:07:44.796636+02:00',
    'text_array': [
    'ee911cd97961447f957477813df5bf4f',
    'd0127d5b3a514e34a860e770e36324af',
],
    'words': 'crab jaguar',
    'nested': {
    'id': 115,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
    -7,
],
    [
    10,
],
    [
    -1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'rhino',
    'bee',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 116,
    'id_str': [
],
    'text_data': 'ef2a18de5f03415683d94dd020d8fb58',
    'rand_digit': 3,
    'rand_number': 0.57203,
    'rand_signed_int': -9,
    'rand_datetime': '2001-01-11 01:24:41-0700',
    'text_array': [
    '791772b0346d49d4bd4a9e9ed0df1cbd',
    'd3023281b2a5477da28b4d19986890f2',
],
    'words': 'dragonfly monkey',
    'nested': {
    'id': 116,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'spider',
    'ape',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': [
    8,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'spider',
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 117,
    'id_str': [
    '02',
    '21',
    '21',
],
    'text_data': '4fb39c08665b4c2ab69a9d96b3f9f280',
    'rand_digit': 9,
    'rand_number': 0.35884,
    'rand_signed_int': 6,
    'rand_datetime': '2000-10-28 14:05',
    'text_array': [
    '4cfc69013eca46ebb811fb9e87c8ac5a',
    'a6a0e2f17de24384b2c8e2bf9641ee62',
],
    'words': 'shark rhino',
    'nested': {
    'id': 117,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 6,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'monkey',
    'horse',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': 18,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 118,
    'id_str': [
    '03',
    '14',
],
    'text_data': '879e8838507c4c6c94c36cfd551aa2f7',
    'rand_digit': 7,
    'rand_number': 0.95256,
    'rand_signed_int': -10,
    'rand_datetime': '2000-09-01 06:23:34.358151',
    'text_array': [
    '94bfb54490a84c188e2f5de5e99f5b2d',
    'd5eba5b5cade4e8dabbcf91c83714123',
],
    'words': 'whale spider',
    'nested': {
    'id': 118,
    'rand_digit': 9,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'hippo',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'monkey',
    'camel',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.87184,
    'maybe': 'crab',
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
    '21',
    '23',
    '06',
    '14',
    '29',
],
    'text_data': '46b37ce937df46e9b759f11db2ce4be4',
    'rand_digit': 5,
    'rand_number': 0.94143,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-18 15:42',
    'text_array': [
    '4ccc129c6e7d4c4a9ce0712ebc293e80',
    'ea012bfe01fd4bd3a477a581b2111ecb',
],
    'words': 'fish panda',
    'nested': {
    'id': 119,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'dragonfly',
    'mosquito',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'whale',
    'maybe_null': None,
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 120,
    'id_str': [
    '17',
    '02',
    '11',
    '13',
    '25',
],
    'text_data': 'd38bb7a73d4146b39c1d2a7e58143752',
    'rand_digit': 1,
    'rand_number': 0.60337,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-14 13:46:53.233560+0700',
    'text_array': [
    '98f4f500dc5742358138095d00c14968',
    'eb1567eda71344e29b30b29a05e050ab',
],
    'words': 'panda bear',
    'nested': {
    'id': 120,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
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
],
    'word': 'monkey',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'zebra',
    'snake',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': [
    90,
],
    'rand_bool': False,
    'mixed_type': 8,
    'maybe': 'rhino',
    'maybe_null': 'cow',
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 121,
    'id_str': [
    '08',
],
    'text_data': 'e5263222cdcf4b8788081e501f45fdfd',
    'rand_digit': 8,
    'rand_number': 0.04118,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-03T17:48:21.818606',
    'text_array': [
    'f9cf70e8ca7b43ccb091109d0e18b3ef',
    'bb7d42f516a64acca76f0aff8173614f',
],
    'words': 'wolf spider',
    'nested': {
    'id': 121,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 5,
},
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
    'hello',
],
    'word': 'cheetah',
    'number': 7,
},
    {
    'nested_empty': None,
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
    'word': 'bear',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'mosquito',
    'jaguar',
],
    'city': {
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'cow',
    'maybe_null': None,
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
    '28',
    '24',
],
    'text_data': 'f698521cfd4c43b49c1f29c83c4835f2',
    'rand_digit': 1,
    'rand_number': 0.32528,
    'rand_signed_int': -1,
    'rand_datetime': '2000-11-06 19:29:28',
    'text_array': [
    '2a251752880141439bc704a4ec519dec',
    '4360a293d3cf4d7ca400134375729bc7',
],
    'words': 'whale snake',
    'nested': {
    'id': 122,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    0,
],
],
    'two_words': [
    'wolf',
    'dog',
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
    'mixed_type': 0,
    'maybe_null': 'duck',
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 123,
    'id_str': [
    '02',
    '22',
],
    'text_data': '6ad042bb849c433c8322f66f5286cefb',
    'rand_digit': 5,
    'rand_number': 0.91614,
    'rand_signed_int': 3,
    'rand_datetime': '2000-07-03T21:03:51.697976',
    'text_array': [
    'b3ff94b7aa6a457cbf0fdb6ab61da5d1',
    '9eddc6c98e96431c9d5e1317d65ec529',
],
    'words': 'scorpion dragonfly',
    'nested': {
    'id': 123,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    7,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'monkey',
    'spider',
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
    'maybe': 'octopus',
    'maybe_null': 'cat',
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 124,
    'id_str': [
    '07',
    '02',
    '23',
    '13',
    '12',
],
    'text_data': '245380acf3d248fa8d7781796e9b2d48',
    'rand_digit': 1,
    'rand_number': 0.67729,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-25 13:49:59',
    'text_array': [
    '339a81ed4018438285f36006a6a775cf',
    'c7ebc1dfdefb401cbe5961430f35c108',
],
    'words': 'lobster camel',
    'nested': {
    'id': 124,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fox',
    'crab',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'frog',
    'maybe_null': 'elephant',
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
    '23',
    '30',
    '05',
    '01',
],
    'text_data': 'b42d8e96072d4ffb863bf3003895f276',
    'rand_digit': 3,
    'rand_number': 0.67761,
    'rand_signed_int': 5,
    'rand_datetime': '2000-07-17 10:35:03-0500',
    'text_array': [
    '35cc2a9306ba4e078a9571c79ddf6319',
    'c79fe1c0712e4c3d80ad5b61aa0e4a6b',
],
    'words': 'mouse dog',
    'nested': {
    'id': 125,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'cheetah',
    'lobster',
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
    'mixed_type': 'kangaroo',
    'maybe': 'crab',
},
},
    {
    'id': 26,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 126,
    'id_str': [
    '19',
    '19',
    '21',
],
    'text_data': '0d229b1839ef4332bb98412073e88205',
    'rand_digit': 2,
    'rand_number': 0.34453,
    'rand_signed_int': 8,
    'rand_datetime': '2000-12-02 18:58:37+1000',
    'text_array': [
    '7a9af1c902584b6ca079189c250831ca',
    '13ff5c9f0ece46a5bd8eeda12ea77613',
],
    'words': 'hippo octopus',
    'nested': {
    'id': 126,
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
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'bee',
    'tiger',
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
    'mixed_type': True,
    'maybe': 'sheep',
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 127,
    'id_str': [
    '24',
],
    'text_data': 'aea25e081d3745a9985f1851c397beed',
    'rand_digit': 1,
    'rand_number': 0.35312,
    'rand_signed_int': -5,
    'rand_datetime': '2000-12-17T21:49:04.106577-0800',
    'text_array': [
    'bcec524dc8264444b54bcb8675b91171',
    'e0b463cc68c94a0abd3fde072f7e6f58',
],
    'words': 'hippo jaguar',
    'nested': {
    'id': 127,
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
    'hello',
],
    'word': 'fox',
    'number': 6,
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
    'word': 'dolphin',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'spider',
    'cow',
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
    'maybe_null': 'spider',
},
},
    {
    'id': 28,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 128,
    'id_str': [
    '11',
    '02',
    '28',
],
    'text_data': 'a6c121d7ad0445f3aeab0972b6a15e72',
    'rand_digit': 2,
    'rand_number': 0.48488,
    'rand_signed_int': 2,
    'rand_datetime': '2000-01-18 23:05:19.378715',
    'text_array': [
    '47343ef278ac44ca807fa127380be3c9',
    'd8bc648969924f848c1809d03d5ff0f7',
],
    'words': 'fish fish',
    'nested': {
    'id': 128,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -6,
],
],
    'two_words': [
    'leopard',
    'mouse',
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
    'mixed_type': 4,
    'maybe': 'cheetah',
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
    '16',
    '18',
],
    'text_data': 'bd6f5226ff6d441d8e8228bd1ff21eda',
    'rand_digit': 2,
    'rand_number': 0.05659,
    'rand_signed_int': -5,
    'rand_datetime': '2000-06-19 11:38:08',
    'text_array': [
    'a98aaf9291ce40bb9446b189a252cb1c',
    'b50de2538b7c4957b1d38ef207ac31ca',
],
    'words': 'scorpion dog',
    'nested': {
    'id': 129,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 6,
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
    -6,
],
],
    'two_words': [
    'giraffe',
    'fly',
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
    'mixed_type': 'dog',
    'maybe': 'wolf',
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 130,
    'id_str': [
],
    'text_data': '2bcb8e4b270e408ca4d7990f7c763e75',
    'rand_digit': 6,
    'rand_number': 0.87117,
    'rand_signed_int': -10,
    'rand_datetime': '2000-04-10T03:25:14.847853',
    'text_array': [
    '87143e422f6a4a408a1055a788c496cd',
    'b485667519c54e62adb4a4b84511c186',
],
    'words': 'leopard horse',
    'nested': {
    'id': 130,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'frog',
    'number': 10,
},
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
],
},
    'nested_array': '__FLOAT_MULTI_DIM_3,3__',
    'two_words': [
    'rabbit',
    'rabbit',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': [
    13,
],
    'rand_bool': False,
    'mixed_type': 3,
    'maybe': 'crab',
    'maybe_null': None,
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 131,
    'id_str': [
    '05',
    '12',
    '25',
],
    'text_data': '5419461183e34bb0bdc33421c81c8db0',
    'rand_digit': 7,
    'rand_number': 0.83212,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-12 18:24:29',
    'text_array': [
    'd6bb5945b08b48288cd293010005422d',
    '82608e5d272f4bf8b33bce49d9b63080',
],
    'words': 'grasshopper octopus',
    'nested': {
    'id': 131,
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
    'number': 2,
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
    'word': 'cow',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'duck',
    'leopard',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'duck',
    'maybe_null': None,
},
},
    {
    'id': 32,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 132,
    'id_str': [
    '15',
],
    'text_data': 'a02f2cf7e4634379864024879b857678',
    'rand_digit': 1,
    'rand_number': 0.15834,
    'rand_signed_int': -2,
    'rand_datetime': '2000-05-13T04:22:58.676609-07:00',
    'text_array': [
    'afb05ead83e54768851d60fed589131f',
    '52a7a03ce2f24ebe898903203393b5b4',
],
    'words': 'giraffe koala',
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
    'word': 'ladybug',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'hyena',
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
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'bee',
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 133,
    'id_str': [
    '17',
    '29',
    '24',
    '30',
],
    'text_data': '5792218de7e5408191802959f44edf70',
    'rand_digit': 6,
    'rand_number': 0.62306,
    'rand_signed_int': 2,
    'rand_datetime': '2000-09-09 17:36:46.843278-0500',
    'text_array': [
    '3513fce1d2f14773bab1b09077bea730',
    '3a3d17eed3ae44b6bcff75e1989d7d28',
],
    'words': 'grasshopper snail',
    'nested': {
    'id': 133,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bird',
    'whale',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': [
    23,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'hippo',
    'maybe_null': 'jaguar',
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 134,
    'id_str': [
    '23',
],
    'text_data': '8447b52bb32e4d6cb22c7501178e10d2',
    'rand_digit': 8,
    'rand_number': 0.18608,
    'rand_signed_int': -7,
    'rand_datetime': '2000-04-08 23:21:18',
    'text_array': [
    '91389427242c405eb9b8623eafa7b45d',
    'c6cf0aed95e243739f4abda2dced13ce',
],
    'words': 'dolphin mosquito',
    'nested': {
    'id': 134,
    'rand_digit': 3,
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
],
    'word': 'chicken',
    'number': 6,
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
    'word': 'giraffe',
    'number': 3,
},
],
},
    'nested_array': [
    [
    4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lobster',
    'lobster',
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
    'mixed_type': None,
    'maybe': 'sheep',
    'maybe_null': None,
},
},
    {
    'id': 35,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 135,
    'id_str': [
    '20',
    '28',
    '23',
    '19',
],
    'text_data': '5c690944bf6342b69ce80ac6c9f5a7d3',
    'rand_digit': 5,
    'rand_number': 0.0578,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-09T01:41:17.389430-0600',
    'text_array': [
    'eab25019877e4eecb6e549a1a9cb0aea',
    '17f11fb0582c40cbb640b71029431362',
],
    'words': 'spider dolphin',
    'nested': {
    'id': 135,
    'rand_digit': 8,
    'array': [
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -1,
],
],
    'two_words': [
    'dog',
    'camel',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'panda',
},
},
    {
    'id': 36,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 136,
    'id_str': [
],
    'text_data': 'ec3ee3619d0c41ab812be4b8616fb0f5',
    'rand_digit': 2,
    'rand_number': 0.51435,
    'rand_signed_int': -1,
    'rand_datetime': '2000-01-29T18:54:42.726259+05:00',
    'text_array': [
    '69f71aadd3f34094ad1bf3881a2782ca',
    '0ebb03bdc8bf43edb113702e50d579d7',
],
    'words': 'monkey goat',
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
    'word': 'wolf',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lion',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'ape',
    'sheep',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'rhino',
    'maybe_null': 'butterfly',
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
    '05',
    '02',
    '04',
],
    'text_data': 'a8921e0c5ffa4762988bc426d40be5bf',
    'rand_digit': 3,
    'rand_number': 0.27403,
    'rand_signed_int': 0,
    'rand_datetime': '2000-06-05 10:47:57',
    'text_array': [
    '157c4a825749429281414486bffeb232',
    'cd2fa273ed11479b9b22647fba96c120',
],
    'words': 'monkey mouse',
    'nested': {
    'id': 137,
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
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'scorpion',
    'monkey',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bear',
    'maybe_null': 'bird',
},
},
    {
    'id': 38,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 138,
    'id_str': [
    '10',
    '01',
    '07',
],
    'text_data': 'd047056dbb7846ebbea43ffe3e8a580e',
    'rand_digit': 1,
    'rand_number': 0.72554,
    'rand_signed_int': 0,
    'rand_datetime': '2000-12-26T14:12:40',
    'text_array': [
    '01ba84c532c6497b826f11a5b6dcf087',
    'f9f504f76d344055b2a9830bb7b37f30',
],
    'words': 'camel panda',
    'nested': {
    'id': 138,
    'rand_digit': 4,
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
    'word': 'fish',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 2,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,3__',
    'two_words': [
    'fox',
    'dragonfly',
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
    'mixed_type': 0.68339,
    'maybe': 'wolf',
    'maybe_null': 'horse',
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 139,
    'id_str': [
    '14',
    '30',
    '12',
    '22',
    '09',
],
    'text_data': '2d20fdb60d704355afdeeb0f999af69b',
    'rand_digit': 4,
    'rand_number': 0.97829,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-15 20:24:35+1000',
    'text_array': [
    '0ca4e7d226664133b82ebd2844c36f01',
    '8c45a919f3c8496ba152aaf4fb0751d5',
],
    'words': 'duck chicken',
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
    'word': 'elephant',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'bird',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'frog',
    'whale',
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
    'maybe_null': None,
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 140,
    'id_str': [
    '26',
    '16',
],
    'text_data': 'dd170f6b25bb4261b1eb15de83a28610',
    'rand_digit': 6,
    'rand_number': 0.14996,
    'rand_signed_int': 2,
    'rand_datetime': '2001-01-03 20:42:20',
    'text_array': [
    'bf4fe23a82a645b79ac29486fbc6ba8d',
    '15ed81270a83470797df256abce28b8e',
],
    'words': 'camel cow',
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
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 9,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'panda',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    8,
],
    [
],
],
    'two_words': [
    'fox',
    'cow',
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
    'maybe': 'lizard',
    'maybe_null': None,
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 141,
    'id_str': [
],
    'text_data': '3e4531ec8c5d42b1a79ec6cd5232d7bb',
    'rand_digit': 0,
    'rand_number': 0.96872,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-08 13:07:02.413895+0200',
    'text_array': [
    '0691c8f65af14153bf50ae8f280d6ad9',
    'a178ae3674b4411eb4de49e90017253e',
],
    'words': 'horse chicken',
    'nested': {
    'id': 141,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'dog',
    'number': 2,
},
],
},
    'nested_array': [
    [
    -2,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'deer',
    'goat',
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
    'mixed_type': 0.31824,
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 142,
    'id_str': [
    '20',
],
    'text_data': '1f6745de8fd94bb49b59653692ae8380',
    'rand_digit': 8,
    'rand_number': 0.60519,
    'rand_signed_int': -7,
    'rand_datetime': '2000-02-25 17:37:07',
    'text_array': [
    '16baec6ff9694210bb7ef4a1ee5175c4',
    '555da8ecd25648769ddfedd560ffd89e',
],
    'words': 'hippo snake',
    'nested': {
    'id': 142,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 1,
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
    'word': 'bear',
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'goat',
    'elephant',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 43,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 143,
    'id_str': [
    '19',
    '20',
    '03',
    '23',
],
    'text_data': '4d68d8665a964ae28408d77d62575c0e',
    'rand_digit': 4,
    'rand_number': 0.83224,
    'rand_signed_int': 9,
    'rand_datetime': '2000-03-15T02:51:57.189531+0200',
    'text_array': [
    '404e42142e114dee9328188ee367ca45',
    '2770e14a629c4b54a50a8025178efc98',
],
    'words': 'kangaroo jaguar',
    'nested': {
    'id': 143,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
],
    'word': 'bee',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'butterfly',
    'goat',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'horse',
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 144,
    'id_str': [
    '02',
    '01',
    '10',
    '17',
    '01',
],
    'text_data': 'a61c8d0003f3491b934f2194954938ec',
    'rand_digit': 7,
    'rand_number': 0.21509,
    'rand_signed_int': 8,
    'rand_datetime': '2000-09-06 14:26:32.330694-0300',
    'text_array': [
    '9adae59d8c8f4bf6b2ed3646a08508f9',
    '2c6381202a9c44adbd5f05064f7a351d',
],
    'words': 'bear jaguar',
    'nested': {
    'id': 144,
    'rand_digit': 5,
    'array': [
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
    [
    5,
],
    [
    -7,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'snail',
    'jaguar',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 145,
    'id_str': [
    '13',
    '06',
    '27',
    '01',
],
    'text_data': 'e5bafea0c33a4abc8e672762aa24343a',
    'rand_digit': 3,
    'rand_number': 0.52579,
    'rand_signed_int': 7,
    'rand_datetime': '2000-03-16',
    'text_array': [
    '3e5ff0a8b3ec4601ae53b8c6f7799aa9',
    '3194ca2cbdbf41108c2e8e902d4ec4de',
],
    'words': 'cheetah ladybug',
    'nested': {
    'id': 145,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 4,
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
    [
    10,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'crab',
    'zebra',
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
    'maybe': 'duck',
    'maybe_null': 'turtle',
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
    '22',
    '18',
    '15',
],
    'text_data': '4ed34936bf6d4efc8bccfed3fa02fc52',
    'rand_digit': 3,
    'rand_number': 0.02395,
    'rand_signed_int': 9,
    'rand_datetime': '2000-01-31T17:06:34.018449',
    'text_array': [
    '2776e71dcf4b4b44a8f3aa758857ddff',
    '6d69fccc4d4e4ecf8bfc8a4c9a228486',
],
    'words': 'giraffe chicken',
    'nested': {
    'id': 146,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 1,
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
],
    'word': 'crab',
    'number': 4,
},
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
    'word': 'fly',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'leopard',
    'deer',
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
    'mixed_type': None,
    'maybe_null': 'ape',
},
},
    {
    'id': 47,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 147,
    'id_str': [
    '06',
    '01',
],
    'text_data': '876fbfd97fa54eb7a00856f4806a1b80',
    'rand_digit': 6,
    'rand_number': 0.18774,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-23 01:44:13',
    'text_array': [
    'c4eda2b1282a46b09bcc6ec6fed22ca5',
    '24bb063bc9ca472b9a1f2784cac1cb07',
],
    'words': 'goat lobster',
    'nested': {
    'id': 147,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'ape',
    'number': 2,
},
],
},
    'nested_array': [
    [
    -2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -4,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'ladybug',
    'dolphin',
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
    'mixed_type': 0.11768,
    'maybe': 'cheetah',
},
},
    {
    'id': 48,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 148,
    'id_str': [
    '18',
    '02',
    '10',
],
    'text_data': 'a2fa44f86da34e039154038e5dbab823',
    'rand_digit': 9,
    'rand_number': 0.61823,
    'rand_signed_int': 3,
    'rand_datetime': '2000-09-22',
    'text_array': [
    '10a33fe645a245b98b4fb7da193ae830',
    'bc7bdc34ef32462a906c9d06456eee6d',
],
    'words': 'frog whale',
    'nested': {
    'id': 148,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'pig',
    'shark',
],
    'city': {
    'name': 'Cardiff',
    'geo': {
    'lat': 51.481581,
    'lon': -3.17909,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 5,
    'maybe': 'snake',
    'maybe_null': 'hyena',
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 149,
    'id_str': [
    '03',
    '29',
    '18',
    '07',
],
    'text_data': '8315a191d6304df59acf177391dd7a27',
    'rand_digit': 3,
    'rand_number': 0.64491,
    'rand_signed_int': -7,
    'rand_datetime': '2000-11-02 19:52:41.301760+0200',
    'text_array': [
    'ab696528a8db4bb9944cc63acf310444',
    '2244cf5cdb674d92bf76d00268d69c4b',
],
    'words': 'fish dolphin',
    'nested': {
    'id': 149,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
    1,
],
],
    'two_words': [
    'monkey',
    'snake',
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
    'content-length': '127',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'context': [
    {
    'positive': 10,
    'negative': 19,
},
],
},
    'using': 'multi-image',
    'limit': 100,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_multivector_discovery_queries.test_context_dot')
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
    test = TestMultivectorDiscoveryQueriestestContextDot()
    test.run_tests()
