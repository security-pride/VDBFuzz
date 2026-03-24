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
logger = logging.getLogger('vdb_fuzzer.test.test_multivector_updates_test_upload_collection_generators')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_multivector_updates.test_upload_collection_generators"
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



class TestMultivectorUpdatestestUploadCollectionGenerators:
    """自动生成的VDB模糊测试类 - test_multivector_updates.test_upload_collection_generators"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_multivector_updates.test_upload_collection_generators"
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
    'content-length': '531507',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 100,
    'id_str': [
    '19',
    '28',
],
    'text_data': '9b099a6808f5498abafb85c9200dc6e9',
    'rand_digit': 6,
    'rand_number': 0.09149,
    'rand_signed_int': 7,
    'rand_datetime': '2000-05-18T22:58:44.198751-10:00',
    'text_array': [
    '7298db1971594d45858a70780d315e97',
    '5836b08537944e7f9f05aaa41687dedd',
],
    'words': 'monkey octopus',
    'nested': {
    'id': 100,
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
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'tiger',
    'dog',
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
    'mixed_type': 'dolphin',
    'maybe_null': 'squid',
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 101,
    'id_str': [
    '09',
    '12',
    '14',
    '19',
],
    'text_data': 'c10e13a6a20e4dc8b68c2b22ff910847',
    'rand_digit': 2,
    'rand_number': 0.29027,
    'rand_signed_int': -10,
    'rand_datetime': '2000-05-28T21:09:54.300876',
    'text_array': [
    '8ec498c29b54464cab60db6e34b971c4',
    'e69b8ef463b741499e423a4754619c7b',
],
    'words': 'ladybug lobster',
    'nested': {
    'id': 101,
    'rand_digit': 8,
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
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'crab',
    'crab',
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
    'mixed_type': 'camel',
    'maybe': 'frog',
    'maybe_null': 'ant',
},
},
    {
    'id': 2,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 102,
    'id_str': [
    '03',
],
    'text_data': '29aa0955b120435290eb94f20ac27c5b',
    'rand_digit': 0,
    'rand_number': 0.92343,
    'rand_signed_int': 4,
    'rand_datetime': '2000-10-09 04:10:12+0400',
    'text_array': [
    'b81f1843e7c0411c9c4034c0087fcfab',
    '1181d16ca7784bc8afd35a092b2927bd',
],
    'words': 'elephant lobster',
    'nested': {
    'id': 102,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 2,
},
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
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,2__',
    'two_words': [
    'gorilla',
    'lizard',
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
    'mixed_type': True,
    'maybe': 'ape',
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 103,
    'id_str': [
    '03',
    '22',
    '05',
    '28',
    '26',
],
    'text_data': 'cd2f810b9e5a494195215b1f8fd05be0',
    'rand_digit': 9,
    'rand_number': 0.36334,
    'rand_signed_int': -6,
    'rand_datetime': '2000-12-28T19:03:14.531892',
    'text_array': [
    '94a88be233b843eaa840cb51b382a152',
    '68f636f2eb7c408d98ff59bf44d3b170',
],
    'words': 'lobster ape',
    'nested': {
    'id': 103,
    'rand_digit': 9,
    'array': [
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
    'word': 'spider',
    'number': 8,
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
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'zebra',
    'crab',
],
    'city': {
    'name': 'Riga',
    'geo': {
    'lat': 56.949649,
    'lon': 24.105186,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'cat',
    'maybe': 'squid',
    'maybe_null': None,
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 104,
    'id_str': [
    '30',
],
    'text_data': 'ba235a74ce8249b9864bf173e41953fc',
    'rand_digit': 8,
    'rand_number': 0.39847,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-13 17:59:52.289428+0500',
    'text_array': [
    '869b557c7711467ba8256228454dd616',
    'c71b0c2cec6b4ef692a5509a7c630a51',
],
    'words': 'jaguar koala',
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
    'word': 'spider',
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 4,
},
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
    'word': 'squid',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'sheep',
    'horse',
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
    'mixed_type': True,
    'maybe_null': 'camel',
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 105,
    'id_str': [
    '28',
    '01',
    '06',
    '30',
],
    'text_data': '061c0a0a4f694aba8bc4102a763361f6',
    'rand_digit': 1,
    'rand_number': 0.39572,
    'rand_signed_int': 7,
    'rand_datetime': '2001-01-12T17:34:12.002228+0900',
    'text_array': [
    '3d2917ceda754b84b4b361547a927fab',
    '34b00c6e52684970aba321d2f6bbaf70',
],
    'words': 'pig hyena',
    'nested': {
    'id': 105,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 8,
},
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
    'hello',
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
    'word': 'cheetah',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'rhino',
    'shark',
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
    'mixed_type': None,
    'maybe_null': 'goat',
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 106,
    'id_str': [
    '22',
    '04',
    '29',
],
    'text_data': '2e9400cd8c284c03a2dadf3c41894850',
    'rand_digit': 4,
    'rand_number': 0.27327,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-08T12:16:17.734817',
    'text_array': [
    '48a2aaf14ec94046838cc1eba52cf16b',
    '36a7c0a4ca1b431da70175097a11bc10',
],
    'words': 'dolphin bear',
    'nested': {
    'id': 106,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'horse',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'turtle',
    'lobster',
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
    'mixed_type': True,
    'maybe': 'bee',
    'maybe_null': 'hippo',
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 107,
    'id_str': [
    '19',
],
    'text_data': 'd50a36c05ae744bbabfbfea194cefce6',
    'rand_digit': 4,
    'rand_number': 0.37101,
    'rand_signed_int': 1,
    'rand_datetime': '2000-12-06 11:02:49',
    'text_array': [
    '88eb6fde9b024be4b8e7357ad416f82d',
    '7720e264983b4acc8212ab56e23525ac',
],
    'words': 'dolphin crab',
    'nested': {
    'id': 107,
    'rand_digit': 1,
    'array': [
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
    [
    -6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'wolf',
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
    'mixed_type': 0.74864,
    'maybe_null': 'ladybug',
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 108,
    'id_str': [
    '14',
    '30',
    '11',
],
    'text_data': 'b12c1f9daef047a9b022ce2af287543c',
    'rand_digit': 6,
    'rand_number': 0.30581,
    'rand_signed_int': -3,
    'rand_datetime': '2000-12-06 11:30:22-1000',
    'text_array': [
    '00b11dbe10d143ae9bb14e804237ef1e',
    'ac29fc1a84914d71965483626cf4f570',
],
    'words': 'rhino ladybug',
    'nested': {
    'id': 108,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    6,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fly',
    'dog',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 109,
    'id_str': [
    '12',
    '02',
    '11',
],
    'text_data': '198b4485b08247649578480b0da0db8c',
    'rand_digit': 7,
    'rand_number': 0.04136,
    'rand_signed_int': -4,
    'rand_datetime': '2000-01-20 15:38:00.791297',
    'text_array': [
    'b5795fdbb9524cb89f9e8d3a2bd751e0',
    'ab0ad3108b3e46ebb8dba1ef591ab779',
],
    'words': 'squid rhino',
    'nested': {
    'id': 109,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'rabbit',
    'ladybug',
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
    'mixed_type': False,
    'maybe': 'monkey',
    'maybe_null': None,
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 110,
    'id_str': [
    '07',
    '07',
    '17',
],
    'text_data': 'b58b70c0c80e45a48788ec0d02925bd4',
    'rand_digit': 1,
    'rand_number': 0.53444,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-06T11:32:30.082259',
    'text_array': [
    'cadef41f88a34344999ac03b3dae6091',
    '480b1fdbc125468d82d79e69838e1b28',
],
    'words': 'goat koala',
    'nested': {
    'id': 110,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'cat',
    'duck',
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
    'mixed_type': None,
    'maybe': 'shark',
    'maybe_null': 'rabbit',
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 111,
    'id_str': [
    '07',
    '06',
    '11',
    '29',
],
    'text_data': '3ba0fbf96b374fe78f2947214386c615',
    'rand_digit': 9,
    'rand_number': 0.23876,
    'rand_signed_int': 8,
    'rand_datetime': '2000-11-29',
    'text_array': [
    '431e0276eab246ce9a3105b756f04ea5',
    '8eaf7ffd3aca424c801031d3abaa62eb',
],
    'words': 'tiger sloth',
    'nested': {
    'id': 111,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'mosquito',
    'duck',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 5,
    'maybe_null': 'fox',
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 112,
    'id_str': [
],
    'text_data': '5c444dc1c4c3406c963ac11e64516efd',
    'rand_digit': 2,
    'rand_number': 0.38828,
    'rand_signed_int': -4,
    'rand_datetime': '2000-07-19T23:47:58.498589',
    'text_array': [
    '0e03ce9162684f96be18ac31dc6f4c7f',
    '4ddfa3aa12e0479aae93af03e813e4f8',
],
    'words': 'wolf chicken',
    'nested': {
    'id': 112,
    'rand_digit': 4,
    'array': [
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
    'word': 'ladybug',
    'number': 6,
},
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
],
    'word': 'spider',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'horse',
    'bee',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': [
    52,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'crab',
    'maybe_null': None,
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 113,
    'id_str': [
    '01',
],
    'text_data': '9953ce528ceb4622aa6853f56bb74b01',
    'rand_digit': 6,
    'rand_number': 0.88169,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-11T12:52:04.487437',
    'text_array': [
    'da86e4cba28341c0afec9405887c2145',
    'ce47c4f6deae4f23beee789eef0b5141',
],
    'words': 'bear kangaroo',
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
    'word': 'frog',
    'number': 5,
},
    {
    'nested_empty': None,
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
],
    'word': 'mouse',
    'number': 2,
},
    {
    'nested_empty': None,
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
    'word': 'elephant',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'leopard',
    'elephant',
],
    'city': {
    'name': 'Dubai',
    'geo': {
    'lat': 25.204849,
    'lon': 55.270783,
},
},
    'rand_tuple': [
    70,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bear',
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 114,
    'id_str': [
    '29',
    '15',
    '24',
    '02',
],
    'text_data': 'f2b01d14a9ef48b78d310aae66c42dd1',
    'rand_digit': 2,
    'rand_number': 0.41608,
    'rand_signed_int': 2,
    'rand_datetime': '2000-03-14T07:22:05.162033',
    'text_array': [
    '0a4a0bec90954b188d91a58591e178a5',
    '42c35a8ea601430da9d518332fbdb3f2',
],
    'words': 'tiger butterfly',
    'nested': {
    'id': 114,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 1,
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
    'hello',
],
    'word': 'bear',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dolphin',
    'leopard',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': [
    34,
],
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'dog',
    'maybe_null': None,
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 115,
    'id_str': [
    '13',
    '06',
    '28',
    '28',
    '07',
],
    'text_data': '3db66a443c4d4507b20bd230ea9f7771',
    'rand_digit': 8,
    'rand_number': 0.5692,
    'rand_signed_int': 4,
    'rand_datetime': '2000-12-12T06:04:20-1000',
    'text_array': [
    '58dc62fa485f4ea794026ea32f482d00',
    'fa19a05bd8894e3cb39f09c4704e968a',
],
    'words': 'grasshopper octopus',
    'nested': {
    'id': 115,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
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
    'number': 8,
},
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
    'word': 'hippo',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    10,
],
    [
    2,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'koala',
    'bear',
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
    'maybe': 'squid',
    'maybe_null': 'elephant',
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 116,
    'id_str': [
    '21',
    '22',
],
    'text_data': 'd05f5c8af83a4d7e8164efaa6fb306a5',
    'rand_digit': 1,
    'rand_number': 0.90957,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-25T07:23:08',
    'text_array': [
    '47152a716fde4efc971b8338b26e1721',
    '08524ceeb87047a391017552c1adf619',
],
    'words': 'sheep fish',
    'nested': {
    'id': 116,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'tiger',
    'jaguar',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
    'maybe_null': 'bear',
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 117,
    'id_str': [
    '21',
    '11',
    '06',
    '08',
],
    'text_data': 'e50cbfc85c504bdca07706703395ebed',
    'rand_digit': 7,
    'rand_number': 0.30653,
    'rand_signed_int': -9,
    'rand_datetime': '2000-03-15 14:18:05',
    'text_array': [
    '12867f55c949496d8ceebe1984e6cb78',
    '70c0bd84546944da80511e0ed110df57',
],
    'words': 'camel sheep',
    'nested': {
    'id': 117,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'duck',
    'number': 8,
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
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'fox',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'snail',
    'lizard',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'pig',
    'maybe': 'crab',
    'maybe_null': 'sloth',
},
},
    {
    'id': 18,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 118,
    'id_str': [
    '09',
],
    'text_data': 'eed80819b8ea4edb832889380b93aefd',
    'rand_digit': 2,
    'rand_number': 0.93297,
    'rand_signed_int': 0,
    'rand_datetime': '2000-06-14T13:57:00.452985',
    'text_array': [
    '89a823dea8b74f5daa636fab93b1c169',
    '0bc2757fce8e4f8a865188386ac0dfb4',
],
    'words': 'hyena elephant',
    'nested': {
    'id': 118,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'deer',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    0,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'ape',
    'kangaroo',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': [
    18,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
],
    'text_data': '171031b8e7f544088f10414479abb424',
    'rand_digit': 3,
    'rand_number': 0.53293,
    'rand_signed_int': -1,
    'rand_datetime': '2000-01-12T17:07:57.083233+1000',
    'text_array': [
    '9b5220db8e6d434aa7b31334cf873255',
    'ade0392d5a324f62afaef663ccf2bed9',
],
    'words': 'panda rhino',
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
    'word': 'goat',
    'number': 9,
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lizard',
    'fly',
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
    'maybe_null': 'goat',
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 120,
    'id_str': [
],
    'text_data': '032fe26a09024603a39adb47a1a4bf00',
    'rand_digit': 1,
    'rand_number': 0.37864,
    'rand_signed_int': -7,
    'rand_datetime': '2000-04-23T20:33:08.692359+04:00',
    'text_array': [
    'ff81f6d8aec04c0eb8db97f2671e6ada',
    '9dc9fd69c151477faeea84e11e093b79',
],
    'words': 'turtle tiger',
    'nested': {
    'id': 120,
    'rand_digit': 7,
    'array': [
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    5,
],
    [
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'dog',
    'bee',
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
    'mixed_type': None,
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 121,
    'id_str': [
],
    'text_data': '2ef1b8b10b364ff08fcb9041c3cb9f1c',
    'rand_digit': 1,
    'rand_number': 0.99035,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-05 15:02:52-0700',
    'text_array': [
    '62a87376ce59462988bc3663140cc513',
    '8fa312b072e04a1d87596409bde349df',
],
    'words': 'zebra bird',
    'nested': {
    'id': 121,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
    4,
],
    [
    -3,
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'shark',
    'snake',
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
    'mixed_type': 0.73007,
    'maybe': 'octopus',
    'maybe_null': None,
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
    '22',
    '05',
    '04',
    '24',
],
    'text_data': '820678bf83d54e5f9e3295774e0e9137',
    'rand_digit': 7,
    'rand_number': 0.4749,
    'rand_signed_int': -10,
    'rand_datetime': '2000-10-31T22:44:32.809775',
    'text_array': [
    '17dab9164a704ed588d3cbb3c146b894',
    '93e6dacf6c99426c9f02255b25deb7da',
],
    'words': 'cheetah panda',
    'nested': {
    'id': 122,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'rabbit',
    'fish',
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
    'mixed_type': True,
    'maybe': 'hippo',
    'maybe_null': 'monkey',
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 123,
    'id_str': [
    '03',
    '04',
    '14',
    '29',
],
    'text_data': '6fd5967894394ab0aa7d77536b6c9c6c',
    'rand_digit': 6,
    'rand_number': 0.18057,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-11T18:17:47+1200',
    'text_array': [
    '5649b47a61d2480ebb7c4f64df9dcaaa',
    'e956eec13af7466d90b314b1046722bc',
],
    'words': 'shark hyena',
    'nested': {
    'id': 123,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'camel',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'cat',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    3,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'dog',
    'snake',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'monkey',
    'maybe_null': 'deer',
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 124,
    'id_str': [
    '20',
    '16',
    '11',
    '23',
    '18',
],
    'text_data': 'ba6597cef2ae4a8896d37484077ed19a',
    'rand_digit': 8,
    'rand_number': 0.52345,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-19 11:01:05.762742',
    'text_array': [
    'c90e99f8d09742339bd83dee5363b9d0',
    '5d04fce10a3846968e3a10476a3ccbee',
],
    'words': 'dog rhino',
    'nested': {
    'id': 124,
    'rand_digit': 8,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'frog',
    'number': 7,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'camel',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'zebra',
    'fox',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'snake',
    'maybe_null': 'lion',
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
    '22',
    '27',
    '26',
    '25',
    '06',
],
    'text_data': '7be08a60e9794b44867f6ea5b5583f23',
    'rand_digit': 6,
    'rand_number': 0.87242,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-04T22:48:51.578117',
    'text_array': [
    '619216043b2240d5b6fe06c0ba690b21',
    '243fc27413254211aeced04639dc4cf4',
],
    'words': 'grasshopper snail',
    'nested': {
    'id': 125,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 6,
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
    'chicken',
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
    'maybe_null': 'pig',
},
},
    {
    'id': 26,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 126,
    'id_str': [
    '25',
    '22',
],
    'text_data': 'c4670e94faa04493b9df45522d239ff0',
    'rand_digit': 7,
    'rand_number': 0.18108,
    'rand_signed_int': 2,
    'rand_datetime': '2000-01-16 21:34:44.828519',
    'text_array': [
    'd721b07922da4a0087f38d7f825d1e8e',
    'd29499a246b34a20aed757a7c1b1fdc0',
],
    'words': 'lion frog',
    'nested': {
    'id': 126,
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
    'number': 10,
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
    'hippo',
    'crab',
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
    'mixed_type': False,
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 127,
    'id_str': [
    '04',
],
    'text_data': 'bc9d60290a4a4fb4b258f614102dd72b',
    'rand_digit': 6,
    'rand_number': 0.72733,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-17T15:19:16.866595',
    'text_array': [
    '86f953e6d392416a97d0f2bbc3f9e4c0',
    '674e2738c0034ba48105d4a39b606043',
],
    'words': 'koala snake',
    'nested': {
    'id': 127,
    'rand_digit': 5,
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
    'word': 'goat',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
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
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'spider',
    'tiger',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
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
    'id': 28,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 128,
    'id_str': [
    '07',
    '25',
    '10',
],
    'text_data': '7d055ee8d18f4444afd6d5d43f6e6f76',
    'rand_digit': 8,
    'rand_number': 0.21582,
    'rand_signed_int': -1,
    'rand_datetime': '2000-06-19 14:21:50.160113',
    'text_array': [
    'c293e9e89ac04e93bcbd7ebe98d86ea3',
    '18e543a093e54a8b866c5417d1d60fe3',
],
    'words': 'horse sheep',
    'nested': {
    'id': 128,
    'rand_digit': 3,
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
    'word': 'leopard',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'koala',
    'pig',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'deer',
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
    '02',
    '21',
    '07',
    '11',
    '20',
],
    'text_data': '78b7344ff5524f53b834892db002d221',
    'rand_digit': 3,
    'rand_number': 0.14092,
    'rand_signed_int': 7,
    'rand_datetime': '2000-12-24 11:44:56-0600',
    'text_array': [
    'fd1c20c7fa454eb6bc0932a7dc1547b2',
    '1cd688e20eb745dba58b5645d90fe677',
],
    'words': 'bee dragonfly',
    'nested': {
    'id': 129,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'rhino',
    'snake',
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
    'mixed_type': None,
    'maybe': 'ladybug',
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 130,
    'id_str': [
    '30',
    '12',
    '11',
    '28',
    '14',
],
    'text_data': '4819fd25ba8741db9aef8c7981ab4d45',
    'rand_digit': 7,
    'rand_number': 0.2608,
    'rand_signed_int': -1,
    'rand_datetime': '2000-04-24T08:02:45.996853',
    'text_array': [
    'fe3cbd3f177b4c3e99a6a4199f92b1d1',
    'c44b5df3e37845adbf51e7df0d0d09f2',
],
    'words': 'snail lion',
    'nested': {
    'id': 130,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'ladybug',
    'number': 1,
},
    {
    'nested_empty': None,
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
    'butterfly',
    'fish',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': [
    28,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': None,
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 131,
    'id_str': [
    '01',
    '03',
    '28',
],
    'text_data': 'adafb61d8e6045e8af4c6703b51cc4c1',
    'rand_digit': 5,
    'rand_number': 0.15938,
    'rand_signed_int': -7,
    'rand_datetime': '2000-04-04T11:17:51.649585+0300',
    'text_array': [
    '1054e1b2dff24ebe90553ef72a0228d8',
    '42927046b02c4bd1944580eab3a04778',
],
    'words': 'hyena jaguar',
    'nested': {
    'id': 131,
    'rand_digit': 6,
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
    'word': 'butterfly',
    'number': 3,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'fox',
    'squid',
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
    'mixed_type': None,
},
},
    {
    'id': 32,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 132,
    'id_str': [
],
    'text_data': '4803a091c2cc44d3a3461661311039ee',
    'rand_digit': 0,
    'rand_number': 0.82235,
    'rand_signed_int': 3,
    'rand_datetime': '2000-09-01 05:07:17+0400',
    'text_array': [
    'b3199a9f304442a29791c686f6a8692a',
    'e7e08f9453fb450db0bec35e2f68bacf',
],
    'words': 'ape snake',
    'nested': {
    'id': 132,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
    5,
],
],
    'two_words': [
    'crab',
    'lizard',
],
    'city': {
    'name': 'Moscow',
    'geo': {
    'lat': 55.755826,
    'lon': 37.6173,
},
},
    'rand_tuple': [
    38,
],
    'rand_bool': False,
    'mixed_type': 0.08137,
    'maybe': 'camel',
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 133,
    'id_str': [
],
    'text_data': '7f9201f4ba3c4462950549fd4e51bbff',
    'rand_digit': 6,
    'rand_number': 0.64959,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-28 00:07:59.741164',
    'text_array': [
    '80d215f4e2e8439e83c1cda7d77a0941',
    '60e9524866784184a81345a92253b039',
],
    'words': 'giraffe dragonfly',
    'nested': {
    'id': 133,
    'rand_digit': 9,
    'array': [
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
    'word': 'giraffe',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    10,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'sloth',
    'bird',
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
    'mixed_type': 'giraffe',
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 134,
    'id_str': [
    '02',
],
    'text_data': '67cae1a3d6db4f21a7c0aa630a333725',
    'rand_digit': 2,
    'rand_number': 0.99327,
    'rand_signed_int': 6,
    'rand_datetime': '2000-10-25 06:53',
    'text_array': [
    '8d58bcee77bc4cc4a3838d9c6db0c723',
    'a54d072cefd54b1f8150753bebbbe272',
],
    'words': 'fox lizard',
    'nested': {
    'id': 134,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'dog',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'kangaroo',
    'fox',
],
    'city': {
    'name': 'Johannesburg',
    'geo': {
    'lat': -26.204103,
    'lon': 28.047305,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'cheetah',
},
},
    {
    'id': 35,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 135,
    'id_str': [
],
    'text_data': 'a826ade2f8a24f82abf8e0418ffe421c',
    'rand_digit': 5,
    'rand_number': 0.66294,
    'rand_signed_int': 9,
    'rand_datetime': '2000-06-10T15:04:24+0100',
    'text_array': [
    'aa27e3dca290442cb9dbad52283a2f4a',
    '49abe865f66742fd8abdb492e6c87d49',
],
    'words': 'scorpion cheetah',
    'nested': {
    'id': 135,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 8,
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
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'jaguar',
    'fly',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'horse',
    'maybe_null': 'sloth',
},
},
    {
    'id': 36,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 136,
    'id_str': [
    '18',
    '02',
    '29',
    '12',
    '26',
],
    'text_data': '8c9a74bea2e1454194318c2982d5f2fb',
    'rand_digit': 1,
    'rand_number': 0.34986,
    'rand_signed_int': -1,
    'rand_datetime': '2000-10-13T06:14:48.611385',
    'text_array': [
    'a5658482a16c4f29949f352abbf81a33',
    '47c7554d42394c12b7a950bf10c9265e',
],
    'words': 'koala leopard',
    'nested': {
    'id': 136,
    'rand_digit': 9,
    'array': [
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
],
    'word': 'hyena',
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
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -5,
],
],
    'two_words': [
    'bee',
    'goat',
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
    'maybe': 'koala',
    'maybe_null': 'tiger',
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
    '14',
],
    'text_data': 'b06e9fa0ddac4826b143328c56d0d63c',
    'rand_digit': 2,
    'rand_number': 0.53288,
    'rand_signed_int': 1,
    'rand_datetime': '2000-03-18T23:07:44.914992',
    'text_array': [
    '8ff29e789e614cfabdb2bd5a6794202e',
    '6445e2cb53904ad38a9c793b49575d25',
],
    'words': 'chicken lobster',
    'nested': {
    'id': 137,
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
    'word': 'dog',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'grasshopper',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hippo',
    'zebra',
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
    'mixed_type': True,
    'maybe_null': 'monkey',
},
},
    {
    'id': 38,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 138,
    'id_str': [
    '12',
    '14',
    '20',
    '12',
    '13',
],
    'text_data': '988036cbc43b473296fa1f6e07c020f3',
    'rand_digit': 7,
    'rand_number': 0.7124,
    'rand_signed_int': 8,
    'rand_datetime': '2000-04-10T03:16:05',
    'text_array': [
    '87f1ba67e49f4cc29403ed70b39b8f24',
    'f9d7a24203c646d4af1c37ef853fd72e',
],
    'words': 'mouse dragonfly',
    'nested': {
    'id': 138,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
    -10,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'gorilla',
    'dog',
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
    'mixed_type': 8,
    'maybe_null': 'turtle',
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 139,
    'id_str': [
],
    'text_data': '12aa3bfb75a94b66909bbd08803008a6',
    'rand_digit': 7,
    'rand_number': 0.59423,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-15T05:45:51.847592+0200',
    'text_array': [
    'f3bd758cc7d045cf81d6a9dcfd40ce14',
    'd738a8a5d8a74aacac16a67424e47a17',
],
    'words': 'giraffe dragonfly',
    'nested': {
    'id': 139,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'scorpion',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'tiger',
    'ladybug',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.46802,
    'maybe_null': 'bee',
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 140,
    'id_str': [
    '17',
    '16',
    '02',
    '11',
],
    'text_data': 'feb3d18fb28649e795aa3d584c816048',
    'rand_digit': 0,
    'rand_number': 0.69516,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-01T00:13:42.068314',
    'text_array': [
    '76ed97c7a5d648e19df446135a9aa0a2',
    '7e87a9af583442a3b8383c7a07fe892a',
],
    'words': 'leopard spider',
    'nested': {
    'id': 140,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 2,
},
    {
    'nested_empty': None,
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
    'word': 'goat',
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
],
    'two_words': [
    'ant',
    'duck',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.19178,
    'maybe_null': None,
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 141,
    'id_str': [
    '29',
],
    'text_data': 'df83c1620ccc468889ec709849832668',
    'rand_digit': 1,
    'rand_number': 0.02743,
    'rand_signed_int': -3,
    'rand_datetime': '2000-09-19T16:52:28+1200',
    'text_array': [
    'd71633d518624902a3053d9cea14715e',
    'ddddb6825fbd42cd9c70762f34575f2a',
],
    'words': 'goat koala',
    'nested': {
    'id': 141,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'panda',
    'number': 1,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'rhino',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lion',
    'ant',
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
    'mixed_type': 6,
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 142,
    'id_str': [
    '19',
    '29',
    '06',
    '18',
    '12',
],
    'text_data': 'e1387e265f384aed98679bef4dce363e',
    'rand_digit': 3,
    'rand_number': 0.79126,
    'rand_signed_int': -4,
    'rand_datetime': '2000-02-24 16:27:51.045121-0300',
    'text_array': [
    '31a53c8f140a4757b340640533928782',
    '1044750ad49647f3ad93cc64ba0a8a8a',
],
    'words': 'lion turtle',
    'nested': {
    'id': 142,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'frog',
    'koala',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
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
    'id': 43,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 143,
    'id_str': [
    '02',
    '22',
    '30',
],
    'text_data': '2394574695f44dff90297a1fa197350a',
    'rand_digit': 1,
    'rand_number': 0.32637,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-01 14:20:09+1100',
    'text_array': [
    '99d8b9c4ece64c5c985c6e994104cad5',
    '475af06203c1426b91f08e12273c1439',
],
    'words': 'goat jaguar',
    'nested': {
    'id': 143,
    'rand_digit': 1,
    'array': [
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    5,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'giraffe',
    'turtle',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'ant',
    'maybe_null': 'fox',
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 144,
    'id_str': [
    '18',
],
    'text_data': '77636a55cd7c402fae537daef8f49364',
    'rand_digit': 0,
    'rand_number': 0.98803,
    'rand_signed_int': 1,
    'rand_datetime': '2000-02-06T07:32:52',
    'text_array': [
    'fc7a9d3182804e1c8ab737b16e67d7ea',
    '891fd8ce547945358f0114638a87e30b',
],
    'words': 'mouse turtle',
    'nested': {
    'id': 144,
    'rand_digit': 3,
    'array': [
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
],
    'word': 'chicken',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'pig',
    'rhino',
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
    'mixed_type': 0,
    'maybe': 'dolphin',
    'maybe_null': 'grasshopper',
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 145,
    'id_str': [
    '17',
    '07',
    '06',
    '20',
    '07',
],
    'text_data': 'd06b374185594f07a8f6f09696a24610',
    'rand_digit': 7,
    'rand_number': 0.51046,
    'rand_signed_int': 3,
    'rand_datetime': '2000-03-28T10:35:22.799522-0100',
    'text_array': [
    'eb261d2939db4223a38503f44f5af683',
    'bed62cf2ed6c423f997f2184bfe0ae20',
],
    'words': 'ladybug cow',
    'nested': {
    'id': 145,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
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
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 6,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'rabbit',
    'bird',
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
    'maybe': 'bee',
    'maybe_null': 'shark',
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
    '29',
    '24',
    '25',
],
    'text_data': '09d07150168746418751a8b61c57e878',
    'rand_digit': 8,
    'rand_number': 0.84266,
    'rand_signed_int': -5,
    'rand_datetime': '2000-07-30',
    'text_array': [
    '4ebbe395c9484867a5ad6991eee509bf',
    'f61991ff8a7842d6ad12f329d766fb72',
],
    'words': 'rabbit ape',
    'nested': {
    'id': 146,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
    0,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'fox',
    'dolphin',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'snake',
    'maybe_null': 'ant',
},
},
    {
    'id': 47,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 147,
    'id_str': [
],
    'text_data': 'cc9d933c134f49f18e8249c0d8f7bb7c',
    'rand_digit': 9,
    'rand_number': 0.61636,
    'rand_signed_int': -9,
    'rand_datetime': '2000-07-13T14:18:14-1200',
    'text_array': [
    '044c74553d49456f97c5272949bff67f',
    '35fb93b83d9f4d4e99b3e6ff5e31e8ec',
],
    'words': 'lion cat',
    'nested': {
    'id': 147,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'camel',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 5,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    2,
],
],
    'two_words': [
    'squid',
    'crab',
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
    'maybe': 'fly',
    'maybe_null': None,
},
},
    {
    'id': 48,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 148,
    'id_str': [
],
    'text_data': '88c627484a9f41f087729f96fab09f59',
    'rand_digit': 1,
    'rand_number': 0.49359,
    'rand_signed_int': 3,
    'rand_datetime': '2001-01-22T04:16:30+0100',
    'text_array': [
    'e2416f125ee14545b0e0dbccd00e7d56',
    '8da29c791ef246bfbf4edf81eb978f7a',
],
    'words': 'cat cat',
    'nested': {
    'id': 148,
    'rand_digit': 0,
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
    'dragonfly',
    'bear',
],
    'city': {
    'name': 'Barcelona',
    'geo': {
    'lat': 41.385064,
    'lon': 2.173403,
},
},
    'rand_tuple': [
    45,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'duck',
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 149,
    'id_str': [
    '06',
    '08',
    '26',
],
    'text_data': 'f979c76a6ee94e48acf4ad02d4125fc9',
    'rand_digit': 4,
    'rand_number': 0.6203,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-21 01:41',
    'text_array': [
    '5b5161cb82e54e28bd2ba4649be2ce85',
    '6c0ac6b7e90449739d3ded4d133c785a',
],
    'words': 'dragonfly frog',
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
    'word': 'pig',
    'number': 10,
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
    'word': 'camel',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mouse',
    'turtle',
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
    'mixed_type': 0.47273,
    'maybe': 'hippo',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 50,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 150,
    'id_str': [
    '08',
    '28',
    '20',
    '23',
],
    'text_data': '11f7bd1425994c8ebb8ff380c7329221',
    'rand_digit': 9,
    'rand_number': 0.87349,
    'rand_signed_int': 7,
    'rand_datetime': '2000-05-22T20:22:11.756077',
    'text_array': [
    '37f4250834dc4a138a7c0154ef28a9cb',
    'bfc484e68c634f5cb58006db9a5a975a',
],
    'words': 'monkey horse',
    'nested': {
    'id': 150,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 2,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 5,
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
],
    'two_words': [
    'zebra',
    'octopus',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': [
    43,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'octopus',
    'maybe_null': None,
},
},
    {
    'id': 51,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 151,
    'id_str': [
    '28',
],
    'text_data': '2e2f48b94190488aaca1a93e2d35f113',
    'rand_digit': 8,
    'rand_number': 0.3335,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-25T11:12:39.908308',
    'text_array': [
    'b7367054a36f41d58b68b92206493a06',
    '2a283a330f4d458e97919af3cffc7b1a',
],
    'words': 'hyena koala',
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
    'word': 'ant',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'dog',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'snail',
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
    'mixed_type': False,
    'maybe_null': None,
},
},
    {
    'id': 52,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 152,
    'id_str': [
],
    'text_data': 'a279fcd6599041d4a8a5815a50a862d4',
    'rand_digit': 7,
    'rand_number': 0.69226,
    'rand_signed_int': -2,
    'rand_datetime': '2000-08-06 00:29',
    'text_array': [
    'fab4cec201154dddab9fbdd74389ac85',
    '54411ecf6b0a4ef093d200ae6da517eb',
],
    'words': 'lizard jaguar',
    'nested': {
    'id': 152,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    [
    -2,
],
    [
    -7,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ape',
    'snail',
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
    'mixed_type': False,
},
},
    {
    'id': 53,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 153,
    'id_str': [
],
    'text_data': 'ec62c2ead2d24d11b8c2e8a6e7125f62',
    'rand_digit': 8,
    'rand_number': 0.02904,
    'rand_signed_int': 8,
    'rand_datetime': '2000-07-27',
    'text_array': [
    '55431364197f4d1084ae4ba974a3f0bf',
    '5e819023cd5e4ff2b57a5d3e58a77871',
],
    'words': 'zebra rhino',
    'nested': {
    'id': 153,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'turtle',
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 5,
},
],
},
    'nested_array': [
    [
    -7,
],
    [
    -4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    2,
],
],
    'two_words': [
    'bird',
    'dog',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.02665,
    'maybe_null': 'sheep',
},
},
    {
    'id': 54,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 154,
    'id_str': [
    '15',
],
    'text_data': 'a0953f5f2fb843599633a750ff4aada3',
    'rand_digit': 8,
    'rand_number': 0.17002,
    'rand_signed_int': -10,
    'rand_datetime': '2000-08-24T08:28:11-1200',
    'text_array': [
    '3b2495c1e47349c9864097321c718baf',
    'c873f97aebd242b6aced5ac586381e9d',
],
    'words': 'wolf kangaroo',
    'nested': {
    'id': 154,
    'rand_digit': 8,
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
],
},
    'nested_array': [
],
    'two_words': [
    'camel',
    'ape',
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
    'mixed_type': 'ladybug',
    'maybe_null': 'kangaroo',
},
},
    {
    'id': 55,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 155,
    'id_str': [
    '05',
],
    'text_data': '35ae1145dccd4ee890e7015df9ce1901',
    'rand_digit': 9,
    'rand_number': 0.99812,
    'rand_signed_int': 10,
    'rand_datetime': '2000-06-09 04:46',
    'text_array': [
    'cbc62446f8f24777b91b5b442b02b8ac',
    'dbfc787fff224cce87db2aac39deada7',
],
    'words': 'monkey pig',
    'nested': {
    'id': 155,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'dog',
    'gorilla',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': [
    33,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'octopus',
    'maybe_null': 'hippo',
},
},
    {
    'id': 56,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 156,
    'id_str': [
    '28',
    '06',
    '01',
],
    'text_data': 'ece8ac56d7f04449b477141dfa0eb307',
    'rand_digit': 6,
    'rand_number': 0.60913,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-24T22:58:08.994172+0500',
    'text_array': [
    'aa0eb80ffaa8406e93d754c6bf22d612',
    'a8f4cea646544b81b5e413744ced4611',
],
    'words': 'zebra goat',
    'nested': {
    'id': 156,
    'rand_digit': 0,
    'array': [
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
    'word': 'horse',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 8,
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    4,
],
    [
],
],
    'two_words': [
    'bear',
    'wolf',
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
    'maybe': 'fish',
    'maybe_null': 'deer',
},
},
    {
    'id': 57,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 157,
    'id_str': [
    '25',
    '01',
    '09',
    '27',
],
    'text_data': '23d5a64b7a6c4c26932480ad678a3b03',
    'rand_digit': 0,
    'rand_number': 0.77064,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-11T20:33:15+0500',
    'text_array': [
    'e2c4b5f41885423ba5cd4956d410c012',
    'b61280725af349bd8d693a45463afc43',
],
    'words': 'mouse snail',
    'nested': {
    'id': 157,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
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
    -2,
],
    [
],
    [
],
],
    'two_words': [
    'wolf',
    'dolphin',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.77097,
    'maybe': 'deer',
    'maybe_null': 'ape',
},
},
    {
    'id': 58,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 158,
    'id_str': [
],
    'text_data': '13a7f00255fd4b45b1085661e4772dad',
    'rand_digit': 5,
    'rand_number': 0.82542,
    'rand_signed_int': 7,
    'rand_datetime': '2000-06-15',
    'text_array': [
    'e0ed609b25ec4eb5a15d89e316e4685c',
    '244b5adb67c14b84a8de5d792c8a423a',
],
    'words': 'rabbit sloth',
    'nested': {
    'id': 158,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 4,
},
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
    'word': 'scorpion',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dolphin',
    'bird',
],
    'city': {
    'name': 'Dubai',
    'geo': {
    'lat': 25.204849,
    'lon': 55.270783,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'cat',
},
},
    {
    'id': 59,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 159,
    'id_str': [
    '07',
],
    'text_data': 'e02eff361560430fa3f2aca4c942afb6',
    'rand_digit': 3,
    'rand_number': 0.58476,
    'rand_signed_int': 0,
    'rand_datetime': '2000-10-15',
    'text_array': [
    '7afde8c8325d40ce854af42cd018ea5e',
    '06a9cf8d790148579d6eea566f81b767',
],
    'words': 'jaguar panda',
    'nested': {
    'id': 159,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'goat',
    'pig',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'snail',
},
},
    {
    'id': 60,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 160,
    'id_str': [
    '10',
    '23',
],
    'text_data': 'fb1abf79805940449fcebef569eb6e05',
    'rand_digit': 9,
    'rand_number': 0.18488,
    'rand_signed_int': 1,
    'rand_datetime': '2000-03-30T07:32:22',
    'text_array': [
    'a864a74e84254d98b3df29dda9c2063b',
    '90c2cb001d3e4b8e96e1abc4cc1ac597',
],
    'words': 'duck dog',
    'nested': {
    'id': 160,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
    'number': 10,
},
],
},
    'nested_array': [
    [
    -3,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cat',
    'camel',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 61,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 161,
    'id_str': [
    '15',
    '18',
    '19',
    '03',
],
    'text_data': 'd0ab2e165aba4b2aad411edcaee1e739',
    'rand_digit': 7,
    'rand_number': 0.29488,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-31 15:53',
    'text_array': [
    '95888881d00e40818ecb4d774762ff27',
    'b506ff7e42834879bab166e4f40dde80',
],
    'words': 'dog leopard',
    'nested': {
    'id': 161,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'jaguar',
    'number': 9,
},
],
},
    'nested_array': [
    [
    9,
],
],
    'two_words': [
    'mouse',
    'goat',
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
    'mixed_type': 0.19525,
    'maybe': 'panda',
    'maybe_null': 'mosquito',
},
},
    {
    'id': 62,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 162,
    'id_str': [
    '22',
    '29',
    '17',
    '05',
],
    'text_data': 'ef881f9c85384d1786ed13834d2c084f',
    'rand_digit': 7,
    'rand_number': 0.47122,
    'rand_signed_int': 10,
    'rand_datetime': '2000-11-08',
    'text_array': [
    '9034db7fa2344130948473cc8dd15e06',
    '7efb7b6650d746f4950720cec7d35bb7',
],
    'words': 'jaguar panda',
    'nested': {
    'id': 162,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'horse',
    'jaguar',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': [
    23,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'jaguar',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 63,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 163,
    'id_str': [
    '05',
    '01',
    '05',
    '14',
    '15',
],
    'text_data': '41c60a77f8474277904c46cb6213fd48',
    'rand_digit': 2,
    'rand_number': 0.60965,
    'rand_signed_int': 0,
    'rand_datetime': '2000-08-06 11:18:15.467776-0600',
    'text_array': [
    'd147fa6be08341699152f7cb77e990b4',
    '126a389f8f9640189f03d9ed6a18d0c9',
],
    'words': 'bear ant',
    'nested': {
    'id': 163,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
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
],
    'word': 'duck',
    'number': 10,
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
    'hello',
],
    'word': 'ant',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    4,
],
    [
],
],
    'two_words': [
    'lion',
    'lobster',
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
    'mixed_type': True,
    'maybe': 'monkey',
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



    def test_request_2(self):
        """测试请求 2 - POST http://localhost:6333/collections/congruence_test_collection/points/scroll"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/scroll")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/scroll'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '52',
}
        
        # 原始请求内容
        original_content = {
    'limit': 200,
    'with_payload': True,
    'with_vector': True,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_multivector_updates.test_upload_collection_generators')
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
    test = TestMultivectorUpdatestestUploadCollectionGenerators()
    test.run_tests()
