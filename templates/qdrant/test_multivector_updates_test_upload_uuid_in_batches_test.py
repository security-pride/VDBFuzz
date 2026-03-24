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
logger = logging.getLogger('vdb_fuzzer.test.test_multivector_updates_test_upload_uuid_in_batches')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_multivector_updates.test_upload_uuid_in_batches"
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



class TestMultivectorUpdatestestUploadUuidInBatches:
    """自动生成的VDB模糊测试类 - test_multivector_updates.test_upload_uuid_in_batches"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_multivector_updates.test_upload_uuid_in_batches"
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
    'content-length': '543096',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 100,
    'id_str': [
],
    'text_data': 'f30ae4ce1fba4d8fbc684c8300479266',
    'rand_digit': 1,
    'rand_number': 0.31123,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-02 13:23:09-0900',
    'text_array': [
    'a508935fb8bc4ed6ba2686921a9574f1',
    '58d6f31c8bc44bfc979a3b884610c389',
],
    'words': 'whale mouse',
    'nested': {
    'id': 100,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 9,
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
    'hello',
],
    'word': 'frog',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'fish',
    'snake',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 101,
    'id_str': [
],
    'text_data': 'cea8c36f12234ccdac0f146a88fb9871',
    'rand_digit': 5,
    'rand_number': 0.33205,
    'rand_signed_int': -4,
    'rand_datetime': '2000-08-23T05:06:27.366070',
    'text_array': [
    '2fade8f70ab04ea5b5c76bdeecb6d3c8',
    '0e6e0fa047484b149882ac8cb64360b1',
],
    'words': 'rabbit hippo',
    'nested': {
    'id': 101,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lizard',
    'bird',
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
    'maybe_null': 'rhino',
},
},
    {
    'id': 2,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 102,
    'id_str': [
    '28',
    '29',
    '25',
],
    'text_data': '921c230824c144c4bf893f3b3aa3f9a1',
    'rand_digit': 5,
    'rand_number': 0.03918,
    'rand_signed_int': -7,
    'rand_datetime': '2000-02-04',
    'text_array': [
    'e3185c333df949d4aa6cd9a0a5d2b848',
    'b75f23ab471347ed928dc637556db982',
],
    'words': 'monkey fish',
    'nested': {
    'id': 102,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'hyena',
    'turtle',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'turtle',
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 103,
    'id_str': [
    '05',
    '28',
    '06',
],
    'text_data': 'c93afc87ef534c4b830a0db3d6c39fc1',
    'rand_digit': 1,
    'rand_number': 0.63144,
    'rand_signed_int': 5,
    'rand_datetime': '2000-07-18 03:11:23.474933',
    'text_array': [
    '0eb6defc78f243e7905fa623fb3c0faa',
    'ab926d10c1374dabb8ab3d1429390ac1',
],
    'words': 'sheep bee',
    'nested': {
    'id': 103,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'sloth',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 7,
},
],
},
    'nested_array': [
    [
    6,
],
],
    'two_words': [
    'rhino',
    'dragonfly',
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
    'mixed_type': None,
    'maybe': 'dog',
    'maybe_null': None,
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 104,
    'id_str': [
    '30',
    '07',
],
    'text_data': 'e0da5e7445404149b1c5944275cfde29',
    'rand_digit': 4,
    'rand_number': 0.10302,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-04 01:28',
    'text_array': [
    '88d3269549ea432e9be626dccdee634c',
    'f7c8b3af1f0c4ce6b73c045a10e52b80',
],
    'words': 'tiger gorilla',
    'nested': {
    'id': 104,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'mosquito',
    'scorpion',
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
    'mixed_type': 0.40518,
    'maybe': 'dragonfly',
    'maybe_null': None,
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 105,
    'id_str': [
    '14',
],
    'text_data': '567d12a14dcc4e2eaaf434cb24a1bef5',
    'rand_digit': 9,
    'rand_number': 0.21099,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-26 14:13:59.702874-0300',
    'text_array': [
    '90f8b47e07c3429db61182fe4f50df91',
    'eb4b4ec858934c9286dacce99fa9e8cd',
],
    'words': 'squid monkey',
    'nested': {
    'id': 105,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'bear',
    'lobster',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': [
    50,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'butterfly',
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 106,
    'id_str': [
    '11',
    '11',
    '06',
    '06',
    '18',
],
    'text_data': 'b818e141b23b472081f57a20e57c9fd0',
    'rand_digit': 2,
    'rand_number': 0.88856,
    'rand_signed_int': 8,
    'rand_datetime': '2000-03-11T23:47:06.564922+0500',
    'text_array': [
    '0fcfb7b23ce24c54ba04c1ac68f1de44',
    '99cc537a59ae4ecd8b604f983a4a5511',
],
    'words': 'bear squid',
    'nested': {
    'id': 106,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bee',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
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
],
    'two_words': [
    'camel',
    'sheep',
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
    'mixed_type': 6,
    'maybe': 'monkey',
    'maybe_null': 'lizard',
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 107,
    'id_str': [
    '21',
    '14',
],
    'text_data': '9795d55000c24542ac21a808405505e1',
    'rand_digit': 2,
    'rand_number': 0.58825,
    'rand_signed_int': 9,
    'rand_datetime': '2001-01-19T11:22:50.788200',
    'text_array': [
    '4c98027e98a44a1391c9738266c1b914',
    'db6b06594661401084a333e78a67b407',
],
    'words': 'lion dog',
    'nested': {
    'id': 107,
    'rand_digit': 0,
    'array': [
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
],
    'word': 'frog',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'leopard',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'gorilla',
    'hippo',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'dog',
    'maybe_null': 'frog',
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 108,
    'id_str': [
    '02',
    '26',
    '28',
    '10',
],
    'text_data': '3bfd26394878400eb6ad1c487c234f42',
    'rand_digit': 4,
    'rand_number': 0.27354,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-01T12:10:50+0900',
    'text_array': [
    '8cbc11d9796043769a961e9115e855b2',
    '83c9f8c31c78437a87eede15cc5d00e3',
],
    'words': 'giraffe leopard',
    'nested': {
    'id': 108,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'panda',
    'squid',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'monkey',
    'maybe_null': 'snail',
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 109,
    'id_str': [
    '13',
    '29',
],
    'text_data': 'e53631d3e21843db9c2acfb90646f076',
    'rand_digit': 2,
    'rand_number': 0.17248,
    'rand_signed_int': 10,
    'rand_datetime': '2000-11-18',
    'text_array': [
    '479ea5be05e9413a8e28100c2f5438f0',
    '87f9101a93a94ccfae3fad76a1d4b5d3',
],
    'words': 'fly gorilla',
    'nested': {
    'id': 109,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 6,
},
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
    'gorilla',
    'frog',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': [
    57,
],
    'rand_bool': False,
    'mixed_type': 'dog',
    'maybe': 'lizard',
    'maybe_null': None,
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 110,
    'id_str': [
    '19',
    '02',
    '26',
    '23',
],
    'text_data': 'f71efd72ada64879b46d3dd8ada5dfff',
    'rand_digit': 6,
    'rand_number': 0.15993,
    'rand_signed_int': -1,
    'rand_datetime': '2001-01-01',
    'text_array': [
    '715595da5cfa495eae9a0fd9d900b830',
    '443afe2ffb6745428affc99f914bd64a',
],
    'words': 'pig shark',
    'nested': {
    'id': 110,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sloth',
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'sheep',
    'lobster',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'ape',
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 111,
    'id_str': [
    '25',
    '20',
    '13',
],
    'text_data': 'd0ecbf3c0b734fd4882f78993677f38a',
    'rand_digit': 8,
    'rand_number': 0.25203,
    'rand_signed_int': 8,
    'rand_datetime': '2000-07-29T19:44:21.412903',
    'text_array': [
    'd6089b4ca99841bb908190bde42f0c08',
    '2e3593e15e4d4c0c9c74fec4512ae406',
],
    'words': 'hyena chicken',
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
    'word': 'snail',
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'mouse',
    'dolphin',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'frog',
    'maybe_null': None,
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 112,
    'id_str': [
    '09',
    '03',
    '20',
],
    'text_data': 'a486967f19114bdbad621e509b7fbaf6',
    'rand_digit': 6,
    'rand_number': 0.3692,
    'rand_signed_int': -10,
    'rand_datetime': '2000-11-19 22:32:24+0700',
    'text_array': [
    '85e00113b30c4dd5bdd061816ff75f87',
    '426689fa5f3044ba960f4caa3f3951a2',
],
    'words': 'turtle horse',
    'nested': {
    'id': 112,
    'rand_digit': 5,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 4,
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
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'rhino',
    'shark',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 113,
    'id_str': [
    '28',
    '04',
    '26',
],
    'text_data': '25ad4789da974204a6b658816179995f',
    'rand_digit': 6,
    'rand_number': 0.94623,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-23 01:39:59',
    'text_array': [
    '7880683ed77540028d1e2ceb026f3e5a',
    '3d6706d3f03a4a44bca75436195963db',
],
    'words': 'grasshopper goat',
    'nested': {
    'id': 113,
    'rand_digit': 7,
    'array': [
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
    'word': 'octopus',
    'number': 5,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'horse',
    'number': 4,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'octopus',
    'panda',
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
    'mixed_type': 6,
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 114,
    'id_str': [
    '26',
    '19',
],
    'text_data': '589771facc0f4adab35d2ae94510d03b',
    'rand_digit': 2,
    'rand_number': 0.07593,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-03T05:38:39-0900',
    'text_array': [
    '0b5ce4f370e64291a0cea226404acf7a',
    '21422ef8807a407eb952fbb8bb5c5466',
],
    'words': 'panda rabbit',
    'nested': {
    'id': 114,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 1,
},
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
],
    'word': 'zebra',
    'number': 5,
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
    'word': 'monkey',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'rhino',
    'gorilla',
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
    'mixed_type': False,
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 115,
    'id_str': [
    '07',
    '27',
],
    'text_data': 'cb2e828eee7b44e68f3c5cd223dfa4f6',
    'rand_digit': 3,
    'rand_number': 0.74793,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-02T08:44:07.706694-0700',
    'text_array': [
    'f3e5f92ac9654fc7b1f78b76c32a2f68',
    'cada9c490d854f59aab9174ff27b7704',
],
    'words': 'duck wolf',
    'nested': {
    'id': 115,
    'rand_digit': 1,
    'array': [
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
    'word': 'snail',
    'number': 9,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'butterfly',
    'monkey',
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
    'mixed_type': 'bear',
    'maybe_null': 'bee',
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 116,
    'id_str': [
    '03',
    '10',
    '20',
    '02',
    '21',
],
    'text_data': '11b2778839984bf8b0b5ba488cf88bd9',
    'rand_digit': 6,
    'rand_number': 0.34241,
    'rand_signed_int': 2,
    'rand_datetime': '2000-03-03 02:25:09.763699-0200',
    'text_array': [
    'f17b18637c7a492784d100a4f7e4fe21',
    '60c1ac66fda246c0b6d34377e16b2556',
],
    'words': 'frog dragonfly',
    'nested': {
    'id': 116,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'lizard',
    'turtle',
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
    'mixed_type': 'cat',
    'maybe': 'spider',
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 117,
    'id_str': [
],
    'text_data': '875d2a50b31d422db38a32f2c461bfe7',
    'rand_digit': 3,
    'rand_number': 0.84798,
    'rand_signed_int': 7,
    'rand_datetime': '2000-02-29T15:17:26.297871-0300',
    'text_array': [
    'dbe2433ec6f54a9eaf2a3be1c9b0cb5a',
    'a7541f429bdc4daeac8eb0e1eec15022',
],
    'words': 'fly snail',
    'nested': {
    'id': 117,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    'rand_tuple': [
    19,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'fly',
},
},
    {
    'id': 18,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 118,
    'id_str': [
],
    'text_data': '887196d5c08f42b29428a257228ca636',
    'rand_digit': 0,
    'rand_number': 0.73344,
    'rand_signed_int': -3,
    'rand_datetime': '2001-01-17',
    'text_array': [
    'f0ed9a4b87404ad8b2b6b3a748839a38',
    '038ab7b57cad4585b742acc82d738b76',
],
    'words': 'goat pig',
    'nested': {
    'id': 118,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 9,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    0,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'wolf',
    'kangaroo',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': [
    39,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'wolf',
    'maybe_null': 'tiger',
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
    '13',
    '08',
    '27',
],
    'text_data': '9d14fc27ecbd4634b126b714dc2027a0',
    'rand_digit': 0,
    'rand_number': 0.54572,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-19T07:22:22.517079',
    'text_array': [
    '55adda7969734f7b82ca05bd7da25809',
    '8592d07a7cc5445c931c09a9e41f01fc',
],
    'words': 'jaguar lobster',
    'nested': {
    'id': 119,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lobster',
    'scorpion',
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
    'mixed_type': 1,
    'maybe': 'leopard',
    'maybe_null': 'fish',
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 120,
    'id_str': [
],
    'text_data': '0a2a47e18b154d089cbe5e4ff96e02ea',
    'rand_digit': 1,
    'rand_number': 0.50699,
    'rand_signed_int': 10,
    'rand_datetime': '2000-08-12T13:49:46.139954',
    'text_array': [
    '80ef28cbca1c417d89c84e12f6401abf',
    'e72a0c75aebd420ab8725ada821c0cfa',
],
    'words': 'mouse ape',
    'nested': {
    'id': 120,
    'rand_digit': 6,
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
    'word': 'cow',
    'number': 9,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'fly',
    'dragonfly',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.16389,
    'maybe_null': 'ladybug',
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 121,
    'id_str': [
],
    'text_data': '85c1023c7135414bb60ac649b7e7efd2',
    'rand_digit': 9,
    'rand_number': 0.71657,
    'rand_signed_int': 10,
    'rand_datetime': '2000-03-24T17:54:08',
    'text_array': [
    'e68a512287bf4caf9e36ed80247fc71b',
    '72d1b47f260540c69657b0c0bbd318ff',
],
    'words': 'lobster rabbit',
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
    'word': 'whale',
    'number': 7,
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
    'hello',
],
    'word': 'mosquito',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 7,
},
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'butterfly',
    'lion',
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
    'mixed_type': 'pig',
    'maybe_null': None,
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
    '04',
    '26',
],
    'text_data': 'b5965e3222114793bba1304e9669822b',
    'rand_digit': 4,
    'rand_number': 0.39613,
    'rand_signed_int': 8,
    'rand_datetime': '2000-09-01T08:14:52+0000',
    'text_array': [
    '69172f5e0c7b487b83b3094896682f6d',
    '33afbfc487ee42bd819b90c1738da9c1',
],
    'words': 'fish wolf',
    'nested': {
    'id': 122,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'wolf',
    'lizard',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': [
    0,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'panda',
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 123,
    'id_str': [
    '30',
],
    'text_data': '5f5e9c2a10b7418d9a6f09ba7297d472',
    'rand_digit': 7,
    'rand_number': 0.48163,
    'rand_signed_int': 7,
    'rand_datetime': '2000-01-19 06:10:50+0700',
    'text_array': [
    '54f96170300b4644beef465f5ab430a4',
    'e1f6ea38ad8e449985755ea9e2ea764d',
],
    'words': 'whale kangaroo',
    'nested': {
    'id': 123,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'bear',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'crab',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'snake',
    'kangaroo',
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
    'mixed_type': False,
    'maybe': 'spider',
    'maybe_null': 'frog',
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 124,
    'id_str': [
    '12',
    '09',
],
    'text_data': '43206ffa00a14955829a7b25937d7760',
    'rand_digit': 8,
    'rand_number': 0.17652,
    'rand_signed_int': -8,
    'rand_datetime': '2000-03-24 10:28:04.857535',
    'text_array': [
    '12ef6a5c7d2e46b4883c3afb9f9fe025',
    '427be54c04bd4a8da2f61ac3a5ced394',
],
    'words': 'dolphin lizard',
    'nested': {
    'id': 124,
    'rand_digit': 5,
    'array': [
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
    'word': 'ant',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'frog',
    'fly',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.96241,
    'maybe': 'whale',
    'maybe_null': 'giraffe',
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
    '26',
    '03',
    '21',
    '05',
],
    'text_data': '83011bf710c84fa28173b0e18b74c3d3',
    'rand_digit': 6,
    'rand_number': 0.20259,
    'rand_signed_int': 3,
    'rand_datetime': '2000-10-03T02:11:05.781490',
    'text_array': [
    '3a1b9a81d0614e809a7f7c8030b85cd1',
    '9ee309e567ec4b5599d0751ca362ffd0',
],
    'words': 'giraffe rhino',
    'nested': {
    'id': 125,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 7,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'leopard',
    'dragonfly',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'sloth',
    'maybe_null': 'mosquito',
},
},
    {
    'id': 26,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 126,
    'id_str': [
    '27',
    '21',
    '27',
    '29',
    '23',
],
    'text_data': 'c0c83987129c4c85ad4c3484e3d10285',
    'rand_digit': 5,
    'rand_number': 0.9305,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-10T19:48:10',
    'text_array': [
    '1e1883c9b02b4ffca1a5e722a0239723',
    '2038c9bc22a24972ac730920158c9428',
],
    'words': 'zebra chicken',
    'nested': {
    'id': 126,
    'rand_digit': 6,
    'array': [
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
    'word': 'grasshopper',
    'number': 7,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 3,
},
],
},
    'nested_array': [
    [
    3,
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'kangaroo',
    'butterfly',
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
    'mixed_type': None,
    'maybe': 'octopus',
    'maybe_null': None,
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 127,
    'id_str': [
    '13',
    '10',
    '26',
    '23',
    '11',
],
    'text_data': '154512e470ec448ab1e1ccb59ae4835b',
    'rand_digit': 3,
    'rand_number': 0.67512,
    'rand_signed_int': 4,
    'rand_datetime': '2000-05-21 03:27:27+0900',
    'text_array': [
    '2838d6b5cbeb40988172cbd3829a9731',
    '88ab0586bd3c45e99029e41284f46d94',
],
    'words': 'fly camel',
    'nested': {
    'id': 127,
    'rand_digit': 5,
    'array': [
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
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lion',
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
    45,
],
    'rand_bool': True,
    'mixed_type': 0.52222,
},
},
    {
    'id': 28,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 128,
    'id_str': [
],
    'text_data': '20dec2cc6e7c4e63b1007d6e38319a53',
    'rand_digit': 4,
    'rand_number': 0.84741,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-13 03:47:43+0700',
    'text_array': [
    'b0e0ecefa89a4588a43eb8bdc82cffb3',
    '96cbd2a6aad849a28741493f58551bf0',
],
    'words': 'chicken tiger',
    'nested': {
    'id': 128,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'snake',
    'number': 8,
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
    'tiger',
    'frog',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': [
    49,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'sloth',
    'maybe_null': None,
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
    '06',
],
    'text_data': '691eb34c1b5446b0973a70d2d2127f4c',
    'rand_digit': 9,
    'rand_number': 0.80068,
    'rand_signed_int': 7,
    'rand_datetime': '2000-07-09T10:39:08.518579-0200',
    'text_array': [
    'dafcd5a68b8c40a0b7ec869d7c3cbab4',
    'e1c2513f161741f39b5462405d581c71',
],
    'words': 'sheep turtle',
    'nested': {
    'id': 129,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'lobster',
    'lion',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'mosquito',
    'maybe_null': None,
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 130,
    'id_str': [
    '14',
],
    'text_data': 'fa65cc4c3fdc4d5d90e7536bb5d6a8e4',
    'rand_digit': 3,
    'rand_number': 0.52655,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-19 23:06:41.499812',
    'text_array': [
    '6f9bf98268f842f4bc652e10e656008e',
    '24e0cd39d9854703b5a9b583b9f55cc5',
],
    'words': 'monkey bear',
    'nested': {
    'id': 130,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 3,
},
],
},
    'nested_array': [
    [
    -10,
],
],
    'two_words': [
    'butterfly',
    'ant',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 131,
    'id_str': [
],
    'text_data': '73f3682b9fb940f3937c2e6cb7022ecb',
    'rand_digit': 4,
    'rand_number': 0.61982,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-22',
    'text_array': [
    '00448312ad334bf8b62ef158296bc92c',
    '09c30d66c8fd415c8c1cc36d8dc0c786',
],
    'words': 'butterfly sloth',
    'nested': {
    'id': 131,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 5,
},
],
},
    'nested_array': [
    [
    8,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'fox',
    'wolf',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.61815,
    'maybe_null': 'pig',
},
},
    {
    'id': 32,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 132,
    'id_str': [
    '02',
    '04',
    '26',
],
    'text_data': '027764f53d7046b3be9e7c454bac4a18',
    'rand_digit': 0,
    'rand_number': 0.24627,
    'rand_signed_int': -2,
    'rand_datetime': '2000-04-08 16:34:37.097648+1200',
    'text_array': [
    '8c4b4b07a5fe47a9b0d54b7dc4bf8333',
    '6bf865ad56354becbcd4ec52a09ddf53',
],
    'words': 'pig fox',
    'nested': {
    'id': 132,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'frog',
    'cow',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': [
    87,
],
    'rand_bool': False,
    'mixed_type': False,
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 133,
    'id_str': [
],
    'text_data': '33deff49f90e4c4fa5fdf979a2bd2f31',
    'rand_digit': 3,
    'rand_number': 0.38329,
    'rand_signed_int': -10,
    'rand_datetime': '2000-09-03 12:36:33.771372+0900',
    'text_array': [
    '807f3fa1945e49c9a7795e5da2ea6e4d',
    '3366db0416bf4872afc4630b62acd55e',
],
    'words': 'wolf elephant',
    'nested': {
    'id': 133,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    10,
],
],
    'two_words': [
    'goat',
    'rabbit',
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
    'mixed_type': 'ape',
    'maybe': 'hyena',
    'maybe_null': 'dog',
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 134,
    'id_str': [
    '12',
    '22',
    '26',
    '15',
],
    'text_data': 'cdd25336ef874835b05406e1bee7650d',
    'rand_digit': 4,
    'rand_number': 0.81231,
    'rand_signed_int': -6,
    'rand_datetime': '2000-07-12 20:31:34.440477',
    'text_array': [
    'c2a666fe40954a828d490a586fcb1d9b',
    'dbfa27553fa44859ad1de812aba4a093',
],
    'words': 'fish turtle',
    'nested': {
    'id': 134,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bear',
    'cheetah',
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
    'mixed_type': 0.23801,
},
},
    {
    'id': 35,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 135,
    'id_str': [
    '10',
],
    'text_data': 'd9e7812d8df4489bb5cf9f8742803461',
    'rand_digit': 1,
    'rand_number': 0.79305,
    'rand_signed_int': -1,
    'rand_datetime': '2001-01-12T08:31:44+0400',
    'text_array': [
    '1bcc2f6362a64cd193666ce542343426',
    '83024d4ceef9465885be9ed23030cdf9',
],
    'words': 'crab bee',
    'nested': {
    'id': 135,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
    'number': 2,
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
    'hello',
],
    'word': 'scorpion',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'tiger',
    'dog',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'snail',
    'maybe_null': None,
},
},
    {
    'id': 36,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 136,
    'id_str': [
    '01',
    '08',
],
    'text_data': '70e7b81225c54226bdd7e05ff6c916b6',
    'rand_digit': 5,
    'rand_number': 0.96775,
    'rand_signed_int': -5,
    'rand_datetime': '2001-01-03 20:04',
    'text_array': [
    '82825b6af26e40e7ae384545570128c4',
    '218ce42cd09f4e12ae8809ae32e593c8',
],
    'words': 'rhino ladybug',
    'nested': {
    'id': 136,
    'rand_digit': 6,
    'array': [
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
    'word': 'scorpion',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fox',
    'horse',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.6738,
    'maybe': 'frog',
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
    '22',
],
    'text_data': '170c998985174de3969f9f8eb1250f4e',
    'rand_digit': 0,
    'rand_number': 0.93424,
    'rand_signed_int': 5,
    'rand_datetime': '2000-08-24T04:20:39.551464-0800',
    'text_array': [
    'c3faa8d1e3fc45bf8031de1e9e01ea65',
    '8563ed54d8974fa1992cfb87f862ae28',
],
    'words': 'tiger chicken',
    'nested': {
    'id': 137,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'giraffe',
    'number': 9,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'scorpion',
    'gorilla',
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
    'mixed_type': 'fish',
    'maybe': 'octopus',
    'maybe_null': 'grasshopper',
},
},
    {
    'id': 38,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 138,
    'id_str': [
],
    'text_data': '9e03b2f010c94d1c9a0d4d1a91a39da3',
    'rand_digit': 2,
    'rand_number': 0.62496,
    'rand_signed_int': -8,
    'rand_datetime': '2000-05-23 11:45',
    'text_array': [
    '4b4db31260444e6ca03a52111ba05fda',
    'ffeefc3350c7463287942f3115e57626',
],
    'words': 'duck butterfly',
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
    'word': 'giraffe',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'crab',
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
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'ladybug',
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 139,
    'id_str': [
    '03',
    '04',
],
    'text_data': 'ecb719279884441bafb7c7b4f54e4e50',
    'rand_digit': 6,
    'rand_number': 0.50733,
    'rand_signed_int': 9,
    'rand_datetime': '2000-09-24T11:53:08-0200',
    'text_array': [
    'ca26ce3d10a4478eb5bbd57f4d6e54e9',
    'e8fa868b8cbd4bb4bfbaf42098225838',
],
    'words': 'lion ape',
    'nested': {
    'id': 139,
    'rand_digit': 2,
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
],
    'word': 'chicken',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'chicken',
    'fox',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'mouse',
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 140,
    'id_str': [
    '24',
    '30',
],
    'text_data': '0f50ef253c75464485bc18e502c23fe7',
    'rand_digit': 1,
    'rand_number': 0.83655,
    'rand_signed_int': 3,
    'rand_datetime': '2000-09-11 13:07:41.784643',
    'text_array': [
    'a79b6d9cc9d54efe807b52a2c3738ac8',
    'f83fd2e127c54bcfbddf86773ceac2a4',
],
    'words': 'pig whale',
    'nested': {
    'id': 140,
    'rand_digit': 6,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'spider',
    'rhino',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': [
    2,
],
    'rand_bool': False,
    'mixed_type': 3,
    'maybe': 'sheep',
    'maybe_null': None,
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 141,
    'id_str': [
    '05',
    '30',
    '12',
    '30',
    '15',
],
    'text_data': 'a8633a2243734245afb0c5d7b9b82332',
    'rand_digit': 9,
    'rand_number': 0.98009,
    'rand_signed_int': 9,
    'rand_datetime': '2000-02-03T01:16:59-1100',
    'text_array': [
    'ebc3c23b4bbf48049f2df486a0779ea1',
    '2d1d5bd6f2a545458531803f2924ca1a',
],
    'words': 'lobster sloth',
    'nested': {
    'id': 141,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ape',
    'dog',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': [
    12,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 142,
    'id_str': [
    '28',
],
    'text_data': 'dd11465847644204906596c94506f6d2',
    'rand_digit': 2,
    'rand_number': 0.04648,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-11T06:33:13+0000',
    'text_array': [
    'dd35b336fbf2439eb8e1d8b511d53a4a',
    '6be011f9b9c54ce7a089e2cc3743b77a',
],
    'words': 'sloth whale',
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
    'word': 'kangaroo',
    'number': 7,
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
    {
    'nested_empty': [
    'hello',
],
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
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'crab',
    'panda',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'sheep',
    'maybe_null': None,
},
},
    {
    'id': 43,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 143,
    'id_str': [
    '10',
    '17',
    '18',
],
    'text_data': 'f05575768be147138e585a80c523eac5',
    'rand_digit': 8,
    'rand_number': 0.31684,
    'rand_signed_int': -7,
    'rand_datetime': '2000-02-24 00:20:43.504980+1100',
    'text_array': [
    'eadf8edd3fca45b388664a9cc62e990a',
    '25358813d59c4ef0960a028534b8a33e',
],
    'words': 'frog cheetah',
    'nested': {
    'id': 143,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 5,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'squid',
    'koala',
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
    'mixed_type': None,
    'maybe': 'bear',
    'maybe_null': None,
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 144,
    'id_str': [
],
    'text_data': 'db482c929bd844a9888cffbb3ecc8463',
    'rand_digit': 2,
    'rand_number': 0.38086,
    'rand_signed_int': 1,
    'rand_datetime': '2000-12-15 17:29:58-0500',
    'text_array': [
    'b1e04214fbba4414ad72fae5324fc2c2',
    'b69accad404345f8adc8f6cab009a027',
],
    'words': 'ladybug lion',
    'nested': {
    'id': 144,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'frog',
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
    59,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'bee',
    'maybe_null': None,
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 145,
    'id_str': [
],
    'text_data': '25d7f943b676464d8daa8a36f53900bb',
    'rand_digit': 8,
    'rand_number': 0.99897,
    'rand_signed_int': 9,
    'rand_datetime': '2000-06-17T18:06:27',
    'text_array': [
    'be808c70ca6742bd9aea550877de8d07',
    '89436884fef947ed8326e607bb9152d3',
],
    'words': 'sheep shark',
    'nested': {
    'id': 145,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 5,
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
    'mixed_type': 'monkey',
    'maybe': 'koala',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
    '26',
],
    'text_data': 'e0dce2fa8d2a450eb92ed503d427d6ee',
    'rand_digit': 4,
    'rand_number': 0.79913,
    'rand_signed_int': 1,
    'rand_datetime': '2000-08-03T19:02:20+0300',
    'text_array': [
    '26cd11ca772a491aa74efb26d085c7f9',
    'ad67de0a1b344a799052cfd9d80c93c2',
],
    'words': 'frog octopus',
    'nested': {
    'id': 146,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'spider',
    'shark',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': 'monkey',
},
},
    {
    'id': 47,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 147,
    'id_str': [
    '15',
    '10',
    '26',
    '29',
    '25',
],
    'text_data': '179930a0d11f40c492a1a889dd6e6ad6',
    'rand_digit': 7,
    'rand_number': 0.0936,
    'rand_signed_int': 2,
    'rand_datetime': '2000-10-11',
    'text_array': [
    '8bcbe3d0ce8847468d88917cf9397801',
    '44cb1f9fcf7349cfa7d64fe787d28c1b',
],
    'words': 'dragonfly shark',
    'nested': {
    'id': 147,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'rabbit',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'bee',
    'bee',
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
    'mixed_type': 2,
},
},
    {
    'id': 48,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 148,
    'id_str': [
    '01',
],
    'text_data': 'fb68c331189d41fa92d43066053ee9be',
    'rand_digit': 0,
    'rand_number': 0.30366,
    'rand_signed_int': 4,
    'rand_datetime': '2000-04-01T00:41:25.227808-04:00',
    'text_array': [
    'f31fff32a752468489adb9b375dae80c',
    'b80ea0f5f42d47d59ad7079995f14f93',
],
    'words': 'hyena dolphin',
    'nested': {
    'id': 148,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 1,
},
],
},
    'nested_array': [
    [
    8,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'dog',
    'zebra',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': [
    81,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 149,
    'id_str': [
    '11',
    '07',
],
    'text_data': '13459e51a22d4893b7fbb5a0bdc2f1fc',
    'rand_digit': 3,
    'rand_number': 0.28782,
    'rand_signed_int': -5,
    'rand_datetime': '2000-06-26 20:22:30-1200',
    'text_array': [
    'abf140d0e7fb4c71928cef88c842116a',
    '05f97d3977554b7a8c96e1c1532f5c04',
],
    'words': 'panda scorpion',
    'nested': {
    'id': 149,
    'rand_digit': 6,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 10,
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
    'word': 'cow',
    'number': 2,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_4,5__',
    'two_words': [
    'giraffe',
    'butterfly',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': [
    56,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'mosquito',
    'maybe_null': 'whale',
},
},
    {
    'id': 50,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 150,
    'id_str': [
    '28',
    '23',
    '05',
    '27',
],
    'text_data': '4ecbc2b9a67041309005c5b99de8fd03',
    'rand_digit': 9,
    'rand_number': 0.10348,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-14T22:13:47',
    'text_array': [
    '817eacd0657c437389a185bd869280c0',
    '93e927b5abad4b939ff0fbdd4eb0b55a',
],
    'words': 'hippo tiger',
    'nested': {
    'id': 150,
    'rand_digit': 7,
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
    'hello',
],
    'word': 'dolphin',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'goat',
    'shark',
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
    'mixed_type': 5,
    'maybe_null': 'dolphin',
},
},
    {
    'id': 51,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 151,
    'id_str': [
    '16',
    '24',
    '18',
    '15',
    '17',
],
    'text_data': 'a7282c3cfbe1472fa5a4f8ad6a061ad6',
    'rand_digit': 4,
    'rand_number': 0.05918,
    'rand_signed_int': -7,
    'rand_datetime': '2000-06-27T04:35:36',
    'text_array': [
    '985f8942df79449bbd12776ebdf21ec2',
    '954a998772b641a18cc4420001dd4224',
],
    'words': 'ape octopus',
    'nested': {
    'id': 151,
    'rand_digit': 4,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'butterfly',
    'kangaroo',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': [
    20,
],
    'rand_bool': False,
    'mixed_type': 0.81364,
    'maybe': 'cat',
    'maybe_null': 'koala',
},
},
    {
    'id': 52,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 152,
    'id_str': [
    '05',
    '27',
],
    'text_data': '03a6bf86ee614122aab63aa89b2e3e32',
    'rand_digit': 6,
    'rand_number': 0.88842,
    'rand_signed_int': -1,
    'rand_datetime': '2000-03-15 01:14',
    'text_array': [
    'd73b4872a0fd43b687c4327341bc2d48',
    '86c3b4348830402ea1ff5079a7a1a40f',
],
    'words': 'shark zebra',
    'nested': {
    'id': 152,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 3,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'deer',
    'kangaroo',
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
    'mixed_type': False,
    'maybe': 'spider',
    'maybe_null': 'turtle',
},
},
    {
    'id': 53,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 153,
    'id_str': [
    '27',
],
    'text_data': 'b2da60d35921496795836cf2274988be',
    'rand_digit': 0,
    'rand_number': 0.85992,
    'rand_signed_int': -7,
    'rand_datetime': '2000-09-14T21:08:02.008160',
    'text_array': [
    '5cc1e83389ea48ee8f2292b05cf229f6',
    '3df05e02924b49fc9a74fb2a980f2a17',
],
    'words': 'rhino lobster',
    'nested': {
    'id': 153,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -4,
],
],
    'two_words': [
    'turtle',
    'octopus',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'octopus',
    'maybe_null': 'crab',
},
},
    {
    'id': 54,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 154,
    'id_str': [
    '19',
    '21',
    '23',
    '27',
],
    'text_data': 'c03fb13d1e844301a59d12fe54cf1ea7',
    'rand_digit': 3,
    'rand_number': 0.12961,
    'rand_signed_int': 4,
    'rand_datetime': '2000-07-20 22:38:43.401289+1200',
    'text_array': [
    'd865c32833824caeb95764deac56d877',
    '8d77f4ec4c3740ad94f26cbbe64c1ab3',
],
    'words': 'fish hippo',
    'nested': {
    'id': 154,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'hippo',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'leopard',
    'zebra',
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
    'maybe_null': 'deer',
},
},
    {
    'id': 55,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 155,
    'id_str': [
    '10',
    '22',
],
    'text_data': '4f23a87213c64eeaa98de23f50360cbb',
    'rand_digit': 8,
    'rand_number': 0.55918,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-26T02:35:38.470449+12:00',
    'text_array': [
    'ff80e944f99f4ba19001a21945234970',
    'f98e6f0c9ca14d28a3ff15bcb97d59a4',
],
    'words': 'bird tiger',
    'nested': {
    'id': 155,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'fly',
    'giraffe',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': [
    10,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'crab',
    'maybe_null': 'lion',
},
},
    {
    'id': 56,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 156,
    'id_str': [
    '28',
    '22',
    '20',
],
    'text_data': 'a2114825bbaa4c318b3125c7cc3fcfb6',
    'rand_digit': 8,
    'rand_number': 0.96024,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-27T01:40:44.901808+04:00',
    'text_array': [
    '0fc0b04e3c6d453082519f6319cddb8e',
    '5fa973850ec14ff0a10e72ceed2a2d23',
],
    'words': 'ant jaguar',
    'nested': {
    'id': 156,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 7,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'whale',
    'dolphin',
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
    'mixed_type': 'squid',
    'maybe': 'giraffe',
},
},
    {
    'id': 57,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 157,
    'id_str': [
    '14',
],
    'text_data': 'b3a9299d87b24a359b14898f8eb7ba11',
    'rand_digit': 7,
    'rand_number': 0.79724,
    'rand_signed_int': -5,
    'rand_datetime': '2000-03-24',
    'text_array': [
    'c6706531b96a40a7b19fe97dfa367e82',
    '14fce1b67e38434b9e9b37fbe2e6f5ca',
],
    'words': 'camel elephant',
    'nested': {
    'id': 157,
    'rand_digit': 4,
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
],
    'word': 'mosquito',
    'number': 7,
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
    [
],
    [
    -4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'rhino',
    'jaguar',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
},
},
    {
    'id': 58,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 158,
    'id_str': [
    '02',
    '05',
    '29',
    '21',
    '24',
],
    'text_data': '1551538d3390459aa9f2f9353f4c6732',
    'rand_digit': 4,
    'rand_number': 0.06062,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-08T13:17:02.619073+0400',
    'text_array': [
    '42f04d03f4dd463fab1939f23f035ce4',
    'de718d014d6e4f63b08d272366afd9a6',
],
    'words': 'horse hyena',
    'nested': {
    'id': 158,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
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
    'hello',
],
    'word': 'bear',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'dog',
    'snake',
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
    'mixed_type': 'spider',
    'maybe': 'monkey',
    'maybe_null': 'zebra',
},
},
    {
    'id': 59,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 159,
    'id_str': [
    '17',
    '18',
    '21',
],
    'text_data': '26ba0c6a1f6b495fa29be8d24fc1f948',
    'rand_digit': 4,
    'rand_number': 0.25901,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-06T01:44:45-0600',
    'text_array': [
    'f4e53387044c4fb4b411540b27fae889',
    '98bde67f97c64d6b938a40094640b22a',
],
    'words': 'octopus squid',
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
    'word': 'bear',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'jaguar',
    'tiger',
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
    'mixed_type': 5,
    'maybe': 'ant',
    'maybe_null': 'koala',
},
},
    {
    'id': 60,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 160,
    'id_str': [
],
    'text_data': '417bfe2168b34682b990fef6a168c55f',
    'rand_digit': 8,
    'rand_number': 0.52549,
    'rand_signed_int': 9,
    'rand_datetime': '2000-10-29T10:01:39.043975+05:00',
    'text_array': [
    '235731d08e754a86a18d37a68b51a363',
    '1861d25a1ad94da8b73e3f209b700f2d',
],
    'words': 'horse lobster',
    'nested': {
    'id': 160,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'bear',
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'shark',
    'number': 9,
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
],
    'two_words': [
    'whale',
    'sloth',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': [
    64,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 61,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 161,
    'id_str': [
    '17',
    '07',
],
    'text_data': '0ca44e83f79845dc98bb4f3476b8605c',
    'rand_digit': 9,
    'rand_number': 0.47224,
    'rand_signed_int': 3,
    'rand_datetime': '2000-10-18T10:44:01.510814-08:00',
    'text_array': [
    '80f0746521084c65b50a4d8a93644039',
    'd993308bd489415898eb665e06eaed5a',
],
    'words': 'chicken lizard',
    'nested': {
    'id': 161,
    'rand_digit': 1,
    'array': [
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
],
    'word': 'sloth',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'crab',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'chicken',
    'koala',
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
    'mixed_type': 'turtle',
    'maybe': 'fox',
    'maybe_null': 'chicken',
},
},
    {
    'id': 62,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 162,
    'id_str': [
    '25',
    '17',
    '12',
],
    'text_data': 'c7332e20a6da425b84e2e56c36a82cfe',
    'rand_digit': 2,
    'rand_number': 0.0816,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-16 09:47',
    'text_array': [
    '33671a3d97f141ceb4ac8802ab2431cf',
    'de617c52979441bebc2a06afc108d168',
],
    'words': 'panda horse',
    'nested': {
    'id': 162,
    'rand_digit': 3,
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
    'hello',
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
    'word': 'whale',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'elephant',
    'panda',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'jaguar',
},
},
    {
    'id': 63,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 163,
    'id_str': [
    '13',
    '16',
    '18',
    '05',
],
    'text_data': '79de684232af459986bfea27debe9446',
    'rand_digit': 7,
    'rand_number': 0.05325,
    'rand_signed_int': 8,
    'rand_datetime': '2000-04-19T09:00:55+1100',
    'text_array': [
    '44cfcb0a330d44949ae4325723f76e71',
    '672ada37eea84dd6ab807ad34bbedeb4',
],
    'words': 'ladybug tiger',
    'nested': {
    'id': 163,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snail',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'rhino',
    'dog',
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
    'mixed_type': True,
    'maybe': 'grasshopper',
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
        """测试请求 2 - PUT http://localhost:6333/collections/congruence_test_collection/points?wait=true"""
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
    'content-length': '865339',
}
        
        # 原始请求内容
        original_content = {
    'batch': {
    'ids': [
    '74beb374-c9b5-4aab-899b-57a12d727301',
    'b2434b57-0dc3-4030-85f2-ba631da0552e',
    '882a6ac5-99c6-4408-ada0-cfdc972ae7ae',
    'c18dc79a-a933-4613-b9cc-2098f847af91',
    '85d868c2-5574-488b-95aa-33a99e7b8f18',
    '5cdcde55-45b8-4ce4-ad1d-aec41dcec374',
    '2f0dff9e-8394-4623-8221-4e0cdb1cc09d',
    '6322b8a2-9298-4f2c-a4b9-d2d21cd317b4',
    'c67e96f1-cb28-4501-bb35-82ae29ae86f8',
    '34d473f2-757d-4b37-9e9e-0f7ad1017d1f',
    'e8386748-98a5-4191-9926-376f3b0a585c',
    '8bdf25ed-3cae-4fbd-a030-8e33b886062e',
    '5314e450-293e-462e-b11d-a34581bfbd79',
    '0ebd414c-2b50-4564-a1e7-fd6fc7fe57b0',
    '28582fbd-ff04-4767-8b9a-fd1b4a0abdb5',
    '9c4c917f-bbd2-4d76-9dcc-7bfb00a23bf5',
    '85ed31d6-da1a-47df-ac44-7911c440bd1b',
    'a51ed41c-a59a-4f84-bda8-56e3932a624c',
    '59ab38d6-06a3-4ebc-a47e-696a5018cb0d',
    '25a8e276-a28a-423c-a394-305a64921024',
    '5c015d9d-869e-4bac-91a3-d2f50006fff0',
    'd3bd8761-62eb-458c-8081-c337bb51bbd0',
    'a217e77c-7dcd-4f66-bb46-0a6d2652c7ae',
    '55865278-00fc-4ee7-85fe-213525a4d3e9',
    'ed8196d4-9603-4bef-91c5-05845f950591',
    'e92f319b-0326-4a47-9539-c339df0fbf34',
    '642b6b1b-e304-407b-9c42-80cfce3302d6',
    'a65012a4-0cf5-46f7-b5ad-db2593ecd60b',
    '8c8f6c09-79cc-451f-8d80-7ed3520126d4',
    'db385ef0-970c-4cc3-ae52-763457b0b581',
    '5750e930-e62d-42cb-8936-1d6413602d6a',
    'f5fb14da-cc6e-40fe-97a1-ac389cdab9da',
    'e0c5cc14-539c-4143-bd1b-b40a258dd02a',
    '54daf94a-92cc-4528-83ca-ff7e4f3b3d61',
    '762066fe-f162-4dd3-b7ff-26e16dc133ce',
    'e05672bd-5dee-43f3-96e0-14c71d9c0faf',
    'efc40266-b074-4c0a-8bca-ca804be08a47',
    '2a2fc054-0aa3-48fa-8d7f-c96997b85fee',
    '7e824a89-e325-4815-9a70-2c6a8a7f375e',
    'd566974b-2634-40b5-a447-687bd8213532',
    'ef48dae0-a78f-4de4-ae3f-7428e85593cf',
    '5b5588d0-4c89-4bdc-b02e-562151a84dc3',
    '0f2c3e0a-4bfc-4177-b2fc-b5abd6fb1fe3',
    '66a9db97-08ea-470f-af8f-efe548f770d8',
    '05be6fb7-2142-4801-8e77-ddb24d0375cf',
    '12fc413a-03ae-4aba-83df-cf77f9cd53fa',
    '49cdd80a-e0b8-40a5-8c97-1c3a6fb817fa',
    '77307577-82b0-434c-b2f9-e5714c3953a9',
    'db818e1f-463f-4b18-a9ba-aa6535d0d957',
    '82f51068-3e4d-4b14-8e49-5ba676f17646',
    '243a5e20-7f21-496c-ac8e-8411593a83d1',
    'dc30f368-c45b-448e-a6b9-5050d1b52ed8',
    '78166f1b-f034-439f-85d6-a65b1360cb04',
    '2f640f33-7f57-4f97-9ac4-0be094f876c6',
    'ffadcc20-be03-4bc5-b154-b1a394d3d0b7',
    '85b2c50f-5527-4fde-930e-7dc0c2033395',
    '6722b036-d78c-4626-bb7a-18c48ddb3daf',
    'ca3ec629-99f0-4fa9-b091-e07bf32c5b5b',
    '287cf9e4-26bf-472c-9b62-459e0c85e097',
    'd7e1c7df-b4cc-46ac-9741-f235ef33e706',
    '6b87b81d-f853-4b45-b3ff-d59b4baaba92',
    'fefaf04f-5346-48ff-b0fe-e747dfe11046',
    '8132a32a-67e2-4097-bea0-9ded2ed7fa66',
    'ecae47f0-f43a-43ae-8de6-8340d6069bf3',
    '2841fc8b-fb2d-48a7-8939-182dcd9fb726',
    '7ed2680d-f516-4538-bcfe-f953295f9ecf',
    '6011aad3-a525-4721-bfa3-0d46f23a5c2b',
    '9fd64e5d-24e5-41be-8998-2106073840ee',
    '03e69419-3636-43c7-837b-0eec88e1e358',
    '4a44839d-b53e-47f1-95d4-48746585ba25',
    'fd218410-3c6d-42b5-960f-4b81d157d915',
    '00291aef-ad91-4a31-bac1-3210e8f6ed53',
    '51f84268-3bd1-4c99-9bed-66e4c93dea45',
    '286c021b-b41b-4dbd-9a0e-46957856f468',
    '921afb48-bd7e-49f8-b10c-a58779f50cae',
    'f9239282-fb23-4e1a-aad9-e557d275f434',
    '4b90e16d-5206-4da3-b8fd-c0417a5cc411',
    '61125754-c952-45f3-9c21-48f4d1fc2c32',
    '4f67d3dd-8f11-44e2-b8db-692c473d3fed',
    '6afdba7b-2d29-48e5-aa9d-7679051a5c98',
    'cb08bf3d-0c9c-4c99-b088-d05b27b9be2e',
    'bab2e58a-b6b4-477e-933c-5ff480c0f4bc',
    '76bd8d10-ffda-470c-9d28-415d052ed03c',
    '541628ba-fa85-4cc6-9110-45b0a8e8e8c7',
    'e9b333a1-d34c-4cc3-88e8-4f784de27098',
    '28e870e0-7425-4ea7-a333-2ea0a8bab88a',
    'd91f2b15-f622-47af-b37b-2d1b86b30b09',
    '47d2fd5a-a900-46e9-944f-5d01c47c3ba8',
    '4fc29c57-4376-4a17-b66b-195c36323685',
    'db045664-bb19-46f0-ac7a-4bbdba3b16d0',
    'a5d473e7-ad86-4828-9460-898c56400fee',
    '7718313c-a66a-4efa-bfe5-9fd4722532a5',
    '3b2184b5-98fa-4c77-9077-00bbdbfca765',
    '59254438-dedb-487e-99a8-a213fa2152f7',
    'adcf0600-bc0f-4daf-a0e0-51c30fcc7b0f',
    '1b7cc2c9-e5ac-49b6-ac30-46daf06bcc62',
    '2994e176-1152-47e5-aa6e-fff73f0015d3',
    '65ebc7cf-6531-46d5-abb2-6cf6996e0041',
    '644e6f83-d350-4bc6-b1d1-9f9a59f3ac15',
    '84ff5eb7-3063-4ee0-80c2-594e41e8a235',
],
    'vectors': {
    'multi-text': [
    '__FLOAT_MULTI_DIM_4,50__',
    '__FLOAT_MULTI_DIM_4,50__',
    '__FLOAT_MULTI_DIM_4,50__',
    '__FLOAT_MULTI_DIM_9,50__',
    '__FLOAT_MULTI_DIM_6,50__',
    '__FLOAT_MULTI_DIM_10,50__',
    '__FLOAT_MULTI_DIM_10,50__',
    '__FLOAT_MULTI_DIM_6,50__',
    self.mutator.generate_float_array(dimension=50, normalized=True),
    '__FLOAT_MULTI_DIM_7,50__',
    '__FLOAT_MULTI_DIM_8,50__',
    '__FLOAT_MULTI_DIM_4,50__',
    '__FLOAT_MULTI_DIM_4,50__',
    '__FLOAT_MULTI_DIM_7,50__',
    '__FLOAT_MULTI_DIM_6,50__',
    '__FLOAT_MULTI_DIM_5,50__',
    '__FLOAT_MULTI_DIM_6,50__',
    '__FLOAT_MULTI_DIM_7,50__',
    '__FLOAT_MULTI_DIM_8,50__',
    '__FLOAT_MULTI_DIM_4,50__',
    '__FLOAT_MULTI_DIM_7,50__',
    '__FLOAT_MULTI_DIM_4,50__',
    '__FLOAT_MULTI_DIM_8,50__',
    '__FLOAT_MULTI_DIM_6,50__',
    '__FLOAT_MULTI_DIM_7,50__',
    '__FLOAT_MULTI_DIM_7,50__',
    '__FLOAT_MULTI_DIM_7,50__',
    '__FLOAT_MULTI_DIM_4,50__',
    '__FLOAT_MULTI_DIM_6,50__',
    '__FLOAT_MULTI_DIM_9,50__',
    '__FLOAT_MULTI_DIM_3,50__',
    '__FLOAT_MULTI_DIM_6,50__',
    '__FLOAT_MULTI_DIM_10,50__',
    '__FLOAT_MULTI_DIM_7,50__',
    '__FLOAT_MULTI_DIM_10,50__',
    '__FLOAT_MULTI_DIM_2,50__',
    '__FLOAT_MULTI_DIM_9,50__',
    '__FLOAT_MULTI_DIM_7,50__',
    '__FLOAT_MULTI_DIM_8,50__',
    '__FLOAT_MULTI_DIM_4,50__',
    '__FLOAT_MULTI_DIM_2,50__',
    '__FLOAT_MULTI_DIM_10,50__',
    '__FLOAT_MULTI_DIM_3,50__',
    '__FLOAT_MULTI_DIM_8,50__',
    self.mutator.generate_float_array(dimension=50, normalized=True),
    '__FLOAT_MULTI_DIM_7,50__',
    '__FLOAT_MULTI_DIM_2,50__',
    self.mutator.generate_float_array(dimension=50, normalized=True),
    self.mutator.generate_float_array(dimension=50, normalized=True),
    '__FLOAT_MULTI_DIM_2,50__',
    '__FLOAT_MULTI_DIM_5,50__',
    '__FLOAT_MULTI_DIM_4,50__',
    '__FLOAT_MULTI_DIM_2,50__',
    '__FLOAT_MULTI_DIM_10,50__',
    '__FLOAT_MULTI_DIM_7,50__',
    '__FLOAT_MULTI_DIM_10,50__',
    '__FLOAT_MULTI_DIM_2,50__',
    '__FLOAT_MULTI_DIM_9,50__',
    '__FLOAT_MULTI_DIM_6,50__',
    '__FLOAT_MULTI_DIM_7,50__',
    '__FLOAT_MULTI_DIM_2,50__',
    '__FLOAT_MULTI_DIM_9,50__',
    '__FLOAT_MULTI_DIM_6,50__',
    '__FLOAT_MULTI_DIM_2,50__',
    '__FLOAT_MULTI_DIM_6,50__',
    '__FLOAT_MULTI_DIM_8,50__',
    '__FLOAT_MULTI_DIM_5,50__',
    '__FLOAT_MULTI_DIM_6,50__',
    '__FLOAT_MULTI_DIM_6,50__',
    '__FLOAT_MULTI_DIM_5,50__',
    '__FLOAT_MULTI_DIM_10,50__',
    self.mutator.generate_float_array(dimension=50, normalized=True),
    '__FLOAT_MULTI_DIM_7,50__',
    self.mutator.generate_float_array(dimension=50, normalized=True),
    '__FLOAT_MULTI_DIM_8,50__',
    '__FLOAT_MULTI_DIM_2,50__',
    '__FLOAT_MULTI_DIM_8,50__',
    '__FLOAT_MULTI_DIM_4,50__',
    '__FLOAT_MULTI_DIM_10,50__',
    '__FLOAT_MULTI_DIM_4,50__',
    '__FLOAT_MULTI_DIM_4,50__',
    '__FLOAT_MULTI_DIM_8,50__',
    '__FLOAT_MULTI_DIM_9,50__',
    '__FLOAT_MULTI_DIM_6,50__',
    '__FLOAT_MULTI_DIM_2,50__',
    '__FLOAT_MULTI_DIM_10,50__',
    '__FLOAT_MULTI_DIM_8,50__',
    '__FLOAT_MULTI_DIM_5,50__',
    '__FLOAT_MULTI_DIM_4,50__',
    '__FLOAT_MULTI_DIM_10,50__',
    '__FLOAT_MULTI_DIM_7,50__',
    '__FLOAT_MULTI_DIM_3,50__',
    '__FLOAT_MULTI_DIM_9,50__',
    '__FLOAT_MULTI_DIM_4,50__',
    '__FLOAT_MULTI_DIM_9,50__',
    '__FLOAT_MULTI_DIM_6,50__',
    '__FLOAT_MULTI_DIM_7,50__',
    '__FLOAT_MULTI_DIM_10,50__',
    self.mutator.generate_float_array(dimension=50, normalized=True),
    '__FLOAT_MULTI_DIM_3,50__',
],
    'multi-image': [
    '__FLOAT_MULTI_DIM_8,100__',
    '__FLOAT_MULTI_DIM_10,100__',
    '__FLOAT_MULTI_DIM_9,100__',
    '__FLOAT_MULTI_DIM_8,100__',
    '__FLOAT_MULTI_DIM_4,100__',
    self.mutator.generate_float_array(dimension=100, normalized=True),
    '__FLOAT_MULTI_DIM_3,100__',
    '__FLOAT_MULTI_DIM_6,100__',
    '__FLOAT_MULTI_DIM_8,100__',
    '__FLOAT_MULTI_DIM_10,100__',
    '__FLOAT_MULTI_DIM_7,100__',
    self.mutator.generate_float_array(dimension=100, normalized=True),
    '__FLOAT_MULTI_DIM_7,100__',
    '__FLOAT_MULTI_DIM_2,100__',
    '__FLOAT_MULTI_DIM_6,100__',
    '__FLOAT_MULTI_DIM_7,100__',
    '__FLOAT_MULTI_DIM_5,100__',
    '__FLOAT_MULTI_DIM_7,100__',
    '__FLOAT_MULTI_DIM_7,100__',
    '__FLOAT_MULTI_DIM_6,100__',
    '__FLOAT_MULTI_DIM_5,100__',
    '__FLOAT_MULTI_DIM_4,100__',
    '__FLOAT_MULTI_DIM_2,100__',
    '__FLOAT_MULTI_DIM_3,100__',
    '__FLOAT_MULTI_DIM_6,100__',
    '__FLOAT_MULTI_DIM_5,100__',
    '__FLOAT_MULTI_DIM_6,100__',
    '__FLOAT_MULTI_DIM_3,100__',
    '__FLOAT_MULTI_DIM_9,100__',
    '__FLOAT_MULTI_DIM_6,100__',
    '__FLOAT_MULTI_DIM_7,100__',
    '__FLOAT_MULTI_DIM_5,100__',
    '__FLOAT_MULTI_DIM_6,100__',
    '__FLOAT_MULTI_DIM_3,100__',
    '__FLOAT_MULTI_DIM_6,100__',
    '__FLOAT_MULTI_DIM_7,100__',
    '__FLOAT_MULTI_DIM_2,100__',
    self.mutator.generate_float_array(dimension=100, normalized=True),
    '__FLOAT_MULTI_DIM_8,100__',
    '__FLOAT_MULTI_DIM_4,100__',
    '__FLOAT_MULTI_DIM_7,100__',
    self.mutator.generate_float_array(dimension=100, normalized=True),
    '__FLOAT_MULTI_DIM_10,100__',
    '__FLOAT_MULTI_DIM_4,100__',
    '__FLOAT_MULTI_DIM_10,100__',
    '__FLOAT_MULTI_DIM_6,100__',
    '__FLOAT_MULTI_DIM_6,100__',
    self.mutator.generate_float_array(dimension=100, normalized=True),
    '__FLOAT_MULTI_DIM_10,100__',
    '__FLOAT_MULTI_DIM_7,100__',
    '__FLOAT_MULTI_DIM_4,100__',
    '__FLOAT_MULTI_DIM_10,100__',
    '__FLOAT_MULTI_DIM_5,100__',
    self.mutator.generate_float_array(dimension=100, normalized=True),
    '__FLOAT_MULTI_DIM_7,100__',
    '__FLOAT_MULTI_DIM_8,100__',
    '__FLOAT_MULTI_DIM_6,100__',
    '__FLOAT_MULTI_DIM_5,100__',
    '__FLOAT_MULTI_DIM_4,100__',
    '__FLOAT_MULTI_DIM_6,100__',
    '__FLOAT_MULTI_DIM_5,100__',
    '__FLOAT_MULTI_DIM_7,100__',
    '__FLOAT_MULTI_DIM_2,100__',
    '__FLOAT_MULTI_DIM_5,100__',
    '__FLOAT_MULTI_DIM_9,100__',
    '__FLOAT_MULTI_DIM_8,100__',
    '__FLOAT_MULTI_DIM_10,100__',
    '__FLOAT_MULTI_DIM_7,100__',
    '__FLOAT_MULTI_DIM_7,100__',
    '__FLOAT_MULTI_DIM_6,100__',
    '__FLOAT_MULTI_DIM_9,100__',
    '__FLOAT_MULTI_DIM_5,100__',
    '__FLOAT_MULTI_DIM_10,100__',
    '__FLOAT_MULTI_DIM_2,100__',
    self.mutator.generate_float_array(dimension=100, normalized=True),
    '__FLOAT_MULTI_DIM_10,100__',
    '__FLOAT_MULTI_DIM_10,100__',
    '__FLOAT_MULTI_DIM_9,100__',
    '__FLOAT_MULTI_DIM_8,100__',
    '__FLOAT_MULTI_DIM_2,100__',
    '__FLOAT_MULTI_DIM_9,100__',
    '__FLOAT_MULTI_DIM_2,100__',
    '__FLOAT_MULTI_DIM_10,100__',
    '__FLOAT_MULTI_DIM_10,100__',
    '__FLOAT_MULTI_DIM_4,100__',
    '__FLOAT_MULTI_DIM_5,100__',
    '__FLOAT_MULTI_DIM_8,100__',
    '__FLOAT_MULTI_DIM_9,100__',
    '__FLOAT_MULTI_DIM_10,100__',
    self.mutator.generate_float_array(dimension=100, normalized=True),
    self.mutator.generate_float_array(dimension=100, normalized=True),
    '__FLOAT_MULTI_DIM_9,100__',
    '__FLOAT_MULTI_DIM_9,100__',
    self.mutator.generate_float_array(dimension=100, normalized=True),
    '__FLOAT_MULTI_DIM_5,100__',
    '__FLOAT_MULTI_DIM_5,100__',
    '__FLOAT_MULTI_DIM_9,100__',
    '__FLOAT_MULTI_DIM_10,100__',
    '__FLOAT_MULTI_DIM_6,100__',
    '__FLOAT_MULTI_DIM_3,100__',
],
    'multi-code': [
    '__FLOAT_MULTI_DIM_4,80__',
    '__FLOAT_MULTI_DIM_9,80__',
    '__FLOAT_MULTI_DIM_6,80__',
    '__FLOAT_MULTI_DIM_3,80__',
    '__FLOAT_MULTI_DIM_6,80__',
    '__FLOAT_MULTI_DIM_10,80__',
    '__FLOAT_MULTI_DIM_10,80__',
    '__FLOAT_MULTI_DIM_8,80__',
    '__FLOAT_MULTI_DIM_9,80__',
    '__FLOAT_MULTI_DIM_9,80__',
    '__FLOAT_MULTI_DIM_3,80__',
    '__FLOAT_MULTI_DIM_7,80__',
    '__FLOAT_MULTI_DIM_10,80__',
    '__FLOAT_MULTI_DIM_4,80__',
    '__FLOAT_MULTI_DIM_7,80__',
    '__FLOAT_MULTI_DIM_8,80__',
    '__FLOAT_MULTI_DIM_5,80__',
    '__FLOAT_MULTI_DIM_5,80__',
    '__FLOAT_MULTI_DIM_5,80__',
    '__FLOAT_MULTI_DIM_3,80__',
    '__FLOAT_MULTI_DIM_5,80__',
    self.mutator.generate_float_array(dimension=80, normalized=True),
    '__FLOAT_MULTI_DIM_8,80__',
    '__FLOAT_MULTI_DIM_2,80__',
    '__FLOAT_MULTI_DIM_7,80__',
    '__FLOAT_MULTI_DIM_9,80__',
    '__FLOAT_MULTI_DIM_7,80__',
    '__FLOAT_MULTI_DIM_10,80__',
    '__FLOAT_MULTI_DIM_3,80__',
    '__FLOAT_MULTI_DIM_3,80__',
    '__FLOAT_MULTI_DIM_4,80__',
    self.mutator.generate_float_array(dimension=80, normalized=True),
    '__FLOAT_MULTI_DIM_3,80__',
    '__FLOAT_MULTI_DIM_7,80__',
    '__FLOAT_MULTI_DIM_7,80__',
    '__FLOAT_MULTI_DIM_9,80__',
    '__FLOAT_MULTI_DIM_3,80__',
    '__FLOAT_MULTI_DIM_7,80__',
    '__FLOAT_MULTI_DIM_2,80__',
    '__FLOAT_MULTI_DIM_2,80__',
    '__FLOAT_MULTI_DIM_7,80__',
    '__FLOAT_MULTI_DIM_7,80__',
    '__FLOAT_MULTI_DIM_2,80__',
    '__FLOAT_MULTI_DIM_3,80__',
    '__FLOAT_MULTI_DIM_4,80__',
    '__FLOAT_MULTI_DIM_9,80__',
    '__FLOAT_MULTI_DIM_9,80__',
    '__FLOAT_MULTI_DIM_8,80__',
    '__FLOAT_MULTI_DIM_5,80__',
    '__FLOAT_MULTI_DIM_2,80__',
    '__FLOAT_MULTI_DIM_3,80__',
    '__FLOAT_MULTI_DIM_2,80__',
    '__FLOAT_MULTI_DIM_4,80__',
    '__FLOAT_MULTI_DIM_4,80__',
    '__FLOAT_MULTI_DIM_2,80__',
    '__FLOAT_MULTI_DIM_10,80__',
    self.mutator.generate_float_array(dimension=80, normalized=True),
    self.mutator.generate_float_array(dimension=80, normalized=True),
    '__FLOAT_MULTI_DIM_4,80__',
    '__FLOAT_MULTI_DIM_9,80__',
    '__FLOAT_MULTI_DIM_7,80__',
    '__FLOAT_MULTI_DIM_7,80__',
    '__FLOAT_MULTI_DIM_8,80__',
    '__FLOAT_MULTI_DIM_10,80__',
    '__FLOAT_MULTI_DIM_7,80__',
    '__FLOAT_MULTI_DIM_4,80__',
    '__FLOAT_MULTI_DIM_3,80__',
    '__FLOAT_MULTI_DIM_10,80__',
    '__FLOAT_MULTI_DIM_2,80__',
    '__FLOAT_MULTI_DIM_5,80__',
    '__FLOAT_MULTI_DIM_8,80__',
    '__FLOAT_MULTI_DIM_5,80__',
    '__FLOAT_MULTI_DIM_5,80__',
    '__FLOAT_MULTI_DIM_9,80__',
    '__FLOAT_MULTI_DIM_2,80__',
    '__FLOAT_MULTI_DIM_10,80__',
    '__FLOAT_MULTI_DIM_7,80__',
    '__FLOAT_MULTI_DIM_4,80__',
    '__FLOAT_MULTI_DIM_2,80__',
    '__FLOAT_MULTI_DIM_8,80__',
    '__FLOAT_MULTI_DIM_6,80__',
    '__FLOAT_MULTI_DIM_6,80__',
    self.mutator.generate_float_array(dimension=80, normalized=True),
    '__FLOAT_MULTI_DIM_6,80__',
    '__FLOAT_MULTI_DIM_10,80__',
    '__FLOAT_MULTI_DIM_4,80__',
    '__FLOAT_MULTI_DIM_2,80__',
    '__FLOAT_MULTI_DIM_7,80__',
    '__FLOAT_MULTI_DIM_5,80__',
    self.mutator.generate_float_array(dimension=80, normalized=True),
    '__FLOAT_MULTI_DIM_2,80__',
    '__FLOAT_MULTI_DIM_8,80__',
    '__FLOAT_MULTI_DIM_2,80__',
    '__FLOAT_MULTI_DIM_3,80__',
    '__FLOAT_MULTI_DIM_4,80__',
    '__FLOAT_MULTI_DIM_9,80__',
    '__FLOAT_MULTI_DIM_3,80__',
    '__FLOAT_MULTI_DIM_7,80__',
    '__FLOAT_MULTI_DIM_8,80__',
    '__FLOAT_MULTI_DIM_5,80__',
],
},
    'payloads': [
    {
    'id': 100,
    'id_str': [
],
    'text_data': 'f30ae4ce1fba4d8fbc684c8300479266',
    'rand_digit': 1,
    'rand_number': 0.31123,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-02 13:23:09-0900',
    'text_array': [
    'a508935fb8bc4ed6ba2686921a9574f1',
    '58d6f31c8bc44bfc979a3b884610c389',
],
    'words': 'whale mouse',
    'nested': {
    'id': 100,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 9,
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
    'hello',
],
    'word': 'frog',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'fish',
    'snake',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
    {
    'id': 101,
    'id_str': [
],
    'text_data': 'cea8c36f12234ccdac0f146a88fb9871',
    'rand_digit': 5,
    'rand_number': 0.33205,
    'rand_signed_int': -4,
    'rand_datetime': '2000-08-23T05:06:27.366070',
    'text_array': [
    '2fade8f70ab04ea5b5c76bdeecb6d3c8',
    '0e6e0fa047484b149882ac8cb64360b1',
],
    'words': 'rabbit hippo',
    'nested': {
    'id': 101,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lizard',
    'bird',
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
    'maybe_null': 'rhino',
},
    {
    'id': 102,
    'id_str': [
    '28',
    '29',
    '25',
],
    'text_data': '921c230824c144c4bf893f3b3aa3f9a1',
    'rand_digit': 5,
    'rand_number': 0.03918,
    'rand_signed_int': -7,
    'rand_datetime': '2000-02-04',
    'text_array': [
    'e3185c333df949d4aa6cd9a0a5d2b848',
    'b75f23ab471347ed928dc637556db982',
],
    'words': 'monkey fish',
    'nested': {
    'id': 102,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'hyena',
    'turtle',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'turtle',
},
    {
    'id': 103,
    'id_str': [
    '05',
    '28',
    '06',
],
    'text_data': 'c93afc87ef534c4b830a0db3d6c39fc1',
    'rand_digit': 1,
    'rand_number': 0.63144,
    'rand_signed_int': 5,
    'rand_datetime': '2000-07-18 03:11:23.474933',
    'text_array': [
    '0eb6defc78f243e7905fa623fb3c0faa',
    'ab926d10c1374dabb8ab3d1429390ac1',
],
    'words': 'sheep bee',
    'nested': {
    'id': 103,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'sloth',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 7,
},
],
},
    'nested_array': [
    [
    6,
],
],
    'two_words': [
    'rhino',
    'dragonfly',
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
    'mixed_type': None,
    'maybe': 'dog',
    'maybe_null': None,
},
    {
    'id': 104,
    'id_str': [
    '30',
    '07',
],
    'text_data': 'e0da5e7445404149b1c5944275cfde29',
    'rand_digit': 4,
    'rand_number': 0.10302,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-04 01:28',
    'text_array': [
    '88d3269549ea432e9be626dccdee634c',
    'f7c8b3af1f0c4ce6b73c045a10e52b80',
],
    'words': 'tiger gorilla',
    'nested': {
    'id': 104,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'mosquito',
    'scorpion',
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
    'mixed_type': 0.40518,
    'maybe': 'dragonfly',
    'maybe_null': None,
},
    {
    'id': 105,
    'id_str': [
    '14',
],
    'text_data': '567d12a14dcc4e2eaaf434cb24a1bef5',
    'rand_digit': 9,
    'rand_number': 0.21099,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-26 14:13:59.702874-0300',
    'text_array': [
    '90f8b47e07c3429db61182fe4f50df91',
    'eb4b4ec858934c9286dacce99fa9e8cd',
],
    'words': 'squid monkey',
    'nested': {
    'id': 105,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'bear',
    'lobster',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': [
    50,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'butterfly',
},
    {
    'id': 106,
    'id_str': [
    '11',
    '11',
    '06',
    '06',
    '18',
],
    'text_data': 'b818e141b23b472081f57a20e57c9fd0',
    'rand_digit': 2,
    'rand_number': 0.88856,
    'rand_signed_int': 8,
    'rand_datetime': '2000-03-11T23:47:06.564922+0500',
    'text_array': [
    '0fcfb7b23ce24c54ba04c1ac68f1de44',
    '99cc537a59ae4ecd8b604f983a4a5511',
],
    'words': 'bear squid',
    'nested': {
    'id': 106,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bee',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
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
],
    'two_words': [
    'camel',
    'sheep',
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
    'mixed_type': 6,
    'maybe': 'monkey',
    'maybe_null': 'lizard',
},
    {
    'id': 107,
    'id_str': [
    '21',
    '14',
],
    'text_data': '9795d55000c24542ac21a808405505e1',
    'rand_digit': 2,
    'rand_number': 0.58825,
    'rand_signed_int': 9,
    'rand_datetime': '2001-01-19T11:22:50.788200',
    'text_array': [
    '4c98027e98a44a1391c9738266c1b914',
    'db6b06594661401084a333e78a67b407',
],
    'words': 'lion dog',
    'nested': {
    'id': 107,
    'rand_digit': 0,
    'array': [
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
],
    'word': 'frog',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'leopard',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'gorilla',
    'hippo',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'dog',
    'maybe_null': 'frog',
},
    {
    'id': 108,
    'id_str': [
    '02',
    '26',
    '28',
    '10',
],
    'text_data': '3bfd26394878400eb6ad1c487c234f42',
    'rand_digit': 4,
    'rand_number': 0.27354,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-01T12:10:50+0900',
    'text_array': [
    '8cbc11d9796043769a961e9115e855b2',
    '83c9f8c31c78437a87eede15cc5d00e3',
],
    'words': 'giraffe leopard',
    'nested': {
    'id': 108,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'panda',
    'squid',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'monkey',
    'maybe_null': 'snail',
},
    {
    'id': 109,
    'id_str': [
    '13',
    '29',
],
    'text_data': 'e53631d3e21843db9c2acfb90646f076',
    'rand_digit': 2,
    'rand_number': 0.17248,
    'rand_signed_int': 10,
    'rand_datetime': '2000-11-18',
    'text_array': [
    '479ea5be05e9413a8e28100c2f5438f0',
    '87f9101a93a94ccfae3fad76a1d4b5d3',
],
    'words': 'fly gorilla',
    'nested': {
    'id': 109,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 6,
},
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
    'gorilla',
    'frog',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': [
    57,
],
    'rand_bool': False,
    'mixed_type': 'dog',
    'maybe': 'lizard',
    'maybe_null': None,
},
    {
    'id': 110,
    'id_str': [
    '19',
    '02',
    '26',
    '23',
],
    'text_data': 'f71efd72ada64879b46d3dd8ada5dfff',
    'rand_digit': 6,
    'rand_number': 0.15993,
    'rand_signed_int': -1,
    'rand_datetime': '2001-01-01',
    'text_array': [
    '715595da5cfa495eae9a0fd9d900b830',
    '443afe2ffb6745428affc99f914bd64a',
],
    'words': 'pig shark',
    'nested': {
    'id': 110,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sloth',
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'sheep',
    'lobster',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'ape',
},
    {
    'id': 111,
    'id_str': [
    '25',
    '20',
    '13',
],
    'text_data': 'd0ecbf3c0b734fd4882f78993677f38a',
    'rand_digit': 8,
    'rand_number': 0.25203,
    'rand_signed_int': 8,
    'rand_datetime': '2000-07-29T19:44:21.412903',
    'text_array': [
    'd6089b4ca99841bb908190bde42f0c08',
    '2e3593e15e4d4c0c9c74fec4512ae406',
],
    'words': 'hyena chicken',
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
    'word': 'snail',
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'mouse',
    'dolphin',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'frog',
    'maybe_null': None,
},
    {
    'id': 112,
    'id_str': [
    '09',
    '03',
    '20',
],
    'text_data': 'a486967f19114bdbad621e509b7fbaf6',
    'rand_digit': 6,
    'rand_number': 0.3692,
    'rand_signed_int': -10,
    'rand_datetime': '2000-11-19 22:32:24+0700',
    'text_array': [
    '85e00113b30c4dd5bdd061816ff75f87',
    '426689fa5f3044ba960f4caa3f3951a2',
],
    'words': 'turtle horse',
    'nested': {
    'id': 112,
    'rand_digit': 5,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 4,
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
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'rhino',
    'shark',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
    {
    'id': 113,
    'id_str': [
    '28',
    '04',
    '26',
],
    'text_data': '25ad4789da974204a6b658816179995f',
    'rand_digit': 6,
    'rand_number': 0.94623,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-23 01:39:59',
    'text_array': [
    '7880683ed77540028d1e2ceb026f3e5a',
    '3d6706d3f03a4a44bca75436195963db',
],
    'words': 'grasshopper goat',
    'nested': {
    'id': 113,
    'rand_digit': 7,
    'array': [
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
    'word': 'octopus',
    'number': 5,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'horse',
    'number': 4,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'octopus',
    'panda',
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
    'mixed_type': 6,
},
    {
    'id': 114,
    'id_str': [
    '26',
    '19',
],
    'text_data': '589771facc0f4adab35d2ae94510d03b',
    'rand_digit': 2,
    'rand_number': 0.07593,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-03T05:38:39-0900',
    'text_array': [
    '0b5ce4f370e64291a0cea226404acf7a',
    '21422ef8807a407eb952fbb8bb5c5466',
],
    'words': 'panda rabbit',
    'nested': {
    'id': 114,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 1,
},
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
],
    'word': 'zebra',
    'number': 5,
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
    'word': 'monkey',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'rhino',
    'gorilla',
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
    'mixed_type': False,
},
    {
    'id': 115,
    'id_str': [
    '07',
    '27',
],
    'text_data': 'cb2e828eee7b44e68f3c5cd223dfa4f6',
    'rand_digit': 3,
    'rand_number': 0.74793,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-02T08:44:07.706694-0700',
    'text_array': [
    'f3e5f92ac9654fc7b1f78b76c32a2f68',
    'cada9c490d854f59aab9174ff27b7704',
],
    'words': 'duck wolf',
    'nested': {
    'id': 115,
    'rand_digit': 1,
    'array': [
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
    'word': 'snail',
    'number': 9,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'butterfly',
    'monkey',
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
    'mixed_type': 'bear',
    'maybe_null': 'bee',
},
    {
    'id': 116,
    'id_str': [
    '03',
    '10',
    '20',
    '02',
    '21',
],
    'text_data': '11b2778839984bf8b0b5ba488cf88bd9',
    'rand_digit': 6,
    'rand_number': 0.34241,
    'rand_signed_int': 2,
    'rand_datetime': '2000-03-03 02:25:09.763699-0200',
    'text_array': [
    'f17b18637c7a492784d100a4f7e4fe21',
    '60c1ac66fda246c0b6d34377e16b2556',
],
    'words': 'frog dragonfly',
    'nested': {
    'id': 116,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'lizard',
    'turtle',
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
    'mixed_type': 'cat',
    'maybe': 'spider',
},
    {
    'id': 117,
    'id_str': [
],
    'text_data': '875d2a50b31d422db38a32f2c461bfe7',
    'rand_digit': 3,
    'rand_number': 0.84798,
    'rand_signed_int': 7,
    'rand_datetime': '2000-02-29T15:17:26.297871-0300',
    'text_array': [
    'dbe2433ec6f54a9eaf2a3be1c9b0cb5a',
    'a7541f429bdc4daeac8eb0e1eec15022',
],
    'words': 'fly snail',
    'nested': {
    'id': 117,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    'rand_tuple': [
    19,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'fly',
},
    {
    'id': 118,
    'id_str': [
],
    'text_data': '887196d5c08f42b29428a257228ca636',
    'rand_digit': 0,
    'rand_number': 0.73344,
    'rand_signed_int': -3,
    'rand_datetime': '2001-01-17',
    'text_array': [
    'f0ed9a4b87404ad8b2b6b3a748839a38',
    '038ab7b57cad4585b742acc82d738b76',
],
    'words': 'goat pig',
    'nested': {
    'id': 118,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 9,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    0,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'wolf',
    'kangaroo',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': [
    39,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'wolf',
    'maybe_null': 'tiger',
},
    {
    'id': 119,
    'id_str': [
    '13',
    '08',
    '27',
],
    'text_data': '9d14fc27ecbd4634b126b714dc2027a0',
    'rand_digit': 0,
    'rand_number': 0.54572,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-19T07:22:22.517079',
    'text_array': [
    '55adda7969734f7b82ca05bd7da25809',
    '8592d07a7cc5445c931c09a9e41f01fc',
],
    'words': 'jaguar lobster',
    'nested': {
    'id': 119,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lobster',
    'scorpion',
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
    'mixed_type': 1,
    'maybe': 'leopard',
    'maybe_null': 'fish',
},
    {
    'id': 120,
    'id_str': [
],
    'text_data': '0a2a47e18b154d089cbe5e4ff96e02ea',
    'rand_digit': 1,
    'rand_number': 0.50699,
    'rand_signed_int': 10,
    'rand_datetime': '2000-08-12T13:49:46.139954',
    'text_array': [
    '80ef28cbca1c417d89c84e12f6401abf',
    'e72a0c75aebd420ab8725ada821c0cfa',
],
    'words': 'mouse ape',
    'nested': {
    'id': 120,
    'rand_digit': 6,
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
    'word': 'cow',
    'number': 9,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'fly',
    'dragonfly',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.16389,
    'maybe_null': 'ladybug',
},
    {
    'id': 121,
    'id_str': [
],
    'text_data': '85c1023c7135414bb60ac649b7e7efd2',
    'rand_digit': 9,
    'rand_number': 0.71657,
    'rand_signed_int': 10,
    'rand_datetime': '2000-03-24T17:54:08',
    'text_array': [
    'e68a512287bf4caf9e36ed80247fc71b',
    '72d1b47f260540c69657b0c0bbd318ff',
],
    'words': 'lobster rabbit',
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
    'word': 'whale',
    'number': 7,
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
    'hello',
],
    'word': 'mosquito',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 7,
},
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'butterfly',
    'lion',
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
    'mixed_type': 'pig',
    'maybe_null': None,
},
    {
    'id': 122,
    'id_str': [
    '04',
    '26',
],
    'text_data': 'b5965e3222114793bba1304e9669822b',
    'rand_digit': 4,
    'rand_number': 0.39613,
    'rand_signed_int': 8,
    'rand_datetime': '2000-09-01T08:14:52+0000',
    'text_array': [
    '69172f5e0c7b487b83b3094896682f6d',
    '33afbfc487ee42bd819b90c1738da9c1',
],
    'words': 'fish wolf',
    'nested': {
    'id': 122,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'wolf',
    'lizard',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': [
    0,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'panda',
},
    {
    'id': 123,
    'id_str': [
    '30',
],
    'text_data': '5f5e9c2a10b7418d9a6f09ba7297d472',
    'rand_digit': 7,
    'rand_number': 0.48163,
    'rand_signed_int': 7,
    'rand_datetime': '2000-01-19 06:10:50+0700',
    'text_array': [
    '54f96170300b4644beef465f5ab430a4',
    'e1f6ea38ad8e449985755ea9e2ea764d',
],
    'words': 'whale kangaroo',
    'nested': {
    'id': 123,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'bear',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'crab',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'snake',
    'kangaroo',
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
    'mixed_type': False,
    'maybe': 'spider',
    'maybe_null': 'frog',
},
    {
    'id': 124,
    'id_str': [
    '12',
    '09',
],
    'text_data': '43206ffa00a14955829a7b25937d7760',
    'rand_digit': 8,
    'rand_number': 0.17652,
    'rand_signed_int': -8,
    'rand_datetime': '2000-03-24 10:28:04.857535',
    'text_array': [
    '12ef6a5c7d2e46b4883c3afb9f9fe025',
    '427be54c04bd4a8da2f61ac3a5ced394',
],
    'words': 'dolphin lizard',
    'nested': {
    'id': 124,
    'rand_digit': 5,
    'array': [
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
    'word': 'ant',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'frog',
    'fly',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.96241,
    'maybe': 'whale',
    'maybe_null': 'giraffe',
},
    {
    'id': 125,
    'id_str': [
    '26',
    '03',
    '21',
    '05',
],
    'text_data': '83011bf710c84fa28173b0e18b74c3d3',
    'rand_digit': 6,
    'rand_number': 0.20259,
    'rand_signed_int': 3,
    'rand_datetime': '2000-10-03T02:11:05.781490',
    'text_array': [
    '3a1b9a81d0614e809a7f7c8030b85cd1',
    '9ee309e567ec4b5599d0751ca362ffd0',
],
    'words': 'giraffe rhino',
    'nested': {
    'id': 125,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 7,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'leopard',
    'dragonfly',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'sloth',
    'maybe_null': 'mosquito',
},
    {
    'id': 126,
    'id_str': [
    '27',
    '21',
    '27',
    '29',
    '23',
],
    'text_data': 'c0c83987129c4c85ad4c3484e3d10285',
    'rand_digit': 5,
    'rand_number': 0.9305,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-10T19:48:10',
    'text_array': [
    '1e1883c9b02b4ffca1a5e722a0239723',
    '2038c9bc22a24972ac730920158c9428',
],
    'words': 'zebra chicken',
    'nested': {
    'id': 126,
    'rand_digit': 6,
    'array': [
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
    'word': 'grasshopper',
    'number': 7,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 3,
},
],
},
    'nested_array': [
    [
    3,
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'kangaroo',
    'butterfly',
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
    'mixed_type': None,
    'maybe': 'octopus',
    'maybe_null': None,
},
    {
    'id': 127,
    'id_str': [
    '13',
    '10',
    '26',
    '23',
    '11',
],
    'text_data': '154512e470ec448ab1e1ccb59ae4835b',
    'rand_digit': 3,
    'rand_number': 0.67512,
    'rand_signed_int': 4,
    'rand_datetime': '2000-05-21 03:27:27+0900',
    'text_array': [
    '2838d6b5cbeb40988172cbd3829a9731',
    '88ab0586bd3c45e99029e41284f46d94',
],
    'words': 'fly camel',
    'nested': {
    'id': 127,
    'rand_digit': 5,
    'array': [
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
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lion',
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
    45,
],
    'rand_bool': True,
    'mixed_type': 0.52222,
},
    {
    'id': 128,
    'id_str': [
],
    'text_data': '20dec2cc6e7c4e63b1007d6e38319a53',
    'rand_digit': 4,
    'rand_number': 0.84741,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-13 03:47:43+0700',
    'text_array': [
    'b0e0ecefa89a4588a43eb8bdc82cffb3',
    '96cbd2a6aad849a28741493f58551bf0',
],
    'words': 'chicken tiger',
    'nested': {
    'id': 128,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'snake',
    'number': 8,
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
    'tiger',
    'frog',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': [
    49,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'sloth',
    'maybe_null': None,
},
    {
    'id': 129,
    'id_str': [
    '06',
],
    'text_data': '691eb34c1b5446b0973a70d2d2127f4c',
    'rand_digit': 9,
    'rand_number': 0.80068,
    'rand_signed_int': 7,
    'rand_datetime': '2000-07-09T10:39:08.518579-0200',
    'text_array': [
    'dafcd5a68b8c40a0b7ec869d7c3cbab4',
    'e1c2513f161741f39b5462405d581c71',
],
    'words': 'sheep turtle',
    'nested': {
    'id': 129,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'lobster',
    'lion',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'mosquito',
    'maybe_null': None,
},
    {
    'id': 130,
    'id_str': [
    '14',
],
    'text_data': 'fa65cc4c3fdc4d5d90e7536bb5d6a8e4',
    'rand_digit': 3,
    'rand_number': 0.52655,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-19 23:06:41.499812',
    'text_array': [
    '6f9bf98268f842f4bc652e10e656008e',
    '24e0cd39d9854703b5a9b583b9f55cc5',
],
    'words': 'monkey bear',
    'nested': {
    'id': 130,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 3,
},
],
},
    'nested_array': [
    [
    -10,
],
],
    'two_words': [
    'butterfly',
    'ant',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
    {
    'id': 131,
    'id_str': [
],
    'text_data': '73f3682b9fb940f3937c2e6cb7022ecb',
    'rand_digit': 4,
    'rand_number': 0.61982,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-22',
    'text_array': [
    '00448312ad334bf8b62ef158296bc92c',
    '09c30d66c8fd415c8c1cc36d8dc0c786',
],
    'words': 'butterfly sloth',
    'nested': {
    'id': 131,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 5,
},
],
},
    'nested_array': [
    [
    8,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'fox',
    'wolf',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.61815,
    'maybe_null': 'pig',
},
    {
    'id': 132,
    'id_str': [
    '02',
    '04',
    '26',
],
    'text_data': '027764f53d7046b3be9e7c454bac4a18',
    'rand_digit': 0,
    'rand_number': 0.24627,
    'rand_signed_int': -2,
    'rand_datetime': '2000-04-08 16:34:37.097648+1200',
    'text_array': [
    '8c4b4b07a5fe47a9b0d54b7dc4bf8333',
    '6bf865ad56354becbcd4ec52a09ddf53',
],
    'words': 'pig fox',
    'nested': {
    'id': 132,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'frog',
    'cow',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': [
    87,
],
    'rand_bool': False,
    'mixed_type': False,
},
    {
    'id': 133,
    'id_str': [
],
    'text_data': '33deff49f90e4c4fa5fdf979a2bd2f31',
    'rand_digit': 3,
    'rand_number': 0.38329,
    'rand_signed_int': -10,
    'rand_datetime': '2000-09-03 12:36:33.771372+0900',
    'text_array': [
    '807f3fa1945e49c9a7795e5da2ea6e4d',
    '3366db0416bf4872afc4630b62acd55e',
],
    'words': 'wolf elephant',
    'nested': {
    'id': 133,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    10,
],
],
    'two_words': [
    'goat',
    'rabbit',
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
    'mixed_type': 'ape',
    'maybe': 'hyena',
    'maybe_null': 'dog',
},
    {
    'id': 134,
    'id_str': [
    '12',
    '22',
    '26',
    '15',
],
    'text_data': 'cdd25336ef874835b05406e1bee7650d',
    'rand_digit': 4,
    'rand_number': 0.81231,
    'rand_signed_int': -6,
    'rand_datetime': '2000-07-12 20:31:34.440477',
    'text_array': [
    'c2a666fe40954a828d490a586fcb1d9b',
    'dbfa27553fa44859ad1de812aba4a093',
],
    'words': 'fish turtle',
    'nested': {
    'id': 134,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bear',
    'cheetah',
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
    'mixed_type': 0.23801,
},
    {
    'id': 135,
    'id_str': [
    '10',
],
    'text_data': 'd9e7812d8df4489bb5cf9f8742803461',
    'rand_digit': 1,
    'rand_number': 0.79305,
    'rand_signed_int': -1,
    'rand_datetime': '2001-01-12T08:31:44+0400',
    'text_array': [
    '1bcc2f6362a64cd193666ce542343426',
    '83024d4ceef9465885be9ed23030cdf9',
],
    'words': 'crab bee',
    'nested': {
    'id': 135,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
    'number': 2,
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
    'hello',
],
    'word': 'scorpion',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'tiger',
    'dog',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'snail',
    'maybe_null': None,
},
    {
    'id': 136,
    'id_str': [
    '01',
    '08',
],
    'text_data': '70e7b81225c54226bdd7e05ff6c916b6',
    'rand_digit': 5,
    'rand_number': 0.96775,
    'rand_signed_int': -5,
    'rand_datetime': '2001-01-03 20:04',
    'text_array': [
    '82825b6af26e40e7ae384545570128c4',
    '218ce42cd09f4e12ae8809ae32e593c8',
],
    'words': 'rhino ladybug',
    'nested': {
    'id': 136,
    'rand_digit': 6,
    'array': [
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
    'word': 'scorpion',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fox',
    'horse',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.6738,
    'maybe': 'frog',
},
    {
    'id': 137,
    'id_str': [
    '22',
],
    'text_data': '170c998985174de3969f9f8eb1250f4e',
    'rand_digit': 0,
    'rand_number': 0.93424,
    'rand_signed_int': 5,
    'rand_datetime': '2000-08-24T04:20:39.551464-0800',
    'text_array': [
    'c3faa8d1e3fc45bf8031de1e9e01ea65',
    '8563ed54d8974fa1992cfb87f862ae28',
],
    'words': 'tiger chicken',
    'nested': {
    'id': 137,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'giraffe',
    'number': 9,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'scorpion',
    'gorilla',
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
    'mixed_type': 'fish',
    'maybe': 'octopus',
    'maybe_null': 'grasshopper',
},
    {
    'id': 138,
    'id_str': [
],
    'text_data': '9e03b2f010c94d1c9a0d4d1a91a39da3',
    'rand_digit': 2,
    'rand_number': 0.62496,
    'rand_signed_int': -8,
    'rand_datetime': '2000-05-23 11:45',
    'text_array': [
    '4b4db31260444e6ca03a52111ba05fda',
    'ffeefc3350c7463287942f3115e57626',
],
    'words': 'duck butterfly',
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
    'word': 'giraffe',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'crab',
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
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'ladybug',
},
    {
    'id': 139,
    'id_str': [
    '03',
    '04',
],
    'text_data': 'ecb719279884441bafb7c7b4f54e4e50',
    'rand_digit': 6,
    'rand_number': 0.50733,
    'rand_signed_int': 9,
    'rand_datetime': '2000-09-24T11:53:08-0200',
    'text_array': [
    'ca26ce3d10a4478eb5bbd57f4d6e54e9',
    'e8fa868b8cbd4bb4bfbaf42098225838',
],
    'words': 'lion ape',
    'nested': {
    'id': 139,
    'rand_digit': 2,
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
],
    'word': 'chicken',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'chicken',
    'fox',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'mouse',
},
    {
    'id': 140,
    'id_str': [
    '24',
    '30',
],
    'text_data': '0f50ef253c75464485bc18e502c23fe7',
    'rand_digit': 1,
    'rand_number': 0.83655,
    'rand_signed_int': 3,
    'rand_datetime': '2000-09-11 13:07:41.784643',
    'text_array': [
    'a79b6d9cc9d54efe807b52a2c3738ac8',
    'f83fd2e127c54bcfbddf86773ceac2a4',
],
    'words': 'pig whale',
    'nested': {
    'id': 140,
    'rand_digit': 6,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'spider',
    'rhino',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': [
    2,
],
    'rand_bool': False,
    'mixed_type': 3,
    'maybe': 'sheep',
    'maybe_null': None,
},
    {
    'id': 141,
    'id_str': [
    '05',
    '30',
    '12',
    '30',
    '15',
],
    'text_data': 'a8633a2243734245afb0c5d7b9b82332',
    'rand_digit': 9,
    'rand_number': 0.98009,
    'rand_signed_int': 9,
    'rand_datetime': '2000-02-03T01:16:59-1100',
    'text_array': [
    'ebc3c23b4bbf48049f2df486a0779ea1',
    '2d1d5bd6f2a545458531803f2924ca1a',
],
    'words': 'lobster sloth',
    'nested': {
    'id': 141,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ape',
    'dog',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': [
    12,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
},
    {
    'id': 142,
    'id_str': [
    '28',
],
    'text_data': 'dd11465847644204906596c94506f6d2',
    'rand_digit': 2,
    'rand_number': 0.04648,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-11T06:33:13+0000',
    'text_array': [
    'dd35b336fbf2439eb8e1d8b511d53a4a',
    '6be011f9b9c54ce7a089e2cc3743b77a',
],
    'words': 'sloth whale',
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
    'word': 'kangaroo',
    'number': 7,
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
    {
    'nested_empty': [
    'hello',
],
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
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'crab',
    'panda',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'sheep',
    'maybe_null': None,
},
    {
    'id': 143,
    'id_str': [
    '10',
    '17',
    '18',
],
    'text_data': 'f05575768be147138e585a80c523eac5',
    'rand_digit': 8,
    'rand_number': 0.31684,
    'rand_signed_int': -7,
    'rand_datetime': '2000-02-24 00:20:43.504980+1100',
    'text_array': [
    'eadf8edd3fca45b388664a9cc62e990a',
    '25358813d59c4ef0960a028534b8a33e',
],
    'words': 'frog cheetah',
    'nested': {
    'id': 143,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 5,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'squid',
    'koala',
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
    'mixed_type': None,
    'maybe': 'bear',
    'maybe_null': None,
},
    {
    'id': 144,
    'id_str': [
],
    'text_data': 'db482c929bd844a9888cffbb3ecc8463',
    'rand_digit': 2,
    'rand_number': 0.38086,
    'rand_signed_int': 1,
    'rand_datetime': '2000-12-15 17:29:58-0500',
    'text_array': [
    'b1e04214fbba4414ad72fae5324fc2c2',
    'b69accad404345f8adc8f6cab009a027',
],
    'words': 'ladybug lion',
    'nested': {
    'id': 144,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'frog',
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
    59,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'bee',
    'maybe_null': None,
},
    {
    'id': 145,
    'id_str': [
],
    'text_data': '25d7f943b676464d8daa8a36f53900bb',
    'rand_digit': 8,
    'rand_number': 0.99897,
    'rand_signed_int': 9,
    'rand_datetime': '2000-06-17T18:06:27',
    'text_array': [
    'be808c70ca6742bd9aea550877de8d07',
    '89436884fef947ed8326e607bb9152d3',
],
    'words': 'sheep shark',
    'nested': {
    'id': 145,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 5,
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
    'mixed_type': 'monkey',
    'maybe': 'koala',
    'maybe_null': 'scorpion',
},
    {
    'id': 146,
    'id_str': [
    '26',
],
    'text_data': 'e0dce2fa8d2a450eb92ed503d427d6ee',
    'rand_digit': 4,
    'rand_number': 0.79913,
    'rand_signed_int': 1,
    'rand_datetime': '2000-08-03T19:02:20+0300',
    'text_array': [
    '26cd11ca772a491aa74efb26d085c7f9',
    'ad67de0a1b344a799052cfd9d80c93c2',
],
    'words': 'frog octopus',
    'nested': {
    'id': 146,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'spider',
    'shark',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': 'monkey',
},
    {
    'id': 147,
    'id_str': [
    '15',
    '10',
    '26',
    '29',
    '25',
],
    'text_data': '179930a0d11f40c492a1a889dd6e6ad6',
    'rand_digit': 7,
    'rand_number': 0.0936,
    'rand_signed_int': 2,
    'rand_datetime': '2000-10-11',
    'text_array': [
    '8bcbe3d0ce8847468d88917cf9397801',
    '44cb1f9fcf7349cfa7d64fe787d28c1b',
],
    'words': 'dragonfly shark',
    'nested': {
    'id': 147,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'rabbit',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'bee',
    'bee',
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
    'mixed_type': 2,
},
    {
    'id': 148,
    'id_str': [
    '01',
],
    'text_data': 'fb68c331189d41fa92d43066053ee9be',
    'rand_digit': 0,
    'rand_number': 0.30366,
    'rand_signed_int': 4,
    'rand_datetime': '2000-04-01T00:41:25.227808-04:00',
    'text_array': [
    'f31fff32a752468489adb9b375dae80c',
    'b80ea0f5f42d47d59ad7079995f14f93',
],
    'words': 'hyena dolphin',
    'nested': {
    'id': 148,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 1,
},
],
},
    'nested_array': [
    [
    8,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'dog',
    'zebra',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': [
    81,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
    {
    'id': 149,
    'id_str': [
    '11',
    '07',
],
    'text_data': '13459e51a22d4893b7fbb5a0bdc2f1fc',
    'rand_digit': 3,
    'rand_number': 0.28782,
    'rand_signed_int': -5,
    'rand_datetime': '2000-06-26 20:22:30-1200',
    'text_array': [
    'abf140d0e7fb4c71928cef88c842116a',
    '05f97d3977554b7a8c96e1c1532f5c04',
],
    'words': 'panda scorpion',
    'nested': {
    'id': 149,
    'rand_digit': 6,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 10,
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
    'word': 'cow',
    'number': 2,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_4,5__',
    'two_words': [
    'giraffe',
    'butterfly',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': [
    56,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'mosquito',
    'maybe_null': 'whale',
},
    {
    'id': 150,
    'id_str': [
    '28',
    '23',
    '05',
    '27',
],
    'text_data': '4ecbc2b9a67041309005c5b99de8fd03',
    'rand_digit': 9,
    'rand_number': 0.10348,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-14T22:13:47',
    'text_array': [
    '817eacd0657c437389a185bd869280c0',
    '93e927b5abad4b939ff0fbdd4eb0b55a',
],
    'words': 'hippo tiger',
    'nested': {
    'id': 150,
    'rand_digit': 7,
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
    'hello',
],
    'word': 'dolphin',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'goat',
    'shark',
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
    'mixed_type': 5,
    'maybe_null': 'dolphin',
},
    {
    'id': 151,
    'id_str': [
    '16',
    '24',
    '18',
    '15',
    '17',
],
    'text_data': 'a7282c3cfbe1472fa5a4f8ad6a061ad6',
    'rand_digit': 4,
    'rand_number': 0.05918,
    'rand_signed_int': -7,
    'rand_datetime': '2000-06-27T04:35:36',
    'text_array': [
    '985f8942df79449bbd12776ebdf21ec2',
    '954a998772b641a18cc4420001dd4224',
],
    'words': 'ape octopus',
    'nested': {
    'id': 151,
    'rand_digit': 4,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'butterfly',
    'kangaroo',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': [
    20,
],
    'rand_bool': False,
    'mixed_type': 0.81364,
    'maybe': 'cat',
    'maybe_null': 'koala',
},
    {
    'id': 152,
    'id_str': [
    '05',
    '27',
],
    'text_data': '03a6bf86ee614122aab63aa89b2e3e32',
    'rand_digit': 6,
    'rand_number': 0.88842,
    'rand_signed_int': -1,
    'rand_datetime': '2000-03-15 01:14',
    'text_array': [
    'd73b4872a0fd43b687c4327341bc2d48',
    '86c3b4348830402ea1ff5079a7a1a40f',
],
    'words': 'shark zebra',
    'nested': {
    'id': 152,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 3,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'deer',
    'kangaroo',
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
    'mixed_type': False,
    'maybe': 'spider',
    'maybe_null': 'turtle',
},
    {
    'id': 153,
    'id_str': [
    '27',
],
    'text_data': 'b2da60d35921496795836cf2274988be',
    'rand_digit': 0,
    'rand_number': 0.85992,
    'rand_signed_int': -7,
    'rand_datetime': '2000-09-14T21:08:02.008160',
    'text_array': [
    '5cc1e83389ea48ee8f2292b05cf229f6',
    '3df05e02924b49fc9a74fb2a980f2a17',
],
    'words': 'rhino lobster',
    'nested': {
    'id': 153,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -4,
],
],
    'two_words': [
    'turtle',
    'octopus',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'octopus',
    'maybe_null': 'crab',
},
    {
    'id': 154,
    'id_str': [
    '19',
    '21',
    '23',
    '27',
],
    'text_data': 'c03fb13d1e844301a59d12fe54cf1ea7',
    'rand_digit': 3,
    'rand_number': 0.12961,
    'rand_signed_int': 4,
    'rand_datetime': '2000-07-20 22:38:43.401289+1200',
    'text_array': [
    'd865c32833824caeb95764deac56d877',
    '8d77f4ec4c3740ad94f26cbbe64c1ab3',
],
    'words': 'fish hippo',
    'nested': {
    'id': 154,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'hippo',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'leopard',
    'zebra',
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
    'maybe_null': 'deer',
},
    {
    'id': 155,
    'id_str': [
    '10',
    '22',
],
    'text_data': '4f23a87213c64eeaa98de23f50360cbb',
    'rand_digit': 8,
    'rand_number': 0.55918,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-26T02:35:38.470449+12:00',
    'text_array': [
    'ff80e944f99f4ba19001a21945234970',
    'f98e6f0c9ca14d28a3ff15bcb97d59a4',
],
    'words': 'bird tiger',
    'nested': {
    'id': 155,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'fly',
    'giraffe',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': [
    10,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'crab',
    'maybe_null': 'lion',
},
    {
    'id': 156,
    'id_str': [
    '28',
    '22',
    '20',
],
    'text_data': 'a2114825bbaa4c318b3125c7cc3fcfb6',
    'rand_digit': 8,
    'rand_number': 0.96024,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-27T01:40:44.901808+04:00',
    'text_array': [
    '0fc0b04e3c6d453082519f6319cddb8e',
    '5fa973850ec14ff0a10e72ceed2a2d23',
],
    'words': 'ant jaguar',
    'nested': {
    'id': 156,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 7,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'whale',
    'dolphin',
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
    'mixed_type': 'squid',
    'maybe': 'giraffe',
},
    {
    'id': 157,
    'id_str': [
    '14',
],
    'text_data': 'b3a9299d87b24a359b14898f8eb7ba11',
    'rand_digit': 7,
    'rand_number': 0.79724,
    'rand_signed_int': -5,
    'rand_datetime': '2000-03-24',
    'text_array': [
    'c6706531b96a40a7b19fe97dfa367e82',
    '14fce1b67e38434b9e9b37fbe2e6f5ca',
],
    'words': 'camel elephant',
    'nested': {
    'id': 157,
    'rand_digit': 4,
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
],
    'word': 'mosquito',
    'number': 7,
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
    [
],
    [
    -4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'rhino',
    'jaguar',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
},
    {
    'id': 158,
    'id_str': [
    '02',
    '05',
    '29',
    '21',
    '24',
],
    'text_data': '1551538d3390459aa9f2f9353f4c6732',
    'rand_digit': 4,
    'rand_number': 0.06062,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-08T13:17:02.619073+0400',
    'text_array': [
    '42f04d03f4dd463fab1939f23f035ce4',
    'de718d014d6e4f63b08d272366afd9a6',
],
    'words': 'horse hyena',
    'nested': {
    'id': 158,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
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
    'hello',
],
    'word': 'bear',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'dog',
    'snake',
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
    'mixed_type': 'spider',
    'maybe': 'monkey',
    'maybe_null': 'zebra',
},
    {
    'id': 159,
    'id_str': [
    '17',
    '18',
    '21',
],
    'text_data': '26ba0c6a1f6b495fa29be8d24fc1f948',
    'rand_digit': 4,
    'rand_number': 0.25901,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-06T01:44:45-0600',
    'text_array': [
    'f4e53387044c4fb4b411540b27fae889',
    '98bde67f97c64d6b938a40094640b22a',
],
    'words': 'octopus squid',
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
    'word': 'bear',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'jaguar',
    'tiger',
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
    'mixed_type': 5,
    'maybe': 'ant',
    'maybe_null': 'koala',
},
    {
    'id': 160,
    'id_str': [
],
    'text_data': '417bfe2168b34682b990fef6a168c55f',
    'rand_digit': 8,
    'rand_number': 0.52549,
    'rand_signed_int': 9,
    'rand_datetime': '2000-10-29T10:01:39.043975+05:00',
    'text_array': [
    '235731d08e754a86a18d37a68b51a363',
    '1861d25a1ad94da8b73e3f209b700f2d',
],
    'words': 'horse lobster',
    'nested': {
    'id': 160,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'bear',
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'shark',
    'number': 9,
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
],
    'two_words': [
    'whale',
    'sloth',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': [
    64,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
    {
    'id': 161,
    'id_str': [
    '17',
    '07',
],
    'text_data': '0ca44e83f79845dc98bb4f3476b8605c',
    'rand_digit': 9,
    'rand_number': 0.47224,
    'rand_signed_int': 3,
    'rand_datetime': '2000-10-18T10:44:01.510814-08:00',
    'text_array': [
    '80f0746521084c65b50a4d8a93644039',
    'd993308bd489415898eb665e06eaed5a',
],
    'words': 'chicken lizard',
    'nested': {
    'id': 161,
    'rand_digit': 1,
    'array': [
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
],
    'word': 'sloth',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'crab',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'chicken',
    'koala',
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
    'mixed_type': 'turtle',
    'maybe': 'fox',
    'maybe_null': 'chicken',
},
    {
    'id': 162,
    'id_str': [
    '25',
    '17',
    '12',
],
    'text_data': 'c7332e20a6da425b84e2e56c36a82cfe',
    'rand_digit': 2,
    'rand_number': 0.0816,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-16 09:47',
    'text_array': [
    '33671a3d97f141ceb4ac8802ab2431cf',
    'de617c52979441bebc2a06afc108d168',
],
    'words': 'panda horse',
    'nested': {
    'id': 162,
    'rand_digit': 3,
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
    'hello',
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
    'word': 'whale',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'elephant',
    'panda',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'jaguar',
},
    {
    'id': 163,
    'id_str': [
    '13',
    '16',
    '18',
    '05',
],
    'text_data': '79de684232af459986bfea27debe9446',
    'rand_digit': 7,
    'rand_number': 0.05325,
    'rand_signed_int': 8,
    'rand_datetime': '2000-04-19T09:00:55+1100',
    'text_array': [
    '44cfcb0a330d44949ae4325723f76e71',
    '672ada37eea84dd6ab807ad34bbedeb4',
],
    'words': 'ladybug tiger',
    'nested': {
    'id': 163,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snail',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'rhino',
    'dog',
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
    'mixed_type': True,
    'maybe': 'grasshopper',
    'maybe_null': 'rhino',
},
    {
    'id': 164,
    'id_str': [
    '13',
],
    'text_data': '69857e1561884fb58112fede8950f897',
    'rand_digit': 3,
    'rand_number': 0.16426,
    'rand_signed_int': -1,
    'rand_datetime': '2000-10-21 12:36:48',
    'text_array': [
    '7e45a3ccc8b4432085527b5609c1f959',
    '3737dba2119c48bbb8ad609046e86195',
],
    'words': 'fish koala',
    'nested': {
    'id': 164,
    'rand_digit': 4,
    'array': [
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
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'chicken',
    'snail',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': [
    15,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
    {
    'id': 165,
    'id_str': [
    '07',
    '16',
    '07',
],
    'text_data': '032c98956870463c85f2702cd1cd5c3a',
    'rand_digit': 9,
    'rand_number': 0.74482,
    'rand_signed_int': 3,
    'rand_datetime': '2000-06-01T02:13:46.047686',
    'text_array': [
    'd4448542cb8749a59c8f5da16257e808',
    '390bffdf205e40af92a20f5523f9f873',
],
    'words': 'horse crab',
    'nested': {
    'id': 165,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 10,
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
    'crab',
    'turtle',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'jaguar',
    'maybe_null': None,
},
    {
    'id': 166,
    'id_str': [
    '25',
    '10',
    '25',
    '06',
],
    'text_data': '4c5e3457c38940d79effd077cbbefe1d',
    'rand_digit': 5,
    'rand_number': 0.06947,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-15',
    'text_array': [
    'c5a4ce713d874f96b6fe88220f9e7445',
    '08c0087ea270428ea735ad2a7f4490ff',
],
    'words': 'hyena camel',
    'nested': {
    'id': 166,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'snake',
    'number': 2,
},
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    [
    -8,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'goat',
    'rhino',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': [
    93,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'butterfly',
    'maybe_null': 'zebra',
},
    {
    'id': 167,
    'id_str': [
    '19',
    '21',
    '15',
    '23',
],
    'text_data': '25da9bca4e9c47f9ae1bf318ec54399d',
    'rand_digit': 8,
    'rand_number': 0.6238,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-16T19:02:23.887184-1200',
    'text_array': [
    'ec6964056e054110ad2ed939574481ee',
    '30f4832fd32348359d250f6856d61478',
],
    'words': 'rabbit snake',
    'nested': {
    'id': 167,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 4,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'lion',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'camel',
    'lion',
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
    'mixed_type': None,
    'maybe_null': 'bear',
},
    {
    'id': 168,
    'id_str': [
    '05',
    '24',
],
    'text_data': 'ae7d5bc15b504b8cb6ca680087d8916b',
    'rand_digit': 2,
    'rand_number': 0.69671,
    'rand_signed_int': 8,
    'rand_datetime': '2000-05-14',
    'text_array': [
    '9a0ab1e5a46b43c285a338816d13b81e',
    '24e1d287d43640e5af4f62e892e51103',
],
    'words': 'koala horse',
    'nested': {
    'id': 168,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'butterfly',
    'number': 4,
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
    'word': 'cat',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hyena',
    'octopus',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'gorilla',
    'maybe_null': 'rabbit',
},
    {
    'id': 169,
    'id_str': [
],
    'text_data': '6e8af1ab73794f0a8f03605c82720353',
    'rand_digit': 4,
    'rand_number': 0.8921,
    'rand_signed_int': -1,
    'rand_datetime': '2000-11-28',
    'text_array': [
    '6c4d9dba857f4e2c8227fce6d8eb2334',
    '425997830b4b4d1c8081399dc53c7bbd',
],
    'words': 'shark snake',
    'nested': {
    'id': 169,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
],
    [
    9,
],
],
    'two_words': [
    'wolf',
    'spider',
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
    'mixed_type': None,
    'maybe': 'ladybug',
    'maybe_null': 'goat',
},
    {
    'id': 170,
    'id_str': [
    '23',
    '30',
],
    'text_data': '5e1e633e4d89421f83f16eeb6e64682a',
    'rand_digit': 4,
    'rand_number': 0.06799,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-18T04:58:33.316924',
    'text_array': [
    '22dab16e6c8148fa872a3c9495fe3c4e',
    '51d6e46f90614f03bcb765e359b652cf',
],
    'words': 'rhino ladybug',
    'nested': {
    'id': 170,
    'rand_digit': 8,
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
],
    'word': 'monkey',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'rhino',
    'rhino',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': [
    66,
],
    'rand_bool': True,
    'mixed_type': 5,
    'maybe_null': 'duck',
},
    {
    'id': 171,
    'id_str': [
    '01',
    '05',
],
    'text_data': 'a976acbda0504673b21c27f637b55d5b',
    'rand_digit': 0,
    'rand_number': 0.66681,
    'rand_signed_int': 5,
    'rand_datetime': '2000-04-03T05:08:49',
    'text_array': [
    '5838dc6424e34f3da68fcdc47ef9e242',
    '5743fa9d4f1d4fc7bfa912e5e413e9c9',
],
    'words': 'gorilla monkey',
    'nested': {
    'id': 171,
    'rand_digit': 9,
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
    'word': 'hippo',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dolphin',
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'jaguar',
    'octopus',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'bird',
    'maybe_null': None,
},
    {
    'id': 172,
    'id_str': [
    '22',
    '19',
],
    'text_data': '643d30db0b1148d088fe014148f06926',
    'rand_digit': 2,
    'rand_number': 0.57338,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-22 15:50:57.112947',
    'text_array': [
    '3ed296d5eea44ab0a3b204cbef321d2f',
    '10ab4a1b044e4581bc516b8047077fb3',
],
    'words': 'mouse fly',
    'nested': {
    'id': 172,
    'rand_digit': 8,
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
    'word': 'kangaroo',
    'number': 9,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'snake',
    'deer',
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
    'mixed_type': 'horse',
    'maybe_null': 'hippo',
},
    {
    'id': 173,
    'id_str': [
    '10',
    '01',
    '30',
    '21',
],
    'text_data': '83f70c86b7bf47d798787c973b4b9d1c',
    'rand_digit': 1,
    'rand_number': 0.69628,
    'rand_signed_int': -10,
    'rand_datetime': '2000-10-23',
    'text_array': [
    '8c4878f9251141708f585e6ee2260179',
    'dc175dee9db04ea48c2ec7a61571a864',
],
    'words': 'panda lobster',
    'nested': {
    'id': 173,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'grasshopper',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'koala',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    2,
],
    [
    -9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'deer',
    'wolf',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
    {
    'id': 174,
    'id_str': [
    '06',
],
    'text_data': '8cb57105a4b5484bb1e8f1ea353032c4',
    'rand_digit': 8,
    'rand_number': 0.73392,
    'rand_signed_int': -10,
    'rand_datetime': '2000-03-30T14:09:04',
    'text_array': [
    '3c3734d20cf84a118b112cd9e645fc33',
    'ffdeebb0097f4c959aca093a576c0268',
],
    'words': 'squid dragonfly',
    'nested': {
    'id': 174,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 7,
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
],
},
    'nested_array': [
],
    'two_words': [
    'elephant',
    'cow',
],
    'city': {
    'name': 'Athens',
    'geo': {
    'lat': 37.98381,
    'lon': 23.727539,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cat',
    'maybe_null': None,
},
    {
    'id': 175,
    'id_str': [
    '06',
    '21',
    '15',
    '06',
    '13',
],
    'text_data': 'e44d7c7f411f41639aa192cdfa9695eb',
    'rand_digit': 7,
    'rand_number': 0.59165,
    'rand_signed_int': 9,
    'rand_datetime': '2001-01-25 19:10:08.147870',
    'text_array': [
    '7ae5c3b584c34c3a8580f1846857617a',
    '0f41fb91e9a44514a0af5103c36cbe40',
],
    'words': 'rhino ant',
    'nested': {
    'id': 175,
    'rand_digit': 0,
    'array': [
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
],
    [
    6,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'hippo',
    'grasshopper',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'grasshopper',
},
    {
    'id': 176,
    'id_str': [
    '30',
    '02',
    '14',
],
    'text_data': 'a03424a3a9bf4efd917cb52c96e0bcee',
    'rand_digit': 8,
    'rand_number': 0.84519,
    'rand_signed_int': -10,
    'rand_datetime': '2000-08-12',
    'text_array': [
    '728579abfb2e457daa902eb7d3a7afc4',
    'c99622d0be72407790aded6fce0f872f',
],
    'words': 'squid squid',
    'nested': {
    'id': 176,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'scorpion',
    'cat',
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
    'mixed_type': 'leopard',
    'maybe': 'panda',
},
    {
    'id': 177,
    'id_str': [
    '09',
    '21',
    '06',
    '01',
],
    'text_data': '9913922051d74eb187d73f37cb815cb6',
    'rand_digit': 1,
    'rand_number': 0.48944,
    'rand_signed_int': -10,
    'rand_datetime': '2000-04-02 22:47:32',
    'text_array': [
    '9be7dbdb5e8e45d4883814945f243ae9',
    '56eb4a6f05ee4ff6bdb2ea2148930b0f',
],
    'words': 'gorilla fish',
    'nested': {
    'id': 177,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 10,
},
],
},
    'nested_array': [
    [
    8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dog',
    'snake',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
},
    {
    'id': 178,
    'id_str': [
    '14',
    '22',
    '06',
],
    'text_data': 'bb45405ed85e4cee8cb968e89f633aeb',
    'rand_digit': 5,
    'rand_number': 0.07819,
    'rand_signed_int': 1,
    'rand_datetime': '2000-12-19T01:49:53+1000',
    'text_array': [
    '541eed73b5b5430aa396f845aeac4fee',
    '29b4255f320842879acc338952a88779',
],
    'words': 'panda rhino',
    'nested': {
    'id': 178,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    2,
],
],
    'two_words': [
    'goat',
    'bear',
],
    'city': {
    'name': 'Athens',
    'geo': {
    'lat': 37.98381,
    'lon': 23.727539,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'mosquito',
},
    {
    'id': 179,
    'id_str': [
    '15',
    '02',
    '16',
    '27',
    '03',
],
    'text_data': 'd68e798bd5d34d23946d7fea3339f73c',
    'rand_digit': 5,
    'rand_number': 0.15428,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-09T09:46:07.397203+1100',
    'text_array': [
    '5d97d93cc5464af3a4a78d9d3c89794f',
    '6fa7ef86d1334eb489c17cda64a70dba',
],
    'words': 'sheep octopus',
    'nested': {
    'id': 179,
    'rand_digit': 4,
    'array': [
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -4,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'scorpion',
    'fox',
],
    'city': {
    'name': 'Barcelona',
    'geo': {
    'lat': 41.385064,
    'lon': 2.173403,
},
},
    'rand_tuple': [
    87,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': None,
},
    {
    'id': 180,
    'id_str': [
    '17',
    '04',
    '13',
],
    'text_data': '6d565f6c767a476883d37bb84b45a8f3',
    'rand_digit': 3,
    'rand_number': 0.29584,
    'rand_signed_int': 0,
    'rand_datetime': '2000-09-14',
    'text_array': [
    '61095a0fd7bc4143a4bda2ce4321f380',
    'f8f84eca63fd4a6183b6f5c797f44415',
],
    'words': 'koala ant',
    'nested': {
    'id': 180,
    'rand_digit': 5,
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
    'word': 'lobster',
    'number': 4,
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
    'word': 'leopard',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'panda',
    'fish',
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
    'mixed_type': 0.89167,
    'maybe': 'bird',
    'maybe_null': None,
},
    {
    'id': 181,
    'id_str': [
    '22',
    '29',
],
    'text_data': '77ad3ea8a5ac4ac9a616a532728097af',
    'rand_digit': 4,
    'rand_number': 0.39331,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-04 04:39:08',
    'text_array': [
    '93942c7ea31646239c6660e445c8c6a3',
    '79a210f004c146618fe772c268296082',
],
    'words': 'fish chicken',
    'nested': {
    'id': 181,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    [
    0,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    -2,
],
],
    'two_words': [
    'hyena',
    'ape',
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
    'mixed_type': 'mosquito',
},
    {
    'id': 182,
    'id_str': [
    '29',
    '17',
],
    'text_data': '9e891241e27349f1b01f3fbd1b2b190b',
    'rand_digit': 6,
    'rand_number': 0.06911,
    'rand_signed_int': -7,
    'rand_datetime': '2000-04-17T07:29:39.284240',
    'text_array': [
    '0eb89ef678ae40438aa4dc42e7de65f3',
    '242f52baf2f34f92a11e8f66fd307b49',
],
    'words': 'camel dragonfly',
    'nested': {
    'id': 182,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 1,
},
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
],
    'word': 'ant',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -3,
],
],
    'two_words': [
    'ant',
    'cow',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.22923,
    'maybe': 'turtle',
    'maybe_null': 'cheetah',
},
    {
    'id': 183,
    'id_str': [
    '18',
    '30',
    '09',
],
    'text_data': '1bd572a3aa1c42318e4a505d711c0bbb',
    'rand_digit': 3,
    'rand_number': 0.51872,
    'rand_signed_int': -8,
    'rand_datetime': '2000-07-24T18:50:27',
    'text_array': [
    '42c13d8f917943869aa7bd733c9a5099',
    '976e236d0fbf4b1482b999ff3352ebc2',
],
    'words': 'giraffe cow',
    'nested': {
    'id': 183,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    7,
],
],
    'two_words': [
    'scorpion',
    'fly',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 5,
    'maybe_null': 'hippo',
},
    {
    'id': 184,
    'id_str': [
    '27',
    '28',
    '09',
    '22',
    '29',
],
    'text_data': '8183017f25354b5db02bae9386117536',
    'rand_digit': 8,
    'rand_number': 0.406,
    'rand_signed_int': 10,
    'rand_datetime': '2000-08-09T16:22:47.539542-0100',
    'text_array': [
    '65c21c9336594caca99b9636bbeabce2',
    'eac5ec46a4ec4799af9c46cb922e9367',
],
    'words': 'fish cheetah',
    'nested': {
    'id': 184,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 8,
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
    'hello',
],
    'word': 'squid',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'chicken',
    'dog',
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
    'mixed_type': 0,
    'maybe_null': 'mosquito',
},
    {
    'id': 185,
    'id_str': [
    '22',
    '07',
    '03',
],
    'text_data': '967c129adc7648838049f210bc16a590',
    'rand_digit': 8,
    'rand_number': 0.67846,
    'rand_signed_int': -10,
    'rand_datetime': '2000-08-18 05:58:08+0200',
    'text_array': [
    'fb017f1bb047446d89dd91d25bcd2784',
    '90471e9d1d0241b8b7ea4a899b32ea2d',
],
    'words': 'snail rabbit',
    'nested': {
    'id': 185,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'hippo',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'sloth',
    'camel',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.53029,
    'maybe': 'tiger',
},
    {
    'id': 186,
    'id_str': [
    '30',
    '17',
    '29',
],
    'text_data': 'a88dba711cb544ae822b7b5315198126',
    'rand_digit': 5,
    'rand_number': 0.84453,
    'rand_signed_int': -10,
    'rand_datetime': '2001-01-12',
    'text_array': [
    '79b84f525afb42c8b773be4a68bedc9e',
    '67ca87a615374ec0ab9a778fd885839e',
],
    'words': 'panda koala',
    'nested': {
    'id': 186,
    'rand_digit': 1,
    'array': [
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
    'hello',
],
    'word': 'fish',
    'number': 9,
},
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
],
    'two_words': [
    'fish',
    'dog',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bear',
},
    {
    'id': 187,
    'id_str': [
],
    'text_data': '2d51479fcfba4ae09b516a6d6a7d11d1',
    'rand_digit': 2,
    'rand_number': 0.53518,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-29T09:14:51.135628-09:00',
    'text_array': [
    '2e2d7c30a0c349aa9c8f4f5ad233631f',
    '0315b3bed9214f2f8a7b0162514af9e5',
],
    'words': 'spider panda',
    'nested': {
    'id': 187,
    'rand_digit': 9,
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
    'word': 'mouse',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'zebra',
    'crab',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': [
    84,
],
    'rand_bool': False,
    'mixed_type': None,
},
    {
    'id': 188,
    'id_str': [
    '06',
    '26',
    '17',
],
    'text_data': '7d3b74058d85437a8d35ca096573194b',
    'rand_digit': 7,
    'rand_number': 0.57784,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-04T12:24:11.853563-12:00',
    'text_array': [
    'f590e8b5eb824314adbe5e34beb57a16',
    '0b466d32dc6c45c6bea3ddda662888de',
],
    'words': 'ape leopard',
    'nested': {
    'id': 188,
    'rand_digit': 2,
    'array': [
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
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'snail',
    'jaguar',
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
    'mixed_type': {
    'key': 'value',
},
},
    {
    'id': 189,
    'id_str': [
],
    'text_data': '7cadac9d1d2845cc9d2cc9fec7797d32',
    'rand_digit': 5,
    'rand_number': 0.78587,
    'rand_signed_int': 1,
    'rand_datetime': '2000-03-17T13:07:08-0100',
    'text_array': [
    'c0bd31c05c034847929dd46b9732ffbd',
    '17e66c1d17cd42209d4c2aba6cf3ada5',
],
    'words': 'fish butterfly',
    'nested': {
    'id': 189,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
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
],
    'word': 'sheep',
    'number': 9,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    7,
],
    [
    -3,
],
    [
    8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'zebra',
    'wolf',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': [
    78,
],
    'rand_bool': False,
    'mixed_type': 0.16764,
    'maybe': 'sloth',
    'maybe_null': None,
},
    {
    'id': 190,
    'id_str': [
],
    'text_data': 'b007b0e8e05449ffac1a16b9c037a3fc',
    'rand_digit': 6,
    'rand_number': 0.78542,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-18T17:07:05+0100',
    'text_array': [
    '0155e09f0af34ce6b0efaca70565ab7c',
    'fd616f6a48e04df09120eb1a593f3314',
],
    'words': 'mosquito zebra',
    'nested': {
    'id': 190,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
    5,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -2,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'scorpion',
    'rhino',
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
    'mixed_type': 1,
    'maybe': 'ant',
    'maybe_null': 'crab',
},
    {
    'id': 191,
    'id_str': [
    '05',
    '26',
    '18',
    '19',
],
    'text_data': '5955eba60c6d43fe8764d602241df566',
    'rand_digit': 5,
    'rand_number': 0.9514,
    'rand_signed_int': -5,
    'rand_datetime': '2000-03-02 12:31',
    'text_array': [
    '69c5fd6c759a4c67818f0cf6867b59aa',
    'a34fc81fea6649cdb14a011605057d9f',
],
    'words': 'chicken fly',
    'nested': {
    'id': 191,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 7,
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
    'word': 'camel',
    'number': 5,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'zebra',
    'lizard',
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
    'mixed_type': True,
    'maybe_null': 'lobster',
},
    {
    'id': 192,
    'id_str': [
    '23',
    '07',
    '06',
],
    'text_data': '829e8099f1dd4c619eacf85579f371f8',
    'rand_digit': 1,
    'rand_number': 0.2606,
    'rand_signed_int': 2,
    'rand_datetime': '2000-11-18 21:13:21+0300',
    'text_array': [
    '1b5b9f1a1c3a4349a315965318a3fa0f',
    '071732961342489ea8d53bd19fcd38a6',
],
    'words': 'turtle dolphin',
    'nested': {
    'id': 192,
    'rand_digit': 9,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'fly',
    'duck',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bee',
},
    {
    'id': 193,
    'id_str': [
    '19',
    '07',
    '30',
    '04',
],
    'text_data': 'cc95351301f64f249eae4e134b8bd5da',
    'rand_digit': 1,
    'rand_number': 0.75398,
    'rand_signed_int': 10,
    'rand_datetime': '2000-09-16',
    'text_array': [
    'f9131e5838d6459a90457a716dd92f22',
    'ae57cac8b388462db9ee15436b524297',
],
    'words': 'bird hippo',
    'nested': {
    'id': 193,
    'rand_digit': 9,
    'array': [
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
    'word': 'rabbit',
    'number': 2,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    1,
],
],
    'two_words': [
    'dragonfly',
    'fish',
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
    'mixed_type': True,
    'maybe_null': 'fly',
},
    {
    'id': 194,
    'id_str': [
    '12',
    '19',
],
    'text_data': '035fb56a0894428ab9ff08a32a247be7',
    'rand_digit': 3,
    'rand_number': 0.15701,
    'rand_signed_int': 2,
    'rand_datetime': '2000-05-15T19:08:26.703384-0500',
    'text_array': [
    '511a9a856da04511be8be6f30b9c70d3',
    'd3c57247ea51400b889fd718e4dfd6b7',
],
    'words': 'goat leopard',
    'nested': {
    'id': 194,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
    6,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fly',
    'jaguar',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'panda',
},
    {
    'id': 195,
    'id_str': [
    '30',
],
    'text_data': 'ee4e39b732d6430eae0a5c935d38b5ac',
    'rand_digit': 1,
    'rand_number': 0.80493,
    'rand_signed_int': 3,
    'rand_datetime': '2000-05-23T02:21:35.260595',
    'text_array': [
    '59ae5115937f4f53aed9a89a5cf9d100',
    '197ace4e63e544a4b42ddb850c153c38',
],
    'words': 'horse lion',
    'nested': {
    'id': 195,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'mouse',
    'duck',
],
    'city': {
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
    {
    'id': 196,
    'id_str': [
    '25',
    '12',
],
    'text_data': 'b81a73af852d4c53bf6ec866e3c3090a',
    'rand_digit': 3,
    'rand_number': 0.40703,
    'rand_signed_int': 5,
    'rand_datetime': '2000-05-14 15:11',
    'text_array': [
    '551a1073f88b4a90b32bb190dc11a027',
    '2c65f39cf50d48cc8e9c757aa7a2812b',
],
    'words': 'monkey chicken',
    'nested': {
    'id': 196,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 10,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'zebra',
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
    'maybe': 'elephant',
    'maybe_null': 'fly',
},
    {
    'id': 197,
    'id_str': [
],
    'text_data': 'decf552744c848d28a87e76d10e3cfe8',
    'rand_digit': 1,
    'rand_number': 0.88201,
    'rand_signed_int': 4,
    'rand_datetime': '2000-02-17',
    'text_array': [
    'f69ebc7ac3544b72bf247e16d28078bd',
    'e4b28d30949945a7a72c23736aef66de',
],
    'words': 'goat fly',
    'nested': {
    'id': 197,
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
    'number': 9,
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
],
    'two_words': [
    'zebra',
    'gorilla',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'cat',
    'maybe_null': 'lion',
},
    {
    'id': 198,
    'id_str': [
    '24',
    '07',
    '17',
],
    'text_data': '62ccbe1ba3a84c5caa9d97ff7d252f33',
    'rand_digit': 5,
    'rand_number': 0.95664,
    'rand_signed_int': -3,
    'rand_datetime': '2000-04-03T17:34:18.640155',
    'text_array': [
    'ff8622c816c142dab2e15649f5e66ecf',
    '510773a768a74cbe94bd0416326cd27b',
],
    'words': 'shark fish',
    'nested': {
    'id': 198,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'leopard',
    'sheep',
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
    'mixed_type': False,
    'maybe': 'frog',
    'maybe_null': None,
},
    {
    'id': 199,
    'id_str': [
],
    'text_data': '6d3fa6b190b14faf8af82fdfc86905e4',
    'rand_digit': 5,
    'rand_number': 0.28895,
    'rand_signed_int': -2,
    'rand_datetime': '2000-03-26T11:19:43',
    'text_array': [
    '10603f97272a4bee8698c10b714772d1',
    '722d7980b67e4365b4919174f359deba',
],
    'words': 'shark fly',
    'nested': {
    'id': 199,
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
    'number': 4,
},
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
    'word': 'sheep',
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
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'fish',
    'bird',
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
    'mixed_type': 0,
    'maybe': 'sheep',
    'maybe_null': 'lizard',
},
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



    def test_request_3(self):
        """测试请求 3 - POST http://localhost:6333/collections/congruence_test_collection/points/scroll"""
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



    def test_request_4(self):
        """测试请求 4 - DELETE http://localhost:6333/collections/congruence_test_collection?timeout=60"""
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_multivector_updates.test_upload_uuid_in_batches')
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
    test = TestMultivectorUpdatestestUploadUuidInBatches()
    test.run_tests()
