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
logger = logging.getLogger('vdb_fuzzer.test.test_multivector_discovery_queries_test_only_target')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_multivector_discovery_queries.test_only_target"
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



class TestMultivectorDiscoveryQueriestestOnlyTarget:
    """自动生成的VDB模糊测试类 - test_multivector_discovery_queries.test_only_target"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_multivector_discovery_queries.test_only_target"
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
    'content-length': '524085',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 100,
    'id_str': [
    '10',
],
    'text_data': 'ae3a698e6d7c4173b3f7aee31fddae22',
    'rand_digit': 7,
    'rand_number': 0.09418,
    'rand_signed_int': -1,
    'rand_datetime': '2000-04-17 06:33:22.288004',
    'text_array': [
    'f25a752b81c5453c89a627b106281d5a',
    '87430c3ccf3546458573df3d378d5552',
],
    'words': 'dragonfly whale',
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
    'word': 'bear',
    'number': 7,
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
],
    'two_words': [
    'gorilla',
    'rhino',
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
    'maybe_null': None,
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 101,
    'id_str': [
    '25',
    '13',
],
    'text_data': 'e5522fe761004096b07f92089f425af0',
    'rand_digit': 9,
    'rand_number': 0.0193,
    'rand_signed_int': 5,
    'rand_datetime': '2000-02-26 08:42:39+0600',
    'text_array': [
    'f25796c588b0426288c9079b675333f5',
    '68a1ba4ed70e4fa48799b876da5a06bd',
],
    'words': 'grasshopper mosquito',
    'nested': {
    'id': 101,
    'rand_digit': 6,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 10,
},
    {
    'nested_empty': None,
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
],
    'word': 'sheep',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mosquito',
    'fox',
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
    'mixed_type': None,
    'maybe_null': 'ant',
},
},
    {
    'id': 2,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 102,
    'id_str': [
    '14',
    '24',
    '17',
],
    'text_data': 'ff4011345d6049f3a4fc5203493f1eca',
    'rand_digit': 6,
    'rand_number': 0.26399,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-16T00:48:13.629769',
    'text_array': [
    'dcd05d830659486d83504e26fa51c5ab',
    '4168396a0d864bdb9f9f6a68df98e8b9',
],
    'words': 'shark scorpion',
    'nested': {
    'id': 102,
    'rand_digit': 1,
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
    'word': 'dog',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 9,
},
],
},
    'nested_array': [
    [
    1,
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'horse',
    'ant',
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
    'mixed_type': 0.10672,
    'maybe': 'grasshopper',
    'maybe_null': 'mouse',
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 103,
    'id_str': [
    '03',
],
    'text_data': 'cfb22b3501704fd8a95c7ca28635417d',
    'rand_digit': 4,
    'rand_number': 0.08899,
    'rand_signed_int': 5,
    'rand_datetime': '2000-03-17 16:29:43.970302',
    'text_array': [
    '6d3e5976a20441169abd8cdaaeb756bc',
    'b7e8eedd48c64e4993b878746284dc93',
],
    'words': 'ape snake',
    'nested': {
    'id': 103,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'dolphin',
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
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'leopard',
    'turtle',
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
    'maybe_null': None,
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 104,
    'id_str': [
    '04',
    '23',
    '13',
],
    'text_data': 'aa0c5986a22f46fbb1e10693985d9e0b',
    'rand_digit': 5,
    'rand_number': 0.66637,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-07T06:41:25+0500',
    'text_array': [
    '9b463be93ee54163a0ac6306e238e12c',
    '8e64bc7e5186441393e01070917a1b0b',
],
    'words': 'gorilla ant',
    'nested': {
    'id': 104,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'ape',
    'sheep',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'jaguar',
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 105,
    'id_str': [
    '14',
    '16',
],
    'text_data': '523ffa0d7d5448cc9f4f010700ebddf2',
    'rand_digit': 7,
    'rand_number': 0.64044,
    'rand_signed_int': -3,
    'rand_datetime': '2000-04-16',
    'text_array': [
    '3774bef8592b498ca99ee88464eda8d9',
    '5526f104abab42c39780ef9df95d9136',
],
    'words': 'kangaroo horse',
    'nested': {
    'id': 105,
    'rand_digit': 8,
    'array': [
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
    'word': 'leopard',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'camel',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'ant',
    'grasshopper',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'lizard',
    'maybe_null': 'chicken',
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 106,
    'id_str': [
    '08',
    '06',
    '21',
],
    'text_data': '5d995b04562e426cb95ccb5e0d9c96a6',
    'rand_digit': 1,
    'rand_number': 0.84265,
    'rand_signed_int': -3,
    'rand_datetime': '2000-05-01T17:43:33-1100',
    'text_array': [
    'd773a3adba854dd1a50ea1b0c3c135a0',
    'd4b94661c97b423b87f2c18d044534c9',
],
    'words': 'bee duck',
    'nested': {
    'id': 106,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'giraffe',
    'giraffe',
],
    'city': {
    'name': 'Frankfurt',
    'geo': {
    'lat': 50.110922,
    'lon': 8.682127,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'crab',
    'maybe_null': 'hippo',
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 107,
    'id_str': [
    '05',
    '11',
    '27',
    '27',
],
    'text_data': '76d7e8e6f1cf4aad9e1484221c760fdb',
    'rand_digit': 4,
    'rand_number': 0.99799,
    'rand_signed_int': -10,
    'rand_datetime': '2000-05-30 15:56:52-0500',
    'text_array': [
    '50c325e5f4374af5b9ccec3cf88374f8',
    'df01d951cb504c34a91501837b668a30',
],
    'words': 'shark hyena',
    'nested': {
    'id': 107,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
    5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'butterfly',
    'dolphin',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': None,
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 108,
    'id_str': [
],
    'text_data': 'a43dc910e9a24b72bc68e41e5ac24500',
    'rand_digit': 9,
    'rand_number': 0.51418,
    'rand_signed_int': -4,
    'rand_datetime': '2000-12-28T15:00:58+0700',
    'text_array': [
    '7506a8480e1a4c22846c11029b2bfbe8',
    '8c6a728d46c047b3968dd52504d5aed0',
],
    'words': 'pig hyena',
    'nested': {
    'id': 108,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 5,
},
    {
    'nested_empty': None,
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
    'tiger',
    'horse',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'koala',
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 109,
    'id_str': [
    '09',
    '09',
    '17',
],
    'text_data': '4f181a2a48854ad88cac50a85acb630b',
    'rand_digit': 9,
    'rand_number': 0.39664,
    'rand_signed_int': 0,
    'rand_datetime': '2000-08-11 19:02',
    'text_array': [
    'b5cc044c9ca5498b80d2863661ec2860',
    '9ede5353da714912a8d808a41f127265',
],
    'words': 'kangaroo giraffe',
    'nested': {
    'id': 109,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'spider',
    'pig',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.8125,
    'maybe': 'crab',
    'maybe_null': 'dog',
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 110,
    'id_str': [
    '08',
],
    'text_data': '508ddd643e7644a393baae3e2ddaa7e6',
    'rand_digit': 0,
    'rand_number': 0.90892,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-10T18:25:48.749707+1200',
    'text_array': [
    '643dad0164bd44e89a11470f00ff3f68',
    '20207f9d6cb24f5bb186505ba251de41',
],
    'words': 'spider chicken',
    'nested': {
    'id': 110,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'rabbit',
    'hyena',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': [
    23,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'snake',
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 111,
    'id_str': [
    '24',
    '23',
    '27',
],
    'text_data': 'b114aad124f44d378e95060861591082',
    'rand_digit': 9,
    'rand_number': 0.55395,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-15T03:28:56',
    'text_array': [
    '34504555575446b7839c4515f73cd543',
    '4615ab2560014f43865305de78390f36',
],
    'words': 'lobster grasshopper',
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
    'word': 'rhino',
    'number': 2,
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
    'panda',
    'pig',
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
    'mixed_type': 'fly',
    'maybe_null': 'goat',
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 112,
    'id_str': [
    '07',
],
    'text_data': '51db0e99e4db470fb0f8dac936a45561',
    'rand_digit': 3,
    'rand_number': 0.68163,
    'rand_signed_int': 5,
    'rand_datetime': '2001-01-19T02:25:47.535968',
    'text_array': [
    '15cdf43803d34118a67bc82221b16bce',
    '06e520d6450c4970989b803441af6689',
],
    'words': 'horse lion',
    'nested': {
    'id': 112,
    'rand_digit': 8,
    'array': [
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
    'word': 'koala',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fish',
    'shark',
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
    'mixed_type': 9,
    'maybe': 'fox',
    'maybe_null': 'fly',
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 113,
    'id_str': [
    '09',
],
    'text_data': 'd689d687e19d42fd90becf18b09c1135',
    'rand_digit': 5,
    'rand_number': 0.00072,
    'rand_signed_int': -9,
    'rand_datetime': '2000-04-21 00:16:34.203687',
    'text_array': [
    'd0c4307addcb4023a5089cbd5764f709',
    'ed04cc400c6a4c8a94542c6de4f2f54b',
],
    'words': 'lion bird',
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
    'word': 'dog',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'jaguar',
    'spider',
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
    'maybe_null': 'hippo',
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 114,
    'id_str': [
    '02',
],
    'text_data': '513001ce6d214afbb08788062b2e20de',
    'rand_digit': 4,
    'rand_number': 0.1923,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-17 15:11:45+0500',
    'text_array': [
    'd3c5f079fccc4b49810d6e4fa9264df2',
    '82c12d680860466a9a5e111bf772c0f8',
],
    'words': 'wolf whale',
    'nested': {
    'id': 114,
    'rand_digit': 4,
    'array': [
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'turtle',
    'squid',
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
    'maybe': 'sloth',
    'maybe_null': 'monkey',
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 115,
    'id_str': [
    '03',
    '06',
    '09',
],
    'text_data': '5a9bdffca63f4aa4b3e5aa05fc639131',
    'rand_digit': 1,
    'rand_number': 0.87786,
    'rand_signed_int': -9,
    'rand_datetime': '2001-01-06T12:43:06.023655-0800',
    'text_array': [
    '95aca724a5c24cae92d56da30513dcb1',
    '9ddd770cae6b4c77b059ff6f77a042fa',
],
    'words': 'cat goat',
    'nested': {
    'id': 115,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ladybug',
    'koala',
],
    'city': {
    'name': 'Moscow',
    'geo': {
    'lat': 55.755826,
    'lon': 37.6173,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 116,
    'id_str': [
    '01',
    '04',
    '01',
],
    'text_data': '44dde19b83864b3387df2d05a48df74a',
    'rand_digit': 5,
    'rand_number': 0.19903,
    'rand_signed_int': -8,
    'rand_datetime': '2000-09-11T01:05:32.008314',
    'text_array': [
    'b98a8789bde94119b8529d8574d9e577',
    'c7568315125948f6bdc39908626738fb',
],
    'words': 'tiger octopus',
    'nested': {
    'id': 116,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'snake',
    'grasshopper',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': [
    87,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'leopard',
    'maybe_null': 'pig',
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 117,
    'id_str': [
    '10',
    '08',
],
    'text_data': '5cbc52d8019849f7a6c41e9435903ad4',
    'rand_digit': 1,
    'rand_number': 0.91027,
    'rand_signed_int': 3,
    'rand_datetime': '2000-07-22',
    'text_array': [
    'e7ea68e8e9e1455d8d3bcf6e5bf8d3bb',
    'ef75f148667743a093da0030e7e54d71',
],
    'words': 'deer fish',
    'nested': {
    'id': 117,
    'rand_digit': 2,
    'array': [
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
    'word': 'goat',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bee',
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
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'monkey',
    'bee',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': [
    62,
],
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
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 118,
    'id_str': [
    '25',
    '01',
    '30',
    '19',
    '29',
],
    'text_data': 'ba62c93e38754e5e9b92ace7f88660cf',
    'rand_digit': 9,
    'rand_number': 0.77929,
    'rand_signed_int': 2,
    'rand_datetime': '2000-11-02T21:00:58.766831Z',
    'text_array': [
    '4cc6ba07f6d04f62b8dbce14bf46cfc1',
    '79c1b7fddf42474dac9beefa212e694a',
],
    'words': 'ape monkey',
    'nested': {
    'id': 118,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    5,
],
],
    'two_words': [
    'goat',
    'kangaroo',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': [
    60,
],
    'rand_bool': False,
    'mixed_type': 0.78462,
    'maybe': 'octopus',
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
    '26',
    '17',
    '05',
    '30',
],
    'text_data': '5a07685adce2451e83173a0fbbc711c7',
    'rand_digit': 3,
    'rand_number': 0.48772,
    'rand_signed_int': -4,
    'rand_datetime': '2000-03-04 21:46:10.198938',
    'text_array': [
    '3d7caba71032435c9237ea8e18f12888',
    'afabb705f5554c0f9c4db1fcfb383974',
],
    'words': 'bird monkey',
    'nested': {
    'id': 119,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'bear',
    'number': 9,
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
],
},
    'nested_array': [
    [
    5,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -5,
],
],
    'two_words': [
    'horse',
    'monkey',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': [
    4,
],
    'rand_bool': False,
    'mixed_type': False,
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 120,
    'id_str': [
    '10',
    '22',
],
    'text_data': '43dc39b2531a4620a06486f3dd803cdf',
    'rand_digit': 4,
    'rand_number': 0.71546,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-29',
    'text_array': [
    'c40b27bcb79e49acbaa2d16bb5fbe920',
    'b88bfc14296a403ca0bbb4035d819e2f',
],
    'words': 'cow squid',
    'nested': {
    'id': 120,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 7,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'sloth',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fox',
    'lion',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 121,
    'id_str': [
    '29',
    '23',
],
    'text_data': 'dca090e8e378496fbf2fdb2c5b9d80d0',
    'rand_digit': 5,
    'rand_number': 0.01171,
    'rand_signed_int': 7,
    'rand_datetime': '2000-06-07T03:18:10.886784+0200',
    'text_array': [
    '2f7b9c1c544e4044a98c676ab4de8568',
    '79b2939edd3f4ff79a7c496714f988f9',
],
    'words': 'turtle dragonfly',
    'nested': {
    'id': 121,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'lion',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 2,
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
],
},
    'nested_array': [
],
    'two_words': [
    'spider',
    'kangaroo',
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
    'mixed_type': 0.43342,
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
    '05',
    '26',
    '26',
    '03',
],
    'text_data': '84d935259f9743cc8b1e10047dc87c48',
    'rand_digit': 9,
    'rand_number': 0.1919,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-01T07:23:53.278390+0900',
    'text_array': [
    '53f680f55a924a589af9bee5ec2fd942',
    'fa774ae975164017b3aee6d3e0527b42',
],
    'words': 'fly sloth',
    'nested': {
    'id': 122,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'leopard',
    'camel',
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
    'mixed_type': False,
    'maybe_null': None,
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 123,
    'id_str': [
    '28',
    '16',
],
    'text_data': '9ecd728e63914c559571db212ff81440',
    'rand_digit': 1,
    'rand_number': 0.48155,
    'rand_signed_int': 9,
    'rand_datetime': '2000-04-03 00:25:53+1000',
    'text_array': [
    '71a445cd22f844719d847ea8d5f76823',
    '23193a084e6d4b06a62ffa0eaa685c9b',
],
    'words': 'scorpion duck',
    'nested': {
    'id': 123,
    'rand_digit': 4,
    'array': [
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
    'word': 'scorpion',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    6,
],
    [
    3,
],
],
    'two_words': [
    'cow',
    'frog',
],
    'city': {
    'name': 'Dubai',
    'geo': {
    'lat': 25.204849,
    'lon': 55.270783,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'frog',
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 124,
    'id_str': [
    '08',
    '26',
    '19',
],
    'text_data': '6ee2a6e82e3f428cbbd8dacfbe162ebc',
    'rand_digit': 5,
    'rand_number': 0.02634,
    'rand_signed_int': 5,
    'rand_datetime': '2000-02-11T14:56:01.007188+0900',
    'text_array': [
    '3d62002e75d74e67bfedffe378645577',
    '4a3cd1b2ba4e4e34a4ce0ee88dee2120',
],
    'words': 'duck dragonfly',
    'nested': {
    'id': 124,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 10,
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
    'word': 'panda',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 8,
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
    0,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'shark',
    'ant',
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
    'mixed_type': 2,
    'maybe_null': None,
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
    '01',
    '24',
    '20',
],
    'text_data': '1e6a697a9ae744e6b7f3abf2811ea3f1',
    'rand_digit': 0,
    'rand_number': 0.43891,
    'rand_signed_int': -6,
    'rand_datetime': '2001-01-22 10:14:04-0800',
    'text_array': [
    '4da60518b5c9407693a1f00b83fc9adb',
    '0c97a4d162b440e7a7acd228fec4e8a4',
],
    'words': 'mosquito duck',
    'nested': {
    'id': 125,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'chicken',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'scorpion',
    'elephant',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cow',
},
},
    {
    'id': 26,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 126,
    'id_str': [
],
    'text_data': 'a5d56313797d4cd592e7115f25a7f3b3',
    'rand_digit': 4,
    'rand_number': 0.86942,
    'rand_signed_int': 8,
    'rand_datetime': '2000-09-08T03:39:22.472387',
    'text_array': [
    '42adb84f2bf24fe3bdd96b8ebe226a60',
    'a19fe224726f43d1bb4248bfcc9aabe7',
],
    'words': 'tiger ladybug',
    'nested': {
    'id': 126,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'tiger',
    'wolf',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 127,
    'id_str': [
    '10',
],
    'text_data': 'bf859f699c67473d9cc7e2bb8b710d9b',
    'rand_digit': 6,
    'rand_number': 0.67664,
    'rand_signed_int': 0,
    'rand_datetime': '2000-10-16 21:31:30',
    'text_array': [
    '1743bd6405624adfac3542989cc1788a',
    'c3684b149a1445e6acb11367f5a86352',
],
    'words': 'hyena giraffe',
    'nested': {
    'id': 127,
    'rand_digit': 3,
    'array': [
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
    'word': 'mosquito',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -8,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'dolphin',
    'jaguar',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'panda',
    'maybe_null': 'butterfly',
},
},
    {
    'id': 28,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 128,
    'id_str': [
    '11',
    '20',
],
    'text_data': 'fc5eefe4dad644368cdddfa5cd15f5d6',
    'rand_digit': 4,
    'rand_number': 0.84072,
    'rand_signed_int': 3,
    'rand_datetime': '2001-01-28T06:22:48',
    'text_array': [
    'f395dd4df1a74097ab178dd3a20e2d88',
    'a42e1dd35915428b98ec34bf67b9cd58',
],
    'words': 'dolphin ladybug',
    'nested': {
    'id': 128,
    'rand_digit': 2,
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
    'word': 'koala',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'bear',
    'mosquito',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': [
    49,
],
    'rand_bool': True,
    'mixed_type': 'hippo',
    'maybe': 'mosquito',
    'maybe_null': 'leopard',
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
    '01',
],
    'text_data': '42c7dffefccb43df9fd5dee2b5d461cc',
    'rand_digit': 7,
    'rand_number': 0.13835,
    'rand_signed_int': 3,
    'rand_datetime': '2000-12-13 14:36:41.791664',
    'text_array': [
    '1cd39f851dae46c9a2b25f7ffcb706e8',
    'bbe96c085e184bf3a76b208cf73bb07e',
],
    'words': 'camel crab',
    'nested': {
    'id': 129,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    [
    -2,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'hippo',
    'ape',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'whale',
    'maybe_null': None,
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 130,
    'id_str': [
],
    'text_data': '6cf5b779be8a417899c993386f0a707a',
    'rand_digit': 9,
    'rand_number': 0.31262,
    'rand_signed_int': -1,
    'rand_datetime': '2000-10-28T17:06:29.631525+10:00',
    'text_array': [
    'b1a9f24d71354d71a8f3b052b2a18295',
    '9a780446a48241c1972dddcd7e317c9e',
],
    'words': 'cat rhino',
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
    'word': 'dragonfly',
    'number': 7,
},
    {
    'nested_empty': None,
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
    'word': 'ape',
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
    'chicken',
    'ladybug',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.94264,
    'maybe': 'mouse',
    'maybe_null': None,
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 131,
    'id_str': [
    '09',
    '14',
    '10',
    '02',
    '19',
],
    'text_data': 'a777ce874af14d22bf4c88fd8012ec31',
    'rand_digit': 4,
    'rand_number': 0.56502,
    'rand_signed_int': 3,
    'rand_datetime': '2000-10-02 02:18:35-0900',
    'text_array': [
    '7c1a7ed45668412698397d18ac79eb8c',
    'ddaa935b9bf44662a2e0ebd991a2f756',
],
    'words': 'goat tiger',
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
    'word': 'cat',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'lion',
    'ladybug',
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
    'mixed_type': 4,
},
},
    {
    'id': 32,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 132,
    'id_str': [
    '18',
    '27',
    '10',
],
    'text_data': '8f66063077df4cc199b66ffafdfb126c',
    'rand_digit': 3,
    'rand_number': 0.65113,
    'rand_signed_int': 7,
    'rand_datetime': '2000-01-03 23:07',
    'text_array': [
    '36eaf4f0314943c8870ff89a616333f8',
    '520a61142c9d4de0bb04f9640b6919a4',
],
    'words': 'fly goat',
    'nested': {
    'id': 132,
    'rand_digit': 3,
    'array': [
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    4,
],
],
    'two_words': [
    'goat',
    'bird',
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
    'maybe_null': 'leopard',
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 133,
    'id_str': [
    '26',
    '26',
    '17',
    '12',
],
    'text_data': 'c06ff187b8cc437493d50bb218d5146e',
    'rand_digit': 4,
    'rand_number': 0.45711,
    'rand_signed_int': 8,
    'rand_datetime': '2000-04-12 01:43',
    'text_array': [
    '1457d53f55b6460897ea5bb69ad04aa7',
    '27b77fdc432547e1825e8679d4c2d484',
],
    'words': 'sheep shark',
    'nested': {
    'id': 133,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 2,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -8,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'goat',
    'squid',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': [
    77,
],
    'rand_bool': True,
    'mixed_type': 'snail',
    'maybe': 'wolf',
    'maybe_null': 'grasshopper',
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 134,
    'id_str': [
    '25',
    '09',
],
    'text_data': '45230ebfeb2c46498de163b1165df949',
    'rand_digit': 3,
    'rand_number': 0.58167,
    'rand_signed_int': -3,
    'rand_datetime': '2001-01-18T18:14:35.749419+0400',
    'text_array': [
    '8f290afb22db42729b2dfa21f97586f7',
    '21ab5761eb65403cb0b5fe2ddc2659ca',
],
    'words': 'kangaroo kangaroo',
    'nested': {
    'id': 134,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'lizard',
    'koala',
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
    'mixed_type': 'dog',
    'maybe': 'elephant',
},
},
    {
    'id': 35,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 135,
    'id_str': [
    '17',
    '12',
    '01',
    '19',
    '07',
],
    'text_data': '329e341d19494f81a87da308e7e13c7e',
    'rand_digit': 8,
    'rand_number': 0.97746,
    'rand_signed_int': -3,
    'rand_datetime': '2000-08-12T03:17:11.783414',
    'text_array': [
    'd38db566d25d456696aeaa6cbab4b85e',
    '7433a6d7282745feb11de451fc26792c',
],
    'words': 'mosquito ape',
    'nested': {
    'id': 135,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fly',
    'number': 7,
},
],
},
    'nested_array': [
    [
    2,
],
    [
    -3,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lobster',
    'dog',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'spider',
},
},
    {
    'id': 36,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 136,
    'id_str': [
    '06',
    '04',
    '02',
    '04',
    '25',
],
    'text_data': '3a22cd930625428fb3060e6654846080',
    'rand_digit': 0,
    'rand_number': 0.25844,
    'rand_signed_int': -3,
    'rand_datetime': '2000-06-07T23:10:43.297695',
    'text_array': [
    '1f0036e457ba426dac555752eb0f9736',
    '7ead48ed4c764e248eb4d9d9c104f7f1',
],
    'words': 'mouse bee',
    'nested': {
    'id': 136,
    'rand_digit': 7,
    'array': [
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
    'word': 'cat',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    0,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'shark',
    'snail',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': [
    8,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
    '07',
],
    'text_data': 'd1718d5c7c4f467c8ce9322bbf70782e',
    'rand_digit': 0,
    'rand_number': 0.26597,
    'rand_signed_int': 9,
    'rand_datetime': '2000-09-21T18:59:47+1100',
    'text_array': [
    '03f5c40a9195414db058b03de3fe52d9',
    'ec6aa6652e284f56af0f370cdea5f6ee',
],
    'words': 'cat ladybug',
    'nested': {
    'id': 137,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 4,
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
    'hello',
],
    'word': 'sheep',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    4,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'cat',
    'crab',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': [
    64,
],
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'lion',
    'maybe_null': 'tiger',
},
},
    {
    'id': 38,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 138,
    'id_str': [
],
    'text_data': '19667e5bbcce4077b3032f291b3a2fe7',
    'rand_digit': 9,
    'rand_number': 0.02813,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-27 23:41:07+0700',
    'text_array': [
    '1b0ef9d05abc452eb64bdbd696c36fa2',
    '3dff719839fb44dd87464491430f2b5c',
],
    'words': 'dog giraffe',
    'nested': {
    'id': 138,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 8,
},
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
    'word': 'zebra',
    'number': 10,
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
],
    'word': 'fish',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'scorpion',
    'crab',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': [
    98,
],
    'rand_bool': False,
    'mixed_type': None,
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 139,
    'id_str': [
    '07',
    '20',
],
    'text_data': '25b3120d0c2f435882892d98356084f3',
    'rand_digit': 5,
    'rand_number': 0.18896,
    'rand_signed_int': 10,
    'rand_datetime': '2000-09-18 09:55:03',
    'text_array': [
    '893d6041ce6c4416adc9e5b9a1cab58b',
    '8f81fd2332624a148b144f5520d9eb6c',
],
    'words': 'koala bear',
    'nested': {
    'id': 139,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 4,
},
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
    'word': 'wolf',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'panda',
    'crab',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'whale',
    'maybe_null': None,
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 140,
    'id_str': [
    '20',
    '09',
    '03',
],
    'text_data': '462423b5dc5a440cb58e7deb22d6782f',
    'rand_digit': 8,
    'rand_number': 0.30387,
    'rand_signed_int': -10,
    'rand_datetime': '2001-01-01',
    'text_array': [
    'd1168b64fa1e4f0889582643116c1796',
    'bad45b378985496d976a81fce478b5ea',
],
    'words': 'koala lizard',
    'nested': {
    'id': 140,
    'rand_digit': 7,
    'array': [
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
],
    'word': 'mouse',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 4,
},
],
},
    'nested_array': [
    [
    -1,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'shark',
    'fox',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'chicken',
    'maybe': 'lion',
    'maybe_null': 'panda',
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 141,
    'id_str': [
    '10',
    '27',
],
    'text_data': '3552d3d4da8c430fa9668db60450db28',
    'rand_digit': 8,
    'rand_number': 0.43406,
    'rand_signed_int': -8,
    'rand_datetime': '2000-05-01T13:27:38',
    'text_array': [
    '0bd5d952a87c468d87b6f5e865b7c376',
    '9a87067a3d1c4e358bda26ab5416b270',
],
    'words': 'bee frog',
    'nested': {
    'id': 141,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'spider',
    'fox',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'sheep',
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 142,
    'id_str': [
    '10',
],
    'text_data': '561b8c8bbebe4daca941ac1e68512569',
    'rand_digit': 4,
    'rand_number': 0.895,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-01T18:14:27-0300',
    'text_array': [
    '24db1afe6fdd4c18b0a5458e92fa3262',
    'f5807370452548dfb7cff7c0f6e0d3ef',
],
    'words': 'tiger dog',
    'nested': {
    'id': 142,
    'rand_digit': 1,
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
    'hello',
],
    'word': 'goat',
    'number': 5,
},
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
],
    'word': 'bear',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mouse',
    'horse',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'deer',
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 43,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 143,
    'id_str': [
    '11',
    '12',
    '14',
    '15',
],
    'text_data': 'c5afb4ec0d6b499ab0ac51fdadc7479f',
    'rand_digit': 1,
    'rand_number': 0.99888,
    'rand_signed_int': -4,
    'rand_datetime': '2000-03-27T20:53:32',
    'text_array': [
    '99b45cd76d974f35911948141c2b4560',
    '39340b682c444863b66bfc4f27bf73e7',
],
    'words': 'bee bear',
    'nested': {
    'id': 143,
    'rand_digit': 8,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'crab',
    'snake',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'crab',
    'maybe_null': 'bear',
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 144,
    'id_str': [
    '26',
    '01',
],
    'text_data': '00c4b91cfe084fc0963635131b607eec',
    'rand_digit': 0,
    'rand_number': 0.0558,
    'rand_signed_int': 2,
    'rand_datetime': '2000-11-15T12:14:31.158575-0300',
    'text_array': [
    'f6d2866b3ea34298b90d73e6b8c1f142',
    '1f87ac7f2497448d9a016bfb6d98908e',
],
    'words': 'jaguar elephant',
    'nested': {
    'id': 144,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
    -10,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'tiger',
    'bird',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'mosquito',
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 145,
    'id_str': [
    '24',
    '19',
    '04',
    '26',
],
    'text_data': 'ad59ed2460254b4c893b007992a4a436',
    'rand_digit': 5,
    'rand_number': 0.78146,
    'rand_signed_int': -1,
    'rand_datetime': '2000-01-21T23:20:05.754597-1000',
    'text_array': [
    '0313674e24e84e61a6183a792b11bed4',
    '9dc6f3b42b1e4d7e98fe2cf9d2257b02',
],
    'words': 'bear zebra',
    'nested': {
    'id': 145,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bird',
    'monkey',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'snake',
    'maybe_null': 'snake',
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
    '01',
    '23',
    '16',
    '22',
    '15',
],
    'text_data': 'ec75c29d637144b6827163b54861333c',
    'rand_digit': 9,
    'rand_number': 0.19515,
    'rand_signed_int': 7,
    'rand_datetime': '2000-02-05T21:44:21.321723',
    'text_array': [
    '5d155b62e88f4376bef1de4bb796e6c2',
    'c40a913eb13d4d47b0841ab10d466c25',
],
    'words': 'wolf fly',
    'nested': {
    'id': 146,
    'rand_digit': 6,
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
],
    'word': 'spider',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 1,
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
],
    'word': 'rhino',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'elephant',
    'scorpion',
],
    'city': {
    'name': 'Kuala Lumpur',
    'geo': {
    'lat': 3.139003,
    'lon': 101.686855,
},
},
    'rand_tuple': [
    87,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 47,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 147,
    'id_str': [
    '21',
    '18',
    '17',
    '30',
],
    'text_data': '8ba2015508044c96a0f6f6d8f9e22075',
    'rand_digit': 0,
    'rand_number': 0.22353,
    'rand_signed_int': -7,
    'rand_datetime': '2000-03-03 14:55',
    'text_array': [
    'f997b003772f46049d7cfb351a119a28',
    '0003ecbf55fb4cb4b7648981025b039c',
],
    'words': 'cat ant',
    'nested': {
    'id': 147,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'cheetah',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
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
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 148,
    'id_str': [
    '19',
    '21',
    '14',
    '24',
],
    'text_data': '9391a41464104dc5b5b9c3f51cf46f9d',
    'rand_digit': 6,
    'rand_number': 0.58201,
    'rand_signed_int': 10,
    'rand_datetime': '2000-09-18T01:40:26.478180-0700',
    'text_array': [
    '49296c200e964f449d7e609af7613a79',
    'b041e433694f45e2a053d8c97c74804d',
],
    'words': 'fox pig',
    'nested': {
    'id': 148,
    'rand_digit': 3,
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
    'hello',
],
    'word': 'butterfly',
    'number': 5,
},
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
    'word': 'cow',
    'number': 3,
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
    -2,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hippo',
    'whale',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'octopus',
    'maybe_null': 'mouse',
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 149,
    'id_str': [
    '27',
],
    'text_data': 'dbeb1283fb6c45fbb3d0734d06c16ce3',
    'rand_digit': 0,
    'rand_number': 0.59556,
    'rand_signed_int': -2,
    'rand_datetime': '2000-02-11 08:14:16.560623',
    'text_array': [
    '36b04350bce84749aaac2f76445462fe',
    '896c73de401e4d74ab51b7524624d89f',
],
    'words': 'scorpion frog',
    'nested': {
    'id': 149,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'goat',
    'wolf',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
},
},
    {
    'id': 50,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 150,
    'id_str': [
    '23',
    '12',
    '18',
],
    'text_data': '03a95f9ec1de4ca19fd6ed452c104056',
    'rand_digit': 4,
    'rand_number': 0.18894,
    'rand_signed_int': -3,
    'rand_datetime': '2000-04-13T00:05:48.631880',
    'text_array': [
    'c6455e9ee5d34312ae14f904157051d2',
    '20c8648c648f4ec8a2b7174127cb3dfc',
],
    'words': 'shark ape',
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
    'word': 'gorilla',
    'number': 9,
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
    'nested_empty': [
    'hello',
],
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
    'word': 'deer',
    'number': 1,
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
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'monkey',
    'maybe_null': None,
},
},
    {
    'id': 51,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 151,
    'id_str': [
],
    'text_data': '7127a7c128c2417bbdc77f7aeb936cea',
    'rand_digit': 6,
    'rand_number': 0.36882,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-11 16:10',
    'text_array': [
    'e29175b1e0094876b7170564658aaf7b',
    'c1262266d5534f4ea0a2eb24fa28435a',
],
    'words': 'bird spider',
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
    'word': 'snake',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'sloth',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -10,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'camel',
    'kangaroo',
],
    'city': {
    'name': 'London',
    'geo': {
    'lat': 51.507351,
    'lon': -0.127758,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'lion',
},
},
    {
    'id': 52,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 152,
    'id_str': [
    '03',
    '09',
    '29',
],
    'text_data': '0155f88b4cca42bcbc0ce105367fe2b4',
    'rand_digit': 4,
    'rand_number': 0.04702,
    'rand_signed_int': -1,
    'rand_datetime': '2000-05-22 00:46:22+0400',
    'text_array': [
    '2cce9ee226d9422fba6cbc44dc658384',
    '5820e683edc744ab848b81ee6d505a3a',
],
    'words': 'whale hippo',
    'nested': {
    'id': 152,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mouse',
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
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'whale',
    'bee',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'cat',
    'maybe_null': 'lobster',
},
},
    {
    'id': 53,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 153,
    'id_str': [
    '14',
    '29',
],
    'text_data': '6817557959dc4cdaa19315dd86dee584',
    'rand_digit': 0,
    'rand_number': 0.90452,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-02 05:15:34.511243',
    'text_array': [
    '1bd8bbd5a9d34fe7a8ad045c32139ec4',
    'c0d09206f8bc41a9a10424390d2acb6d',
],
    'words': 'lion wolf',
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
    'word': 'cat',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'hyena',
    'number': 2,
},
],
},
    'nested_array': [
    [
    5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'lizard',
    'butterfly',
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
    'mixed_type': 0,
    'maybe': 'whale',
    'maybe_null': 'zebra',
},
},
    {
    'id': 54,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 154,
    'id_str': [
],
    'text_data': '17267d4103f14ae693b2965b8cb22e26',
    'rand_digit': 0,
    'rand_number': 0.89089,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-10T03:08:50.321039-11:00',
    'text_array': [
    '7078e81af73742129b681f66ff5947c8',
    '274844fc306d451db62c615d73837324',
],
    'words': 'giraffe bird',
    'nested': {
    'id': 154,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 8,
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
    'nested_array': [
    [
    -5,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'tiger',
    'wolf',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 'scorpion',
    'maybe': 'octopus',
},
},
    {
    'id': 55,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 155,
    'id_str': [
    '13',
    '02',
],
    'text_data': '49d176e87635415c9310b1cca8e64419',
    'rand_digit': 7,
    'rand_number': 0.74013,
    'rand_signed_int': -8,
    'rand_datetime': '2000-10-15T05:30:07.454976',
    'text_array': [
    '60b2e6a2cd424cb3aa993529fc621817',
    '55314cd516fe4f90880647f804183d1d',
],
    'words': 'octopus whale',
    'nested': {
    'id': 155,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 1,
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
    'nested_array': [
    [
    1,
],
    [
    8,
],
    [
    2,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'cat',
    'snail',
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
    'mixed_type': 0.19358,
    'maybe': 'crab',
    'maybe_null': None,
},
},
    {
    'id': 56,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 156,
    'id_str': [
    '02',
    '29',
    '14',
    '28',
    '06',
],
    'text_data': '7d657ae4a0134c4dbe802639648740d2',
    'rand_digit': 1,
    'rand_number': 0.59506,
    'rand_signed_int': 8,
    'rand_datetime': '2000-11-12T20:09:59.284205',
    'text_array': [
    'd5b30905eb534f869b09f6acb620090e',
    '9ebb1a1f8e3942af9bd20b3088596b99',
],
    'words': 'mosquito cow',
    'nested': {
    'id': 156,
    'rand_digit': 9,
    'array': [
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
    [
    -10,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'deer',
    'kangaroo',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 9,
    'maybe': 'chicken',
    'maybe_null': 'squid',
},
},
    {
    'id': 57,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 157,
    'id_str': [
    '16',
    '11',
    '25',
    '09',
],
    'text_data': 'f286ba4b271f48d4a74604c31302a764',
    'rand_digit': 3,
    'rand_number': 0.46851,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-31',
    'text_array': [
    'cfcf39ca80da4888a5b1038fd436ebf7',
    '025539a6b80a4a41b141aeeabe56a174',
],
    'words': 'grasshopper hyena',
    'nested': {
    'id': 157,
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
    'number': 4,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'horse',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'panda',
    'wolf',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': [
    85,
],
    'rand_bool': False,
    'mixed_type': 0.72002,
    'maybe': 'sheep',
    'maybe_null': None,
},
},
    {
    'id': 58,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 158,
    'id_str': [
    '29',
    '20',
],
    'text_data': 'afb4c745e86b45f78877a69904812bc9',
    'rand_digit': 5,
    'rand_number': 0.39475,
    'rand_signed_int': 8,
    'rand_datetime': '2000-11-19 07:35',
    'text_array': [
    '6664872d48a94d3aa4cb7125fa651a19',
    'c8ec644761ba4f45b49822b4c389ad61',
],
    'words': 'dog bee',
    'nested': {
    'id': 158,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 8,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'fox',
    'turtle',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'turtle',
    'maybe_null': 'frog',
},
},
    {
    'id': 59,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 159,
    'id_str': [
    '15',
    '07',
    '03',
],
    'text_data': '90adb10a38cb41778e72a07fd29dd45d',
    'rand_digit': 8,
    'rand_number': 0.98761,
    'rand_signed_int': 5,
    'rand_datetime': '2000-11-19T17:08:20.657306',
    'text_array': [
    '86cb80902bd546a48b28adef5a659ff9',
    'd0f6a270e6f9410a8acea6f4d23632d4',
],
    'words': 'grasshopper grasshopper',
    'nested': {
    'id': 159,
    'rand_digit': 2,
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
],
    'word': 'chicken',
    'number': 3,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -1,
],
],
    'two_words': [
    'cat',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'crab',
    'maybe_null': None,
},
},
    {
    'id': 60,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 160,
    'id_str': [
],
    'text_data': 'b5d5769e819e41298a69fa830ebc2691',
    'rand_digit': 7,
    'rand_number': 0.99208,
    'rand_signed_int': -10,
    'rand_datetime': '2000-02-25 22:57',
    'text_array': [
    '5c3aa5617f44405a8c9d5dfa55d6d79f',
    '6e4c0f9f7edb4845bc9deb011b4afd8d',
],
    'words': 'sloth crab',
    'nested': {
    'id': 160,
    'rand_digit': 4,
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
    'word': 'cow',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    6,
],
    [
    9,
],
],
    'two_words': [
    'rhino',
    'ladybug',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.90185,
    'maybe_null': 'rhino',
},
},
    {
    'id': 61,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 161,
    'id_str': [
    '08',
    '13',
    '07',
    '18',
],
    'text_data': '74d42af91c284df9a9ff9d5615686d49',
    'rand_digit': 0,
    'rand_number': 0.816,
    'rand_signed_int': 0,
    'rand_datetime': '2000-08-06 05:51:34-0900',
    'text_array': [
    '0afb0f9aa7584d09b1fb309200a2638f',
    'f68b06540a2546fab32d28a76cf05045',
],
    'words': 'spider cat',
    'nested': {
    'id': 161,
    'rand_digit': 3,
    'array': [
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
    'word': 'whale',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'horse',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cheetah',
    'hyena',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'gorilla',
},
},
    {
    'id': 62,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 162,
    'id_str': [
    '10',
    '26',
    '12',
],
    'text_data': 'f524c31e899447bcb5f978ae0414871f',
    'rand_digit': 2,
    'rand_number': 0.59611,
    'rand_signed_int': 4,
    'rand_datetime': '2000-08-28 05:07:06.716437',
    'text_array': [
    '95b5faa7c7c842caa57bc4262dbe25dd',
    'a85318af08c94e1095b614431abcc91d',
],
    'words': 'snail rabbit',
    'nested': {
    'id': 162,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 3,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'panda',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    8,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'rabbit',
    'horse',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'panda',
    'maybe_null': 'zebra',
},
},
    {
    'id': 63,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 163,
    'id_str': [
    '17',
    '16',
],
    'text_data': '29edde0de3d9450f84b804370e16cf06',
    'rand_digit': 9,
    'rand_number': 0.7743,
    'rand_signed_int': -10,
    'rand_datetime': '2000-10-09 02:49',
    'text_array': [
    'bdd67e4389064886a031a2e689de1a3c',
    'b4c6b442630c45178b5a536fbfe861f7',
],
    'words': 'snake hippo',
    'nested': {
    'id': 163,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'octopus',
    'number': 10,
},
],
},
    'nested_array': [
    [
    -10,
],
    [
    10,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fox',
    'zebra',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 'zebra',
    'maybe_null': 'camel',
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
    'content-length': '413689',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 100,
    'id_str': [
    '13',
    '16',
    '04',
    '05',
    '07',
],
    'text_data': 'f20c171ec5c04e23ba7d7954376326c3',
    'rand_digit': 7,
    'rand_number': 0.27938,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-29T15:24:50.921640',
    'text_array': [
    '44def81eae704aa092f49213dbc185b2',
    'ab2865b1324d4ec58812686c0749f0f0',
],
    'words': 'mosquito gorilla',
    'nested': {
    'id': 100,
    'rand_digit': 5,
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
    'nested_empty': None,
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
    'hello',
],
    'word': 'jaguar',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'duck',
    'sloth',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'bee',
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 101,
    'id_str': [
],
    'text_data': '737d47e49b074bc39f6bbac4b1321073',
    'rand_digit': 5,
    'rand_number': 0.41483,
    'rand_signed_int': -5,
    'rand_datetime': '2000-10-24 15:29:24-1000',
    'text_array': [
    '901c65e307a74f81839368535bad9860',
    'f65b1113f61048fabe9abc64ecbbab38',
],
    'words': 'sheep spider',
    'nested': {
    'id': 101,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'tiger',
    'bear',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
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
    'id': 2,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 102,
    'id_str': [
    '28',
    '11',
    '18',
    '12',
],
    'text_data': 'bb2bebe679da47d484024efe0b1bdf29',
    'rand_digit': 4,
    'rand_number': 0.3837,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-12 13:11:23.063912',
    'text_array': [
    'c6f57f9bb8bd4d1e850ffa5223d87568',
    'cf24fc5619354d5f8a2337b2cabdfa77',
],
    'words': 'grasshopper camel',
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
    'word': 'mouse',
    'number': 7,
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
    'nested_empty': None,
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
    'word': 'octopus',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'rhino',
    'hyena',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'sloth',
    'maybe_null': 'hippo',
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 103,
    'id_str': [
    '20',
    '10',
    '25',
    '15',
],
    'text_data': 'bfaa29c993e14768a20d3bd642045ef7',
    'rand_digit': 4,
    'rand_number': 0.89273,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-14 12:33:37.448184-1200',
    'text_array': [
    'c1cc296d281e4d959ce8754d3d541b54',
    '1a4d4b965c2844e8b192ba01556210f0',
],
    'words': 'dog lion',
    'nested': {
    'id': 103,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'giraffe',
    'pig',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'ladybug',
    'maybe_null': 'lizard',
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 104,
    'id_str': [
    '03',
    '27',
    '21',
],
    'text_data': 'f8e1a90512ad4e5c9dc6414b1c9bc1ce',
    'rand_digit': 4,
    'rand_number': 0.87458,
    'rand_signed_int': 8,
    'rand_datetime': '2000-05-23',
    'text_array': [
    '2647312eb7924cd7be5bfa858dabc0c7',
    'b844c41b68164338b162ab5586b8bc1a',
],
    'words': 'cow fox',
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
    'word': 'frog',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'ant',
    'scorpion',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': [
    86,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'deer',
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 105,
    'id_str': [
    '22',
    '14',
    '28',
],
    'text_data': '36def194a2e242bfabb9f75061a7151b',
    'rand_digit': 2,
    'rand_number': 0.15148,
    'rand_signed_int': 9,
    'rand_datetime': '2000-05-29T07:05:39-0400',
    'text_array': [
    '30e146b404f04123a28ab870095e69fe',
    '51bc6d5191e64caca213e5cab9d4e46e',
],
    'words': 'elephant horse',
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
    'word': 'grasshopper',
    'number': 3,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'squid',
    'spider',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': [
    87,
],
    'rand_bool': False,
    'mixed_type': 0.18131,
    'maybe_null': 'rhino',
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 106,
    'id_str': [
    '15',
    '09',
    '28',
    '04',
    '02',
],
    'text_data': '2c0b1de32e3445aeb3a24cb86773184b',
    'rand_digit': 0,
    'rand_number': 0.87028,
    'rand_signed_int': -4,
    'rand_datetime': '2000-07-06',
    'text_array': [
    'd2b59b63bb89441fb2c8831807659aee',
    '711d8ee1bb494c84a8c8068f0819220b',
],
    'words': 'lobster squid',
    'nested': {
    'id': 106,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
    -9,
],
],
    'two_words': [
    'butterfly',
    'camel',
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
    'mixed_type': False,
    'maybe': 'tiger',
    'maybe_null': 'lizard',
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 107,
    'id_str': [
],
    'text_data': 'a8de33127a3d4f8d96dcff369a59bb4d',
    'rand_digit': 7,
    'rand_number': 0.0922,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-27 15:46:26.008919+0200',
    'text_array': [
    'fe218d5b79254c23956b84eecc386876',
    '74a8fd0791af47d99a809bc7a108079d',
],
    'words': 'goat rabbit',
    'nested': {
    'id': 107,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'whale',
    'giraffe',
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
    'mixed_type': 5,
    'maybe_null': None,
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 108,
    'id_str': [
    '29',
    '05',
    '21',
    '23',
],
    'text_data': '0f68c603f165403c821338aeeef54074',
    'rand_digit': 9,
    'rand_number': 0.99389,
    'rand_signed_int': 4,
    'rand_datetime': '2000-04-09 15:47:56.019556',
    'text_array': [
    '7079ccd7e7614f0399c5b534e5b09c00',
    'fa66d22eaa974a019dcc74cb74e3099c',
],
    'words': 'octopus deer',
    'nested': {
    'id': 108,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
    5,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    1,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'fox',
    'grasshopper',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'squid',
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 109,
    'id_str': [
    '14',
    '30',
],
    'text_data': 'c84d9b841833494ca3a57734b0ce5a01',
    'rand_digit': 9,
    'rand_number': 0.42674,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-15 11:12',
    'text_array': [
    'cdf1788dc8c54039b05477346daad43f',
    '7561deed3c114122af67e0021672e02b',
],
    'words': 'goat ape',
    'nested': {
    'id': 109,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'spider',
    'number': 7,
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
],
    'word': 'cow',
    'number': 8,
},
],
},
    'nested_array': [
    [
    4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'turtle',
    'mosquito',
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
    'maybe': 'ape',
    'maybe_null': 'cow',
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 110,
    'id_str': [
    '02',
    '15',
],
    'text_data': 'fdde8c4487364e4e977cb0034d354467',
    'rand_digit': 0,
    'rand_number': 0.71657,
    'rand_signed_int': 5,
    'rand_datetime': '2000-04-26T20:19:22-1100',
    'text_array': [
    'b81381ad9c174d6980267a503955f3d0',
    'decce601fe454a0a926dc9350fa49853',
],
    'words': 'snail giraffe',
    'nested': {
    'id': 110,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'goat',
    'hyena',
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
    'mixed_type': 'grasshopper',
    'maybe': 'bee',
    'maybe_null': None,
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 111,
    'id_str': [
    '21',
    '20',
    '14',
],
    'text_data': '78536495a4524ee1b12c4db2e3559cc3',
    'rand_digit': 6,
    'rand_number': 0.25709,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-17 02:29:13',
    'text_array': [
    '46f9043bf7f54c6ab01d5eab12fafe70',
    '6d4371626ee54b168773399b01206ddb',
],
    'words': 'whale lion',
    'nested': {
    'id': 111,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'zebra',
    'panda',
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
    'mixed_type': 0.70004,
    'maybe': 'horse',
    'maybe_null': 'mosquito',
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 112,
    'id_str': [
    '08',
    '12',
    '25',
    '07',
    '28',
],
    'text_data': '75107869947c471cb142b01a4aa49c69',
    'rand_digit': 2,
    'rand_number': 0.07298,
    'rand_signed_int': -4,
    'rand_datetime': '2000-11-15 18:24:40-0800',
    'text_array': [
    '075c51aa49b64e35b706de79ea4c1e93',
    '1ae2fb52b98d4827963d2a5f1f8d2bc3',
],
    'words': 'ant turtle',
    'nested': {
    'id': 112,
    'rand_digit': 5,
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
    'word': 'ant',
    'number': 9,
},
],
},
    'nested_array': [
    [
    4,
],
    [
    4,
],
],
    'two_words': [
    'monkey',
    'fox',
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
    'maybe': 'hippo',
    'maybe_null': None,
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 113,
    'id_str': [
    '30',
    '10',
    '28',
],
    'text_data': '9f5f73c40d4e4f559845c8887a22a9a5',
    'rand_digit': 9,
    'rand_number': 0.12822,
    'rand_signed_int': 10,
    'rand_datetime': '2000-06-23T15:05:34.056689+12:00',
    'text_array': [
    '849124c8164944d599656fd82806c8f1',
    '3da53ccccbb24379be2ee5d049ed79ad',
],
    'words': 'wolf fly',
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
    'word': 'mosquito',
    'number': 4,
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
],
    'two_words': [
    'ladybug',
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
    'mixed_type': 0.85191,
    'maybe': 'fox',
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 114,
    'id_str': [
    '30',
    '21',
    '21',
],
    'text_data': 'af786af74569461f9637752f0c05ecbb',
    'rand_digit': 7,
    'rand_number': 0.23859,
    'rand_signed_int': -9,
    'rand_datetime': '2000-08-19T21:49:53.096340',
    'text_array': [
    '020ce42c51b944fd893973b240ede036',
    '069bd2f30e5b474cb8470cf420c52ab9',
],
    'words': 'leopard chicken',
    'nested': {
    'id': 114,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'hippo',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'koala',
    'fish',
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
    'mixed_type': None,
    'maybe': 'turtle',
    'maybe_null': None,
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 115,
    'id_str': [
    '24',
    '20',
],
    'text_data': '1d3d9c088f2a4272ae48aafe19887f4a',
    'rand_digit': 4,
    'rand_number': 0.68153,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-11 02:14:41-0500',
    'text_array': [
    'f945f81cef504e5cb60057ac75ab2bcd',
    'ef82b7f01f8a4001b91581ab1fc4002a',
],
    'words': 'dolphin cheetah',
    'nested': {
    'id': 115,
    'rand_digit': 9,
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
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'whale',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -6,
],
],
    'two_words': [
    'elephant',
    'chicken',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 116,
    'id_str': [
    '24',
    '29',
    '04',
],
    'text_data': 'da275337452d465c9900769c6b2f2ab9',
    'rand_digit': 1,
    'rand_number': 0.80256,
    'rand_signed_int': -4,
    'rand_datetime': '2000-11-18T19:10:38.675814-0500',
    'text_array': [
    '44a5f07377d147bc81077396eb7d66dd',
    '135104c409c64be4b132f18d70f39893',
],
    'words': 'rhino dragonfly',
    'nested': {
    'id': 116,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'lizard',
    'number': 7,
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
    'hello',
],
    'word': 'squid',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'scorpion',
    'giraffe',
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
    'mixed_type': 3,
    'maybe': 'sheep',
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 117,
    'id_str': [
    '12',
    '04',
    '05',
    '09',
    '11',
],
    'text_data': 'a718792033ff4e0d9937044993fe9011',
    'rand_digit': 0,
    'rand_number': 0.50049,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-01 06:39',
    'text_array': [
    '701d71a8016b405188e2ce5163f03242',
    '3e9341d6191643188e12eeaa4e631b79',
],
    'words': 'wolf leopard',
    'nested': {
    'id': 117,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'frog',
    'wolf',
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
    'mixed_type': 1,
},
},
    {
    'id': 18,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 118,
    'id_str': [
    '09',
],
    'text_data': 'c0d9fb3468024716b4da88af3fb42405',
    'rand_digit': 9,
    'rand_number': 0.54407,
    'rand_signed_int': -4,
    'rand_datetime': '2000-08-12 12:12:33',
    'text_array': [
    'b91e3753dd0b46918fddb1909e808760',
    'b9d77fdb9cd941568ab97a642f2529cf',
],
    'words': 'cheetah cat',
    'nested': {
    'id': 118,
    'rand_digit': 7,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 1,
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
    'word': 'spider',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'grasshopper',
    'lizard',
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
    'maybe_null': 'cheetah',
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
    '24',
    '07',
    '19',
    '28',
],
    'text_data': '4f1819c233f140fb8f2a97de840fc90e',
    'rand_digit': 6,
    'rand_number': 0.65987,
    'rand_signed_int': 5,
    'rand_datetime': '2000-02-13 14:57',
    'text_array': [
    '44cd200b115b4f8eba9c4ce867ecd171',
    'eff53e65f5cd4ef687a7403315b44a2a',
],
    'words': 'hyena pig',
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
    'word': 'sloth',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    6,
],
],
    'two_words': [
    'pig',
    'crab',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'squid',
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 120,
    'id_str': [
],
    'text_data': 'a10e745f1b5042449dd9d0e72017f912',
    'rand_digit': 1,
    'rand_number': 0.04402,
    'rand_signed_int': 5,
    'rand_datetime': '2000-01-21 01:25:53.690772',
    'text_array': [
    '728d208f64024e79903b76428ef72f58',
    '1b22ff8f9ba14881866cec1067b2064f',
],
    'words': 'kangaroo bird',
    'nested': {
    'id': 120,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'kangaroo',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'spider',
    'ape',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': [
    74,
],
    'rand_bool': False,
    'mixed_type': 'koala',
    'maybe': 'dog',
    'maybe_null': 'hyena',
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 121,
    'id_str': [
],
    'text_data': 'aac5f6c7200849a3ab887574fc917e0e',
    'rand_digit': 6,
    'rand_number': 0.39526,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-26 01:33:07',
    'text_array': [
    'fc11f1aeeb094f11bce81e3575d97b6e',
    '7c650e627c2d4dbebcb7f215af4351fe',
],
    'words': 'elephant kangaroo',
    'nested': {
    'id': 121,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
    7,
],
],
    'two_words': [
    'bee',
    'butterfly',
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
    'mixed_type': 'fly',
    'maybe': 'turtle',
    'maybe_null': 'sloth',
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
    '21',
    '21',
    '01',
],
    'text_data': '302b8c9ba3e94ff283d4495f206227f6',
    'rand_digit': 8,
    'rand_number': 0.0536,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-21T00:30:53.153969',
    'text_array': [
    '9383385b3af84e0497f4b855dcee0291',
    '0efd63e0ee074de2bcc4b83a200aed82',
],
    'words': 'gorilla butterfly',
    'nested': {
    'id': 122,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'goat',
    'camel',
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
    'mixed_type': True,
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 123,
    'id_str': [
    '05',
    '23',
],
    'text_data': '0f813e68a7f54cc9824c0cfca1db519e',
    'rand_digit': 5,
    'rand_number': 0.72812,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-03 20:47:01.632322',
    'text_array': [
    '8c6cae02cfd74dc9957fbeab6781cbd8',
    'eede8e1214df415eac0941f106e45800',
],
    'words': 'snake cheetah',
    'nested': {
    'id': 123,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
    1,
],
],
    'two_words': [
    'leopard',
    'monkey',
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
    'mixed_type': 0.08714,
    'maybe_null': 'horse',
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 124,
    'id_str': [
    '17',
    '21',
],
    'text_data': '1e23b0c6f5e94aa2a1f44d9479a47b0f',
    'rand_digit': 5,
    'rand_number': 0.39741,
    'rand_signed_int': -2,
    'rand_datetime': '2000-05-30 03:00',
    'text_array': [
    '96def38c179e4182862a7e5702326323',
    '24dfed2ddad14842b4291c8118355790',
],
    'words': 'jaguar lion',
    'nested': {
    'id': 124,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    [
],
    [
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'panda',
    'bee',
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
    'mixed_type': 0.12422,
    'maybe': 'spider',
    'maybe_null': None,
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
    '30',
    '08',
    '06',
    '08',
    '14',
],
    'text_data': '50c84f1ec8b34bf2be939715bc47a2b6',
    'rand_digit': 9,
    'rand_number': 0.32317,
    'rand_signed_int': -6,
    'rand_datetime': '2000-03-30 03:23:28',
    'text_array': [
    'c9b5474523be4f4f81f38c5d6ab379c0',
    '2e4e962291c14d0ba0cb59287199f4c7',
],
    'words': 'dragonfly cat',
    'nested': {
    'id': 125,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 9,
},
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
    'word': 'rhino',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fish',
    'grasshopper',
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
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': 26,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 126,
    'id_str': [
    '13',
    '07',
],
    'text_data': '7e3d46ccd726474ea52abf529c3be03b',
    'rand_digit': 8,
    'rand_number': 0.48628,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-15',
    'text_array': [
    '376bd6fd25bf41a39aa26485d6ab53ae',
    '06a28641da224aae912b58eac5eb6033',
],
    'words': 'shark mosquito',
    'nested': {
    'id': 126,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 9,
},
],
},
    'nested_array': [
    [
    5,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'tiger',
    'ant',
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
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 127,
    'id_str': [
    '16',
    '20',
    '01',
    '28',
    '12',
],
    'text_data': '386c9df9cf6d4e089efaa59c45656257',
    'rand_digit': 2,
    'rand_number': 0.98366,
    'rand_signed_int': 3,
    'rand_datetime': '2000-02-17T08:26:37.836888-1100',
    'text_array': [
    'f0a1df534ef7440d846a94667eae09d0',
    '5acb6383aedc44bb8ebde0d2b0f44031',
],
    'words': 'ladybug goat',
    'nested': {
    'id': 127,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snail',
    'jaguar',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 28,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 128,
    'id_str': [
    '15',
    '06',
],
    'text_data': 'ffdfef1b7842433f9cd469fa96576eaa',
    'rand_digit': 0,
    'rand_number': 0.25161,
    'rand_signed_int': -7,
    'rand_datetime': '2000-05-28 01:11:31',
    'text_array': [
    '0f5d3851465b40ab9daf82412b74039a',
    'a9a75045d97348d790921bd38c65558e',
],
    'words': 'grasshopper ape',
    'nested': {
    'id': 128,
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
    'word': 'jaguar',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lizard',
    'cow',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'butterfly',
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
    '19',
    '13',
    '05',
    '21',
    '18',
],
    'text_data': '3768d0ffeb3c42d59040146d06fdf2d6',
    'rand_digit': 2,
    'rand_number': 0.42229,
    'rand_signed_int': 9,
    'rand_datetime': '2000-12-04T04:00:07.330274-0300',
    'text_array': [
    '5460d4bef77c4c73a97287c553518d71',
    'c0fca3dc3b454d14a3013b41f7b7c357',
],
    'words': 'grasshopper goat',
    'nested': {
    'id': 129,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'camel',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'gorilla',
    'dolphin',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'bird',
    'maybe': 'snake',
    'maybe_null': None,
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 130,
    'id_str': [
    '03',
    '10',
],
    'text_data': '5189b588bd4946dc969c5d3b1e93266d',
    'rand_digit': 8,
    'rand_number': 0.67425,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-05 09:16:04.665894',
    'text_array': [
    '1abee18ba2704d61b48d7fa203b3bb26',
    '01ec5fbfd116442bb5a749d6c85e61e9',
],
    'words': 'tiger koala',
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
    'word': 'pig',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
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
    'number': 3,
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
    'hello',
],
    'word': 'ladybug',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'sheep',
    'shark',
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
    'mixed_type': 5,
    'maybe': 'ape',
    'maybe_null': 'cat',
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 131,
    'id_str': [
    '24',
    '10',
    '18',
    '14',
],
    'text_data': '679a1c316fa24d5ebdf7e6ff270c9244',
    'rand_digit': 7,
    'rand_number': 0.82151,
    'rand_signed_int': 8,
    'rand_datetime': '2000-12-30T14:58:25.606206',
    'text_array': [
    '9ddeb80c5bba40c3ad838acff2adf18d',
    'e082e4a491a74a2ead8d73a3a17160ac',
],
    'words': 'elephant ladybug',
    'nested': {
    'id': 131,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 5,
},
    {
    'nested_empty': None,
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
    'word': 'panda',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'monkey',
    'grasshopper',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'panda',
},
},
    {
    'id': 32,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 132,
    'id_str': [
    '12',
],
    'text_data': 'cdbeb9ecc21b48f580d61f223b014306',
    'rand_digit': 1,
    'rand_number': 0.70806,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-13 05:32:45+1100',
    'text_array': [
    '1a2c7ecb59d941869a12510e0f0292c9',
    '2f4480847c114df2b9b3063ab4dd3774',
],
    'words': 'fox wolf',
    'nested': {
    'id': 132,
    'rand_digit': 3,
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
    'word': 'gorilla',
    'number': 3,
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
    'word': 'bee',
    'number': 5,
},
],
},
    'nested_array': [
    [
    4,
],
    [
    -8,
],
],
    'two_words': [
    'goat',
    'deer',
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
    'mixed_type': 1,
    'maybe_null': None,
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 133,
    'id_str': [
],
    'text_data': '4089c47e5dcd4bce86a46613e025721a',
    'rand_digit': 0,
    'rand_number': 0.42036,
    'rand_signed_int': -10,
    'rand_datetime': '2000-05-09 13:09:21.240528+0600',
    'text_array': [
    '7735cf0d44454d9a8e30303e46f050d7',
    'c948db8bd28f4d13a14b00650f6d5ca9',
],
    'words': 'chicken rhino',
    'nested': {
    'id': 133,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'camel',
    'ladybug',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 'wolf',
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 134,
    'id_str': [
],
    'text_data': '83959bcc76b34d3ca3e87acc5f3c6343',
    'rand_digit': 7,
    'rand_number': 0.60426,
    'rand_signed_int': 10,
    'rand_datetime': '2000-05-20T05:50:14.975814+0900',
    'text_array': [
    '26df97ec93d7456781316743c30eec0a',
    '46ae9b4de92941bd807b491850982ca8',
],
    'words': 'leopard shark',
    'nested': {
    'id': 134,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'wolf',
    'sheep',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': [
    4,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'ant',
},
},
    {
    'id': 35,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 135,
    'id_str': [
    '29',
    '30',
],
    'text_data': '9aa8066971c140e3bf1ee949bd48bf05',
    'rand_digit': 0,
    'rand_number': 0.38961,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-03T19:40:47.827664',
    'text_array': [
    'c7d062978c9e4ebbbc842c8d5cc4ffd1',
    '4740515001a94063974f7859ef75e039',
],
    'words': 'hippo cow',
    'nested': {
    'id': 135,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -1,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'spider',
    'snail',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': [
    46,
],
    'rand_bool': False,
    'mixed_type': 0.08074,
    'maybe_null': 'elephant',
},
},
    {
    'id': 36,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 136,
    'id_str': [
    '13',
    '22',
    '20',
    '01',
],
    'text_data': 'f134b8e127cb4e689370c69327b5ef17',
    'rand_digit': 3,
    'rand_number': 0.79758,
    'rand_signed_int': 8,
    'rand_datetime': '2000-09-23T20:43:49.621411+0800',
    'text_array': [
    'df34800493134634ad09b66691bd0c89',
    'fb3cf7ba030441abba96ef5e9eade712',
],
    'words': 'panda chicken',
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
    'word': 'hyena',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 3,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'kangaroo',
    'jaguar',
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
    'mixed_type': True,
    'maybe_null': 'wolf',
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
    '25',
    '04',
],
    'text_data': 'f42ef73ec7d64b50a8b2a39e037344eb',
    'rand_digit': 1,
    'rand_number': 0.49955,
    'rand_signed_int': -3,
    'rand_datetime': '2000-07-24 20:22:49+0500',
    'text_array': [
    'ebc8b6a4b05744088cfedd511f9003d1',
    'bf8c431adbd546cfb83c5d694466c11e',
],
    'words': 'ladybug fox',
    'nested': {
    'id': 137,
    'rand_digit': 4,
    'array': [
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
    'hello',
],
    'word': 'sloth',
    'number': 9,
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
    'word': 'lion',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bee',
    'leopard',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'rabbit',
},
},
    {
    'id': 38,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 138,
    'id_str': [
    '01',
    '03',
    '11',
],
    'text_data': 'd299a7ef3e2944bd8cb0d4a614be2040',
    'rand_digit': 2,
    'rand_number': 0.63674,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-12T04:17:33.527090',
    'text_array': [
    '9fbc602b0d2d423ba12c05117b029af9',
    '0d96b3ebc9f245cfa84c05e6ed06df8a',
],
    'words': 'ladybug lion',
    'nested': {
    'id': 138,
    'rand_digit': 6,
    'array': [
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
    'word': 'elephant',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'pig',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -8,
],
],
    'two_words': [
    'rabbit',
    'dragonfly',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'fly',
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 139,
    'id_str': [
    '22',
],
    'text_data': '42fed10791ef4f78a89bf3723deb116a',
    'rand_digit': 0,
    'rand_number': 0.72011,
    'rand_signed_int': 9,
    'rand_datetime': '2000-08-29 22:07:01',
    'text_array': [
    '7f71d7e467ac4b1b91415b3dc14ef256',
    '3920e79d06184e2aba6ecb950c82b56c',
],
    'words': 'sloth bird',
    'nested': {
    'id': 139,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 10,
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
    3,
],
],
    'two_words': [
    'horse',
    'rhino',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'chicken',
    'maybe': 'hyena',
    'maybe_null': None,
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 140,
    'id_str': [
    '17',
],
    'text_data': '0d2e59c7e19c44bd8d5441bc6131d186',
    'rand_digit': 0,
    'rand_number': 0.27439,
    'rand_signed_int': -10,
    'rand_datetime': '2000-04-07',
    'text_array': [
    '51f0c898ca8c445eb70b795cfeecd5d4',
    'f70ee5014e6a443ebf263ce94987b5f9',
],
    'words': 'leopard ant',
    'nested': {
    'id': 140,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'ladybug',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dolphin',
    'kangaroo',
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
    'mixed_type': False,
    'maybe_null': 'sloth',
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 141,
    'id_str': [
    '02',
    '09',
    '06',
],
    'text_data': '82c1eded97824155b57789a709be1daa',
    'rand_digit': 1,
    'rand_number': 0.14424,
    'rand_signed_int': 3,
    'rand_datetime': '2000-07-21',
    'text_array': [
    '93d8c7e9ca3e49f9b41db16c49a23f83',
    '8f28329012ce466fbb14701e9512b05e',
],
    'words': 'zebra chicken',
    'nested': {
    'id': 141,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'lizard',
    'ladybug',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'ant',
    'maybe_null': 'mosquito',
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 142,
    'id_str': [
    '26',
],
    'text_data': '3c6fcc1dd0c04dac8bbf0c56a87dbd49',
    'rand_digit': 0,
    'rand_number': 0.15467,
    'rand_signed_int': 2,
    'rand_datetime': '2000-04-20T19:43:00.043986-06:00',
    'text_array': [
    '10747167e7ff4a3f98d78edb61caf44c',
    'c83b3293f680488dacc219e055e79ddb',
],
    'words': 'frog sloth',
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
    'word': 'giraffe',
    'number': 10,
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
    'word': 'rabbit',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 7,
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
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'rhino',
    'zebra',
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
    'mixed_type': 5,
    'maybe_null': None,
},
},
    {
    'id': 43,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 143,
    'id_str': [
    '01',
    '09',
],
    'text_data': '521c302d23f24f3da12e259516e5a317',
    'rand_digit': 4,
    'rand_number': 0.59389,
    'rand_signed_int': 7,
    'rand_datetime': '2000-10-12T01:33:13+1000',
    'text_array': [
    '76861a7f33254002a3648d9f0ad450d6',
    '634be98bdad14df2b9cdea7ea4c744be',
],
    'words': 'chicken spider',
    'nested': {
    'id': 143,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    10,
],
],
    'two_words': [
    'bee',
    'grasshopper',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': [
    97,
],
    'rand_bool': False,
    'mixed_type': 0.02136,
    'maybe': 'dolphin',
    'maybe_null': 'elephant',
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 144,
    'id_str': [
    '16',
    '24',
    '21',
],
    'text_data': 'ab9cbe4cc0f4481a887616d72920bd31',
    'rand_digit': 5,
    'rand_number': 0.12805,
    'rand_signed_int': -4,
    'rand_datetime': '2000-05-20 04:42:43+0600',
    'text_array': [
    'a9309cb63f55489499fb1ad163a0eee6',
    '02ce499ad599438a980fcf364f1e8b8e',
],
    'words': 'crab turtle',
    'nested': {
    'id': 144,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 5,
},
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
    'word': 'horse',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'chicken',
    'fish',
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
    'mixed_type': None,
    'maybe': 'shark',
    'maybe_null': 'mouse',
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 145,
    'id_str': [
    '04',
    '23',
],
    'text_data': 'b4a1ad13cb634a5d8b9be7696922ecb6',
    'rand_digit': 2,
    'rand_number': 0.89364,
    'rand_signed_int': 4,
    'rand_datetime': '2000-06-21T14:06:55.164084',
    'text_array': [
    '1a09a8d6bdfe49b6b045c3958e8e0e4e',
    '2b0f21337e81489c8e4563c581ab81e5',
],
    'words': 'rhino bird',
    'nested': {
    'id': 145,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'zebra',
    'rabbit',
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
    'mixed_type': None,
    'maybe_null': 'zebra',
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
    '21',
],
    'text_data': 'a98b44dd10704d0d8e0cfc803d5ed24b',
    'rand_digit': 0,
    'rand_number': 0.40227,
    'rand_signed_int': 8,
    'rand_datetime': '2000-07-30T20:40:43.503818',
    'text_array': [
    '791ccb72b9e043d2b32bda3ddf1d4b6a',
    '3cfb38c81ac7442da33d26d70b632a4f',
],
    'words': 'turtle dragonfly',
    'nested': {
    'id': 146,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'ant',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 3,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -4,
],
    [
],
],
    'two_words': [
    'sloth',
    'lizard',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'giraffe',
},
},
    {
    'id': 47,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 147,
    'id_str': [
    '25',
    '17',
],
    'text_data': '752acef2916046f3991078c8728230cb',
    'rand_digit': 6,
    'rand_number': 0.77228,
    'rand_signed_int': 9,
    'rand_datetime': '2001-01-26 13:55:39',
    'text_array': [
    'e64634f713f44e4483cff17c59056118',
    'b741692b62924d19b06d70f9082f21ce',
],
    'words': 'cow spider',
    'nested': {
    'id': 147,
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
    'word': 'hyena',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'panda',
    'ladybug',
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
    'maybe_null': None,
},
},
    {
    'id': 48,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 148,
    'id_str': [
    '23',
    '07',
],
    'text_data': 'd77e64366fba4106a8eff0705e69a9f4',
    'rand_digit': 3,
    'rand_number': 0.99385,
    'rand_signed_int': 8,
    'rand_datetime': '2000-07-10 22:45:21.027721',
    'text_array': [
    '9afd0ec2ff5540878e0b375eacc965b7',
    'c9076a3e70394f52a4c238ae3825bcc4',
],
    'words': 'lobster koala',
    'nested': {
    'id': 148,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'shark',
    'number': 7,
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
    'word': 'bear',
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
    'chicken',
    'kangaroo',
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
    'mixed_type': 0.68267,
    'maybe': 'butterfly',
    'maybe_null': 'bird',
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 149,
    'id_str': [
    '02',
    '09',
    '03',
    '24',
],
    'text_data': '5aabc01ff5bc436392aeec2f272f6f7a',
    'rand_digit': 3,
    'rand_number': 0.9833,
    'rand_signed_int': -3,
    'rand_datetime': '2000-12-13 22:16:13+0600',
    'text_array': [
    '7efcb87c1b9546fe89e97d68a20249a6',
    'e90137a5c8714628a321c9284ff62ae3',
],
    'words': 'koala cow',
    'nested': {
    'id': 149,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    8,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'wolf',
    'snail',
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
    'mixed_type': 0.06208,
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
    'content-length': '122',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'discover': {
    'target': 10,
    'context': [
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_multivector_discovery_queries.test_only_target')
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
    test = TestMultivectorDiscoveryQueriestestOnlyTarget()
    test.run_tests()
