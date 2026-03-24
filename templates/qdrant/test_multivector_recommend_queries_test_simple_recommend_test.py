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
logger = logging.getLogger('vdb_fuzzer.test.test_multivector_recommend_queries_test_simple_recommend')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_multivector_recommend_queries.test_simple_recommend"
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



class TestMultivectorRecommendQueriestestSimpleRecommend:
    """自动生成的VDB模糊测试类 - test_multivector_recommend_queries.test_simple_recommend"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_multivector_recommend_queries.test_simple_recommend"
        self.test_count = 11  # 测试方法数量
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
    'content-length': '538733',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 100,
    'id_str': [
    '08',
    '15',
    '28',
],
    'text_data': '2ab45370cece4dd2a87a22f9c49e9e08',
    'rand_digit': 7,
    'rand_number': 0.71366,
    'rand_signed_int': 7,
    'rand_datetime': '2000-09-26T00:57:45.657106+0200',
    'text_array': [
    '33461967907843ba8357f64ce7f40111',
    'fe4af790ad7d4a1ea76b26cb36f163c3',
],
    'words': 'butterfly snake',
    'nested': {
    'id': 100,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'giraffe',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    5,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'rhino',
    'fox',
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
    'mixed_type': 3,
    'maybe_null': None,
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 101,
    'id_str': [
    '30',
],
    'text_data': 'e210db57c3e94d6ea84576fdc98b7b1d',
    'rand_digit': 8,
    'rand_number': 0.98005,
    'rand_signed_int': 3,
    'rand_datetime': '2000-02-25 00:52:08',
    'text_array': [
    '7a6f43272dd14b089df3f7404d6b2cd2',
    '58d8982b8c4a4fb39cabe3b04a1566c2',
],
    'words': 'lobster crab',
    'nested': {
    'id': 101,
    'rand_digit': 0,
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
    'word': 'duck',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'dolphin',
    'number': 8,
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
    'zebra',
    'dolphin',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': [
    15,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'ape',
},
},
    {
    'id': 2,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 102,
    'id_str': [
    '23',
],
    'text_data': '7ac897737d7e4a998630ba3b6cfc3065',
    'rand_digit': 9,
    'rand_number': 0.73057,
    'rand_signed_int': 5,
    'rand_datetime': '2000-11-22T03:58:13-0200',
    'text_array': [
    'e8ca578d24394e1f815dafac8f0cf7fc',
    '1b05674a164c44db8c606b8c92804e2f',
],
    'words': 'gorilla gorilla',
    'nested': {
    'id': 102,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    9,
],
],
    'two_words': [
    'bee',
    'snail',
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
    'mixed_type': 'rabbit',
    'maybe': 'giraffe',
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 103,
    'id_str': [
    '23',
    '21',
    '26',
    '15',
],
    'text_data': '9800a6e6772b46768f4ee22de0a8802a',
    'rand_digit': 3,
    'rand_number': 0.52908,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-15 20:04',
    'text_array': [
    '4e47cea9104a4c249c19aca1d8745753',
    'cde89c9ad61f4c9d9195c57d92c47849',
],
    'words': 'leopard bird',
    'nested': {
    'id': 103,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
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
    'cat',
    'spider',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'deer',
    'maybe_null': None,
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 104,
    'id_str': [
    '05',
    '19',
    '06',
    '15',
    '27',
],
    'text_data': '247866b2e5934df5adaa004f5923ebf9',
    'rand_digit': 2,
    'rand_number': 0.69162,
    'rand_signed_int': 1,
    'rand_datetime': '2000-04-16 03:44:41.301841',
    'text_array': [
    'aa4b102b43cf4e8f95e1c8213858d8f0',
    '105b0e8e66494c52a9c1b44f48faca20',
],
    'words': 'mosquito gorilla',
    'nested': {
    'id': 104,
    'rand_digit': 2,
    'array': [
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
    'hello',
],
    'word': 'frog',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 6,
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
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lion',
    'ladybug',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': [
    29,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cheetah',
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 105,
    'id_str': [
    '04',
    '22',
],
    'text_data': '8e8686e5228b440eac56b1444e3eb223',
    'rand_digit': 2,
    'rand_number': 0.05256,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-12T14:47:15.856723',
    'text_array': [
    '9a5d886ec6254ae8861837472420db3d',
    '59c3556e39db4beeac572dd544b896bf',
],
    'words': 'rhino goat',
    'nested': {
    'id': 105,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
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
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hippo',
    'turtle',
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
    'maybe_null': None,
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 106,
    'id_str': [
],
    'text_data': 'f33d1e118d5343cb82d50f85171947d2',
    'rand_digit': 2,
    'rand_number': 0.73529,
    'rand_signed_int': 0,
    'rand_datetime': '2000-06-11',
    'text_array': [
    'a1f0a16131d644c191cfdd2348cd7409',
    '032a3a20507c4a50826d27e36093df51',
],
    'words': 'crab lobster',
    'nested': {
    'id': 106,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'turtle',
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
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'rhino',
    'dragonfly',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': [
    47,
],
    'rand_bool': False,
    'mixed_type': 0.52868,
    'maybe': 'goat',
    'maybe_null': 'leopard',
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 107,
    'id_str': [
],
    'text_data': '2828a94817134ffc912ee5dbd9af98ab',
    'rand_digit': 0,
    'rand_number': 0.49739,
    'rand_signed_int': 6,
    'rand_datetime': '2000-08-28T05:02:41.765649-0100',
    'text_array': [
    '80b6f609b9cb424a88027ec47936d761',
    'cbca28e93c8d4f9481eb563904708c98',
],
    'words': 'butterfly monkey',
    'nested': {
    'id': 107,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'hyena',
    'snail',
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
    'mixed_type': 'turtle',
    'maybe': 'mouse',
    'maybe_null': 'lion',
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 108,
    'id_str': [
    '15',
    '22',
],
    'text_data': '05070878ac2b4dff83c52a01344932c0',
    'rand_digit': 3,
    'rand_number': 0.16269,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-18T17:10:53.255923',
    'text_array': [
    'ccf30c9be7624f9da8a36cc20c9caf32',
    'f701536051314972bbeba606cc4fcc00',
],
    'words': 'cow crab',
    'nested': {
    'id': 108,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 7,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'whale',
    'squid',
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
    'mixed_type': False,
    'maybe': 'fish',
    'maybe_null': 'duck',
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 109,
    'id_str': [
    '09',
    '07',
    '07',
],
    'text_data': 'd92282b91b7b4591b5e11ad82f0fc740',
    'rand_digit': 6,
    'rand_number': 0.00244,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-25 17:12',
    'text_array': [
    '097752a0a9ca41bbbb22b5ba68dc10fe',
    'c233847a127c4be3bc004ac34d55cc1d',
],
    'words': 'pig sheep',
    'nested': {
    'id': 109,
    'rand_digit': 4,
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
    'word': 'bee',
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
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'elephant',
    'jaguar',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'camel',
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 110,
    'id_str': [
    '14',
],
    'text_data': '5fa63b9b77e641bc890d8f3c71fa48d8',
    'rand_digit': 4,
    'rand_number': 0.90289,
    'rand_signed_int': 0,
    'rand_datetime': '2000-11-28',
    'text_array': [
    'fdcea55f0d1f42f29e4602ef4d7360d7',
    '98c325681a2d4754acfb8cc41cb9bd22',
],
    'words': 'hyena mosquito',
    'nested': {
    'id': 110,
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
    'word': 'lizard',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
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
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -10,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lizard',
    'ant',
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
    'maybe': 'bee',
    'maybe_null': 'gorilla',
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 111,
    'id_str': [
    '21',
],
    'text_data': 'e6d95627f0e9454abf599f9ac26d9e73',
    'rand_digit': 1,
    'rand_number': 0.48359,
    'rand_signed_int': 7,
    'rand_datetime': '2000-10-14T08:44:23.186658+12:00',
    'text_array': [
    '632dfadbfab64ec88b543db74e3d4ba4',
    '540a02164ea64939affaa84dd2f1a904',
],
    'words': 'mosquito bee',
    'nested': {
    'id': 111,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 10,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'deer',
    'wolf',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 'lobster',
    'maybe': 'horse',
    'maybe_null': None,
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 112,
    'id_str': [
],
    'text_data': '6fa50e74c42d477a8d084d4bd5a0d534',
    'rand_digit': 3,
    'rand_number': 0.61339,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-30 10:02',
    'text_array': [
    'e4473eb27b8f409bb89fbebedd0488d4',
    'f331b33a1b624b84b9f038c0539d1eec',
],
    'words': 'dog gorilla',
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
    'word': 'koala',
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
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'cat',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    5,
],
],
    'two_words': [
    'camel',
    'turtle',
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
    'mixed_type': 'camel',
    'maybe': 'dog',
    'maybe_null': 'zebra',
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 113,
    'id_str': [
    '02',
],
    'text_data': 'f50893d1396b40899387123d955f19b8',
    'rand_digit': 7,
    'rand_number': 0.15293,
    'rand_signed_int': -2,
    'rand_datetime': '2000-04-05T02:26:11-1100',
    'text_array': [
    '550f7da3a68d40d0a267b4cf6a7bf008',
    '6cb01069e6cd493f971914f73c9ff3fd',
],
    'words': 'mosquito ladybug',
    'nested': {
    'id': 113,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'crab',
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 3,
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
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bird',
    'maybe_null': 'elephant',
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 114,
    'id_str': [
    '28',
    '22',
],
    'text_data': '6ff30f497bf04293a453a410f07fb4c7',
    'rand_digit': 3,
    'rand_number': 0.44089,
    'rand_signed_int': 1,
    'rand_datetime': '2000-08-18 09:49',
    'text_array': [
    '677c8dc08bb84c67a1fbbef877b7eb99',
    '32042d84b9d843429e156333d967118e',
],
    'words': 'elephant monkey',
    'nested': {
    'id': 114,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -8,
],
],
    'two_words': [
    'butterfly',
    'snail',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': [
    84,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'jaguar',
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 115,
    'id_str': [
    '11',
],
    'text_data': 'c68fc736cf6e49faa8d432b23485aff5',
    'rand_digit': 4,
    'rand_number': 0.61717,
    'rand_signed_int': -5,
    'rand_datetime': '2000-06-12',
    'text_array': [
    'a39484047e5649c086de7a573355a046',
    'b3030443505f42c99a93a353f7288bbf',
],
    'words': 'butterfly zebra',
    'nested': {
    'id': 115,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 2,
},
],
},
    'nested_array': [
    [
    -6,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    4,
],
],
    'two_words': [
    'gorilla',
    'frog',
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
    'mixed_type': 0.80675,
    'maybe': 'tiger',
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 116,
    'id_str': [
    '20',
    '01',
    '27',
    '27',
    '28',
],
    'text_data': '7d0111a964974325b4b9248d7a59b16c',
    'rand_digit': 6,
    'rand_number': 0.50048,
    'rand_signed_int': -4,
    'rand_datetime': '2000-08-07 17:20',
    'text_array': [
    'f773b2f1916b4491b44119351db1a891',
    '12ce5f564fda40e2aa70d1f97facf95a',
],
    'words': 'lobster whale',
    'nested': {
    'id': 116,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'jaguar',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 6,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fox',
    'panda',
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
    'mixed_type': 4,
    'maybe_null': None,
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 117,
    'id_str': [
    '27',
    '05',
    '09',
],
    'text_data': 'eb36974888514d45b3e3f408782908d6',
    'rand_digit': 6,
    'rand_number': 0.51844,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-21T11:11:32.324967+01:00',
    'text_array': [
    '24d5cb29b48946b9b1f9ee136436d93d',
    'e11458065cdc45519a5b7b14a679c48c',
],
    'words': 'zebra ladybug',
    'nested': {
    'id': 117,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 8,
},
    {
    'nested_empty': None,
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
    'word': 'jaguar',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'deer',
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
    26,
],
    'rand_bool': False,
    'mixed_type': None,
},
},
    {
    'id': 18,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 118,
    'id_str': [
    '04',
    '20',
],
    'text_data': '426bbdaa222f4f9fae36fe67cfa3d8fe',
    'rand_digit': 7,
    'rand_number': 0.7621,
    'rand_signed_int': 8,
    'rand_datetime': '2000-08-23 17:53:26.581703',
    'text_array': [
    'f6b99e26374e4a14811741a356913a7b',
    'c7b649bc1fff4cbf9e904f4a91eb36eb',
],
    'words': 'giraffe cow',
    'nested': {
    'id': 118,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -6,
],
    [
    -6,
],
],
    'two_words': [
    'fish',
    'ape',
],
    'city': {
    'name': 'Rome',
    'geo': {
    'lat': 41.902782,
    'lon': 12.496366,
},
},
    'rand_tuple': [
    16,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
    '01',
    '02',
],
    'text_data': 'c38bdfaa02a1413c878340fc756e4293',
    'rand_digit': 8,
    'rand_number': 0.97816,
    'rand_signed_int': 5,
    'rand_datetime': '2000-07-13T14:07:41.014253+09:00',
    'text_array': [
    '520b27f0fc334cd9a1aeb8d8cb0fb06a',
    'ce31229bf5a947289b734ef23f21b9b5',
],
    'words': 'dragonfly bird',
    'nested': {
    'id': 119,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cat',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'goat',
    'gorilla',
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
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 120,
    'id_str': [
    '19',
    '28',
],
    'text_data': '5865e5b28e724bebbbbbfca3ed350d39',
    'rand_digit': 9,
    'rand_number': 0.99849,
    'rand_signed_int': -7,
    'rand_datetime': '2000-09-06 15:08:51.021841+0400',
    'text_array': [
    '4356446a79744d5e9fcddbe5b3e6413f',
    '38ebd9fdcd8241018d16d1f1968d9a8e',
],
    'words': 'horse ape',
    'nested': {
    'id': 120,
    'rand_digit': 2,
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
    'word': 'lobster',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'grasshopper',
    'sheep',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'dog',
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 121,
    'id_str': [
    '12',
    '09',
    '10',
    '14',
],
    'text_data': 'bcb61d5e627d4138b4493ef0b96d2b13',
    'rand_digit': 4,
    'rand_number': 0.7139,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-12T13:19:28',
    'text_array': [
    '72182a546d9d419dbb5ceec16e6cfa6f',
    'f16293ce404b4a1fa2aa8b91c0029946',
],
    'words': 'turtle elephant',
    'nested': {
    'id': 121,
    'rand_digit': 8,
    'array': [
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
    'word': 'dolphin',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 6,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'dog',
    'lizard',
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
    'mixed_type': None,
    'maybe_null': 'koala',
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
],
    'text_data': '4661a65c10f0463c869a2ce4461974a3',
    'rand_digit': 8,
    'rand_number': 0.72125,
    'rand_signed_int': 7,
    'rand_datetime': '2001-01-26 20:18',
    'text_array': [
    '2a104ce67615448da7a5c5203a93b719',
    '778b4389ebfd4d15969a29e9fd8355b1',
],
    'words': 'lobster bird',
    'nested': {
    'id': 122,
    'rand_digit': 3,
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
],
    'word': 'cat',
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
    'number': 7,
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
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dolphin',
    'lion',
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
    'mixed_type': 1,
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 123,
    'id_str': [
    '16',
    '01',
],
    'text_data': '2515cc72dd204d90aefd8f484cb8e97a',
    'rand_digit': 0,
    'rand_number': 0.88228,
    'rand_signed_int': -1,
    'rand_datetime': '2000-04-03 08:11',
    'text_array': [
    '1deacaed8dff4f59a676d24a416b61cc',
    '62e837ccbc944926b3e8e55f19e73203',
],
    'words': 'ape panda',
    'nested': {
    'id': 123,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'cheetah',
    'dragonfly',
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
    'mixed_type': 0.37746,
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 124,
    'id_str': [
],
    'text_data': '497819ba9c8241fc892c61630f48a9aa',
    'rand_digit': 3,
    'rand_number': 0.36551,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-30 17:31:08-1200',
    'text_array': [
    '6d7b8aa2072e46cbbe4f247f90bb76e6',
    'fadabb9a24e94aa6949762d94cf47e9f',
],
    'words': 'bee sheep',
    'nested': {
    'id': 124,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
],
    'word': 'mosquito',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'koala',
    'number': 3,
},
    {
    'nested_empty': None,
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
    -8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'frog',
    'butterfly',
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
    'mixed_type': 0,
    'maybe': 'jaguar',
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
    '22',
    '23',
],
    'text_data': '430867fd181d4b4088a7a484d1161033',
    'rand_digit': 1,
    'rand_number': 0.94738,
    'rand_signed_int': -9,
    'rand_datetime': '2000-07-13 13:57:08.063422+0300',
    'text_array': [
    '2d39159bd2f943aba0b1125cee33a4de',
    '73ba9adeddd8479f8e243c04efb95b30',
],
    'words': 'giraffe mouse',
    'nested': {
    'id': 125,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'cheetah',
    'number': 2,
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
    'hello',
],
    'word': 'ladybug',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 1,
},
],
},
    'nested_array': [
    [
    -2,
],
],
    'two_words': [
    'rabbit',
    'bee',
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
    'mixed_type': None,
    'maybe': 'deer',
    'maybe_null': 'zebra',
},
},
    {
    'id': 26,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 126,
    'id_str': [
    '29',
    '08',
    '23',
],
    'text_data': '4f3d1809986a494abe6ac13391f20ea5',
    'rand_digit': 4,
    'rand_number': 0.47388,
    'rand_signed_int': -8,
    'rand_datetime': '2000-02-15',
    'text_array': [
    '0f382b48ed0b479ab7f753169128be3a',
    '24fc0d14f25549a6941d135388b7e355',
],
    'words': 'grasshopper cheetah',
    'nested': {
    'id': 126,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'lion',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lion',
    'zebra',
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
    'mixed_type': True,
    'maybe': 'butterfly',
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 127,
    'id_str': [
    '09',
    '06',
    '14',
    '10',
    '23',
],
    'text_data': 'c9aa028f6c62477cae73b2218d921eaa',
    'rand_digit': 3,
    'rand_number': 0.68436,
    'rand_signed_int': -6,
    'rand_datetime': '2001-01-24 17:16:46+0700',
    'text_array': [
    '18632ae1ec504686b9d91851c610cadd',
    '3831acd4ae7e4f33a396064fc871de67',
],
    'words': 'scorpion squid',
    'nested': {
    'id': 127,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 4,
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
    'word': 'lizard',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -4,
],
],
    'two_words': [
    'ant',
    'monkey',
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
    'mixed_type': 'frog',
    'maybe_null': 'gorilla',
},
},
    {
    'id': 28,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 128,
    'id_str': [
    '17',
],
    'text_data': '265598ba2c6d46caa22f76727e94a0cb',
    'rand_digit': 7,
    'rand_number': 0.06502,
    'rand_signed_int': 10,
    'rand_datetime': '2000-03-28 08:20:37.737157',
    'text_array': [
    'ffbadbdc10f24888b7ca80fed83fd807',
    '30a528102d3c4416a6a82c6b14cad7b4',
],
    'words': 'horse cheetah',
    'nested': {
    'id': 128,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'lion',
    'number': 1,
},
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
    'word': 'ladybug',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    9,
],
    [
    -3,
],
],
    'two_words': [
    'hyena',
    'snail',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'lion',
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
    '05',
    '10',
],
    'text_data': '06d05907257f45edae0ebe51baf8a55a',
    'rand_digit': 9,
    'rand_number': 0.43741,
    'rand_signed_int': -5,
    'rand_datetime': '2000-10-03 17:33:53',
    'text_array': [
    'cd5ac00952304fac8edf830a05430f9d',
    '8efeded2fe8e4cedb6abad6bff5f631b',
],
    'words': 'dog tiger',
    'nested': {
    'id': 129,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
    -10,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'mosquito',
    'goat',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 130,
    'id_str': [
],
    'text_data': '109f6a082cb747d98d70fddae2520efd',
    'rand_digit': 4,
    'rand_number': 0.48187,
    'rand_signed_int': -5,
    'rand_datetime': '2000-04-06T13:52:23.825545+08:00',
    'text_array': [
    'eb0120bdbf164ecea8cc2242be8d4ffb',
    '0224506c28f0473dba415db6ce8c8edb',
],
    'words': 'spider leopard',
    'nested': {
    'id': 130,
    'rand_digit': 6,
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
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -8,
],
],
    'two_words': [
    'rabbit',
    'rhino',
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
    'mixed_type': None,
    'maybe_null': 'horse',
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 131,
    'id_str': [
],
    'text_data': 'f490b04e61fd4c8aac5f1732b0f504f9',
    'rand_digit': 7,
    'rand_number': 0.29524,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-28 23:25:40-1100',
    'text_array': [
    '9ccf6b691816421e91a6170990edd2ff',
    '652f9ffa322d4ca4a862c1745c454f21',
],
    'words': 'rabbit sheep',
    'nested': {
    'id': 131,
    'rand_digit': 2,
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
],
},
    'nested_array': [
],
    'two_words': [
    'cow',
    'giraffe',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'squid',
    'maybe_null': None,
},
},
    {
    'id': 32,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 132,
    'id_str': [
],
    'text_data': 'ff129b5b7e204c0e95265b34bfe7acc2',
    'rand_digit': 2,
    'rand_number': 0.93501,
    'rand_signed_int': -2,
    'rand_datetime': '2000-09-17T21:01:04+0200',
    'text_array': [
    '36755b04683e4a069162d5defe8ecdc6',
    'bef2cb19e680493f95a61f377c81c549',
],
    'words': 'sheep turtle',
    'nested': {
    'id': 132,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'lizard',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -9,
],
    [
    0,
],
],
    'two_words': [
    'ladybug',
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
    'mixed_type': False,
    'maybe': 'hippo',
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 133,
    'id_str': [
    '26',
    '04',
    '21',
    '18',
],
    'text_data': '57a615a7771b4d71892c7686f8ed1846',
    'rand_digit': 4,
    'rand_number': 0.4014,
    'rand_signed_int': 6,
    'rand_datetime': '2000-08-31 20:54:02.678043-0900',
    'text_array': [
    '6133220ccf084f5d978d28dff0125eef',
    'f4b54228a2384b2d8eb5f3f4c612aaa4',
],
    'words': 'bee lobster',
    'nested': {
    'id': 133,
    'rand_digit': 1,
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
    'word': 'fox',
    'number': 9,
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
    'nested_array': [
    [
    6,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'tiger',
    'hippo',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': [
    95,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'lion',
    'maybe_null': 'whale',
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 134,
    'id_str': [
    '05',
    '07',
    '07',
    '29',
    '05',
],
    'text_data': '2c134fd56d9945d999baad9d2aadda07',
    'rand_digit': 2,
    'rand_number': 0.0523,
    'rand_signed_int': -2,
    'rand_datetime': '2000-05-10 21:51:59',
    'text_array': [
    '4a146bb4b22941d8baf152c34fd45f6d',
    '4a7a6cb313804448adac33b21f86cb2f',
],
    'words': 'lizard lobster',
    'nested': {
    'id': 134,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'cat',
    'scorpion',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.68839,
    'maybe_null': 'giraffe',
},
},
    {
    'id': 35,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 135,
    'id_str': [
    '29',
    '06',
    '24',
    '23',
    '10',
],
    'text_data': '488391ca8b274da39f449547eb8accc1',
    'rand_digit': 3,
    'rand_number': 0.41783,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-29 03:49',
    'text_array': [
    '068b1e8d165d40869c0f06cf4dceab52',
    '1759721272f1477ea1942c345f88cdd0',
],
    'words': 'cat dog',
    'nested': {
    'id': 135,
    'rand_digit': 9,
    'array': [
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
],
    'word': 'lion',
    'number': 1,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'kangaroo',
    'pig',
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
    'mixed_type': 2,
    'maybe': 'grasshopper',
    'maybe_null': None,
},
},
    {
    'id': 36,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 136,
    'id_str': [
    '02',
],
    'text_data': '2ca4685a614b4554adc305bc953d5ccb',
    'rand_digit': 5,
    'rand_number': 0.97016,
    'rand_signed_int': 0,
    'rand_datetime': '2000-12-16',
    'text_array': [
    '3ef3deae649743e7b277cb8219813037',
    '5a363f6a2c834add92ac591447891c72',
],
    'words': 'sloth ape',
    'nested': {
    'id': 136,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'butterfly',
    'number': 2,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'zebra',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'grasshopper',
    'mouse',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'zebra',
    'maybe': 'wolf',
    'maybe_null': 'octopus',
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
    '22',
    '16',
    '27',
],
    'text_data': '661b53a4266b41deb01799094030651c',
    'rand_digit': 2,
    'rand_number': 0.26646,
    'rand_signed_int': -10,
    'rand_datetime': '2000-07-02 08:39:08',
    'text_array': [
    'a198e9f544d54743a4f50d131ee069a8',
    '15e84760894f44feb9b515d642c1f559',
],
    'words': 'hyena chicken',
    'nested': {
    'id': 137,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'chicken',
    'wolf',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'crab',
},
},
    {
    'id': 38,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 138,
    'id_str': [
],
    'text_data': '906f42de55c043c4b262198efba611ca',
    'rand_digit': 7,
    'rand_number': 0.98241,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-27T03:04:49.952261',
    'text_array': [
    '5015c129b5294cb8ac4d1ea3f3f07058',
    'fdeac69f0a2942208bf276a7d9803912',
],
    'words': 'deer rabbit',
    'nested': {
    'id': 138,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 8,
},
],
},
    'nested_array': [
    [
    8,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'koala',
    'bear',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.0048,
    'maybe_null': None,
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 139,
    'id_str': [
],
    'text_data': 'c1eddec88f414be382d99f6f636dcf99',
    'rand_digit': 7,
    'rand_number': 0.58997,
    'rand_signed_int': 5,
    'rand_datetime': '2000-03-05T21:43:25',
    'text_array': [
    '3e0487bb8723434481b73b53766e3f64',
    '0760b23a10294b7bae423ce075ecac38',
],
    'words': 'snake cheetah',
    'nested': {
    'id': 139,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 6,
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
    'hello',
],
    'word': 'kangaroo',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'hippo',
    'gorilla',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'panda',
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 140,
    'id_str': [
    '27',
    '22',
    '12',
    '19',
    '13',
],
    'text_data': '745ee267925f4aa4aabee131c1981c6d',
    'rand_digit': 3,
    'rand_number': 0.83142,
    'rand_signed_int': -8,
    'rand_datetime': '2000-07-14 21:10:11.987337+0400',
    'text_array': [
    '19b62a9e95a34c9990d0fe21ab5f6fb6',
    'fd8d9794373a457fbcc7a2c59b52d284',
],
    'words': 'dragonfly squid',
    'nested': {
    'id': 140,
    'rand_digit': 8,
    'array': [
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
    'bird',
    'whale',
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
    'mixed_type': 7,
    'maybe_null': None,
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 141,
    'id_str': [
    '11',
],
    'text_data': '1cb262cb6c8a4275a6ef7702a4fa171b',
    'rand_digit': 8,
    'rand_number': 0.13223,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-03T12:16:30-1200',
    'text_array': [
    '716dbb654f634fc981cbd1c86d202b58',
    '613a99f1d1bf491d953365378221f1e0',
],
    'words': 'kangaroo ape',
    'nested': {
    'id': 141,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'lizard',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    3,
],
],
    'two_words': [
    'cheetah',
    'bear',
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
    'mixed_type': False,
    'maybe': 'pig',
    'maybe_null': 'whale',
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 142,
    'id_str': [
    '15',
    '17',
    '08',
    '01',
    '08',
],
    'text_data': '49d50912e4b24a12aaedc59e8d191d01',
    'rand_digit': 1,
    'rand_number': 0.12538,
    'rand_signed_int': 9,
    'rand_datetime': '2000-01-23T10:37:57.964356+0700',
    'text_array': [
    'aa1f8d159c5d424da4622d2afcaad851',
    '917095a2229d4ae99e97c5c6444c7ced',
],
    'words': 'monkey cheetah',
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
    'word': 'lobster',
    'number': 8,
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
    [
    -3,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'goat',
    'rabbit',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': [
    66,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 43,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 143,
    'id_str': [
    '25',
    '14',
],
    'text_data': '51abaf896e5643269883dcccd71db235',
    'rand_digit': 1,
    'rand_number': 0.15958,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-09 16:35:54.653632',
    'text_array': [
    'd48a5fa2086f4647bdc6014893f69eef',
    '37d30bf9e1c7483cb980f659cb673c5c',
],
    'words': 'lobster wolf',
    'nested': {
    'id': 143,
    'rand_digit': 3,
    'array': [
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
],
    'word': 'squid',
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
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 4,
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
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'tiger',
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 144,
    'id_str': [
],
    'text_data': 'def45b3df7d2452ea2410b2293e812e7',
    'rand_digit': 0,
    'rand_number': 0.29158,
    'rand_signed_int': -10,
    'rand_datetime': '2000-01-13T18:08:48.043457',
    'text_array': [
    '1e0522707ea84a679f16e15d07156682',
    '13f1a405b2e94854802df6cbf0b85caf',
],
    'words': 'sheep sheep',
    'nested': {
    'id': 144,
    'rand_digit': 2,
    'array': [
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
    'word': 'octopus',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 4,
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
    'dolphin',
    'sloth',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'horse',
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 145,
    'id_str': [
    '02',
    '22',
    '07',
],
    'text_data': '22914084614147a98138de4e6ba2de33',
    'rand_digit': 2,
    'rand_number': 0.5396,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-21T13:31:21.247439',
    'text_array': [
    '930ccfdbec3049a6986c9dc41ea91817',
    'e9f7fd8eab5740cab4cd4237607b266d',
],
    'words': 'ant fish',
    'nested': {
    'id': 145,
    'rand_digit': 0,
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
    'word': 'squid',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    [
    6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'monkey',
    'ape',
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
    'mixed_type': 0.35892,
    'maybe': 'pig',
    'maybe_null': 'spider',
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
    '13',
    '21',
    '01',
    '12',
],
    'text_data': 'dc040d2847cc44ebab1b2dc4f0dc6a1c',
    'rand_digit': 1,
    'rand_number': 0.19747,
    'rand_signed_int': -4,
    'rand_datetime': '2000-03-08T02:50:23+0000',
    'text_array': [
    '8ad57b9ee9a249ca92b538c10e545308',
    'e7def64e8e1d4c3090bfa1cf472d801e',
],
    'words': 'cow wolf',
    'nested': {
    'id': 146,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'kangaroo',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 7,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
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
    'fish',
    'pig',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': [
    98,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'dog',
    'maybe_null': 'mouse',
},
},
    {
    'id': 47,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 147,
    'id_str': [
    '02',
    '06',
    '13',
    '08',
],
    'text_data': 'f5aef6062e9648f4affac5a5a81ec8b5',
    'rand_digit': 6,
    'rand_number': 0.28045,
    'rand_signed_int': -7,
    'rand_datetime': '2000-11-27 06:46:29+0900',
    'text_array': [
    '000c114dda4f4b3cadef471ca1920010',
    '4989970ce2bb4f50b9b50072627917e1',
],
    'words': 'elephant monkey',
    'nested': {
    'id': 147,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'dragonfly',
    'bee',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 48,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 148,
    'id_str': [
    '06',
    '17',
],
    'text_data': '6ac846fabc904e8e8f7f31d1912cb1d2',
    'rand_digit': 6,
    'rand_number': 0.8731,
    'rand_signed_int': 0,
    'rand_datetime': '2000-09-10 11:10:45.129496-0500',
    'text_array': [
    'a3c672a1cfd2499fae3e8b2f356bf035',
    '1a395f1637f34869b61bb18afe50623f',
],
    'words': 'giraffe fox',
    'nested': {
    'id': 148,
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
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'deer',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cow',
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
    'mixed_type': 0.48865,
    'maybe': 'sheep',
    'maybe_null': None,
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 149,
    'id_str': [
    '08',
    '10',
],
    'text_data': 'f97193efa3b74125801854a94a59c3bb',
    'rand_digit': 6,
    'rand_number': 0.5425,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-30T10:48:23.036607+06:00',
    'text_array': [
    '8a6e410b5e854e80b47d2a2688c89120',
    '988cdf165b1a494c86203fc5de5a4891',
],
    'words': 'lizard giraffe',
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
    'word': 'snake',
    'number': 6,
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
    'word': 'cat',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'gorilla',
    'camel',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fly',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 50,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 150,
    'id_str': [
    '04',
    '29',
    '27',
],
    'text_data': '4a23a60b673e4c3990155a3d39332d63',
    'rand_digit': 3,
    'rand_number': 0.9941,
    'rand_signed_int': 4,
    'rand_datetime': '2000-11-04T06:45:26-1100',
    'text_array': [
    'afd65e8c8f3f461c9795ca28feab5fcd',
    '57ec1e179d7a42f791735074cdcbe5cc',
],
    'words': 'squid zebra',
    'nested': {
    'id': 150,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
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
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'goat',
    'duck',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'mouse',
},
},
    {
    'id': 51,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 151,
    'id_str': [
    '04',
    '22',
],
    'text_data': 'c4bb1584600141ad8645a27a77e0b315',
    'rand_digit': 9,
    'rand_number': 0.71735,
    'rand_signed_int': 8,
    'rand_datetime': '2000-04-10T12:45:08.373592',
    'text_array': [
    '7d0bf8c04c4d4ebcab467612a6b99d62',
    '71707b5aaca24620b9d5f3e8cbc6f7b7',
],
    'words': 'camel squid',
    'nested': {
    'id': 151,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 1,
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
    'word': 'rabbit',
    'number': 6,
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
    'fox',
    'sloth',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': [
    0,
],
    'rand_bool': True,
    'mixed_type': 7,
    'maybe': 'cow',
    'maybe_null': None,
},
},
    {
    'id': 52,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 152,
    'id_str': [
    '08',
    '26',
    '21',
    '12',
],
    'text_data': '7e648c4886254d08bc8f1693a273b586',
    'rand_digit': 1,
    'rand_number': 0.66787,
    'rand_signed_int': 0,
    'rand_datetime': '2000-09-30T00:55:30.159970+05:00',
    'text_array': [
    '212b400ec81a46caa42317733b442e03',
    '7fde35c83ad147ec93779742a2c86788',
],
    'words': 'kangaroo sloth',
    'nested': {
    'id': 152,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 9,
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
    'word': 'bear',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'hyena',
    'ant',
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
    'mixed_type': True,
    'maybe': 'crab',
},
},
    {
    'id': 53,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 153,
    'id_str': [
    '07',
    '16',
    '18',
],
    'text_data': '0dd0c8a8596e47c0bdda183a860b500e',
    'rand_digit': 7,
    'rand_number': 0.20646,
    'rand_signed_int': -4,
    'rand_datetime': '2000-02-12',
    'text_array': [
    '4f9000430fe945d0afbb9ba9df9e7079',
    '2ff1f5c4911540c28e32549875cf8d5f',
],
    'words': 'hyena deer',
    'nested': {
    'id': 153,
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
    'number': 4,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 2,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -4,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'pig',
    'butterfly',
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
    'mixed_type': 0.88059,
    'maybe': 'pig',
    'maybe_null': None,
},
},
    {
    'id': 54,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 154,
    'id_str': [
    '19',
    '16',
    '18',
    '19',
],
    'text_data': 'c7bbe29835944ceaa582a84e1921febe',
    'rand_digit': 9,
    'rand_number': 0.05232,
    'rand_signed_int': -6,
    'rand_datetime': '2001-01-21 11:06:45.144335',
    'text_array': [
    'be80f338567e4d73bf289b1be0b48695',
    '185a543276d342f285c2fc48291e9ad1',
],
    'words': 'tiger frog',
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'koala',
    'camel',
],
    'city': {
    'name': 'Athens',
    'geo': {
    'lat': 37.98381,
    'lon': 23.727539,
},
},
    'rand_tuple': [
    75,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'shark',
    'maybe_null': 'cat',
},
},
    {
    'id': 55,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 155,
    'id_str': [
    '10',
    '14',
    '27',
    '21',
],
    'text_data': 'bb0ae6e601f94a849f3be061cffe53ad',
    'rand_digit': 8,
    'rand_number': 0.86234,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-28T17:33:55.382922+0900',
    'text_array': [
    '2c81aff093b94b0fad8249819c2d2b7b',
    '16b13fdc25e24a21a72772aef87a6d14',
],
    'words': 'bear zebra',
    'nested': {
    'id': 155,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'crab',
    'bird',
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
    'maybe': 'sloth',
    'maybe_null': 'ladybug',
},
},
    {
    'id': 56,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 156,
    'id_str': [
],
    'text_data': 'b9d0e64b0051497bbde5ecf28b83e68c',
    'rand_digit': 1,
    'rand_number': 0.58932,
    'rand_signed_int': -9,
    'rand_datetime': '2000-04-03T05:52:10.279379+11:00',
    'text_array': [
    '4ea5c0dba6b743369998164a86f6a6ae',
    '37221f0bd612453da2bdf4fbe87f08f5',
],
    'words': 'turtle bee',
    'nested': {
    'id': 156,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lion',
    'number': 9,
},
    {
    'nested_empty': None,
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
    'word': 'sloth',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 6,
},
],
},
    'nested_array': [
    [
    -7,
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'cheetah',
    'whale',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': [
    10,
],
    'rand_bool': True,
    'mixed_type': 'dragonfly',
},
},
    {
    'id': 57,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 157,
    'id_str': [
    '30',
    '09',
    '01',
],
    'text_data': '61697d2e2cd1473585c98fa4cd6eb8a7',
    'rand_digit': 6,
    'rand_number': 0.4577,
    'rand_signed_int': 4,
    'rand_datetime': '2000-12-31 16:57:16+0100',
    'text_array': [
    '8a69ba2ce75445a58af753497ba06fe9',
    '27a3a35284d34adabf47a61c3ac71ecb',
],
    'words': 'snail dog',
    'nested': {
    'id': 157,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'lion',
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'dolphin',
    'monkey',
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
    'mixed_type': 3,
    'maybe_null': 'octopus',
},
},
    {
    'id': 58,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 158,
    'id_str': [
    '27',
    '17',
    '27',
    '14',
    '28',
],
    'text_data': '1fa99c398bf540c8b6081f6c7457cd36',
    'rand_digit': 9,
    'rand_number': 0.34393,
    'rand_signed_int': -2,
    'rand_datetime': '2000-02-27 03:04:56',
    'text_array': [
    'fc37caa30eb2478da91a34bcdaa34f42',
    'dcb3f438b0a74452b02d73b64e72e746',
],
    'words': 'dragonfly lobster',
    'nested': {
    'id': 158,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 7,
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
    'word': 'spider',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'squid',
    'bear',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'ladybug',
    'maybe_null': 'mouse',
},
},
    {
    'id': 59,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 159,
    'id_str': [
    '14',
    '09',
],
    'text_data': '853ec40234684924a2c4385079597563',
    'rand_digit': 9,
    'rand_number': 0.50874,
    'rand_signed_int': 9,
    'rand_datetime': '2000-04-10 08:33:04-0700',
    'text_array': [
    '155f5d87695149e59fb14c474c0de3b8',
    '5881dacd5bd549c88e355402cd18f9db',
],
    'words': 'fox ladybug',
    'nested': {
    'id': 159,
    'rand_digit': 4,
    'array': [
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
    'hello',
],
    'word': 'spider',
    'number': 6,
},
    {
    'nested_empty': None,
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
    'word': 'fish',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fox',
    'lobster',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 60,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 160,
    'id_str': [
],
    'text_data': 'eada132744fc423e91beb710525d16e5',
    'rand_digit': 3,
    'rand_number': 0.27667,
    'rand_signed_int': 6,
    'rand_datetime': '2000-11-03T05:43:57-0500',
    'text_array': [
    '212151db490242a291244cc893485057',
    '0aa11e992bd548f3a436207ffa80cd6e',
],
    'words': 'octopus fish',
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
    'word': 'jaguar',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'koala',
    'deer',
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
    'mixed_type': False,
    'maybe_null': None,
},
},
    {
    'id': 61,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 161,
    'id_str': [
    '07',
    '11',
],
    'text_data': '7dbdc1ff5f754f578667cdd4285aa7f3',
    'rand_digit': 9,
    'rand_number': 0.90803,
    'rand_signed_int': -5,
    'rand_datetime': '2001-01-17 06:36:41.806140-1200',
    'text_array': [
    '3ae25a4ea60c4e0385639bb1b87cfcb4',
    'bdad7aeceb3043b98423ea1058a331b1',
],
    'words': 'duck goat',
    'nested': {
    'id': 161,
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
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    [
    -1,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
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
    13,
],
    'rand_bool': True,
    'mixed_type': 0.63124,
    'maybe': 'bear',
    'maybe_null': None,
},
},
    {
    'id': 62,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 162,
    'id_str': [
],
    'text_data': 'aebfdfc1e0e3434eb8c54a239cd64f49',
    'rand_digit': 3,
    'rand_number': 0.09076,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-09 20:03:19-0600',
    'text_array': [
    '7d8e9486523e436fa74e2e664425ca36',
    'f55f98ac193f4d10aebe4f76f8ce0a27',
],
    'words': 'bird rabbit',
    'nested': {
    'id': 162,
    'rand_digit': 5,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -3,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ant',
    'ape',
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
    'mixed_type': False,
    'maybe_null': 'hippo',
},
},
    {
    'id': 63,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 163,
    'id_str': [
    '02',
    '30',
    '10',
    '03',
],
    'text_data': '4866c3cb81514d14a5f28a9ef5ff8288',
    'rand_digit': 1,
    'rand_number': 0.70852,
    'rand_signed_int': -4,
    'rand_datetime': '2000-01-20T18:06:39.893297',
    'text_array': [
    '98b28e1f070a48adae1e4e15f7e6a9f2',
    '6c161d4beaf14bdb81f630ce0ca49e3d',
],
    'words': 'leopard rhino',
    'nested': {
    'id': 163,
    'rand_digit': 0,
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
    'word': 'kangaroo',
    'number': 5,
},
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
    'word': 'bird',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    0,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'giraffe',
    'sheep',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 'fish',
    'maybe': 'cat',
    'maybe_null': 'rhino',
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
    'content-length': '440159',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 100,
    'id_str': [
    '11',
],
    'text_data': '1a5f7766bf9245708bbdf244b22ef969',
    'rand_digit': 7,
    'rand_number': 0.67448,
    'rand_signed_int': 2,
    'rand_datetime': '2000-10-15 01:25:09',
    'text_array': [
    'f5e0e5a8cf3443f182fc68b38228d3c4',
    'bb80df19ecce4c5b89ff3dd17114f227',
],
    'words': 'cat monkey',
    'nested': {
    'id': 100,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
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
    'number': 3,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
    -2,
],
    [
    10,
],
],
    'two_words': [
    'lion',
    'giraffe',
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
    'mixed_type': 3,
    'maybe_null': None,
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 101,
    'id_str': [
    '24',
    '09',
    '01',
    '16',
    '02',
],
    'text_data': '8d8ae08c718f4df5bcaa02764d129009',
    'rand_digit': 9,
    'rand_number': 0.98743,
    'rand_signed_int': -10,
    'rand_datetime': '2000-07-27T13:53:16.755070',
    'text_array': [
    '35628a3e529d4a708964c6022bc1f530',
    'f355d420d38a4a47bff0eb494d1744c2',
],
    'words': 'fish panda',
    'nested': {
    'id': 101,
    'rand_digit': 8,
    'array': [
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    3,
],
],
    'two_words': [
    'rabbit',
    'turtle',
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
    'maybe': 'duck',
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 2,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 102,
    'id_str': [
],
    'text_data': '3d3900bffdf440f8888072503300fb46',
    'rand_digit': 0,
    'rand_number': 0.5927,
    'rand_signed_int': -1,
    'rand_datetime': '2000-11-30T03:21:00.589636',
    'text_array': [
    '6575603950df47ffa6f5d3cc36912771',
    '445196e6feaa4a62b6f210551ee695a2',
],
    'words': 'shark cheetah',
    'nested': {
    'id': 102,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 4,
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
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'monkey',
    'giraffe',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': [
    25,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'snail',
    'maybe_null': None,
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 103,
    'id_str': [
    '29',
    '09',
],
    'text_data': 'c1d23482ba114c1d91194401a6d20b27',
    'rand_digit': 0,
    'rand_number': 0.04265,
    'rand_signed_int': 4,
    'rand_datetime': '2000-10-07T21:37:11.606789-0800',
    'text_array': [
    '61669da190a142bab5ab48b7aa47a81d',
    '99a41edf503c4546b7498dcbe6210f6a',
],
    'words': 'koala gorilla',
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
    'word': 'goat',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 1,
},
],
},
    'nested_array': [
    [
    5,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -10,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'panda',
    'lizard',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 104,
    'id_str': [
],
    'text_data': '30be1c6b013349a3b018bc4346dc0f75',
    'rand_digit': 8,
    'rand_number': 0.88825,
    'rand_signed_int': -9,
    'rand_datetime': '2000-08-02T18:44:50.953483',
    'text_array': [
    '595d0d47c3ef4b619675a167aab24976',
    'e021430416124a4db609000d7504cc9c',
],
    'words': 'cat deer',
    'nested': {
    'id': 104,
    'rand_digit': 9,
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
    'hello',
],
    'word': 'fish',
    'number': 7,
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
    'word': 'whale',
    'number': 6,
},
],
},
    'nested_array': [
    [
    5,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    10,
],
],
    'two_words': [
    'lobster',
    'giraffe',
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
    'mixed_type': 'goat',
    'maybe': 'chicken',
    'maybe_null': 'tiger',
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 105,
    'id_str': [
    '02',
],
    'text_data': '35665378a19245c69b9ac57d7556c115',
    'rand_digit': 5,
    'rand_number': 0.65828,
    'rand_signed_int': 1,
    'rand_datetime': '2000-05-20T03:59:24',
    'text_array': [
    'bfe070fc37534c1f93078c5d3c6fe379',
    '163cd6daeea44a14ab9b2cb061535625',
],
    'words': 'butterfly kangaroo',
    'nested': {
    'id': 105,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 2,
},
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
    'word': 'fish',
    'number': 5,
},
],
},
    'nested_array': [
    [
    0,
],
],
    'two_words': [
    'snail',
    'duck',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'leopard',
    'maybe_null': 'gorilla',
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 106,
    'id_str': [
    '16',
    '05',
    '23',
    '04',
],
    'text_data': '3a23bb317cf14170a60cdf762b50d430',
    'rand_digit': 2,
    'rand_number': 0.94965,
    'rand_signed_int': 2,
    'rand_datetime': '2000-01-15 00:50',
    'text_array': [
    'ab8c69e0cf6647d89d804e6675cbeaef',
    '4e157bbcb416455ca0a53f3efb7d19ba',
],
    'words': 'crab dolphin',
    'nested': {
    'id': 106,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 2,
},
],
},
    'nested_array': [
    [
    3,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'whale',
    'cow',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'leopard',
    'maybe_null': 'fly',
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 107,
    'id_str': [
    '21',
    '24',
    '29',
    '10',
    '18',
],
    'text_data': 'f9ce2901f309413c9090f4209430411c',
    'rand_digit': 6,
    'rand_number': 0.59273,
    'rand_signed_int': -6,
    'rand_datetime': '2000-01-15 11:15:26',
    'text_array': [
    '77c1dc02b48c4d9b992bb5cdd3fcbb04',
    'b8f6bc21267d476b9abc0b8735f0edbe',
],
    'words': 'pig scorpion',
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
    'word': 'goat',
    'number': 8,
},
],
},
    'nested_array': [
    [
    -1,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
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
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.23815,
    'maybe': 'hippo',
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 108,
    'id_str': [
    '16',
],
    'text_data': 'f3ddef4bddd14733a3e5d829ad1db4b9',
    'rand_digit': 1,
    'rand_number': 0.82299,
    'rand_signed_int': -4,
    'rand_datetime': '2000-05-29',
    'text_array': [
    'e0c2e15094644c14aff5bcb04ce80f86',
    'a1c7563103dd463b971f11d3cfcfebda',
],
    'words': 'octopus octopus',
    'nested': {
    'id': 108,
    'rand_digit': 7,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'deer',
    'lion',
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
    'mixed_type': 0.90967,
    'maybe_null': 'ladybug',
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 109,
    'id_str': [
],
    'text_data': 'b2942b32de894efa8dd08e95b745f12a',
    'rand_digit': 0,
    'rand_number': 0.23342,
    'rand_signed_int': -6,
    'rand_datetime': '2000-07-14 19:57:50-0500',
    'text_array': [
    'b0a53ac4e1134dd782e9c4dba4276344',
    '687c2510f5df4812a32581236a0c8263',
],
    'words': 'panda turtle',
    'nested': {
    'id': 109,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'dog',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fish',
    'mosquito',
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
    'mixed_type': 'fish',
    'maybe': 'wolf',
    'maybe_null': None,
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 110,
    'id_str': [
    '13',
    '26',
],
    'text_data': 'a0f93029021c4eb88c792e9f6ff22c01',
    'rand_digit': 9,
    'rand_number': 0.14851,
    'rand_signed_int': -2,
    'rand_datetime': '2000-11-11',
    'text_array': [
    '40ed419c43b845cb92f30a75ede99111',
    'e06b7927650c4d80a4d1444cdd41d5fd',
],
    'words': 'elephant rabbit',
    'nested': {
    'id': 110,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 5,
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
    'nested_empty': [
    'hello',
],
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
    'word': 'ladybug',
    'number': 1,
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
    [
],
],
    'two_words': [
    'dolphin',
    'fish',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': [
    100,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'ant',
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 111,
    'id_str': [
    '22',
    '25',
],
    'text_data': '855942c87b46435388e01659acad757a',
    'rand_digit': 1,
    'rand_number': 0.17715,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-29 01:36:16.086976-0500',
    'text_array': [
    'a05224e3de56441a8297a1544393d78f',
    '3bdace08b82c4cb3a718718b68e8444e',
],
    'words': 'horse shark',
    'nested': {
    'id': 111,
    'rand_digit': 1,
    'array': [
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
    'word': 'sloth',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
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
    -9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lobster',
    'zebra',
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
    'mixed_type': 'shark',
    'maybe': 'deer',
    'maybe_null': None,
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 112,
    'id_str': [
    '02',
    '14',
    '03',
    '11',
    '28',
],
    'text_data': 'd6ec50251455402a8cc2e01294928a58',
    'rand_digit': 3,
    'rand_number': 0.7092,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-01T13:26:24.800348',
    'text_array': [
    '932538d5b0744f49b6cedcd0809820fa',
    'a59dfe471f1d49618d6234aa6c03ad79',
],
    'words': 'rabbit lion',
    'nested': {
    'id': 112,
    'rand_digit': 1,
    'array': [
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
],
    'word': 'cheetah',
    'number': 1,
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
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'scorpion',
    'dragonfly',
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
    'mixed_type': 2,
    'maybe_null': 'monkey',
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 113,
    'id_str': [
    '10',
    '28',
    '03',
    '08',
],
    'text_data': 'f1ea2e3c66bd4692aa71e95d6c1aa8ce',
    'rand_digit': 8,
    'rand_number': 0.9034,
    'rand_signed_int': 2,
    'rand_datetime': '2000-01-24T10:42:07.501278+0000',
    'text_array': [
    'f313eaaed12a4bd59c5e1bf2c2f48521',
    'cd857bb25aa34333b25cb022dfc6d69e',
],
    'words': 'zebra grasshopper',
    'nested': {
    'id': 113,
    'rand_digit': 0,
    'array': [
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
    'word': 'fly',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -8,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lobster',
    'cat',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.47846,
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 114,
    'id_str': [
],
    'text_data': '4eb33d7a1fb34b0b96da9e2b50f13c9d',
    'rand_digit': 3,
    'rand_number': 0.09658,
    'rand_signed_int': 3,
    'rand_datetime': '2000-05-02T16:57:22.129574+06:00',
    'text_array': [
    'ac70ed96ecb1477896b23f7ab076dd85',
    '66137fe5938a47a48693854763267578',
],
    'words': 'snake giraffe',
    'nested': {
    'id': 114,
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
],
},
    'nested_array': [
    [
    2,
],
],
    'two_words': [
    'bird',
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
    'mixed_type': 'mouse',
    'maybe': 'goat',
    'maybe_null': 'snake',
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 115,
    'id_str': [
    '29',
    '25',
],
    'text_data': 'f5787ffcea71433e8bab8e72078ce630',
    'rand_digit': 3,
    'rand_number': 0.31666,
    'rand_signed_int': -8,
    'rand_datetime': '2000-05-16',
    'text_array': [
    'c08f52868ccb474c92638bde844d2a6e',
    '341293ae71fd48dcaa9556f4ee83eda2',
],
    'words': 'monkey lobster',
    'nested': {
    'id': 115,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'mosquito',
    'duck',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': [
    5,
],
    'rand_bool': False,
    'mixed_type': 'duck',
    'maybe_null': None,
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 116,
    'id_str': [
    '13',
    '23',
    '21',
],
    'text_data': '2a8b2ad924a14eeabfaf9afa2fc71abd',
    'rand_digit': 9,
    'rand_number': 0.96303,
    'rand_signed_int': 10,
    'rand_datetime': '2000-03-29 14:05:37-1100',
    'text_array': [
    '1397729ee6134658abb1305d37d24d84',
    'b27606107bc640679d941b71e24a25dc',
],
    'words': 'goat duck',
    'nested': {
    'id': 116,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 9,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    1,
],
],
    'two_words': [
    'frog',
    'zebra',
],
    'city': {
    'name': 'Zurich',
    'geo': {
    'lat': 47.376887,
    'lon': 8.541694,
},
},
    'rand_tuple': [
    70,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'snake',
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 117,
    'id_str': [
    '16',
    '15',
    '04',
    '12',
    '20',
],
    'text_data': 'f9c7d0423af6428189054bb389a9103a',
    'rand_digit': 8,
    'rand_number': 0.10442,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-21T20:01:18-1100',
    'text_array': [
    '9d9e56527a59482d9dbb4edc0b237d71',
    'da89e5a07c28474182a12ac39d29f4c2',
],
    'words': 'cat kangaroo',
    'nested': {
    'id': 117,
    'rand_digit': 9,
    'array': [
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
    'word': 'leopard',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
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
    'monkey',
    'bird',
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
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'camel',
},
},
    {
    'id': 18,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 118,
    'id_str': [
    '05',
    '19',
    '26',
    '23',
],
    'text_data': '2ffe066c3bca4a709b5428774f391455',
    'rand_digit': 7,
    'rand_number': 0.05247,
    'rand_signed_int': -5,
    'rand_datetime': '2000-10-24T01:14:26',
    'text_array': [
    'bfd54436ec574d9b86e09abac352d130',
    '7ca33cb3ee3b49bb9b0fc6cae73ec6dd',
],
    'words': 'kangaroo bee',
    'nested': {
    'id': 118,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'fish',
    'lizard',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'jaguar',
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
],
    'text_data': 'd3180d70437046f8b2b63f1a0d943bd5',
    'rand_digit': 6,
    'rand_number': 0.54887,
    'rand_signed_int': -9,
    'rand_datetime': '2000-07-05 10:22:20.162842+1000',
    'text_array': [
    '1ee2a25a0fe74ebe9aff7c97561ad2e1',
    'fe5481d200b343288bed5443d54111f7',
],
    'words': 'frog frog',
    'nested': {
    'id': 119,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'hippo',
    'lion',
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
    'mixed_type': True,
    'maybe_null': 'turtle',
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 120,
    'id_str': [
    '02',
    '26',
    '03',
],
    'text_data': '41517ee96107479eb8aa18d5f09cf961',
    'rand_digit': 8,
    'rand_number': 0.89127,
    'rand_signed_int': 8,
    'rand_datetime': '2000-03-11 18:28:31',
    'text_array': [
    '42a0e531c211464bb1c830b4cfa69c94',
    '844184291edd4b0da4649a23adad1583',
],
    'words': 'lizard goat',
    'nested': {
    'id': 120,
    'rand_digit': 9,
    'array': [
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
    'word': 'jaguar',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'bee',
    'bear',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bear',
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 121,
    'id_str': [
    '20',
    '17',
    '22',
    '17',
    '08',
],
    'text_data': 'ece553c13b514f3e88c31702e662b25f',
    'rand_digit': 2,
    'rand_number': 0.64662,
    'rand_signed_int': 6,
    'rand_datetime': '2000-11-27T15:19:28.999502-1000',
    'text_array': [
    '094c1dcaa5c143839c0759dfed2b2247',
    '897f60431e19480f9e8585e456ed5734',
],
    'words': 'bird gorilla',
    'nested': {
    'id': 121,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'mosquito',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 3,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'chicken',
    'fish',
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
    'maybe': 'goat',
    'maybe_null': 'cat',
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
    '14',
    '20',
    '04',
    '13',
    '27',
],
    'text_data': '3b1e5126d14e40b99fe2444dd9ac8674',
    'rand_digit': 4,
    'rand_number': 0.80483,
    'rand_signed_int': -10,
    'rand_datetime': '2000-11-22 04:35',
    'text_array': [
    '7f39ac0f513740e495e1114769f6b6cc',
    '7135fc6595a94dffb189484cd84e8f39',
],
    'words': 'fish panda',
    'nested': {
    'id': 122,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'dolphin',
    'snail',
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
    'mixed_type': None,
    'maybe': 'crab',
    'maybe_null': 'whale',
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 123,
    'id_str': [
    '21',
    '27',
],
    'text_data': '49de2d7eed1d472e9b92ca5585ba47ed',
    'rand_digit': 8,
    'rand_number': 0.30559,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-02T23:43:53.638031-02:00',
    'text_array': [
    '6b06d0352e5549f0938d613b29e71ce6',
    'ce0b7d6bf9af419696e818b389188eae',
],
    'words': 'scorpion kangaroo',
    'nested': {
    'id': 123,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 10,
},
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lion',
    'number': 10,
},
    {
    'nested_empty': None,
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
    'dragonfly',
    'panda',
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
    'mixed_type': 0.07586,
    'maybe_null': 'frog',
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 124,
    'id_str': [
    '28',
    '26',
    '09',
    '04',
    '26',
],
    'text_data': '80a863b5c93344858049fb3752cb879f',
    'rand_digit': 3,
    'rand_number': 0.43645,
    'rand_signed_int': 3,
    'rand_datetime': '2000-07-26 00:43',
    'text_array': [
    '098dd246178748febb437e4ab4997746',
    '7d34f3cd98404d24b5157c07e670de1d',
],
    'words': 'bee bee',
    'nested': {
    'id': 124,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    1,
],
    [
],
],
    'two_words': [
    'panda',
    'frog',
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
    'mixed_type': 0.51533,
    'maybe_null': 'butterfly',
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
    '15',
    '01',
    '07',
    '04',
    '10',
],
    'text_data': 'c1fce18d90b542feb88bf8d8fdf70ade',
    'rand_digit': 0,
    'rand_number': 0.8641,
    'rand_signed_int': 3,
    'rand_datetime': '2000-03-25 09:10',
    'text_array': [
    '63ef7d850bbb4ff3aab33c7e98288804',
    'dbf345a52ffc471b9234d23627f785fc',
],
    'words': 'koala hyena',
    'nested': {
    'id': 125,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 8,
},
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
],
    'word': 'jaguar',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
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
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fly',
    'frog',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 26,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 126,
    'id_str': [
    '20',
    '10',
    '09',
    '23',
    '29',
],
    'text_data': '2473f3a9843545e0ac9915862ba29412',
    'rand_digit': 8,
    'rand_number': 0.7706,
    'rand_signed_int': 3,
    'rand_datetime': '2001-01-02T23:14:14.072396',
    'text_array': [
    '16cb49eed5b3486b8b8f51288e3717bd',
    '285d2efc3c304bf7b15a13b4c3ce4764',
],
    'words': 'butterfly whale',
    'nested': {
    'id': 126,
    'rand_digit': 1,
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
    'hello',
],
    'word': 'duck',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    9,
],
],
    'two_words': [
    'kangaroo',
    'rhino',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'giraffe',
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 127,
    'id_str': [
],
    'text_data': '04e54f0a90f945a7a8de57aea71aadc3',
    'rand_digit': 2,
    'rand_number': 0.89471,
    'rand_signed_int': -3,
    'rand_datetime': '2000-09-02',
    'text_array': [
    'cb6e42d787ad42f390f3e7fbc7eeccf9',
    '96a2015487d34eff9783a6291c3bfd98',
],
    'words': 'cow snail',
    'nested': {
    'id': 127,
    'rand_digit': 9,
    'array': [
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
    'word': 'koala',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'chicken',
    'cow',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': [
    45,
],
    'rand_bool': False,
    'mixed_type': 2,
    'maybe': 'wolf',
    'maybe_null': 'dog',
},
},
    {
    'id': 28,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 128,
    'id_str': [
],
    'text_data': '7cb69d2debd342b3a45ad130f8ecd9cc',
    'rand_digit': 8,
    'rand_number': 0.99468,
    'rand_signed_int': 4,
    'rand_datetime': '2000-11-26T20:56:56.720343+0200',
    'text_array': [
    'f8585e18751a43e593b8f14a63140d59',
    'e64000f594084a9c8f494bf01b18adbd',
],
    'words': 'elephant fly',
    'nested': {
    'id': 128,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lobster',
    'lobster',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'elephant',
    'maybe_null': 'monkey',
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
    '27',
    '01',
    '05',
    '23',
    '01',
],
    'text_data': 'f1e49d0889bf4da39237fabb9f35eec1',
    'rand_digit': 8,
    'rand_number': 0.70147,
    'rand_signed_int': 0,
    'rand_datetime': '2001-01-02 20:06:34-1200',
    'text_array': [
    '297abed1ee7f4dab88875f79845689a3',
    '1c65f46ebac6401aa8950747db7c19dc',
],
    'words': 'rabbit fly',
    'nested': {
    'id': 129,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ant',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 10,
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
    'chicken',
    'koala',
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
    'mixed_type': 'camel',
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 130,
    'id_str': [
],
    'text_data': '758fc11ed09a48519490907746c28d70',
    'rand_digit': 1,
    'rand_number': 0.59196,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-17T05:35:37.501075-09:00',
    'text_array': [
    'ab433f1ebebb413baaa1adfeb8b37219',
    '3d48235cd6994342bb6c33aaba2ea791',
],
    'words': 'lion mouse',
    'nested': {
    'id': 130,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 4,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,5__',
    'two_words': [
    'hyena',
    'fish',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': [
    75,
],
    'rand_bool': False,
    'mixed_type': 'lion',
    'maybe': 'lobster',
    'maybe_null': None,
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 131,
    'id_str': [
],
    'text_data': '249d9d200f7d436c8215cdc2b25d9092',
    'rand_digit': 2,
    'rand_number': 0.04634,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-08T12:48:44.925796',
    'text_array': [
    '12e11aab61034d1ca1f99c88c4a15072',
    'a8a6be69ba74401cbd2bd5f0030c2b0d',
],
    'words': 'deer snail',
    'nested': {
    'id': 131,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 10,
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
],
    'word': 'hyena',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'scorpion',
    'octopus',
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
    'mixed_type': None,
    'maybe': 'panda',
    'maybe_null': 'tiger',
},
},
    {
    'id': 32,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 132,
    'id_str': [
    '28',
    '03',
    '07',
],
    'text_data': '691f9c221c09443ebe307ebff39cb275',
    'rand_digit': 1,
    'rand_number': 0.7158,
    'rand_signed_int': 1,
    'rand_datetime': '2000-10-17 13:08:47',
    'text_array': [
    '9fbf54b37a894d9b836e53d5c470bb17',
    'aea3698af71e4688b8c3b1133353b370',
],
    'words': 'zebra elephant',
    'nested': {
    'id': 132,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'fish',
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -3,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'snake',
    'turtle',
],
    'city': {
    'name': 'London',
    'geo': {
    'lat': 51.507351,
    'lon': -0.127758,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'jaguar',
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 133,
    'id_str': [
    '16',
    '03',
],
    'text_data': '1f1bdf8f3595414d9bb6f9055da8a0ca',
    'rand_digit': 3,
    'rand_number': 0.34824,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-26T16:15:12+0500',
    'text_array': [
    '4d938b6165d44775b3fbfb3f0999f090',
    '2800e96d06784fc08204b69a577307d9',
],
    'words': 'leopard elephant',
    'nested': {
    'id': 133,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 8,
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
],
    'word': 'whale',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'ladybug',
    'spider',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'shark',
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 134,
    'id_str': [
    '05',
    '20',
    '08',
    '02',
],
    'text_data': '06eaa86df7e0445dada0364b0875ff62',
    'rand_digit': 5,
    'rand_number': 0.10705,
    'rand_signed_int': 3,
    'rand_datetime': '2000-02-15 01:18:37+0300',
    'text_array': [
    'e3df5b867d05470da8cdf8d819552f1f',
    'e40695ec4354494a895f9bac70a4176e',
],
    'words': 'camel panda',
    'nested': {
    'id': 134,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 9,
},
    {
    'nested_empty': None,
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
    'word': 'cheetah',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'horse',
    'butterfly',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'ape',
    'maybe_null': 'ant',
},
},
    {
    'id': 35,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 135,
    'id_str': [
    '11',
    '03',
    '23',
],
    'text_data': '4b6f7b557bb94f09b4504559656f0a23',
    'rand_digit': 3,
    'rand_number': 0.71099,
    'rand_signed_int': 3,
    'rand_datetime': '2000-01-04 15:59:34',
    'text_array': [
    '0832c95d91b04f67bb75bbe507412034',
    '3b3fcf4cf15e4c97aa913719b100569f',
],
    'words': 'frog deer',
    'nested': {
    'id': 135,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 3,
},
],
},
    'nested_array': [
    [
    -10,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'bird',
    'mouse',
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
    'id': 36,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 136,
    'id_str': [
    '01',
    '03',
    '04',
    '02',
],
    'text_data': 'f754d20e2a38428990c5c45bef984e8c',
    'rand_digit': 6,
    'rand_number': 0.95135,
    'rand_signed_int': -8,
    'rand_datetime': '2000-01-30 05:04:47.530727',
    'text_array': [
    'af2f731035b340f8891eaa113ab2bc8c',
    'd49aacff40ca401d9ff4ed205d0f7584',
],
    'words': 'dog ladybug',
    'nested': {
    'id': 136,
    'rand_digit': 9,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'bird',
    'lion',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'rabbit',
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
    '03',
    '03',
    '23',
],
    'text_data': 'd2d2161242454955a3b77584dd3bdadc',
    'rand_digit': 4,
    'rand_number': 0.6555,
    'rand_signed_int': 1,
    'rand_datetime': '2000-03-12',
    'text_array': [
    '8042a10e1f2e4f3bae272e73fc92413c',
    'af0cf970844d475889d694dff826861e',
],
    'words': 'deer crab',
    'nested': {
    'id': 137,
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
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 10,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 1,
},
],
},
    'nested_array': [
    [
    -3,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'fox',
    'fish',
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
    'mixed_type': 'bear',
    'maybe': 'snake',
    'maybe_null': 'cow',
},
},
    {
    'id': 38,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 138,
    'id_str': [
    '23',
    '04',
],
    'text_data': '1837fc083d9b4a7e8c1e96160a83045b',
    'rand_digit': 1,
    'rand_number': 0.71449,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-12 02:03:38.464560+1000',
    'text_array': [
    'f365855cb8e14185b71ce7475759bd35',
    'c64ebfc3f0ca440ea8e0a9bfe50870ce',
],
    'words': 'grasshopper deer',
    'nested': {
    'id': 138,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 6,
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
    'grasshopper',
    'sheep',
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
    'maybe': 'lobster',
    'maybe_null': 'fly',
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 139,
    'id_str': [
    '02',
],
    'text_data': '9ed583a8bfe74548b496dff640f3d53d',
    'rand_digit': 3,
    'rand_number': 0.90159,
    'rand_signed_int': 8,
    'rand_datetime': '2000-07-05T02:54:25.858927',
    'text_array': [
    'aa2430922e3e4bcdbb90b5c309c5f5d2',
    'c7738630b27b4cd3b68930378ab0637f',
],
    'words': 'elephant koala',
    'nested': {
    'id': 139,
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
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'shark',
    'turtle',
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
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 140,
    'id_str': [
    '23',
    '19',
],
    'text_data': '6ca672a9cc2844d693ef8371b26c7378',
    'rand_digit': 4,
    'rand_number': 0.42242,
    'rand_signed_int': 1,
    'rand_datetime': '2000-02-20 13:13:47',
    'text_array': [
    '91fd3a0294ec4f5b91dca0b05c1c1ed6',
    'dd06d3ada9d741f7963b90f7140454ab',
],
    'words': 'koala zebra',
    'nested': {
    'id': 140,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'ladybug',
    'lobster',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'fly',
    'maybe_null': 'cheetah',
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 141,
    'id_str': [
],
    'text_data': 'b98aab874314453bbec364335eb1dbb3',
    'rand_digit': 1,
    'rand_number': 0.29117,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-23T03:24:28.850649',
    'text_array': [
    '42b10e6c70294bba933e8b56aac194c4',
    '335b81fafc524c96a9822c2c3bd82509',
],
    'words': 'fox koala',
    'nested': {
    'id': 141,
    'rand_digit': 4,
    'array': [
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
    'nested_array': [
],
    'two_words': [
    'snake',
    'deer',
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
    'mixed_type': 8,
    'maybe': 'snail',
    'maybe_null': 'bird',
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 142,
    'id_str': [
    '23',
    '01',
    '17',
    '19',
],
    'text_data': '61f7ae4274574cc68882bab24b11ea83',
    'rand_digit': 3,
    'rand_number': 0.81346,
    'rand_signed_int': -5,
    'rand_datetime': '2000-11-21T00:43:03-0600',
    'text_array': [
    'd150c3b3a376406cb8e7317b136b52f5',
    '88d7ab9b04c1473a8121331c4c3763a6',
],
    'words': 'hyena panda',
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
    'word': 'lobster',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'duck',
    'number': 9,
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
    'word': 'grasshopper',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'bird',
    'turtle',
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
    'mixed_type': 'sloth',
    'maybe': 'chicken',
    'maybe_null': None,
},
},
    {
    'id': 43,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 143,
    'id_str': [
    '16',
    '02',
    '01',
],
    'text_data': '9efb76feedc6481eae2ad2de6b332099',
    'rand_digit': 3,
    'rand_number': 0.04558,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-01 09:55:52+1100',
    'text_array': [
    '879e5fd49da64c0dbb1ae6dfb52d127c',
    '3f7a8b7768704c07a281b28ae5f7bb00',
],
    'words': 'mosquito panda',
    'nested': {
    'id': 143,
    'rand_digit': 8,
    'array': [
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
    'word': 'snake',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    [
    8,
],
    [
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'sloth',
    'grasshopper',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'elephant',
    'maybe_null': None,
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 144,
    'id_str': [
    '22',
    '21',
    '07',
    '14',
    '15',
],
    'text_data': '11a2eb7e657b41cda9318a58998c642d',
    'rand_digit': 5,
    'rand_number': 0.27346,
    'rand_signed_int': -7,
    'rand_datetime': '2000-07-31 10:56:53.588871',
    'text_array': [
    'afff171aba324665ab6b920f83e6d1c7',
    'd61ddd2a70984160a5aa8b46b43b49a4',
],
    'words': 'leopard hyena',
    'nested': {
    'id': 144,
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
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'tiger',
    'bear',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': [
    74,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cow',
    'maybe_null': None,
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 145,
    'id_str': [
    '18',
    '07',
    '15',
],
    'text_data': '15ccdb6ac8524b89bc67f1d2284e5fd0',
    'rand_digit': 6,
    'rand_number': 0.42138,
    'rand_signed_int': -3,
    'rand_datetime': '2000-09-04T12:40:42',
    'text_array': [
    '7f4a69b755824aa8a7542964106a13f8',
    '8d881302c1cc48ba9fc65b738b53b7b5',
],
    'words': 'snail goat',
    'nested': {
    'id': 145,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'jaguar',
    'pig',
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
    'mixed_type': 0.24561,
    'maybe': 'koala',
    'maybe_null': None,
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
    '22',
],
    'text_data': 'dbab4aff488f4122a441b5ffa8dee2d3',
    'rand_digit': 9,
    'rand_number': 0.134,
    'rand_signed_int': -10,
    'rand_datetime': '2000-03-10 14:04:05.574018+1000',
    'text_array': [
    '66cc28183f79435da10b0f2973eebaf4',
    '089e126354944783aa48ad4728dedc34',
],
    'words': 'elephant ape',
    'nested': {
    'id': 146,
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
    'number': 4,
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
    'hello',
],
    'word': 'kangaroo',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -5,
],
    [
],
],
    'two_words': [
    'spider',
    'deer',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': [
    99,
],
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'mouse',
    'maybe_null': 'goat',
},
},
    {
    'id': 47,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 147,
    'id_str': [
    '15',
    '29',
    '15',
    '03',
],
    'text_data': '33bbc8e9700742eeaae3f8725c67ceee',
    'rand_digit': 9,
    'rand_number': 0.48032,
    'rand_signed_int': -2,
    'rand_datetime': '2000-09-14',
    'text_array': [
    '68e1ac737e214cae9475d6a3a1572399',
    '25131740ae4e447994180e142059401e',
],
    'words': 'panda wolf',
    'nested': {
    'id': 147,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'snail',
    'lion',
],
    'city': {
    'name': 'Zurich',
    'geo': {
    'lat': 47.376887,
    'lon': 8.541694,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 4,
    'maybe_null': 'gorilla',
},
},
    {
    'id': 48,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 148,
    'id_str': [
    '29',
    '13',
    '23',
],
    'text_data': '81495dcb386e43dca3036e6d19edd67d',
    'rand_digit': 2,
    'rand_number': 0.73976,
    'rand_signed_int': 1,
    'rand_datetime': '2000-05-31T18:00:51',
    'text_array': [
    'c736dd7194d9414d8e2a2e9293cd3a5b',
    '0fcb8840719749a3a5b05a44b2635c7a',
],
    'words': 'fox hippo',
    'nested': {
    'id': 148,
    'rand_digit': 2,
    'array': [
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
    'word': 'mouse',
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
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lobster',
    'sloth',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'sheep',
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 149,
    'id_str': [
    '26',
],
    'text_data': '8ed1e6db5aa54b2ca19c07808b08648b',
    'rand_digit': 4,
    'rand_number': 0.77348,
    'rand_signed_int': -10,
    'rand_datetime': '2000-01-23 21:40',
    'text_array': [
    '0b10f6ab9f4f4a78a141b55f94a5ba58',
    '0b82f39153ab414db200f6a425415952',
],
    'words': 'sloth duck',
    'nested': {
    'id': 149,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'cat',
    'mouse',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': [
    98,
],
    'rand_bool': False,
    'mixed_type': 1,
    'maybe': 'ape',
    'maybe_null': 'bear',
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
    'content-length': '128',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'recommend': {
    'positive': [
    10,
],
    'negative': [
],
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
        """测试请求 5 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '218',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'recommend': {
    'positive': [
    10,
],
    'negative': self.mutator.generate_float_array(dimension=2, normalized=True),
},
},
    'using': 'multi-image',
    'limit': 10,
    'with_vector': False,
    'with_payload': True,
    'lookup_from': {
    'collection': 'congruence_secondary_collection',
    'vector': 'multi-image',
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



    def test_request_6(self):
        """测试请求 6 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '141',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'recommend': {
    'positive': self.mutator.generate_float_array(dimension=2, normalized=True),
    'strategy': 'best_score',
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



    def test_request_7(self):
        """测试请求 7 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '151',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'recommend': {
    'positive': [
    10,
],
    'negative': [
],
    'strategy': 'best_score',
},
},
    'using': 'multi-code',
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



    def test_request_8(self):
        """测试请求 8 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '141',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'recommend': {
    'negative': self.mutator.generate_float_array(dimension=2, normalized=True),
    'strategy': 'best_score',
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



    def test_request_9(self):
        """测试请求 9 - POST http://localhost:6333/collections/congruence_test_collection/points/query/batch"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/query/batch")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/query/batch'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '326',
}
        
        # 原始请求内容
        original_content = {
    'searches': [
    {
    'query': {
    'recommend': {
    'positive': [
    10,
],
    'negative': [
],
    'strategy': 'average_vector',
},
},
    'using': 'multi-image',
    'limit': 2,
    'lookup_from': {
    'collection': 'congruence_secondary_collection',
    'vector': 'multi-image',
},
},
    {
    'query': {
    'recommend': {
    'positive': [
    3,
],
    'negative': [
],
    'strategy': 'best_score',
},
},
    'using': 'multi-code',
    'limit': 2,
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



    def test_request_10(self):
        """测试请求 10 - DELETE http://localhost:6333/collections/congruence_test_collection?timeout=60"""
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_multivector_recommend_queries.test_simple_recommend')
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
    test = TestMultivectorRecommendQueriestestSimpleRecommend()
    test.run_tests()
