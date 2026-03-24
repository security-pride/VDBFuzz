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
logger = logging.getLogger('vdb_fuzzer.test.test_multivector_search_queries_test_simple')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_multivector_search_queries.test_simple"
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



class TestMultivectorSearchQueriestestSimple:
    """自动生成的VDB模糊测试类 - test_multivector_search_queries.test_simple"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_multivector_search_queries.test_simple"
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
    'content-length': '562336',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 100,
    'id_str': [
    '02',
    '13',
],
    'text_data': 'd962465e077b4862a73e0d697d378dae',
    'rand_digit': 2,
    'rand_number': 0.47063,
    'rand_signed_int': 10,
    'rand_datetime': '2000-11-14T04:28:57.030652',
    'text_array': [
    'edd0d4651a7f43c28abe5b46f0042965',
    'af7a5b1b8e0b45b4a04b38adb48f90e2',
],
    'words': 'lizard fly',
    'nested': {
    'id': 100,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'crab',
    'duck',
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
    'mixed_type': None,
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 101,
    'id_str': [
],
    'text_data': '32c6d9a633a5494f90346c8af7fd5ed8',
    'rand_digit': 0,
    'rand_number': 0.17754,
    'rand_signed_int': 0,
    'rand_datetime': '2000-05-04',
    'text_array': [
    '34cdd1668eca4d458b8feab85a113850',
    'c64768cb8101472abf13ebb1efae8b8b',
],
    'words': 'hippo wolf',
    'nested': {
    'id': 101,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lion',
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
    'nested_array': [
    [
    -3,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'gorilla',
    'rabbit',
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
    'maybe': 'cheetah',
},
},
    {
    'id': 2,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 102,
    'id_str': [
    '27',
    '07',
    '02',
    '29',
],
    'text_data': 'd9e03d22947a409c86b701d0adbbca58',
    'rand_digit': 5,
    'rand_number': 0.74531,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-16T18:23:47.361348',
    'text_array': [
    '9afe49c1b2c04efb8b0a42ea5c5cb01e',
    'f6921f2b32864b44be670805e3c82acf',
],
    'words': 'cat lizard',
    'nested': {
    'id': 102,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 7,
},
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
],
    'word': 'octopus',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'chicken',
    'dog',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 103,
    'id_str': [
    '03',
],
    'text_data': '2ec3b98f5de64b149d797eb03e5be794',
    'rand_digit': 2,
    'rand_number': 0.21692,
    'rand_signed_int': 6,
    'rand_datetime': '2000-11-29T17:48:32.924854-0600',
    'text_array': [
    '4b3ca4d7c6384c8a8d0ce6eb0969fd38',
    'e62b74bdc31e48d3a307ec8a6efac105',
],
    'words': 'rabbit rabbit',
    'nested': {
    'id': 103,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
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
    'giraffe',
    'bear',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': [
    1,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 104,
    'id_str': [
    '18',
    '18',
],
    'text_data': '1fb79cdeb6ab44ce944b8e127026b3d7',
    'rand_digit': 0,
    'rand_number': 0.20873,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-28 17:54:29+0500',
    'text_array': [
    'b99c09dc5a3a416f9e7c0a1a939535b2',
    '36b6e92d6ad84fd1a3a0b88f3a35106c',
],
    'words': 'hyena duck',
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
    'word': 'rabbit',
    'number': 3,
},
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
    'word': 'crab',
    'number': 7,
},
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    8,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'snake',
    'cat',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'shark',
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 105,
    'id_str': [
    '09',
    '10',
],
    'text_data': '656603ba8b9344fc84cfe4149d3922ba',
    'rand_digit': 6,
    'rand_number': 0.80929,
    'rand_signed_int': -7,
    'rand_datetime': '2000-11-12T18:23:12',
    'text_array': [
    '9e8a5175f6e54341a96826c42d776c4f',
    '88f278269eee4cd2939c1fb282711e05',
],
    'words': 'hyena koala',
    'nested': {
    'id': 105,
    'rand_digit': 0,
    'array': [
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
],
    'word': 'snake',
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
    'chicken',
    'shark',
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
    'mixed_type': 0.63954,
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 106,
    'id_str': [
    '02',
    '20',
    '21',
    '17',
],
    'text_data': 'd5a5c7bc070d4c8b822db9c60582a8e0',
    'rand_digit': 6,
    'rand_number': 0.99584,
    'rand_signed_int': 5,
    'rand_datetime': '2000-08-08 21:53:12',
    'text_array': [
    '48a5300b84944403b855e36a3d910dab',
    'ad94df27bf2644f3b048ce2221cd3859',
],
    'words': 'snail sloth',
    'nested': {
    'id': 106,
    'rand_digit': 9,
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
    'hello',
],
    'word': 'lobster',
    'number': 9,
},
    {
    'nested_empty': None,
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
    'word': 'horse',
    'number': 1,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'leopard',
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
    'mixed_type': True,
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 107,
    'id_str': [
    '19',
],
    'text_data': '333ccf93ff8949098fde9c83f8eeb792',
    'rand_digit': 2,
    'rand_number': 0.08633,
    'rand_signed_int': -8,
    'rand_datetime': '2000-09-22T10:47:16.700364',
    'text_array': [
    '5e250c8d1f0247feb7c243ba5681f98d',
    '052d33dffe914b509d5cb9c842fd475f',
],
    'words': 'snail mosquito',
    'nested': {
    'id': 107,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'kangaroo',
    'rabbit',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.52118,
    'maybe': 'whale',
    'maybe_null': None,
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 108,
    'id_str': [
    '28',
    '02',
],
    'text_data': 'e01806e61a674919b67bd6b454d8ffe1',
    'rand_digit': 0,
    'rand_number': 0.88973,
    'rand_signed_int': 8,
    'rand_datetime': '2000-09-17T11:56:50-0300',
    'text_array': [
    '4041b2fe66e44c51b92a386c6f4b50af',
    'f26d221c70e942e5988552ec0850c50f',
],
    'words': 'octopus fish',
    'nested': {
    'id': 108,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'dragonfly',
    'panda',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'snake',
    'maybe_null': 'koala',
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 109,
    'id_str': [
    '15',
    '19',
    '07',
    '18',
],
    'text_data': '2de57d8a84e84bc3918101711c8c0301',
    'rand_digit': 7,
    'rand_number': 0.03442,
    'rand_signed_int': -6,
    'rand_datetime': '2000-06-25T06:27:33.449157+0200',
    'text_array': [
    '9ebd8d146a5943e8a105a109869c68be',
    '5912c39d7cb646508d95099fc0202544',
],
    'words': 'goat hippo',
    'nested': {
    'id': 109,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 2,
},
    {
    'nested_empty': None,
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
    'word': 'cat',
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'bee',
    'ant',
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
    'maybe_null': 'giraffe',
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 110,
    'id_str': [
    '16',
    '04',
],
    'text_data': '06ea43f50861472aa2ecde302166c43e',
    'rand_digit': 3,
    'rand_number': 0.69842,
    'rand_signed_int': -1,
    'rand_datetime': '2000-06-22 12:21',
    'text_array': [
    '834b563dfa1444228b2c1ea71e2d5806',
    '9b788c5c29724d9c8ba56fb37cd7f980',
],
    'words': 'dolphin camel',
    'nested': {
    'id': 110,
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
],
    'two_words': [
    'octopus',
    'sloth',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': [
    90,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'duck',
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 111,
    'id_str': [
    '07',
],
    'text_data': '12a8d97b82c04e41a0b48c5ca68264c7',
    'rand_digit': 7,
    'rand_number': 0.15784,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-17 11:53:40',
    'text_array': [
    '1028b4be6cfc46e9bb2d93a539b218aa',
    '5c12b897f0434a08a4dfc850ba1e6b4a',
],
    'words': 'sheep monkey',
    'nested': {
    'id': 111,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'spider',
    'lion',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'camel',
    'maybe_null': None,
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 112,
    'id_str': [
    '23',
],
    'text_data': 'c1dd9e5fbb8944048aabd89a440087b1',
    'rand_digit': 8,
    'rand_number': 0.13853,
    'rand_signed_int': -7,
    'rand_datetime': '2000-05-27 15:34:43.370998',
    'text_array': [
    'b32a133c5783424bbb17dd0fb8bc44e1',
    '6e6f1568f3f547cd98cbf37cc9e9c468',
],
    'words': 'ladybug spider',
    'nested': {
    'id': 112,
    'rand_digit': 3,
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
    'word': 'squid',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
],
    'two_words': [
    'chicken',
    'leopard',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 113,
    'id_str': [
],
    'text_data': '9f12ac3ea961430295fb91fad8392ed3',
    'rand_digit': 7,
    'rand_number': 0.31793,
    'rand_signed_int': 9,
    'rand_datetime': '2000-12-27 12:09:24',
    'text_array': [
    'e6bee09275ed44d08586b2ac961baf4d',
    '08e594c6f2d0410db1df08e625a5c55f',
],
    'words': 'dragonfly squid',
    'nested': {
    'id': 113,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dog',
    'snake',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': [
    77,
],
    'rand_bool': False,
    'mixed_type': 'dolphin',
    'maybe': 'snail',
    'maybe_null': None,
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 114,
    'id_str': [
    '27',
],
    'text_data': '021781a0c1a148efb2ff55792429b623',
    'rand_digit': 7,
    'rand_number': 0.31784,
    'rand_signed_int': -7,
    'rand_datetime': '2001-01-16T13:57:27.261259',
    'text_array': [
    '0fd843fb13034e77b18a81cc6f8451ff',
    '63d60235af3f41a29f07b8707469679f',
],
    'words': 'whale grasshopper',
    'nested': {
    'id': 114,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'spider',
    'gorilla',
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
    'mixed_type': 'rabbit',
    'maybe_null': None,
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 115,
    'id_str': [
    '25',
],
    'text_data': '32ab2bb129b04990bff6f93b9fcaec37',
    'rand_digit': 9,
    'rand_number': 0.4744,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-18 00:31',
    'text_array': [
    '87ff05d20d3246c491488e3278171f15',
    '3201b9d08cac4aac8fd0a17a2a161f1c',
],
    'words': 'ant scorpion',
    'nested': {
    'id': 115,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    [
    7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    4,
],
],
    'two_words': [
    'deer',
    'leopard',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 116,
    'id_str': [
    '24',
],
    'text_data': 'f61cad70171b4dcc8e1863233665806d',
    'rand_digit': 1,
    'rand_number': 0.48123,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-19T15:06:28.158404',
    'text_array': [
    '26e6da7d878c467781f68c6414586949',
    '957ff6628fb84d0593ef5aee0befe00f',
],
    'words': 'dolphin giraffe',
    'nested': {
    'id': 116,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dragonfly',
    'grasshopper',
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
    'maybe_null': 'mosquito',
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 117,
    'id_str': [
    '13',
    '08',
    '25',
],
    'text_data': 'a88909d70fbc4292a85b4624fd45e7ad',
    'rand_digit': 8,
    'rand_number': 0.80384,
    'rand_signed_int': 2,
    'rand_datetime': '2000-02-07T23:51:47.052908-08:00',
    'text_array': [
    '7f764746c2b44df4b5d25606ea73b4cd',
    'e582372c1e7c4f62ada766477662134b',
],
    'words': 'mouse turtle',
    'nested': {
    'id': 117,
    'rand_digit': 3,
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
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'pig',
    'octopus',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'wolf',
},
},
    {
    'id': 18,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 118,
    'id_str': [
],
    'text_data': 'ddae3fbec00f49628ee0897518c36a60',
    'rand_digit': 0,
    'rand_number': 0.14598,
    'rand_signed_int': -10,
    'rand_datetime': '2000-07-13T00:57:05.721773-0300',
    'text_array': [
    '24ae31162a6a4484a1dcf25ead3d9ab4',
    '6fcbee078b9642e9b7c4911774b88138',
],
    'words': 'lizard lion',
    'nested': {
    'id': 118,
    'rand_digit': 0,
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
    'hello',
],
    'word': 'wolf',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'grasshopper',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'duck',
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
    '16',
    '25',
    '04',
    '05',
    '25',
],
    'text_data': '48613b4f806f4865a1e866701642d43b',
    'rand_digit': 1,
    'rand_number': 0.63189,
    'rand_signed_int': 6,
    'rand_datetime': '2000-11-26T12:44:18.815519',
    'text_array': [
    '59fd41a00a974b89a4068e8fae02b7dd',
    '670add27724f4c3f957b67b0a22a4858',
],
    'words': 'scorpion crab',
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
    'word': 'rabbit',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'zebra',
    'sheep',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': [
    50,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'deer',
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 120,
    'id_str': [
    '15',
    '10',
    '24',
],
    'text_data': '899ab5c6d8c646bb8dd222d2784b5cdc',
    'rand_digit': 5,
    'rand_number': 0.58206,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-26T12:52:06.901306',
    'text_array': [
    '0493b38c43bd42f2b2713b1bdad6ab42',
    '10a929333c404c3599fe8708dec246d1',
],
    'words': 'duck monkey',
    'nested': {
    'id': 120,
    'rand_digit': 6,
    'array': [
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
    'word': 'cat',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'scorpion',
    'crab',
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
    'mixed_type': 3,
    'maybe': 'rhino',
    'maybe_null': 'duck',
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 121,
    'id_str': [
    '19',
],
    'text_data': '686f902121e14c4aaa89893c7c1b7e10',
    'rand_digit': 7,
    'rand_number': 0.46898,
    'rand_signed_int': 3,
    'rand_datetime': '2000-02-09 18:01:13+0400',
    'text_array': [
    '7a2c5b3649384c3ca84448ced34c63f6',
    'fef4de7c723644d49afdc1e90e092134',
],
    'words': 'scorpion rabbit',
    'nested': {
    'id': 121,
    'rand_digit': 3,
    'array': [
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
],
    'two_words': [
    'bee',
    'snake',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'jaguar',
    'maybe_null': 'butterfly',
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
    '03',
    '19',
    '17',
    '30',
],
    'text_data': '3c51dac563614ed78ae9be95b991665c',
    'rand_digit': 2,
    'rand_number': 0.32587,
    'rand_signed_int': 1,
    'rand_datetime': '2000-03-02 09:38:53+0600',
    'text_array': [
    'e3532685310a47bfac65ceebf5c3b3b9',
    'be1e1e2fb8c34080ad4e9e48b45fd0bf',
],
    'words': 'camel giraffe',
    'nested': {
    'id': 122,
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
    'word': 'camel',
    'number': 8,
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
    'word': 'dog',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'whale',
    'hyena',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': [
    83,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 123,
    'id_str': [
    '05',
    '10',
    '30',
    '21',
],
    'text_data': 'e4440360226c4ce680ce0490f4553b56',
    'rand_digit': 4,
    'rand_number': 0.49526,
    'rand_signed_int': -1,
    'rand_datetime': '2000-12-07 00:39:39.193694+0200',
    'text_array': [
    'a76d9dd46ec24b5ea0993e45987f4f6d',
    'f2670bc7d4274cd0a64ae60d9e2ebb90',
],
    'words': 'lobster gorilla',
    'nested': {
    'id': 123,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
    9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'lizard',
    'elephant',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': [
    76,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'wolf',
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 124,
    'id_str': [
    '11',
    '03',
    '18',
    '23',
    '30',
],
    'text_data': '05a778b56f1b4e7eb47b193b139ac041',
    'rand_digit': 1,
    'rand_number': 0.06124,
    'rand_signed_int': 2,
    'rand_datetime': '2000-11-21T11:46:47',
    'text_array': [
    '9b7aa5f45ce6477ab4b246953f7335da',
    'b62b0e95c4d24f6286b6d0d05574d217',
],
    'words': 'frog grasshopper',
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
    'word': 'giraffe',
    'number': 3,
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
    'hello',
],
    'word': 'cheetah',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -1,
],
],
    'two_words': [
    'cow',
    'bee',
],
    'city': {
    'name': 'Zurich',
    'geo': {
    'lat': 47.376887,
    'lon': 8.541694,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'hyena',
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
    '09',
    '15',
    '11',
    '10',
],
    'text_data': 'b915ba6976c24adca58bdd168b900034',
    'rand_digit': 8,
    'rand_number': 0.23863,
    'rand_signed_int': 8,
    'rand_datetime': '2000-06-22T23:35:12.516781+0000',
    'text_array': [
    'bd1c6967c8024e3b874587b10b2c4f07',
    'f29c1fa68a4740e7a007988ebdeefcc9',
],
    'words': 'crab mouse',
    'nested': {
    'id': 125,
    'rand_digit': 9,
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
    'hello',
],
    'word': 'dog',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
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
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
    4,
],
],
    'two_words': [
    'wolf',
    'tiger',
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
    'mixed_type': 6,
    'maybe': 'cheetah',
    'maybe_null': None,
},
},
    {
    'id': 26,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 126,
    'id_str': [
],
    'text_data': '7904614de2774e0994bf67375da6ae17',
    'rand_digit': 0,
    'rand_number': 0.55196,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-12',
    'text_array': [
    '609d119a416341298efe4005b1826ba0',
    '8e98ca6dc36445968ac20b71f5a1558c',
],
    'words': 'spider kangaroo',
    'nested': {
    'id': 126,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ape',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    3,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'leopard',
    'hippo',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'koala',
    'maybe_null': 'monkey',
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 127,
    'id_str': [
    '06',
    '28',
    '08',
],
    'text_data': '9013a577de2e4df9b27d9bdaca09dbb4',
    'rand_digit': 7,
    'rand_number': 0.72787,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-03T14:29:05.338148-0300',
    'text_array': [
    'f5a7df5da3484196bea7a2efd37ef0db',
    '0c55360f6a40454aa2d3910b52ebec1d',
],
    'words': 'cat cow',
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
    'word': 'hippo',
    'number': 2,
},
],
},
    'nested_array': [
    [
    -2,
],
    [
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'chicken',
    'octopus',
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
    'maybe_null': None,
},
},
    {
    'id': 28,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 128,
    'id_str': [
    '21',
    '29',
],
    'text_data': '2195ab08302e44dfb7237b11049992cd',
    'rand_digit': 0,
    'rand_number': 0.10776,
    'rand_signed_int': 7,
    'rand_datetime': '2000-11-28 04:04:34.312952+0900',
    'text_array': [
    'dc6b04c82bc34a77957029b1b4a5bc4a',
    '52dacf9d05104d8d93cc981d1e9cc614',
],
    'words': 'dog jaguar',
    'nested': {
    'id': 128,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 7,
},
    {
    'nested_empty': None,
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
    'word': 'ladybug',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -2,
],
    [
    -4,
],
],
    'two_words': [
    'bird',
    'sheep',
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
    'maybe': 'lizard',
    'maybe_null': 'frog',
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
    '13',
],
    'text_data': '9285b4d513844aa0ad51470ffd5ce8f7',
    'rand_digit': 8,
    'rand_number': 0.27635,
    'rand_signed_int': 3,
    'rand_datetime': '2000-07-22 03:04:39.438655-0900',
    'text_array': [
    '8ffc6f1bbabf46d989b6fb615df48434',
    'e0c05da48b314127897599023ce94336',
],
    'words': 'giraffe gorilla',
    'nested': {
    'id': 129,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'duck',
    'pig',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 9,
    'maybe_null': None,
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 130,
    'id_str': [
    '05',
    '15',
    '29',
    '26',
],
    'text_data': '5e4c191abdea46959c5a6cf05eefbaec',
    'rand_digit': 6,
    'rand_number': 0.2147,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-24',
    'text_array': [
    '0816706be3ac44ffaccf42564c9a561c',
    'c6557fd8670c4472bcb43238da447228',
],
    'words': 'dragonfly pig',
    'nested': {
    'id': 130,
    'rand_digit': 5,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 4,
},
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'rabbit',
    'lizard',
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
    'mixed_type': 2,
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 131,
    'id_str': [
    '01',
    '30',
    '18',
    '04',
    '26',
],
    'text_data': '97ef9628070a4b64ab977e4073317629',
    'rand_digit': 5,
    'rand_number': 0.44616,
    'rand_signed_int': -4,
    'rand_datetime': '2000-12-21T15:04:24.202889',
    'text_array': [
    'b2236944d30c4721a5d7ebf5da1a640c',
    '3fa9ac2fd5b5490492c8b86767e56b5f',
],
    'words': 'elephant squid',
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
    'word': 'cheetah',
    'number': 9,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fish',
    'horse',
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
    'mixed_type': None,
    'maybe': 'fox',
},
},
    {
    'id': 32,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 132,
    'id_str': [
    '26',
    '29',
    '07',
],
    'text_data': 'ef7f807ff0ba4ca185abb27fff510f3d',
    'rand_digit': 4,
    'rand_number': 0.55826,
    'rand_signed_int': -10,
    'rand_datetime': '2000-06-08 04:09:33.107903',
    'text_array': [
    '5231dba0c5e648b3b3f7de123b47dfa6',
    '871a9f415ea647d597c05a3f6136c7fc',
],
    'words': 'crab lobster',
    'nested': {
    'id': 132,
    'rand_digit': 3,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 2,
},
],
},
    'nested_array': [
    [
    0,
],
    [
],
    [
],
],
    'two_words': [
    'fish',
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
    59,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 133,
    'id_str': [
    '08',
    '09',
],
    'text_data': '7643acd506294e318a779621b3d0999d',
    'rand_digit': 4,
    'rand_number': 0.46197,
    'rand_signed_int': -7,
    'rand_datetime': '2000-09-02 12:01:11+0200',
    'text_array': [
    'd64cfab78af84a1882559d73c693d670',
    'ddb30d44d2fa4be189646cb7aace5210',
],
    'words': 'sloth octopus',
    'nested': {
    'id': 133,
    'rand_digit': 8,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'horse',
    'squid',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.50361,
    'maybe_null': None,
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 134,
    'id_str': [
    '16',
],
    'text_data': '764465cce9b5492e9a50eb19d74c14c1',
    'rand_digit': 6,
    'rand_number': 0.50131,
    'rand_signed_int': -6,
    'rand_datetime': '2000-12-10 06:21:20.525082-0900',
    'text_array': [
    '49efc84b56b64fb889483a6c4414ced3',
    '4f3b8fa96e314aed8ccaef17cb1e98f3',
],
    'words': 'horse mouse',
    'nested': {
    'id': 134,
    'rand_digit': 6,
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cow',
    'ladybug',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'fox',
},
},
    {
    'id': 35,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 135,
    'id_str': [
],
    'text_data': '08e7ca4779df4f359e29b0e29105e1cd',
    'rand_digit': 9,
    'rand_number': 0.93061,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-26',
    'text_array': [
    'aee5404f16e04fb3abdb1419a5983567',
    '30866378e059486a933c9e8871bec0c5',
],
    'words': 'hyena rabbit',
    'nested': {
    'id': 135,
    'rand_digit': 9,
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
    'nested_empty': None,
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
    'word': 'rabbit',
    'number': 8,
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
    -8,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'cat',
    'spider',
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
},
},
    {
    'id': 36,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 136,
    'id_str': [
    '06',
    '12',
    '23',
    '07',
],
    'text_data': 'd5932ba528f2477d93ae1c3f6dd3340d',
    'rand_digit': 2,
    'rand_number': 0.53567,
    'rand_signed_int': 1,
    'rand_datetime': '2000-12-23T20:24:56.097397',
    'text_array': [
    '4159fde251df4d50b6b9967355d58e7f',
    '1e7bb609b99d47b7b78357b21e83af32',
],
    'words': 'scorpion dog',
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
    'word': 'crab',
    'number': 6,
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
    'hello',
],
    'word': 'monkey',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'shark',
    'goat',
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
    'mixed_type': 0.67427,
    'maybe': 'ant',
    'maybe_null': None,
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
    '23',
],
    'text_data': '5240b542ebdb40dc841e6c1002e3cf16',
    'rand_digit': 2,
    'rand_number': 0.95313,
    'rand_signed_int': -8,
    'rand_datetime': '2000-01-26T10:30:44.252834',
    'text_array': [
    '839d6ff020ae4101bdbc6dc4aedb7ee7',
    'c852243cc9bf44a0a3d646cf620f44ea',
],
    'words': 'whale lobster',
    'nested': {
    'id': 137,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 3,
},
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
    'word': 'fly',
    'number': 4,
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
    'butterfly',
    'octopus',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': [
    38,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'ladybug',
},
},
    {
    'id': 38,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 138,
    'id_str': [
    '14',
],
    'text_data': 'e4ba5404753543719c09757d3e73416a',
    'rand_digit': 7,
    'rand_number': 0.04549,
    'rand_signed_int': -2,
    'rand_datetime': '2000-04-01 00:33:11.130262-1200',
    'text_array': [
    '8cb5d8adafbf4cf48e3a1fb0dd50c018',
    '66ae04db2b0d4ad79b53be0558caa0cc',
],
    'words': 'rabbit hippo',
    'nested': {
    'id': 138,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 1,
},
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
],
},
    'nested_array': [
    [
    -6,
],
    [
    3,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
    -2,
],
],
    'two_words': [
    'cheetah',
    'dolphin',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': [
    64,
],
    'rand_bool': False,
    'mixed_type': 0.03044,
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 139,
    'id_str': [
    '10',
    '23',
    '03',
    '18',
],
    'text_data': 'b7a3efd4514345b5841151badcbd949b',
    'rand_digit': 9,
    'rand_number': 0.64046,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-04 12:05:24',
    'text_array': [
    '6aef340ad0c04f28811f47e6a5ddf8ad',
    '2e5da2a60e7743009096188aba923874',
],
    'words': 'duck fish',
    'nested': {
    'id': 139,
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
    'hello',
],
    'word': 'mouse',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'lion',
    'pig',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'grasshopper',
    'maybe_null': 'rabbit',
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 140,
    'id_str': [
    '06',
],
    'text_data': '00265778fcbf46d1b5e7b4d2344b364d',
    'rand_digit': 4,
    'rand_number': 0.99871,
    'rand_signed_int': 2,
    'rand_datetime': '2000-03-28 09:49:38-0200',
    'text_array': [
    '3a31dbd7cf78466090afe5614e8de671',
    'ddfba439c1e64a919640911601237504',
],
    'words': 'kangaroo camel',
    'nested': {
    'id': 140,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'scorpion',
    'number': 3,
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
    'word': 'tiger',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'deer',
    'snail',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 9,
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 141,
    'id_str': [
    '06',
    '18',
    '15',
],
    'text_data': 'b63f1fae7165496ea86834e27a10fb59',
    'rand_digit': 6,
    'rand_number': 0.72785,
    'rand_signed_int': 9,
    'rand_datetime': '2000-06-30T03:26:43.943292',
    'text_array': [
    '1e73ae17d05c4e8aa536622a8ded8f25',
    '42a93efd0bcc47a28ff5b631a3dbcb74',
],
    'words': 'octopus turtle',
    'nested': {
    'id': 141,
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
    'number': 9,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'spider',
    'squid',
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
    'maybe_null': 'dog',
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 142,
    'id_str': [
    '14',
    '27',
    '21',
],
    'text_data': '01180c55810e470f80b81d2ab0d192a7',
    'rand_digit': 2,
    'rand_number': 0.99609,
    'rand_signed_int': 10,
    'rand_datetime': '2000-07-10T08:50:54.312742+07:00',
    'text_array': [
    '389f1eb41ed04257a87f06bc9dafe77a',
    'fe489d4fa15c48fdbf9e71b73c561e1d',
],
    'words': 'deer cow',
    'nested': {
    'id': 142,
    'rand_digit': 5,
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
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'fish',
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
    'mixed_type': None,
    'maybe': 'jaguar',
    'maybe_null': 'hyena',
},
},
    {
    'id': 43,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 143,
    'id_str': [
],
    'text_data': '3ec13e634360443a8d46f018b83ffdab',
    'rand_digit': 1,
    'rand_number': 0.16633,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-29 14:40:44',
    'text_array': [
    '5941853fd6a24b86a21aaeb5f67fcb22',
    '1cc43b8976674b82953e1586442c963f',
],
    'words': 'zebra hyena',
    'nested': {
    'id': 143,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'ant',
    'crab',
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
    'mixed_type': None,
    'maybe': 'snake',
    'maybe_null': 'jaguar',
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 144,
    'id_str': [
],
    'text_data': 'ae197dd5921d4daf94f34c16c7dd2efb',
    'rand_digit': 9,
    'rand_number': 0.93257,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-14 18:50:09.708703-0700',
    'text_array': [
    '97125f90e00641b2a70fd08baf73e89f',
    '422f91189f4a48e7a164fc7eed497f92',
],
    'words': 'pig pig',
    'nested': {
    'id': 144,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 6,
},
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
    'hello',
],
    'word': 'giraffe',
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
],
    'two_words': [
    'duck',
    'octopus',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': [
    3,
],
    'rand_bool': True,
    'mixed_type': 0.7686,
    'maybe_null': 'bee',
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 145,
    'id_str': [
    '03',
    '28',
    '04',
],
    'text_data': '662fb1b716854f2e89f58c117e951259',
    'rand_digit': 5,
    'rand_number': 0.42072,
    'rand_signed_int': -2,
    'rand_datetime': '2000-10-25T22:04:56+1200',
    'text_array': [
    '2995e1ba40ba422fb6640f1c97fb68b8',
    '9ab58bb76b1846c696a14f63bd6503c9',
],
    'words': 'dog butterfly',
    'nested': {
    'id': 145,
    'rand_digit': 7,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
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
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cheetah',
    'fly',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
],
    'text_data': '2df775c93eb640bb8f0c9852089c3104',
    'rand_digit': 5,
    'rand_number': 0.71159,
    'rand_signed_int': -6,
    'rand_datetime': '2000-03-19 01:01:20',
    'text_array': [
    'de36a21a3b6f4e308aaa0b4282b17109',
    'a638c8875fc1446eaf28a87074e67922',
],
    'words': 'sloth hyena',
    'nested': {
    'id': 146,
    'rand_digit': 0,
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
],
},
    'nested_array': [
],
    'two_words': [
    'horse',
    'whale',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'wolf',
    'maybe_null': 'lizard',
},
},
    {
    'id': 47,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 147,
    'id_str': [
    '05',
],
    'text_data': '53637e2afd2642eb931a7eb4f0d0b271',
    'rand_digit': 9,
    'rand_number': 0.09433,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-09T08:25:49',
    'text_array': [
    'b54272deb22a494ca356ad58d7b625e2',
    'e15a6e2196484a84a973cedf56b838d7',
],
    'words': 'grasshopper ape',
    'nested': {
    'id': 147,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
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
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
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
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'spider',
},
},
    {
    'id': 48,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 148,
    'id_str': [
    '05',
],
    'text_data': '0bcf7324ffef4990ae7333d1c265db18',
    'rand_digit': 3,
    'rand_number': 0.26439,
    'rand_signed_int': -6,
    'rand_datetime': '2000-09-26 02:28:30',
    'text_array': [
    'c03182ad7c4f46f380aaabd3727e2716',
    '4552746e267d484b930a0b2317755af6',
],
    'words': 'frog grasshopper',
    'nested': {
    'id': 148,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'crab',
    'leopard',
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
    'mixed_type': False,
    'maybe_null': 'horse',
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 149,
    'id_str': [
    '07',
    '16',
    '22',
    '04',
    '30',
],
    'text_data': 'dabc54d960c9453c9edc47f9b632b557',
    'rand_digit': 3,
    'rand_number': 0.2114,
    'rand_signed_int': -10,
    'rand_datetime': '2000-09-15',
    'text_array': [
    'e99a01c767e94d70b23ec2d26a69dba6',
    '372e14e3c4d84df38a7d3d51c5739bad',
],
    'words': 'goat sloth',
    'nested': {
    'id': 149,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'mosquito',
    'jaguar',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fly',
    'maybe_null': None,
},
},
    {
    'id': 50,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 150,
    'id_str': [
    '01',
    '06',
    '02',
    '01',
],
    'text_data': 'a5730c85b80043f9ad9b6b02ce34cab7',
    'rand_digit': 2,
    'rand_number': 0.4867,
    'rand_signed_int': -9,
    'rand_datetime': '2000-03-04 09:39:11.875346-0200',
    'text_array': [
    '1f2222ac256741458a398cb131d13219',
    '18e26b0f638d4281bdb9e8337efff019',
],
    'words': 'snail pig',
    'nested': {
    'id': 150,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'sheep',
    'monkey',
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
    'mixed_type': 4,
    'maybe_null': 'ant',
},
},
    {
    'id': 51,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 151,
    'id_str': [
    '26',
    '22',
    '23',
    '13',
],
    'text_data': '38f6ac62aa9f427d9673025646d4152f',
    'rand_digit': 9,
    'rand_number': 0.31391,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-19',
    'text_array': [
    '34710ce37cfe435887a26fa8a3a7550a',
    '7cda5c98d37549dcbd093d3814933fe4',
],
    'words': 'ant bear',
    'nested': {
    'id': 151,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'mosquito',
    'dog',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'ladybug',
    'maybe_null': None,
},
},
    {
    'id': 52,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 152,
    'id_str': [
    '23',
],
    'text_data': 'b160713957344fc6b2ae1e96cb028210',
    'rand_digit': 4,
    'rand_number': 0.56282,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-09 21:35',
    'text_array': [
    '6e143a40e42a4eb583c32e07bb351a62',
    'a1e22d008a894836a2c4b0358bb686fa',
],
    'words': 'lion camel',
    'nested': {
    'id': 152,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
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
    'hello',
],
    'word': 'tiger',
    'number': 3,
},
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
],
    'two_words': [
    'lion',
    'cow',
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
    'maybe': 'ladybug',
},
},
    {
    'id': 53,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 153,
    'id_str': [
    '23',
    '22',
    '23',
    '11',
    '16',
],
    'text_data': '446bccea3898425398e691b891b729dd',
    'rand_digit': 9,
    'rand_number': 0.81851,
    'rand_signed_int': 3,
    'rand_datetime': '2000-03-26',
    'text_array': [
    'cd82e6de947f4cc6ba04bf2f3fa2d9d8',
    'a9694b0a778e4a878bb3a35650665e08',
],
    'words': 'rabbit panda',
    'nested': {
    'id': 153,
    'rand_digit': 3,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'crab',
    'squid',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cheetah',
    'maybe_null': 'gorilla',
},
},
    {
    'id': 54,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 154,
    'id_str': [
    '17',
    '30',
    '10',
    '08',
],
    'text_data': 'afd88d049a1942ed8ea197ca794e2021',
    'rand_digit': 0,
    'rand_number': 0.51173,
    'rand_signed_int': -10,
    'rand_datetime': '2000-02-15',
    'text_array': [
    'e03a40e4d11c483c9f9d4bdb1caf2fb3',
    'ed55ab2f94654327b8723140c3a5715a',
],
    'words': 'panda grasshopper',
    'nested': {
    'id': 154,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
    6,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bird',
    'octopus',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'goat',
    'maybe_null': 'snake',
},
},
    {
    'id': 55,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 155,
    'id_str': [
    '26',
],
    'text_data': '572c0de3f756473e8adc54a759f9779c',
    'rand_digit': 1,
    'rand_number': 0.21106,
    'rand_signed_int': -2,
    'rand_datetime': '2000-06-21T23:46:38.461456',
    'text_array': [
    '39fb143e2a174a4b989ad73fb0aadee5',
    '68589548de474a35bd57f0bf4b756436',
],
    'words': 'rabbit mouse',
    'nested': {
    'id': 155,
    'rand_digit': 5,
    'array': [
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -8,
],
],
    'two_words': [
    'ape',
    'snake',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': [
    69,
],
    'rand_bool': False,
    'mixed_type': 9,
    'maybe': 'ant',
},
},
    {
    'id': 56,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 156,
    'id_str': [
    '20',
    '06',
    '23',
    '27',
],
    'text_data': '5ad21759de92480388fa979596611b3e',
    'rand_digit': 0,
    'rand_number': 0.96074,
    'rand_signed_int': 0,
    'rand_datetime': '2000-12-16 19:42:05.663976',
    'text_array': [
    'b46dd01649d2439c9d6ef08506e48d8a',
    '3d425f7e785f4eb78a2d7b3a475d8550',
],
    'words': 'shark rabbit',
    'nested': {
    'id': 156,
    'rand_digit': 9,
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
],
    'word': 'rhino',
    'number': 8,
},
    {
    'nested_empty': None,
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
    'word': 'panda',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    10,
],
],
    'two_words': [
    'dragonfly',
    'giraffe',
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
    'mixed_type': 'zebra',
    'maybe_null': 'snake',
},
},
    {
    'id': 57,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 157,
    'id_str': [
    '18',
    '18',
],
    'text_data': 'a05a990948654d5a9b1bc2fa0edf6e7e',
    'rand_digit': 8,
    'rand_number': 0.80747,
    'rand_signed_int': 0,
    'rand_datetime': '2000-06-02T08:06:48.126900',
    'text_array': [
    '4326e428d60c4496b93f1d2ea85b95ab',
    '91bf43a7f7144b2e9b052bd043e465c8',
],
    'words': 'dragonfly squid',
    'nested': {
    'id': 157,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'koala',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -10,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cat',
    'lobster',
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
    'mixed_type': None,
    'maybe': 'bee',
    'maybe_null': None,
},
},
    {
    'id': 58,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 158,
    'id_str': [
    '04',
],
    'text_data': '5d24e9c7e21c4b38a498dd42ff2af52f',
    'rand_digit': 7,
    'rand_number': 0.46059,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-10 04:04:05.969881+0900',
    'text_array': [
    '9dd46fabd6224f96a78d95bb590cf36c',
    '463724e1dcb54dcda69e40c313b02647',
],
    'words': 'bear lion',
    'nested': {
    'id': 158,
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
    'number': 3,
},
],
},
    'nested_array': [
    [
    9,
],
],
    'two_words': [
    'octopus',
    'wolf',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': [
    41,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 59,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 159,
    'id_str': [
    '21',
    '12',
    '30',
    '12',
],
    'text_data': '549916c94f504f538a7b3416a59cc396',
    'rand_digit': 4,
    'rand_number': 0.42656,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-14 05:49:59.836073',
    'text_array': [
    'c0f2f187ef144c4e83247720a2838cfd',
    '7a279102314a49c5beca849b7e46417f',
],
    'words': 'monkey sloth',
    'nested': {
    'id': 159,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'panda',
    'scorpion',
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
    'mixed_type': None,
    'maybe': 'shark',
    'maybe_null': None,
},
},
    {
    'id': 60,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 160,
    'id_str': [
    '11',
    '22',
],
    'text_data': '6b78ecab78114080bff8147d3d8c4c30',
    'rand_digit': 4,
    'rand_number': 0.50793,
    'rand_signed_int': 9,
    'rand_datetime': '2000-08-30T15:43:22.594985',
    'text_array': [
    'e71de5a78e5b46bab2006ad8c02a9fd5',
    '01e8e969ce0a490ab908e0e84643bb87',
],
    'words': 'jaguar scorpion',
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
    'word': 'hyena',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'wolf',
    'horse',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 61,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 161,
    'id_str': [
    '29',
    '09',
    '06',
    '18',
],
    'text_data': '9e58399bd5624a0f878477b32b730686',
    'rand_digit': 0,
    'rand_number': 0.87311,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-14T19:19:42.286024-0600',
    'text_array': [
    'afe7b67d2e24414da620e57cdd8676a7',
    'b374ae09352247e4881a3db2f625975d',
],
    'words': 'octopus leopard',
    'nested': {
    'id': 161,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'sloth',
    'squid',
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
    'mixed_type': 4,
    'maybe': 'ape',
    'maybe_null': 'rabbit',
},
},
    {
    'id': 62,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 162,
    'id_str': [
    '24',
],
    'text_data': 'a32793e645164296b8ad296c56a416af',
    'rand_digit': 7,
    'rand_number': 0.24966,
    'rand_signed_int': -2,
    'rand_datetime': '2000-06-28T05:54:59.304209+0900',
    'text_array': [
    'b015bbdd82104830ae3156e55b4bf2ce',
    'f5b730df1332497083992f4a34850d6a',
],
    'words': 'panda ladybug',
    'nested': {
    'id': 162,
    'rand_digit': 9,
    'array': [
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'pig',
    'wolf',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': [
    1,
],
    'rand_bool': False,
    'mixed_type': 0.27813,
    'maybe_null': 'camel',
},
},
    {
    'id': 63,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 163,
    'id_str': [
    '07',
    '25',
    '10',
],
    'text_data': '3a62c2d5d64e420a987edee2101becf5',
    'rand_digit': 8,
    'rand_number': 0.87484,
    'rand_signed_int': -7,
    'rand_datetime': '2000-06-26T22:58:46.206619',
    'text_array': [
    '6c3885fc5cb04a8bbf323f23dbbdab7f',
    '3ceac4d1f2be47ee83c876a63ebc12d6',
],
    'words': 'spider panda',
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
    'word': 'koala',
    'number': 9,
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
    'octopus',
    'kangaroo',
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
    'mixed_type': {
    'key': 'value',
},
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
    'content-length': '3067',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': '__FLOAT_MULTI_DIM_10,50__',
},
    'using': 'multi-text',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_multivector_search_queries.test_simple')
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
    test = TestMultivectorSearchQueriestestSimple()
    test.run_tests()
