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
logger = logging.getLogger('vdb_fuzzer.test.test_updates_test_upsert')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_updates.test_upsert"
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



class TestUpdatestestUpsert:
    """自动生成的VDB模糊测试类 - test_updates.test_upsert"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_updates.test_upsert"
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
    'content-length': '210562',
}
        
        # 原始请求内容
        original_content = {
    'batch': {
    'ids': self.mutator.generate_float_array(dimension=100, normalized=True),
    'vectors': {
    'text': '__FLOAT_MULTI_DIM_100,50__',
    'image': '__FLOAT_MULTI_DIM_100,100__',
    'code': '__FLOAT_MULTI_DIM_100,80__',
},
    'payloads': [
    {
    'id': 100,
    'id_str': [
    '30',
    '17',
    '18',
],
    'text_data': '41c5146cacab450ab001d109dd766caf',
    'rand_digit': 8,
    'rand_number': 0.39492,
    'rand_signed_int': 10,
    'rand_datetime': '2000-12-30 02:54:05-1200',
    'text_array': [
    'fe6ee57f51b043b4930750c1e78f8304',
    '546511aceb6c468fae3e1f29be6fb96c',
],
    'words': 'mosquito horse',
    'nested': {
    'id': 100,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'cat',
    'dolphin',
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
    'maybe': 'shark',
    'maybe_null': None,
},
    {
    'id': 101,
    'id_str': [
    '14',
    '09',
    '15',
    '19',
],
    'text_data': 'f5e29db7ddb2484994c44b0e7c38b133',
    'rand_digit': 4,
    'rand_number': 0.69053,
    'rand_signed_int': -5,
    'rand_datetime': '2000-10-30 03:49:35.594432',
    'text_array': [
    '6df1b672c23e4cda974ef37c231c2a15',
    '5abbfbd202614982b6075c287db0fdbb',
],
    'words': 'chicken pig',
    'nested': {
    'id': 101,
    'rand_digit': 1,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ape',
    'rabbit',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'turtle',
},
    {
    'id': 102,
    'id_str': [
],
    'text_data': '3024067036e442b99fb91254562b9a83',
    'rand_digit': 4,
    'rand_number': 0.56601,
    'rand_signed_int': 4,
    'rand_datetime': '2000-10-29T01:30:07-0500',
    'text_array': [
    '944611b887414c7b9466fda795cd13ef',
    '7c15aca7204741e9a12817ac50da3f97',
],
    'words': 'hippo cow',
    'nested': {
    'id': 102,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 2,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -7,
],
    [
],
    [
    -10,
],
],
    'two_words': [
    'hippo',
    'horse',
],
    'city': {
    'name': 'London',
    'geo': {
    'lat': 51.507351,
    'lon': -0.127758,
},
},
    'rand_tuple': [
    49,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'butterfly',
    'maybe_null': None,
},
    {
    'id': 103,
    'id_str': [
    '08',
    '06',
],
    'text_data': 'e3147fc20647481f83831240312a72cd',
    'rand_digit': 3,
    'rand_number': 0.30611,
    'rand_signed_int': 9,
    'rand_datetime': '2000-01-28 14:59:06.557484+0700',
    'text_array': [
    'd778d579c3fc430a94ceab5d7c3b2ada',
    '31c050b2356e4e72a53d86d5e018f666',
],
    'words': 'bear gorilla',
    'nested': {
    'id': 103,
    'rand_digit': 6,
    'array': [
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
    5,
],
],
    'two_words': [
    'dog',
    'snake',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': [
    6,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'panda',
},
    {
    'id': 104,
    'id_str': [
],
    'text_data': '51c360e4377e426e9ed65e2a0d58bf9f',
    'rand_digit': 8,
    'rand_number': 0.41792,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-17T21:54:55.895604',
    'text_array': [
    '965326c6201f42e792ca501ef0139b81',
    'e3cb56ce6f394c83a460967109ded043',
],
    'words': 'cat mosquito',
    'nested': {
    'id': 104,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 3,
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
    [
    5,
],
],
    'two_words': [
    'fish',
    'bear',
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
},
    {
    'id': 105,
    'id_str': [
    '29',
    '19',
],
    'text_data': '53dfffaee00b4b06a44840704eb7a2b1',
    'rand_digit': 7,
    'rand_number': 0.49995,
    'rand_signed_int': -10,
    'rand_datetime': '2000-11-12T18:54:12.262481',
    'text_array': [
    '8e815f0299ec432c926b6b0966265e95',
    '8125ee6ec289413584662f98044cbfe2',
],
    'words': 'dragonfly rhino',
    'nested': {
    'id': 105,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'whale',
    'sloth',
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
    'mixed_type': None,
},
    {
    'id': 106,
    'id_str': [
    '07',
    '17',
],
    'text_data': '0851f1fd0e7d40828f51489e995affc9',
    'rand_digit': 0,
    'rand_number': 0.04898,
    'rand_signed_int': -10,
    'rand_datetime': '2001-01-01 12:29:29',
    'text_array': [
    'cae640e94b904e6488413065086852c3',
    '69022bb1681842ceb2044832aa5cb043',
],
    'words': 'mosquito horse',
    'nested': {
    'id': 106,
    'rand_digit': 7,
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
],
    'word': 'fox',
    'number': 9,
},
    {
    'nested_empty': None,
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
    'word': 'mosquito',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 8,
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
    'hippo',
    'sloth',
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
    'mixed_type': 0.23558,
    'maybe': 'wolf',
    'maybe_null': 'leopard',
},
    {
    'id': 107,
    'id_str': [
    '01',
    '02',
    '20',
    '25',
],
    'text_data': '3d022ac960ab4866b0215fcfa220e00a',
    'rand_digit': 6,
    'rand_number': 0.54911,
    'rand_signed_int': 0,
    'rand_datetime': '2000-05-26 04:15:50.582396',
    'text_array': [
    '92899a508b01446b8698ceb032d7c0f6',
    'e0c8ccebcb364a14af04f381f9ed56b5',
],
    'words': 'lion grasshopper',
    'nested': {
    'id': 107,
    'rand_digit': 2,
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
    'word': 'mouse',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'cheetah',
    'dragonfly',
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
    'mixed_type': 'snail',
    'maybe': 'octopus',
},
    {
    'id': 108,
    'id_str': [
    '29',
    '17',
    '11',
    '30',
],
    'text_data': '351b502f06e042ec9a5318c5d4295e9d',
    'rand_digit': 9,
    'rand_number': 0.7489,
    'rand_signed_int': -5,
    'rand_datetime': '2000-01-14',
    'text_array': [
    'ff1d1933a35c495db920a1190994aea8',
    '646d7e1f554e4ad7bfd4cacf275621c3',
],
    'words': 'squid fly',
    'nested': {
    'id': 108,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'gorilla',
    'lion',
],
    'city': {
    'name': 'Kharkiv',
    'geo': {
    'lat': 49.980812,
    'lon': 36.25272,
},
},
    'rand_tuple': [
    25,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'crab',
    'maybe_null': None,
},
    {
    'id': 109,
    'id_str': [
    '20',
    '17',
    '21',
    '09',
    '20',
],
    'text_data': '04b34ed51670459c91162e0f4444a439',
    'rand_digit': 7,
    'rand_number': 0.79027,
    'rand_signed_int': -7,
    'rand_datetime': '2000-03-07 20:54:55.477799',
    'text_array': [
    'c603a2976cb64e87ac72494772ae930c',
    '0e798fa0819f489182c0b0f0b09524c4',
],
    'words': 'koala turtle',
    'nested': {
    'id': 109,
    'rand_digit': 6,
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
    'hello',
],
    'word': 'octopus',
    'number': 6,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fox',
    'number': 9,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -2,
],
],
    'two_words': [
    'turtle',
    'fox',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 8,
    'maybe': 'snake',
},
    {
    'id': 110,
    'id_str': [
    '25',
    '08',
    '29',
],
    'text_data': '05c35b5784e74896ba356b9d0a6bddc0',
    'rand_digit': 5,
    'rand_number': 0.73825,
    'rand_signed_int': -6,
    'rand_datetime': '2000-12-24T15:38:51.811574',
    'text_array': [
    '308b4ca378034e1c86b575fdcc5711bf',
    '47e5b21f7f874133a9f85c08aa67ec2a',
],
    'words': 'ape rabbit',
    'nested': {
    'id': 110,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'bird',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'shark',
    'fox',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': [
    11,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
    {
    'id': 111,
    'id_str': [
    '27',
    '01',
    '10',
    '15',
    '07',
],
    'text_data': 'b93f31e4bb1740d1bd4e041cc4564514',
    'rand_digit': 5,
    'rand_number': 0.09035,
    'rand_signed_int': 8,
    'rand_datetime': '2000-07-23 23:32',
    'text_array': [
    '795d628a07ed44f2b9c547e8ebffc0a0',
    'e7efe2954c6246b38fc5db45924f8cb9',
],
    'words': 'pig dolphin',
    'nested': {
    'id': 111,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 4,
},
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
    'word': 'lizard',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'snail',
    'hippo',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': [
    10,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'ladybug',
},
    {
    'id': 112,
    'id_str': [
    '14',
],
    'text_data': 'a6aaf6fb7b5a4f6f99760e8c21c463de',
    'rand_digit': 0,
    'rand_number': 0.54832,
    'rand_signed_int': -8,
    'rand_datetime': '2000-04-10 02:13',
    'text_array': [
    '5946367c35a24719bd2b4372f44e0a5f',
    '1c4f445a20c84422b5534955ccac5178',
],
    'words': 'monkey lizard',
    'nested': {
    'id': 112,
    'rand_digit': 3,
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
    'word': 'bird',
    'number': 9,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lobster',
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
    'mixed_type': 0.77605,
    'maybe': 'rhino',
},
    {
    'id': 113,
    'id_str': [
    '12',
    '12',
    '21',
    '09',
    '16',
],
    'text_data': '87aeef4d17514fc58826aec10482a767',
    'rand_digit': 0,
    'rand_number': 0.40887,
    'rand_signed_int': 3,
    'rand_datetime': '2000-09-06 02:10:54.049027-0100',
    'text_array': [
    '3c0bb8b5e1db4834a47c0478d694d1ac',
    '161423e03308403ab43ca1b9e586b70c',
],
    'words': 'rabbit shark',
    'nested': {
    'id': 113,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'cheetah',
    'octopus',
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
    'mixed_type': 3,
    'maybe': 'cow',
    'maybe_null': 'snake',
},
    {
    'id': 114,
    'id_str': [
    '16',
],
    'text_data': 'ea417f10e615423da75962f32474648f',
    'rand_digit': 3,
    'rand_number': 0.28535,
    'rand_signed_int': -6,
    'rand_datetime': '2000-04-23T15:51:45.612570-1100',
    'text_array': [
    '9e9e8bca4ffb4d798fef8539ae4d622e',
    'c24aada5b73b4d83a7d8ee4c6b428989',
],
    'words': 'deer snail',
    'nested': {
    'id': 114,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    [
    -4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dolphin',
    'zebra',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'chicken',
    'maybe_null': 'zebra',
},
    {
    'id': 115,
    'id_str': [
],
    'text_data': '3da0d299af70421887e480cc06a7b3f4',
    'rand_digit': 1,
    'rand_number': 0.47161,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-08 10:00:26.144268',
    'text_array': [
    '777138fec9dc4ba2a7b39b3a8eec5deb',
    'e63cd0f3758e40e1b0d802a6cb9c99f2',
],
    'words': 'whale spider',
    'nested': {
    'id': 115,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'ape',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dog',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
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
    'turtle',
    'chicken',
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
    'mixed_type': None,
    'maybe': 'rhino',
    'maybe_null': None,
},
    {
    'id': 116,
    'id_str': [
    '27',
    '25',
],
    'text_data': '1f1b922bc83a4f87989d6d9429985ef5',
    'rand_digit': 8,
    'rand_number': 0.95322,
    'rand_signed_int': 9,
    'rand_datetime': '2000-07-01 02:54:22.553901+1000',
    'text_array': [
    '731541374de04efabc50bb7e8420564a',
    '04c1abe50ad545d9b5103cd65a0cadff',
],
    'words': 'fox rabbit',
    'nested': {
    'id': 116,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
    -7,
],
],
    'two_words': [
    'spider',
    'tiger',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'gorilla',
    'maybe_null': 'mosquito',
},
    {
    'id': 117,
    'id_str': [
],
    'text_data': '4708e3d0d7314e7ebe307a8920195cd9',
    'rand_digit': 3,
    'rand_number': 0.30316,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-25',
    'text_array': [
    '180ba8a1765e4a999287b1b4aae0a153',
    'b0b2f9d99a85493a8622e8d14efd38dc',
],
    'words': 'rhino chicken',
    'nested': {
    'id': 117,
    'rand_digit': 7,
    'array': [
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
    'word': 'whale',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'duck',
    'lion',
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
    'maybe_null': 'bird',
},
    {
    'id': 118,
    'id_str': [
    '10',
],
    'text_data': '02f777e0876842bc832b3e7aac6b72a5',
    'rand_digit': 2,
    'rand_number': 0.75658,
    'rand_signed_int': 10,
    'rand_datetime': '2000-09-05 00:45:39.264815+0300',
    'text_array': [
    'f6cb1ff9292a42dcb908473029782690',
    'd3ccfb08cc3b409092c56565ea80da7b',
],
    'words': 'scorpion zebra',
    'nested': {
    'id': 118,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'elephant',
    'ant',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'goat',
},
    {
    'id': 119,
    'id_str': [
],
    'text_data': 'c00f4b1c4672402da6ee0cf474924955',
    'rand_digit': 3,
    'rand_number': 0.9701,
    'rand_signed_int': 4,
    'rand_datetime': '2000-12-08T15:23:39.914409-0900',
    'text_array': [
    '6429b525f1174b9e8f0867b27515da06',
    'f14641cb98b54b3d861554f9d60d74ec',
],
    'words': 'butterfly tiger',
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
    'word': 'cheetah',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 7,
},
],
},
    'nested_array': [
    [
    9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    8,
],
],
    'two_words': [
    'rhino',
    'hippo',
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
    'mixed_type': True,
    'maybe_null': None,
},
    {
    'id': 120,
    'id_str': [
    '19',
    '14',
],
    'text_data': '6ce78ce6a1b0419cbd0dec8785b0ba06',
    'rand_digit': 8,
    'rand_number': 0.71685,
    'rand_signed_int': 5,
    'rand_datetime': '2000-03-26',
    'text_array': [
    '586e20c084504afdad315a87a51419a1',
    'feb368d5f5c342fda661701ac2ffc71a',
],
    'words': 'panda horse',
    'nested': {
    'id': 120,
    'rand_digit': 1,
    'array': [
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
    'word': 'grasshopper',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -8,
],
],
    'two_words': [
    'lion',
    'zebra',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'monkey',
},
    {
    'id': 121,
    'id_str': [
    '14',
    '14',
    '27',
    '07',
],
    'text_data': 'a82e1a1e290f46f782037c05f3fb4d5b',
    'rand_digit': 1,
    'rand_number': 0.63531,
    'rand_signed_int': 3,
    'rand_datetime': '2000-10-11 19:55:43.752443',
    'text_array': [
    'bf6c88106584405d80cb3768045f990e',
    '25dda314a6dd4a4f9cbcfd4cbbfbcb15',
],
    'words': 'gorilla camel',
    'nested': {
    'id': 121,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
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
    'word': 'dog',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'bird',
    'duck',
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
    'maybe': 'mouse',
    'maybe_null': 'chicken',
},
    {
    'id': 122,
    'id_str': [
    '23',
    '06',
    '29',
],
    'text_data': 'a315c2f2e7474a01b9448ff8ddd9fe41',
    'rand_digit': 0,
    'rand_number': 0.68273,
    'rand_signed_int': 2,
    'rand_datetime': '2001-01-17',
    'text_array': [
    '3fa5d0a1dfde440a96a63482ac4ed04c',
    '88a408f42326485bb5c142b97d6bf310',
],
    'words': 'duck lobster',
    'nested': {
    'id': 122,
    'rand_digit': 1,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'camel',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'pig',
    'elephant',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'hyena',
},
    {
    'id': 123,
    'id_str': [
],
    'text_data': '5a084e499d0d4aad939770a3c13579b6',
    'rand_digit': 1,
    'rand_number': 0.84476,
    'rand_signed_int': -4,
    'rand_datetime': '2000-06-08 04:49',
    'text_array': [
    'f5fdf5006193414e86eee79a650dac70',
    'b997dce03b044d61b8f7ad13cfd79f71',
],
    'words': 'rhino scorpion',
    'nested': {
    'id': 123,
    'rand_digit': 0,
    'array': [
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    1,
],
],
    'two_words': [
    'lobster',
    'crab',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': [
    43,
],
    'rand_bool': False,
    'mixed_type': 0.90726,
    'maybe': 'koala',
    'maybe_null': 'lion',
},
    {
    'id': 124,
    'id_str': [
    '24',
],
    'text_data': '78263433f42b46c7a85f9da8ba17ffc6',
    'rand_digit': 1,
    'rand_number': 0.83781,
    'rand_signed_int': -10,
    'rand_datetime': '2000-07-31T08:48:38.461259',
    'text_array': [
    '95c0cff0edd240f7928288f017e58153',
    'cff2d9baa8dc40a489a7993691a7217f',
],
    'words': 'bee whale',
    'nested': {
    'id': 124,
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
],
},
    'nested_array': [
    [
    -9,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'bee',
    'lion',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
    {
    'id': 125,
    'id_str': [
    '03',
    '21',
    '12',
],
    'text_data': '1b4280392b2246bd8f42d1add73e6819',
    'rand_digit': 6,
    'rand_number': 0.48496,
    'rand_signed_int': -4,
    'rand_datetime': '2000-11-20T20:17:00.181859',
    'text_array': [
    'e56660c3b508476a90f8698a0fe77f62',
    '742e8c7b837a44098e77fe2f6fb67de5',
],
    'words': 'turtle cheetah',
    'nested': {
    'id': 125,
    'rand_digit': 1,
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
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fox',
    'mosquito',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 'leopard',
    'maybe': 'bee',
    'maybe_null': None,
},
    {
    'id': 126,
    'id_str': [
    '20',
    '19',
],
    'text_data': 'd663b6226f4445ffb20f5326ca2a449a',
    'rand_digit': 8,
    'rand_number': 0.38139,
    'rand_signed_int': -10,
    'rand_datetime': '2000-08-08T08:57:08',
    'text_array': [
    'f62331bebaf64dd1a0acd2aae9e073e2',
    'c54c746ceaf342c7bde871077f321982',
],
    'words': 'kangaroo goat',
    'nested': {
    'id': 126,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'turtle',
    'butterfly',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'cow',
},
    {
    'id': 127,
    'id_str': [
    '09',
],
    'text_data': '724b82ce71c1497aad80316690f053c2',
    'rand_digit': 1,
    'rand_number': 0.89913,
    'rand_signed_int': -6,
    'rand_datetime': '2000-07-10 08:25:25',
    'text_array': [
    '0a0bfae0f55f477db855ecdf82718e84',
    '0193070d081545a3ba9c69889e2985fd',
],
    'words': 'snail snake',
    'nested': {
    'id': 127,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'dog',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ant',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fish',
    'bird',
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
    'mixed_type': 0.52209,
    'maybe_null': 'snake',
},
    {
    'id': 128,
    'id_str': [
    '02',
    '09',
],
    'text_data': '92e871987cee4132a2c2967482813962',
    'rand_digit': 9,
    'rand_number': 0.23168,
    'rand_signed_int': 3,
    'rand_datetime': '2000-01-07 16:18',
    'text_array': [
    '6953422c691e4d19aa62d824878946be',
    '1434ce43480c41de9112ba0d79bdddb6',
],
    'words': 'mouse butterfly',
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
    'word': 'ape',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'giraffe',
    'koala',
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
    'mixed_type': None,
    'maybe': 'monkey',
    'maybe_null': None,
},
    {
    'id': 129,
    'id_str': [
    '02',
    '08',
    '22',
    '02',
    '28',
],
    'text_data': 'a8957e8caf3c4880b66e1f3930367f43',
    'rand_digit': 2,
    'rand_number': 0.05835,
    'rand_signed_int': -2,
    'rand_datetime': '2000-05-25 01:54:17-0100',
    'text_array': [
    'e988ed14a05c4cd9b61c29e490b1f2d8',
    'b82101d8f940461191e16ccb75bfdd44',
],
    'words': 'crab dog',
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
    'word': 'cow',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    9,
],
],
    'two_words': [
    'shark',
    'jaguar',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'snake',
    'maybe_null': 'fish',
},
    {
    'id': 130,
    'id_str': [
    '15',
    '19',
],
    'text_data': '8a937d14ebf54c919b91828365d49f69',
    'rand_digit': 4,
    'rand_number': 0.54145,
    'rand_signed_int': -4,
    'rand_datetime': '2000-01-25 01:55',
    'text_array': [
    'f2b2f86234614470852e8814a3f381b1',
    'fbe448660e634a0592e38dc7c72ca1ee',
],
    'words': 'zebra bird',
    'nested': {
    'id': 130,
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
],
    'word': 'whale',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'octopus',
    'dog',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': [
    88,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
    {
    'id': 131,
    'id_str': [
    '28',
    '21',
    '08',
    '20',
    '18',
],
    'text_data': '9e7353a00fce41d39a6b2d9f311a3e35',
    'rand_digit': 4,
    'rand_number': 0.4596,
    'rand_signed_int': 7,
    'rand_datetime': '2000-08-05 19:53:27+0600',
    'text_array': [
    'da1902fdd88c4b2992cdf7abb3ecfe03',
    '5bc96bc9562d4fc0bb67d3defffe1eb7',
],
    'words': 'turtle crab',
    'nested': {
    'id': 131,
    'rand_digit': 3,
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
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'zebra',
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
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bee',
    'squid',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'shark',
},
    {
    'id': 132,
    'id_str': [
    '19',
],
    'text_data': '8c8570127bb048cc879a816c79c13bc3',
    'rand_digit': 1,
    'rand_number': 0.51874,
    'rand_signed_int': 0,
    'rand_datetime': '2001-01-10T08:54:28+0200',
    'text_array': [
    '0e43485449ce4a7eaf4f66ba715e0b74',
    'a3d52c8f64c04b6c8da04ae8bd4b8c17',
],
    'words': 'octopus shark',
    'nested': {
    'id': 132,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'chicken',
    'squid',
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
    'mixed_type': {
    'key': 'value',
},
},
    {
    'id': 133,
    'id_str': [
    '15',
    '18',
    '08',
    '10',
    '26',
],
    'text_data': 'fd639e3716174324bc2161a97c57eb4f',
    'rand_digit': 7,
    'rand_number': 0.11745,
    'rand_signed_int': -6,
    'rand_datetime': '2000-02-05 00:17:10.294711-1100',
    'text_array': [
    '4a318f8aa3be4500a2e1fbe5be54ea7d',
    '90a5e95d19004d19b90650bcad08383b',
],
    'words': 'panda ape',
    'nested': {
    'id': 133,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'zebra',
    'number': 4,
},
    {
    'nested_empty': None,
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
    'word': 'duck',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    6,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    2,
],
    [
],
],
    'two_words': [
    'frog',
    'snake',
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
},
    {
    'id': 134,
    'id_str': [
    '12',
    '01',
    '27',
    '06',
],
    'text_data': '8e8c688ba2634c0e860bd26fdaa4f810',
    'rand_digit': 4,
    'rand_number': 0.32628,
    'rand_signed_int': 5,
    'rand_datetime': '2000-06-20',
    'text_array': [
    '8ad516e76cb54aa2b3421919da881038',
    '7f5cc16d98b14f73ac031b4ac53a7211',
],
    'words': 'turtle pig',
    'nested': {
    'id': 134,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'turtle',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bee',
    'dolphin',
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
    'maybe': 'giraffe',
},
    {
    'id': 135,
    'id_str': [
    '20',
],
    'text_data': '29ff32ac6b77485aa34af08523221809',
    'rand_digit': 3,
    'rand_number': 0.78256,
    'rand_signed_int': 3,
    'rand_datetime': '2000-01-02T05:02:07',
    'text_array': [
    'f77fbeef10ee45f3b862036910375ce1',
    '66813ee5a7c74fd689d269576427aaae',
],
    'words': 'elephant sloth',
    'nested': {
    'id': 135,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'horse',
    'dragonfly',
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
    'mixed_type': 0,
    'maybe': 'snail',
    'maybe_null': 'ant',
},
    {
    'id': 136,
    'id_str': [
    '07',
    '07',
    '16',
    '29',
    '04',
],
    'text_data': 'cd3fa9f245554ab0b61df4411b06d54b',
    'rand_digit': 0,
    'rand_number': 0.16731,
    'rand_signed_int': -1,
    'rand_datetime': '2000-06-26T20:25:18.479580',
    'text_array': [
    '147f6a2a824c4372a5fbc5a9de144c37',
    'a981b3d4ee784800acc7080894aa9974',
],
    'words': 'crab ape',
    'nested': {
    'id': 136,
    'rand_digit': 1,
    'array': [
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
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'shark',
    'sheep',
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
    'mixed_type': 0.39928,
    'maybe_null': 'bear',
},
    {
    'id': 137,
    'id_str': [
    '15',
],
    'text_data': 'e94b0cc39e7940ef846f8e61dda7aef3',
    'rand_digit': 8,
    'rand_number': 0.16432,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-25T22:35:04.189143+0100',
    'text_array': [
    '8bc6590d816e4ebdaaee08efe8495bff',
    'dc69a060beca426b8834a9c4fe13c7e3',
],
    'words': 'giraffe ape',
    'nested': {
    'id': 137,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snail',
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
    'number': 4,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'gorilla',
    'lizard',
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
    'mixed_type': True,
    'maybe': 'dragonfly',
    'maybe_null': 'cow',
},
    {
    'id': 138,
    'id_str': [
],
    'text_data': 'c0d83b1a204b4ca5af6870514f151215',
    'rand_digit': 3,
    'rand_number': 0.71558,
    'rand_signed_int': 5,
    'rand_datetime': '2000-11-21T19:22:09',
    'text_array': [
    'e4c049b7a4c94f8fab1a3a94485875ce',
    '8886614abf4b4c36a50b997a3a11b7c3',
],
    'words': 'rabbit butterfly',
    'nested': {
    'id': 138,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 1,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 1,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,3__',
    'two_words': [
    'mosquito',
    'dolphin',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'hippo',
    'maybe_null': None,
},
    {
    'id': 139,
    'id_str': [
    '03',
    '03',
    '19',
    '16',
],
    'text_data': 'b4ebcd6dfce74920ad6421c977d51c78',
    'rand_digit': 1,
    'rand_number': 0.70039,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-08T07:33:16.585453',
    'text_array': [
    'c494dbdfb7074bf3a0a73ef53ab8da8d',
    'b12cd8235da64939983a010c315c9c9d',
],
    'words': 'deer mosquito',
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
    'word': 'turtle',
    'number': 6,
},
    {
    'nested_empty': None,
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
],
    'word': 'bear',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -7,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'frog',
    'grasshopper',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': [
    38,
],
    'rand_bool': False,
    'mixed_type': 'fish',
    'maybe_null': 'fish',
},
    {
    'id': 140,
    'id_str': [
],
    'text_data': '182d3e8c7d66466daaa1299c71329cbe',
    'rand_digit': 1,
    'rand_number': 0.14551,
    'rand_signed_int': -1,
    'rand_datetime': '2000-04-12T07:51:20.816406',
    'text_array': [
    '2690aa2495fd4b04838d6c5907c13250',
    '74449a0ff16143f59bdf6a1efdbeeaf3',
],
    'words': 'chicken spider',
    'nested': {
    'id': 140,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'dragonfly',
    'turtle',
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
},
    {
    'id': 141,
    'id_str': [
    '30',
    '14',
    '17',
    '06',
],
    'text_data': 'c6936828a5c14e0db29976ef2f595acd',
    'rand_digit': 8,
    'rand_number': 0.40403,
    'rand_signed_int': -5,
    'rand_datetime': '2000-12-02T05:36:35.018790-0500',
    'text_array': [
    '8e39b32db7db4558a3309f15bbfb2362',
    'a1f79b1e9bb643959d4630473288d08f',
],
    'words': 'rhino sloth',
    'nested': {
    'id': 141,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ape',
    'crab',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': [
    71,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'grasshopper',
},
    {
    'id': 142,
    'id_str': [
    '06',
    '10',
    '03',
    '01',
],
    'text_data': 'bf846db28929407a9918a75cf88429c0',
    'rand_digit': 2,
    'rand_number': 0.59133,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-21 06:45:59.561888+1000',
    'text_array': [
    '3937c7d9b1304dce906c10a1ed103b62',
    '5243bc420ca24ae6aa8d59e67a6c4a1e',
],
    'words': 'rhino jaguar',
    'nested': {
    'id': 142,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 7,
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
    'turtle',
    'octopus',
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
    'mixed_type': 5,
},
    {
    'id': 143,
    'id_str': [
    '24',
    '07',
    '05',
    '27',
    '08',
],
    'text_data': '701b89d5792849c9bb3fc2c7ccb16d1c',
    'rand_digit': 6,
    'rand_number': 0.98484,
    'rand_signed_int': 3,
    'rand_datetime': '2000-03-02T17:02:01.055681',
    'text_array': [
    '5c0046a8633746c5a2b39c2115134ed5',
    'd0c98c4374fb47a6b4d43ddcb6611d10',
],
    'words': 'sloth tiger',
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
    'word': 'zebra',
    'number': 5,
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
    {
    'nested_empty': [
    'hello',
],
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
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'lobster',
    'elephant',
],
    'city': {
    'name': 'Kharkiv',
    'geo': {
    'lat': 49.980812,
    'lon': 36.25272,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 'bee',
    'maybe': 'chicken',
    'maybe_null': 'hyena',
},
    {
    'id': 144,
    'id_str': [
    '07',
    '18',
    '10',
],
    'text_data': '8c122200d2cb4a79acee37fd9ee9e0b2',
    'rand_digit': 1,
    'rand_number': 0.42165,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-18 10:29:51.243453-0600',
    'text_array': [
    'e51e5d2751444846bad2bd461771a0bb',
    '5787322eed8f4dab93271d2f1e53058a',
],
    'words': 'rabbit butterfly',
    'nested': {
    'id': 144,
    'rand_digit': 1,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    6,
],
    [
],
],
    'two_words': [
    'rabbit',
    'jaguar',
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
    'mixed_type': 0.64781,
    'maybe_null': 'mosquito',
},
    {
    'id': 145,
    'id_str': [
],
    'text_data': '111f8e94f1f74b28ae66cfc810416971',
    'rand_digit': 8,
    'rand_number': 0.06825,
    'rand_signed_int': -2,
    'rand_datetime': '2000-11-19',
    'text_array': [
    'c4b98c9abbf24c8b9818903bc47eaa63',
    'cec6f5dda8ae4624ae7ecbc10340a890',
],
    'words': 'bird panda',
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
    'word': 'cat',
    'number': 5,
},
    {
    'nested_empty': None,
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
    'word': 'dog',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'dragonfly',
    'bird',
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
    'mixed_type': 0.90227,
    'maybe_null': 'lion',
},
    {
    'id': 146,
    'id_str': [
    '08',
    '04',
    '24',
],
    'text_data': '5f38f576b36b49a681b898f838456d34',
    'rand_digit': 6,
    'rand_number': 0.65008,
    'rand_signed_int': 2,
    'rand_datetime': '2000-02-13T02:35:18',
    'text_array': [
    '3923eae9c30a40beab7b6f3d85abc8d8',
    'fcfe425eda2d47ada01ec8fd76688405',
],
    'words': 'dog bird',
    'nested': {
    'id': 146,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'lion',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'octopus',
    'bear',
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
    'mixed_type': True,
    'maybe': 'whale',
    'maybe_null': 'shark',
},
    {
    'id': 147,
    'id_str': [
    '08',
],
    'text_data': '497ed35d7113432cbb11f8a631992527',
    'rand_digit': 2,
    'rand_number': 0.60808,
    'rand_signed_int': 7,
    'rand_datetime': '2000-08-17 06:53:04.855426+0500',
    'text_array': [
    'b9294cd3688f4da396763c94c0257cb0',
    'e775add301044a37b8952d45af536a29',
],
    'words': 'ant elephant',
    'nested': {
    'id': 147,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'frog',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 10,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -2,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'frog',
    'gorilla',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': [
    26,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'rabbit',
},
    {
    'id': 148,
    'id_str': [
    '05',
    '23',
],
    'text_data': 'c841eea93db7469e84c746a12047cead',
    'rand_digit': 5,
    'rand_number': 0.64797,
    'rand_signed_int': -3,
    'rand_datetime': '2000-05-28 14:05:12',
    'text_array': [
    '27f164a239c64be6acedc5f8d651b116',
    '854ce6c834084e1699558027ad1866b4',
],
    'words': 'ladybug gorilla',
    'nested': {
    'id': 148,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'rhino',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'whale',
    'panda',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': [
    12,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': None,
},
    {
    'id': 149,
    'id_str': [
    '18',
    '27',
    '24',
    '23',
],
    'text_data': 'cf4cfb17084345a7858066bf27caaac6',
    'rand_digit': 7,
    'rand_number': 0.1123,
    'rand_signed_int': 10,
    'rand_datetime': '2000-08-18T06:19:16+0400',
    'text_array': [
    'fbc19ecde714472c88b7225d039b252c',
    'b82f6641e2774a7f9521d788f02075d9',
],
    'words': 'koala shark',
    'nested': {
    'id': 149,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'camel',
    'dog',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'octopus',
},
    {
    'id': 150,
    'id_str': [
    '19',
    '23',
    '11',
    '03',
],
    'text_data': '722a299f0dc74acb94fe546e046dbc3a',
    'rand_digit': 4,
    'rand_number': 0.15062,
    'rand_signed_int': -5,
    'rand_datetime': '2000-06-12T01:00:03.310387',
    'text_array': [
    '440c7395d17a4f1089e2113c880211fe',
    '5f0bfa42a44e4024aa145cfa315b6fb2',
],
    'words': 'dolphin ladybug',
    'nested': {
    'id': 150,
    'rand_digit': 0,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ape',
    'hyena',
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
    'mixed_type': 0.07932,
    'maybe_null': None,
},
    {
    'id': 151,
    'id_str': [
],
    'text_data': '074bdcbf96394593b9dfc4acfcce9696',
    'rand_digit': 2,
    'rand_number': 0.39688,
    'rand_signed_int': 4,
    'rand_datetime': '2000-04-14T20:42:34.862422+0500',
    'text_array': [
    'f3d3e9c9d68c4761893e1ea995c32e3d',
    '5fa24c5969e541518eaf1b1b6d5a77df',
],
    'words': 'crab hippo',
    'nested': {
    'id': 151,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dragonfly',
    'panda',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'giraffe',
    'maybe_null': None,
},
    {
    'id': 152,
    'id_str': [
],
    'text_data': '0f2639f437994c7dad46ebe9995dd780',
    'rand_digit': 1,
    'rand_number': 0.07312,
    'rand_signed_int': 6,
    'rand_datetime': '2000-10-16T14:37:57.501309',
    'text_array': [
    'df5cccbb2d614619b19b94d9226de63b',
    'c3ff4d2d044a475c9a34a8f53d27b84b',
],
    'words': 'lobster horse',
    'nested': {
    'id': 152,
    'rand_digit': 4,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
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
    'pig',
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
    'maybe_null': None,
},
    {
    'id': 153,
    'id_str': [
    '26',
],
    'text_data': 'c68cac5a28a04c7f9d3d9301ede96b0b',
    'rand_digit': 3,
    'rand_number': 0.73423,
    'rand_signed_int': -3,
    'rand_datetime': '2000-05-12 20:34:54.376036+1100',
    'text_array': [
    'e0de876b26274a5f9af64cf2f5bbcc53',
    '5389038420b440d092873df7a22a064c',
],
    'words': 'lion gorilla',
    'nested': {
    'id': 153,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 6,
},
    {
    'nested_empty': None,
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
    'word': 'rabbit',
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
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'scorpion',
    'ape',
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
    'mixed_type': 0.81659,
    'maybe': 'turtle',
    'maybe_null': 'cheetah',
},
    {
    'id': 154,
    'id_str': [
    '09',
    '28',
    '06',
],
    'text_data': '60c953fc73da4d7c90cf3610a7153158',
    'rand_digit': 9,
    'rand_number': 0.8444,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-07 05:05:11.487311',
    'text_array': [
    '8b4430cce8b94bf9987f92c0a6632d6d',
    'b31963cb9c03486dafb3a248c5c7f5ad',
],
    'words': 'lizard shark',
    'nested': {
    'id': 154,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
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
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'butterfly',
    'wolf',
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
    'mixed_type': 'goat',
    'maybe': 'cat',
    'maybe_null': 'grasshopper',
},
    {
    'id': 155,
    'id_str': [
    '09',
    '15',
    '03',
    '12',
    '20',
],
    'text_data': '375d082b14fe43efa162a757fd786279',
    'rand_digit': 1,
    'rand_number': 0.33572,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-31T05:14:56+0600',
    'text_array': [
    '26b46d0cca1f4716be255535af67d853',
    'c1b85887693e449cb3da2f0e4aeee6a8',
],
    'words': 'octopus snake',
    'nested': {
    'id': 155,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bird',
    'ape',
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
    'mixed_type': None,
    'maybe': 'mouse',
    'maybe_null': None,
},
    {
    'id': 156,
    'id_str': [
    '29',
    '06',
],
    'text_data': 'f87d6c3840ae42ca9a7e102b608e0562',
    'rand_digit': 9,
    'rand_number': 0.7841,
    'rand_signed_int': 4,
    'rand_datetime': '2000-11-02 10:16:18.002546-1100',
    'text_array': [
    '19be6656186747ed9dc4f8ed73dd6072',
    '757053ec21954f6daa60e90069413aa8',
],
    'words': 'cat horse',
    'nested': {
    'id': 156,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'cheetah',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'lion',
    'snake',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 4,
    'maybe_null': 'crab',
},
    {
    'id': 157,
    'id_str': [
    '08',
],
    'text_data': '755b2a5e777c49138a09e3de402da5ac',
    'rand_digit': 6,
    'rand_number': 0.58111,
    'rand_signed_int': 5,
    'rand_datetime': '2000-08-27 00:53:07.465699',
    'text_array': [
    '9d3fc3f588ab4fb8953f11bdd0914428',
    '1ce845d399014a41a1924a84be0e991c',
],
    'words': 'goat sheep',
    'nested': {
    'id': 157,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -7,
],
    [
],
],
    'two_words': [
    'dolphin',
    'sloth',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
    {
    'id': 158,
    'id_str': [
    '03',
    '14',
    '30',
],
    'text_data': '718dee505f6448119d3616fac09315aa',
    'rand_digit': 3,
    'rand_number': 0.20141,
    'rand_signed_int': -6,
    'rand_datetime': '2000-08-19T04:43:21.466580+0700',
    'text_array': [
    '455d72fca84548c3aa660551e3e839f1',
    '74db6095163f4ea791e70d70aaa33581',
],
    'words': 'lizard camel',
    'nested': {
    'id': 158,
    'rand_digit': 8,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 6,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'wolf',
    'scorpion',
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
    'mixed_type': 7,
    'maybe': 'cat',
    'maybe_null': 'gorilla',
},
    {
    'id': 159,
    'id_str': [
],
    'text_data': 'a61271505cf34b4dbe28e2554b1d323a',
    'rand_digit': 8,
    'rand_number': 0.99097,
    'rand_signed_int': -3,
    'rand_datetime': '2000-06-21 08:30:49.840161+0900',
    'text_array': [
    '16cec7f4cb87435486c54f158522dd79',
    '6b05c851320c4a5d92f11149aeb853d9',
],
    'words': 'octopus rhino',
    'nested': {
    'id': 159,
    'rand_digit': 1,
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
    {
    'nested_empty': None,
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
],
    'word': 'grasshopper',
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
],
},
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'snail',
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
    'mixed_type': False,
    'maybe': 'frog',
    'maybe_null': None,
},
    {
    'id': 160,
    'id_str': [
],
    'text_data': '712ccfd54127452894b862ee020379f1',
    'rand_digit': 6,
    'rand_number': 0.06036,
    'rand_signed_int': 8,
    'rand_datetime': '2000-11-05',
    'text_array': [
    '5355a916ddc54a6684c00eb545588c40',
    '70c6d14507634c8eaee9bb29396a737d',
],
    'words': 'butterfly koala',
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
    'word': 'fly',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 8,
},
],
},
    'nested_array': [
    [
    5,
],
],
    'two_words': [
    'zebra',
    'pig',
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
    'mixed_type': 0.10898,
    'maybe': 'kangaroo',
},
    {
    'id': 161,
    'id_str': [
    '20',
    '13',
],
    'text_data': '4830121a848c419a99da8ebfd482865a',
    'rand_digit': 9,
    'rand_number': 0.50608,
    'rand_signed_int': -9,
    'rand_datetime': '2000-06-07T15:40:01.557384+0400',
    'text_array': [
    '1d53344eb52a4b899e74ed249319d494',
    '8939f57449ce47ab8e9e567f9bac4c89',
],
    'words': 'cat bird',
    'nested': {
    'id': 161,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'snake',
    'snake',
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
    'maybe_null': 'dog',
},
    {
    'id': 162,
    'id_str': [
],
    'text_data': 'fffaef5b64a14157b3c5eba84dda31bc',
    'rand_digit': 9,
    'rand_number': 0.77528,
    'rand_signed_int': -5,
    'rand_datetime': '2000-02-23T20:25:31.254712+0300',
    'text_array': [
    '585c72135bc5451589268cd8dd23a09a',
    '73feeb008f2f43f19a49e7f123b26654',
],
    'words': 'mosquito jaguar',
    'nested': {
    'id': 162,
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
    'hello',
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
    'word': 'bee',
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
    'number': 5,
},
],
},
    'nested_array': [
    [
    6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'cat',
    'gorilla',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.93981,
},
    {
    'id': 163,
    'id_str': [
    '15',
    '14',
    '27',
    '07',
    '19',
],
    'text_data': '537a209d7ccc4076a43fd7e889bbff13',
    'rand_digit': 7,
    'rand_number': 0.27087,
    'rand_signed_int': -6,
    'rand_datetime': '2001-01-05T05:21:04.922690',
    'text_array': [
    'b3bc8314775943b9995b562c556ebe0d',
    'a98cd053c0fc49e8beeb1364554f5f85',
],
    'words': 'duck cheetah',
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
    'word': 'mosquito',
    'number': 8,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 6,
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
],
},
    'nested_array': [
],
    'two_words': [
    'bird',
    'cow',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'leopard',
},
    {
    'id': 164,
    'id_str': [
    '12',
    '10',
    '14',
    '18',
    '13',
],
    'text_data': '6555a73fabdb4efe88ba4abb1161669c',
    'rand_digit': 0,
    'rand_number': 0.44774,
    'rand_signed_int': 8,
    'rand_datetime': '2000-01-04 13:39:23.076987+0800',
    'text_array': [
    '3c9e3c3166834164ad337551a750b010',
    'bbf2f9f518f4452a8875e3bad6e34138',
],
    'words': 'jaguar dragonfly',
    'nested': {
    'id': 164,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 7,
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
    [
    -1,
],
],
    'two_words': [
    'bear',
    'hippo',
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
    'mixed_type': False,
    'maybe': 'rhino',
},
    {
    'id': 165,
    'id_str': [
    '16',
],
    'text_data': 'ec3189cc54084a49b9cb90264562de62',
    'rand_digit': 6,
    'rand_number': 0.37697,
    'rand_signed_int': -9,
    'rand_datetime': '2000-07-18T13:30:28-0300',
    'text_array': [
    'df07f0fb8df8494db7b48ebb1cb09913',
    '380e9f4ecea44970b02df7ccdff81f86',
],
    'words': 'lobster cheetah',
    'nested': {
    'id': 165,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'shark',
    'mosquito',
],
    'city': {
    'name': 'Rome',
    'geo': {
    'lat': 41.902782,
    'lon': 12.496366,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.78269,
},
    {
    'id': 166,
    'id_str': [
    '17',
    '03',
    '25',
    '28',
    '01',
],
    'text_data': '82cd2cf690794aa7819f821f2446fc1a',
    'rand_digit': 9,
    'rand_number': 0.83148,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-11',
    'text_array': [
    '4384abf4bdf3421fb9ae8690894f70f3',
    'd920caaac8c54825bfb328176181b666',
],
    'words': 'ant cow',
    'nested': {
    'id': 166,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'pig',
    'number': 10,
},
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'hyena',
    'mouse',
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
    'maybe': 'cheetah',
    'maybe_null': 'kangaroo',
},
    {
    'id': 167,
    'id_str': [
],
    'text_data': 'e65ab44d0b65476194e62ace7f72b04b',
    'rand_digit': 9,
    'rand_number': 0.49475,
    'rand_signed_int': 0,
    'rand_datetime': '2000-09-13T04:03:03.253916',
    'text_array': [
    'ef5363c5e94d4ab3bdeac1fca25b3c8c',
    'b08b739d97e948c5a5669facf70b5f5d',
],
    'words': 'bear dolphin',
    'nested': {
    'id': 167,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    -8,
],
    [
    3,
],
],
    'two_words': [
    'mouse',
    'rabbit',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
},
    {
    'id': 168,
    'id_str': [
    '11',
    '26',
    '30',
    '07',
],
    'text_data': '4700ad6b559b4997a0274dc955d30e06',
    'rand_digit': 9,
    'rand_number': 0.5079,
    'rand_signed_int': 0,
    'rand_datetime': '2000-07-16T10:12:15-0400',
    'text_array': [
    '8034c6742479496d8c394f92188e106d',
    '66d05119567e453fb19ae89dea9edbea',
],
    'words': 'giraffe bear',
    'nested': {
    'id': 168,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'spider',
    'ladybug',
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
    'mixed_type': 0.13239,
},
    {
    'id': 169,
    'id_str': [
    '19',
    '05',
    '06',
],
    'text_data': 'ebfe6c96a84a4d8f8bbf37d68c6fdbe6',
    'rand_digit': 7,
    'rand_number': 0.78302,
    'rand_signed_int': -2,
    'rand_datetime': '2000-12-25T12:26:09-0100',
    'text_array': [
    '962870a715984447b371dbb5d39d6ff6',
    '0dc2126c1bd74669b4c1ef72a82a24e9',
],
    'words': 'fish rhino',
    'nested': {
    'id': 169,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'goat',
    'snake',
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
    'mixed_type': False,
    'maybe_null': None,
},
    {
    'id': 170,
    'id_str': [
    '26',
    '26',
    '06',
    '28',
    '04',
],
    'text_data': '64315f101cd64d42aafc80fc8f4d3389',
    'rand_digit': 8,
    'rand_number': 0.65145,
    'rand_signed_int': -6,
    'rand_datetime': '2000-09-29 20:29:12+0600',
    'text_array': [
    '9dc001ecfbb0491990cceb17ad04f133',
    'd4a65f3fe01e4a39b8247656b7d9d895',
],
    'words': 'fox mouse',
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
    'word': 'pig',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
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
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    8,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'duck',
    'scorpion',
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
    'mixed_type': None,
    'maybe_null': None,
},
    {
    'id': 171,
    'id_str': [
],
    'text_data': '050d3544b06a4216b6ef2d67b924a283',
    'rand_digit': 1,
    'rand_number': 0.40857,
    'rand_signed_int': 8,
    'rand_datetime': '2000-06-24 15:58:06-1200',
    'text_array': [
    '9549b44a14374b1b93e1a2a1691be168',
    '63c22e9e41ca4accaa89606742fea355',
],
    'words': 'leopard cheetah',
    'nested': {
    'id': 171,
    'rand_digit': 0,
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
    'hello',
],
    'word': 'ladybug',
    'number': 1,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    5,
],
],
    'two_words': [
    'chicken',
    'rhino',
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
    'mixed_type': 'mouse',
    'maybe_null': None,
},
    {
    'id': 172,
    'id_str': [
    '14',
    '27',
],
    'text_data': 'e693af89bdd247beb19210a488d4cf38',
    'rand_digit': 5,
    'rand_number': 0.25598,
    'rand_signed_int': 6,
    'rand_datetime': '2000-05-14T10:24:00.641692-03:00',
    'text_array': [
    '3894fd21f382417987ce4306e4c542c1',
    '0a0d467da51e4c6e9c59fdd51dc7bd46',
],
    'words': 'goat kangaroo',
    'nested': {
    'id': 172,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hyena',
    'kangaroo',
],
    'city': {
    'name': 'Dubai',
    'geo': {
    'lat': 25.204849,
    'lon': 55.270783,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
},
    {
    'id': 173,
    'id_str': [
    '11',
    '13',
],
    'text_data': 'b6fcae292d494db8816d7ba62961f1e9',
    'rand_digit': 8,
    'rand_number': 0.4389,
    'rand_signed_int': 3,
    'rand_datetime': '2000-02-19 08:31:58.292357',
    'text_array': [
    'e2b2fba83d4c4e7c8d806d093317cc52',
    'f0675245dbae4fb28d1329adf9aad3df',
],
    'words': 'rabbit chicken',
    'nested': {
    'id': 173,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'scorpion',
    'fish',
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
    'mixed_type': 0.76136,
    'maybe': 'elephant',
},
    {
    'id': 174,
    'id_str': [
],
    'text_data': 'c8b0cfc099be4beb8c2b39e94d0cbc50',
    'rand_digit': 3,
    'rand_number': 0.19135,
    'rand_signed_int': -8,
    'rand_datetime': '2000-09-03T17:31:28',
    'text_array': [
    'fdec136278c241d08291a7c6c225cd7e',
    '95ef4a2c39414359ba99b530fab2b457',
],
    'words': 'hyena grasshopper',
    'nested': {
    'id': 174,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 3,
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
    'hello',
],
    'word': 'crab',
    'number': 3,
},
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
    -10,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'panda',
    'rhino',
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
    'mixed_type': 0.92231,
    'maybe_null': 'cheetah',
},
    {
    'id': 175,
    'id_str': [
    '12',
    '25',
    '11',
    '25',
],
    'text_data': 'bd20a44a0b9c4a018b193e494c6bdf3d',
    'rand_digit': 7,
    'rand_number': 0.77622,
    'rand_signed_int': -1,
    'rand_datetime': '2000-04-19T21:54:21+0900',
    'text_array': [
    '3bd2bb1aa9e2452f8e45e522c2242e48',
    '9482b3b59763469395dc376b9f72e67b',
],
    'words': 'cow fish',
    'nested': {
    'id': 175,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 8,
},
    {
    'nested_empty': None,
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
    'word': 'horse',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'elephant',
    'ant',
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
    'mixed_type': 4,
    'maybe': 'jaguar',
    'maybe_null': 'panda',
},
    {
    'id': 176,
    'id_str': [
    '26',
    '12',
],
    'text_data': '2d8e5b47b9a8437eb101ccab6299209c',
    'rand_digit': 5,
    'rand_number': 0.58312,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-27 12:50:18.970389',
    'text_array': [
    '9bbf2fdaaf3c49689c141182cfc921dd',
    '731d4d03584047adacaacb3bd0ac016f',
],
    'words': 'duck dog',
    'nested': {
    'id': 176,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 1,
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
    -1,
],
],
    'two_words': [
    'fish',
    'koala',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': [
    1,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'tiger',
    'maybe_null': 'sloth',
},
    {
    'id': 177,
    'id_str': [
    '04',
    '04',
    '21',
    '15',
    '15',
],
    'text_data': 'a07225e2a9ae4957aff80a90bab6155b',
    'rand_digit': 2,
    'rand_number': 0.68279,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-28T09:55:24.669552',
    'text_array': [
    '1ce6023534c9451fa038c0354f558b53',
    '74ac049621384926b9d722a1ef2000e1',
],
    'words': 'bee octopus',
    'nested': {
    'id': 177,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -3,
],
],
    'two_words': [
    'sheep',
    'giraffe',
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
    'mixed_type': False,
    'maybe': 'tiger',
    'maybe_null': 'cheetah',
},
    {
    'id': 178,
    'id_str': [
    '25',
    '23',
    '20',
    '16',
],
    'text_data': '5dfb017f3aa24d5d9a26233253b33b49',
    'rand_digit': 9,
    'rand_number': 0.63628,
    'rand_signed_int': 7,
    'rand_datetime': '2000-09-15',
    'text_array': [
    '0b04b58b0ede4ad0816085a8d321bf1e',
    '16db3d38325347b290b01ccc04357f33',
],
    'words': 'bird elephant',
    'nested': {
    'id': 178,
    'rand_digit': 3,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'fly',
    'hippo',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'lion',
},
    {
    'id': 179,
    'id_str': [
    '16',
],
    'text_data': 'ec465f47b7814fabb5a676b61b7e4d7b',
    'rand_digit': 2,
    'rand_number': 0.6254,
    'rand_signed_int': 8,
    'rand_datetime': '2000-01-06 14:55:31+0300',
    'text_array': [
    '7da1f98fdec548bda07186835fe490b6',
    '76550322d5e14bbfaeb915cfe0fa0a4d',
],
    'words': 'dragonfly lobster',
    'nested': {
    'id': 179,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'tiger',
    'horse',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': [
    49,
],
    'rand_bool': True,
    'mixed_type': 8,
    'maybe': 'scorpion',
    'maybe_null': None,
},
    {
    'id': 180,
    'id_str': [
],
    'text_data': '1a1d7550c62b4792a13cb9390eaa5a2b',
    'rand_digit': 1,
    'rand_number': 0.86404,
    'rand_signed_int': -10,
    'rand_datetime': '2000-06-06T17:14:34.751793',
    'text_array': [
    '55cb862faa1c407fb25d10da7bd0a543',
    '9c4e0401fab34b9fb6c2378b65473931',
],
    'words': 'lobster mosquito',
    'nested': {
    'id': 180,
    'rand_digit': 0,
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
    'hello',
],
    'word': 'cheetah',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -8,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'sloth',
    'bird',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'goat',
},
    {
    'id': 181,
    'id_str': [
    '24',
    '08',
    '28',
    '22',
],
    'text_data': '8b25ef72fb1f480988c5748a629e33b3',
    'rand_digit': 7,
    'rand_number': 0.31092,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-03 03:18',
    'text_array': [
    'e1a74662a2924245a6fd3ae279ae7b47',
    '38e7722bb4dc465f8dbe313f223ef2a7',
],
    'words': 'duck lobster',
    'nested': {
    'id': 181,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'snail',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -1,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'bird',
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
    'mixed_type': None,
    'maybe_null': None,
},
    {
    'id': 182,
    'id_str': [
    '29',
    '13',
    '08',
],
    'text_data': '512d706e4dba4f0696fda3c8ecf25377',
    'rand_digit': 8,
    'rand_number': 0.65889,
    'rand_signed_int': -7,
    'rand_datetime': '2000-04-20T00:30:44',
    'text_array': [
    'f7052737f0b3463297a5200a2fa9494f',
    'f8ea088abfdf423084f4d99cf49a103c',
],
    'words': 'kangaroo shark',
    'nested': {
    'id': 182,
    'rand_digit': 2,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
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
    'word': 'giraffe',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'turtle',
    'duck',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'sloth',
    'maybe_null': 'monkey',
},
    {
    'id': 183,
    'id_str': [
    '10',
    '09',
    '24',
],
    'text_data': '340027cf06de49458435f37f804a1df3',
    'rand_digit': 2,
    'rand_number': 0.72726,
    'rand_signed_int': -2,
    'rand_datetime': '2000-02-08T02:18:15.657949',
    'text_array': [
    '27574ce4de7c4c8dbacef42441e979e4',
    'd7dfbd30226b48fe8f15876aa7306c31',
],
    'words': 'kangaroo jaguar',
    'nested': {
    'id': 183,
    'rand_digit': 5,
    'array': [
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
],
    'word': 'spider',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 1,
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
    [
],
],
    'two_words': [
    'dog',
    'deer',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'dolphin',
    'maybe_null': 'scorpion',
},
    {
    'id': 184,
    'id_str': [
    '23',
    '21',
    '10',
    '22',
    '13',
],
    'text_data': 'ac44960fc77646b6b69fb47bb337a92a',
    'rand_digit': 9,
    'rand_number': 0.8739,
    'rand_signed_int': -4,
    'rand_datetime': '2000-07-19T13:34:18.882811',
    'text_array': [
    'c83636f5df4e4f6eae9490de392452ae',
    '30cc2a9a5601479a9d0bb7a6580b0462',
],
    'words': 'whale deer',
    'nested': {
    'id': 184,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ant',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 7,
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
    [
    -8,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -9,
],
    [
    4,
],
],
    'two_words': [
    'wolf',
    'spider',
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
    'mixed_type': None,
},
    {
    'id': 185,
    'id_str': [
],
    'text_data': '24e599512e1d4483bdd39ecde51e1e35',
    'rand_digit': 9,
    'rand_number': 0.84586,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-16 08:14:34',
    'text_array': [
    'd8fa2dac1cf24c14b345f7f7dad8d516',
    '77c47a582ec8413ca67ef5a506eede53',
],
    'words': 'goat kangaroo',
    'nested': {
    'id': 185,
    'rand_digit': 6,
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
    'word': 'shark',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'wolf',
    'cheetah',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': [
    84,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'horse',
    'maybe_null': 'butterfly',
},
    {
    'id': 186,
    'id_str': [
    '18',
    '24',
    '12',
    '08',
    '03',
],
    'text_data': 'bc2e613c7ab24a17a1dce47a4a1fa9b8',
    'rand_digit': 5,
    'rand_number': 0.16974,
    'rand_signed_int': -7,
    'rand_datetime': '2000-05-05T10:17:24.550998+0000',
    'text_array': [
    '60bf8762793e43d28f8574453feaf3f3',
    '76a23d7d66854419a01cd215191020b0',
],
    'words': 'pig octopus',
    'nested': {
    'id': 186,
    'rand_digit': 1,
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
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'bird',
    'snail',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 'crab',
    'maybe': 'bee',
    'maybe_null': 'wolf',
},
    {
    'id': 187,
    'id_str': [
],
    'text_data': '7d6ce99494534423993d7a48d50cd155',
    'rand_digit': 2,
    'rand_number': 0.57818,
    'rand_signed_int': -10,
    'rand_datetime': '2000-11-02T02:32:07.407795',
    'text_array': [
    'a41c7f2e865046b29ed43168277ffa80',
    '0b1d1cde421e42308e78b7cb2f33bc05',
],
    'words': 'cat goat',
    'nested': {
    'id': 187,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'wolf',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 7,
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
    'bee',
    'fly',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
    {
    'id': 188,
    'id_str': [
],
    'text_data': 'd4e5a034295a4bcbbcfdc98f43115be5',
    'rand_digit': 4,
    'rand_number': 0.95446,
    'rand_signed_int': -2,
    'rand_datetime': '2000-11-17T00:57:47',
    'text_array': [
    '3717d62a8a68478e8cb333a2a77e2378',
    'a6c6658be4b34d1eaf0feb43fd64ef69',
],
    'words': 'duck bear',
    'nested': {
    'id': 188,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'snake',
    'number': 6,
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
    'word': 'kangaroo',
    'number': 3,
},
],
},
    'nested_array': [
    [
    -9,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'koala',
    'cheetah',
],
    'city': {
    'name': 'Johannesburg',
    'geo': {
    'lat': -26.204103,
    'lon': 28.047305,
},
},
    'rand_tuple': [
    92,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'fish',
},
    {
    'id': 189,
    'id_str': [
    '26',
    '15',
],
    'text_data': '20fe268bbc8b45aa8edfb44822b4602d',
    'rand_digit': 1,
    'rand_number': 0.01462,
    'rand_signed_int': 8,
    'rand_datetime': '2000-01-07',
    'text_array': [
    '5879a27fb078497a91629ea529df4fb4',
    '23684a90e1f24246b95fabd1c2f3190d',
],
    'words': 'bird butterfly',
    'nested': {
    'id': 189,
    'rand_digit': 8,
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
],
},
    'nested_array': [
],
    'two_words': [
    'lion',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'rabbit',
},
    {
    'id': 190,
    'id_str': [
    '23',
    '06',
    '06',
],
    'text_data': '512102edac434be9a31c99950933173a',
    'rand_digit': 8,
    'rand_number': 0.03117,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-27 15:56',
    'text_array': [
    'e4eea6284e0942e58a5694960ad51b7b',
    '79fa8aa9f644498b9300fb562b6c7ac7',
],
    'words': 'camel fly',
    'nested': {
    'id': 190,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'rhino',
    'number': 3,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    3,
],
    [
    -4,
],
],
    'two_words': [
    'hyena',
    'snake',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'ladybug',
    'maybe_null': 'zebra',
},
    {
    'id': 191,
    'id_str': [
    '25',
],
    'text_data': 'a9772ac45e584c5bb3167c00367e6749',
    'rand_digit': 0,
    'rand_number': 0.46173,
    'rand_signed_int': -5,
    'rand_datetime': '2000-01-01 21:24:47.239387',
    'text_array': [
    '1f56a90cd6ab407ba32bba20952225bb',
    '781ab8757b0947fe909b484548e5a650',
],
    'words': 'ape dolphin',
    'nested': {
    'id': 191,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 10,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'deer',
    'number': 5,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,5__',
    'two_words': [
    'cat',
    'duck',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.34261,
    'maybe': 'duck',
    'maybe_null': 'duck',
},
    {
    'id': 192,
    'id_str': [
],
    'text_data': '28356400f23e4fd189baedbafb7cc937',
    'rand_digit': 6,
    'rand_number': 0.71896,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-27',
    'text_array': [
    '061d01cc38db40cf9461e871f1439aa7',
    '10feb47a7a704cce955078ccfe12c31c',
],
    'words': 'jaguar lizard',
    'nested': {
    'id': 192,
    'rand_digit': 9,
    'array': [
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
    'word': 'rabbit',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'dog',
    'fly',
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
    'mixed_type': 7,
    'maybe': 'cat',
},
    {
    'id': 193,
    'id_str': [
],
    'text_data': 'b52959f006c54e9e9a2d9ee736c6df96',
    'rand_digit': 7,
    'rand_number': 0.48849,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-08T14:52:11',
    'text_array': [
    '4ddaa1c043994b148ecb56b7a8f37706',
    '94d7f8624fd34679a3839b1fd78fa913',
],
    'words': 'dragonfly dragonfly',
    'nested': {
    'id': 193,
    'rand_digit': 0,
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
    'word': 'ape',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snail',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 5,
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
    [
],
],
    'two_words': [
    'rhino',
    'butterfly',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'sloth',
    'maybe_null': 'cheetah',
},
    {
    'id': 194,
    'id_str': [
    '19',
],
    'text_data': '42c2f743faa347988ec3419c07d91cf1',
    'rand_digit': 2,
    'rand_number': 0.8006,
    'rand_signed_int': -7,
    'rand_datetime': '2000-01-19T03:35:20+0700',
    'text_array': [
    '9a9e6476cd964261b1b7ddc8214b370b',
    '6fc8edc7b5214dd4ac8dac0fb68bf938',
],
    'words': 'crab bee',
    'nested': {
    'id': 194,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'ape',
    'sheep',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': [
    93,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'cat',
    'maybe_null': None,
},
    {
    'id': 195,
    'id_str': [
    '08',
],
    'text_data': 'f50d9a91ae3f4355ab1c688177862ae2',
    'rand_digit': 2,
    'rand_number': 0.87598,
    'rand_signed_int': 2,
    'rand_datetime': '2000-06-21T19:56:51.743100',
    'text_array': [
    '1e63ec392c2e487db995bbb1f04f255c',
    'ecbfefd5fc1c42fbb6ed649614727fb1',
],
    'words': 'kangaroo bee',
    'nested': {
    'id': 195,
    'rand_digit': 5,
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
    'nested_empty': None,
    'nested_empty2': [
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
    'number': 4,
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
    'rabbit',
    'lobster',
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
    'mixed_type': 0.63463,
    'maybe': 'elephant',
    'maybe_null': 'spider',
},
    {
    'id': 196,
    'id_str': [
    '16',
    '17',
],
    'text_data': '5cb6d26310a842fa8c0c293bdb056df6',
    'rand_digit': 5,
    'rand_number': 0.43848,
    'rand_signed_int': 3,
    'rand_datetime': '2000-06-05T23:34:54.888017',
    'text_array': [
    '96ff46a37faf4f40adf8381bf516f749',
    '27ed2ab34de541ac86f13baa24a82686',
],
    'words': 'zebra goat',
    'nested': {
    'id': 196,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    [
    9,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'goat',
    'snake',
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
    'mixed_type': False,
    'maybe_null': None,
},
    {
    'id': 197,
    'id_str': [
],
    'text_data': '9f4088f5e4a749fbb76471b5a06ee65d',
    'rand_digit': 7,
    'rand_number': 0.98613,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-08T10:28:51.324441',
    'text_array': [
    '41ef2becb5164083b2c2d58d2d2541f4',
    'a7bfc79a71b14cf191a2b58077a33580',
],
    'words': 'octopus fish',
    'nested': {
    'id': 197,
    'rand_digit': 7,
    'array': [
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
    'word': 'bear',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'frog',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'deer',
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
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': None,
},
    {
    'id': 198,
    'id_str': [
    '27',
    '15',
    '29',
    '28',
],
    'text_data': 'e68b7769d4644789a3d015fc7799f7ef',
    'rand_digit': 7,
    'rand_number': 0.2703,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-09 07:48:01.660431',
    'text_array': [
    '7f92604fe621402c9d9d53a236c8cba8',
    'd30410781b154bf4888047f0202dcc5d',
],
    'words': 'chicken mouse',
    'nested': {
    'id': 198,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'monkey',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'monkey',
    'deer',
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
    'mixed_type': None,
    'maybe': 'shark',
    'maybe_null': None,
},
    {
    'id': 199,
    'id_str': [
    '02',
    '07',
],
    'text_data': '665ea3c2249143b784fb407fb01dd7f2',
    'rand_digit': 3,
    'rand_number': 0.2439,
    'rand_signed_int': 3,
    'rand_datetime': '2000-09-03 16:55:45',
    'text_array': [
    '20b077f500324d12ae23bc3d23c7f832',
    'ff036daedeee4680befec5561fa8c79c',
],
    'words': 'chicken giraffe',
    'nested': {
    'id': 199,
    'rand_digit': 9,
    'array': [
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
    'word': 'tiger',
    'number': 2,
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
    'hello',
],
    'word': 'tiger',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lobster',
    'lobster',
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
    'mixed_type': 3,
    'maybe': 'lizard',
    'maybe_null': None,
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
    'content-length': '86',
}
        
        # 原始请求内容
        original_content = {
    'limit': 1,
    'filter': {
    'must': [
    {
    'has_id': [
    0,
],
},
],
},
    'with_payload': True,
    'with_vector': False,
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
        """测试请求 3 - PUT http://localhost:6333/collections/congruence_test_collection/points?wait=true"""
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
    'content-length': '2302',
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
    '09',
    '12',
    '18',
    '20',
    '23',
],
    'text_data': 'f02c8dad64104476acb54667cfbfc757',
    'rand_digit': 3,
    'rand_number': 0.62992,
    'rand_signed_int': -2,
    'rand_datetime': '2000-04-08 23:44:06.411550',
    'text_array': [
    '1f69a31554dc47f1988b7188f8960a7b',
    'b71b712f28994a9794567f17932056d8',
],
    'words': 'mosquito grasshopper',
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
    'word': 'jaguar',
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
    'number': 3,
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
    [
    3,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fox',
    'snail',
],
    'city': {
    'name': 'Barcelona',
    'geo': {
    'lat': 41.385064,
    'lon': 2.173403,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 1,
    'maybe': 'dog',
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
        """测试请求 4 - POST http://localhost:6333/collections/congruence_test_collection/points/scroll"""
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_updates.test_upsert')
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
    test = TestUpdatestestUpsert()
    test.run_tests()
