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
logger = logging.getLogger('vdb_fuzzer.test.test_scroll_test_sparse_mixed_ids')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_scroll.test_sparse_mixed_ids"
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



class TestScrolltestSparseMixedIds:
    """自动生成的VDB模糊测试类 - test_scroll.test_sparse_mixed_ids"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_scroll.test_sparse_mixed_ids"
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
    'content-length': '200',
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
    'sparse_vectors': {
    'sparse-text': {
},
    'sparse-image': {
},
    'sparse-code': {
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
    'content-length': '2000260',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 'cc12527b-4a73-4c2b-8514-4cc2ac085efc',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 198,
    'id_str': [
],
    'text_data': '4bb39acbd93943e5973fea86b4439e37',
    'rand_digit': 2,
    'rand_number': 0.17028,
    'rand_signed_int': -6,
    'rand_datetime': '2000-11-09 16:04:41.246001',
    'text_array': [
    'af82ee76a4694047879dc6fc3032449a',
    'a9d201ed7ab8419b8a218684e91d8500',
],
    'words': 'snake jaguar',
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
    'word': 'ladybug',
    'number': 7,
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
],
    'word': 'squid',
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'butterfly',
    'lizard',
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
    'mixed_type': 5,
    'maybe': 'sloth',
},
},
    {
    'id': 30,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 130,
    'id_str': [
    '22',
    '15',
],
    'text_data': 'd4b413809a4446409ad49f940f874f79',
    'rand_digit': 0,
    'rand_number': 0.11183,
    'rand_signed_int': -9,
    'rand_datetime': '2000-12-14 09:00:33-1100',
    'text_array': [
    '75c5425c01754d17b065909cf0ff6d1b',
    'fd20c79f482d4ad4a0dcc013eeb6acc1',
],
    'words': 'elephant cow',
    'nested': {
    'id': 130,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bird',
    'octopus',
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
    'mixed_type': 8,
    'maybe_null': None,
},
},
    {
    'id': 79,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 179,
    'id_str': [
    '08',
],
    'text_data': 'fd31416686604635b807f4ac9a382810',
    'rand_digit': 7,
    'rand_number': 0.7985,
    'rand_signed_int': -5,
    'rand_datetime': '2000-07-30T12:30:51.784406',
    'text_array': [
    '20d914b8528d4813980732180e02aef6',
    '31d52b4679b543f2b907dde2c2d54cd6',
],
    'words': 'panda spider',
    'nested': {
    'id': 179,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 6,
},
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
    'word': 'octopus',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 1,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'gorilla',
    'koala',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 'ccb60fa8-12ea-44bd-b5b8-337507ee3175',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 147,
    'id_str': [
],
    'text_data': '808c290488f74ec6a4727b514fbf4b80',
    'rand_digit': 2,
    'rand_number': 0.90254,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-19',
    'text_array': [
    '7808b0fd44f54e9091a1f5cae95551a6',
    'e3bdc651e8c44ee085f80b23feb6c37e',
],
    'words': 'fox giraffe',
    'nested': {
    'id': 147,
    'rand_digit': 7,
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
],
    'word': 'dragonfly',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'giraffe',
    'dragonfly',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'chicken',
},
},
    {
    'id': 28,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 128,
    'id_str': [
    '17',
],
    'text_data': '94bd16caebad44748ae6919cbe4034ff',
    'rand_digit': 0,
    'rand_number': 0.39828,
    'rand_signed_int': -10,
    'rand_datetime': '2000-08-29 05:27:48.498302-0700',
    'text_array': [
    '0384acfd980d4966a5465814f498f803',
    'c87bef5601c94d27b1cbe3cbd7c44cf0',
],
    'words': 'cow lobster',
    'nested': {
    'id': 128,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'ape',
    'bear',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'cheetah',
    'maybe': 'lobster',
},
},
    {
    'id': 'e1856584-4264-487e-b8e3-87d33206af5d',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 125,
    'id_str': [
],
    'text_data': '0a1e641541b641c8a05f3aa20c6f26ce',
    'rand_digit': 4,
    'rand_number': 0.71217,
    'rand_signed_int': -4,
    'rand_datetime': '2000-04-10T23:22:43.792476-08:00',
    'text_array': [
    '11c4f7d7ce02464fbd0692f575413d0f',
    '6a1c4585a65549b7b4acf32e2dc4d731',
],
    'words': 'duck elephant',
    'nested': {
    'id': 125,
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
    'number': 2,
},
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 7,
},
],
},
    'nested_array': [
    [
    1,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    -7,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'scorpion',
    'lobster',
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
    'mixed_type': 'sheep',
    'maybe': 'duck',
    'maybe_null': 'duck',
},
},
    {
    'id': 93,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 193,
    'id_str': [
    '12',
    '28',
    '24',
    '18',
],
    'text_data': '1af13128845446738940d360603e2b0d',
    'rand_digit': 3,
    'rand_number': 0.98167,
    'rand_signed_int': -10,
    'rand_datetime': '2000-01-19T00:19:17.829382',
    'text_array': [
    'bdb1794bcd1d450e87d134636f8c2104',
    '2a980fda377643caa935d9d5793f116e',
],
    'words': 'tiger lion',
    'nested': {
    'id': 193,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'duck',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'turtle',
    'ant',
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
    'mixed_type': False,
    'maybe': 'koala',
    'maybe_null': 'dog',
},
},
    {
    'id': 99,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 199,
    'id_str': [
],
    'text_data': '75008d71c90a49439e794b34b62d42a8',
    'rand_digit': 3,
    'rand_number': 0.64262,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-30T23:32:55.754680+1100',
    'text_array': [
    '96139d246fe94ac0b6af02cdc7bbb62b',
    '65d6eabe1d6942cf90e2fb5c3af416bd',
],
    'words': 'jaguar monkey',
    'nested': {
    'id': 199,
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
    'number': 7,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'deer',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'monkey',
    'scorpion',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': [
    56,
],
    'rand_bool': True,
    'mixed_type': 'rabbit',
},
},
    {
    'id': 55,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 155,
    'id_str': [
    '17',
    '17',
    '09',
],
    'text_data': '15916af1af6647ebb74cef39d9595f97',
    'rand_digit': 1,
    'rand_number': 0.23875,
    'rand_signed_int': 8,
    'rand_datetime': '2000-03-01 22:59:43',
    'text_array': [
    '9f778511da5041e0967738e15a968617',
    'e0b1b4f31dce4224bfb67c0f29010ac6',
],
    'words': 'whale fly',
    'nested': {
    'id': 155,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    [
    -2,
],
],
    'two_words': [
    'panda',
    'rabbit',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.93757,
    'maybe_null': 'cheetah',
},
},
    {
    'id': 'b41f3824-c8a5-4bb5-a407-97d55636f846',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 121,
    'id_str': [
    '17',
    '27',
    '13',
    '09',
    '16',
],
    'text_data': '2358d06ac2bc43288dab445ac54c25b9',
    'rand_digit': 6,
    'rand_number': 0.6463,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-17 05:53',
    'text_array': [
    'b93b7ab017a44fe491efa90c2c9cf8c9',
    '8035f411fb764651bc620f7a1a72c565',
],
    'words': 'octopus giraffe',
    'nested': {
    'id': 121,
    'rand_digit': 6,
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
    'word': 'fish',
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'leopard',
    'dolphin',
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
    'maybe': 'fox',
    'maybe_null': 'wolf',
},
},
    {
    'id': '5055f7a0-5ef6-487c-ae31-9daf917952d5',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 174,
    'id_str': [
    '27',
    '10',
    '11',
],
    'text_data': 'b3927cebc8584fdab162a5c540b4c881',
    'rand_digit': 8,
    'rand_number': 0.22424,
    'rand_signed_int': -10,
    'rand_datetime': '2000-01-09',
    'text_array': [
    '02538ecc929b4aa8ac8d7ee636117ffe',
    '33cd05ba1a444fa5989b6ea9108626ce',
],
    'words': 'chicken snail',
    'nested': {
    'id': 174,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,3__',
    'two_words': [
    'goat',
    'lizard',
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
    'mixed_type': 'sloth',
    'maybe_null': 'jaguar',
},
},
    {
    'id': 49,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 149,
    'id_str': [
    '24',
    '13',
],
    'text_data': '62b93d029ab44da180d04d256ed8292f',
    'rand_digit': 6,
    'rand_number': 0.86217,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-12',
    'text_array': [
    '2aadff60a5e2476080df12ffd8b1b874',
    '2cd129efce394fc19cacc26ad7c999f3',
],
    'words': 'cow whale',
    'nested': {
    'id': 149,
    'rand_digit': 8,
    'array': [
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -1,
],
],
    'two_words': [
    'frog',
    'lizard',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'crab',
},
},
    {
    'id': 36,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 136,
    'id_str': [
    '26',
],
    'text_data': '2959a1fbf1034dfd96f39068fa2e7fe0',
    'rand_digit': 9,
    'rand_number': 0.30144,
    'rand_signed_int': -9,
    'rand_datetime': '2000-09-24T14:40:17.758148',
    'text_array': [
    'd43819c2d4ea4850a6d3dcf8e5d82023',
    'd24d95a8ee8f4fb6bae50fafa19de586',
],
    'words': 'shark gorilla',
    'nested': {
    'id': 136,
    'rand_digit': 3,
    'array': [
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
    'word': 'bee',
    'number': 2,
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
    'hello',
],
    'word': 'kangaroo',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 8,
},
],
},
    'nested_array': [
    [
    -5,
],
    [
],
    [
    -8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'rhino',
    'chicken',
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
    'mixed_type': 'cat',
    'maybe': 'octopus',
},
},
    {
    'id': '7316262c-ae62-4c13-9e6c-278dfc285b1a',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 188,
    'id_str': [
    '28',
],
    'text_data': '1a226ba021394e298ff39e18454f893b',
    'rand_digit': 6,
    'rand_number': 0.23685,
    'rand_signed_int': -5,
    'rand_datetime': '2000-06-26 11:02:34',
    'text_array': [
    '7c8b4aef27164ab7a02d891d3147ab60',
    '122af43d093144719d366f2c5ec6748b',
],
    'words': 'mosquito scorpion',
    'nested': {
    'id': 188,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'rabbit',
    'number': 3,
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
],
    'word': 'horse',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'cow',
    'butterfly',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'shark',
    'maybe_null': 'horse',
},
},
    {
    'id': 'ad2f436f-a144-49d3-b2da-97d2a3b2086f',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 179,
    'id_str': [
    '05',
    '09',
    '05',
    '04',
],
    'text_data': '366bed7fc97e4dcea6bca9a16b73427e',
    'rand_digit': 0,
    'rand_number': 0.83008,
    'rand_signed_int': 9,
    'rand_datetime': '2000-01-06 08:39',
    'text_array': [
    '0714c92cdfb74411b3b03dcaf025f269',
    'b66a639ed0654dc3b0fdfad64e5a1930',
],
    'words': 'fox horse',
    'nested': {
    'id': 179,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 10,
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
    'word': 'frog',
    'number': 4,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'dolphin',
    'dolphin',
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
    'mixed_type': 8,
    'maybe': 'koala',
    'maybe_null': 'dog',
},
},
    {
    'id': 63,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 163,
    'id_str': [
    '22',
    '08',
    '10',
    '02',
],
    'text_data': '18f3facaa65f483eaa7cc0ea407e73f7',
    'rand_digit': 9,
    'rand_number': 0.5732,
    'rand_signed_int': 4,
    'rand_datetime': '2000-07-11T05:43:00.561009-03:00',
    'text_array': [
    '15716ba13fe1492292846e10b4fe6f9e',
    '18ee9cf9a83b4f8ba6c9519016f8207a',
],
    'words': 'hippo sheep',
    'nested': {
    'id': 163,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'turtle',
    'lion',
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
    'mixed_type': 'wolf',
    'maybe': 'deer',
},
},
    {
    'id': 95,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 195,
    'id_str': [
    '13',
    '23',
    '21',
    '03',
    '11',
],
    'text_data': 'af5988af3f1844d58fb26f23f4d699a8',
    'rand_digit': 7,
    'rand_number': 0.58512,
    'rand_signed_int': -2,
    'rand_datetime': '2000-12-18T15:47:48',
    'text_array': [
    'd052334e5fa645378d42b602d8118f62',
    '2d9b4254dfe54ecd916bad15b6c0c11b',
],
    'words': 'bird bee',
    'nested': {
    'id': 195,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'dolphin',
    'bird',
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
    'mixed_type': 'cat',
    'maybe': 'sheep',
    'maybe_null': 'bird',
},
},
    {
    'id': 39,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 139,
    'id_str': [
    '13',
    '03',
],
    'text_data': 'f3c4356a70ef4adfad10acde0d3a4316',
    'rand_digit': 6,
    'rand_number': 0.70593,
    'rand_signed_int': -2,
    'rand_datetime': '2000-01-09T12:23:27.688427+07:00',
    'text_array': [
    'f8684db9480343239ec364423897788e',
    'd004c0d14b6543f4b403057a8ba0e1ae',
],
    'words': 'kangaroo lion',
    'nested': {
    'id': 139,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'turtle',
    'elephant',
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
    'mixed_type': None,
    'maybe': 'zebra',
    'maybe_null': None,
},
},
    {
    'id': '2137385e-2b88-4253-a295-a7e533e8238c',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 160,
    'id_str': [
    '11',
    '02',
    '12',
],
    'text_data': '43db49a68be04bf289c8ce06ec297b1e',
    'rand_digit': 1,
    'rand_number': 0.8135,
    'rand_signed_int': -10,
    'rand_datetime': '2000-03-09T18:06:58-0400',
    'text_array': [
    '33bbff3a9ef84304a7dd7398ffc27a2c',
    'bd797a9f342144908f72a3c888e6b40c',
],
    'words': 'squid fly',
    'nested': {
    'id': 160,
    'rand_digit': 8,
    'array': [
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
    'word': 'giraffe',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cow',
    'mouse',
],
    'city': {
    'name': 'Dubai',
    'geo': {
    'lat': 25.204849,
    'lon': 55.270783,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'lobster',
},
},
    {
    'id': 18,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 118,
    'id_str': [
    '22',
    '05',
    '17',
],
    'text_data': '76ef692e7fce42c3977740d1af971074',
    'rand_digit': 5,
    'rand_number': 0.48735,
    'rand_signed_int': 5,
    'rand_datetime': '2000-08-16 07:55:27',
    'text_array': [
    '3d892231c2d7450caecedf10ba8db2e3',
    'fcd370c65771460ebb0413b50a7faa5a',
],
    'words': 'hyena jaguar',
    'nested': {
    'id': 118,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'whale',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ant',
    'rhino',
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
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': 43,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 143,
    'id_str': [
    '02',
],
    'text_data': 'd337fdc4fedd4a6f90b95b6898b8275d',
    'rand_digit': 4,
    'rand_number': 0.67262,
    'rand_signed_int': -6,
    'rand_datetime': '2000-09-23 06:24:00.548030-0100',
    'text_array': [
    '33159c013d3d43b38490261644589122',
    'ad32348a1d1540a9af183ed54104035d',
],
    'words': 'snake snail',
    'nested': {
    'id': 143,
    'rand_digit': 1,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'dolphin',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'frog',
    'grasshopper',
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
    'mixed_type': False,
    'maybe': 'frog',
},
},
    {
    'id': 1,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 101,
    'id_str': [
    '11',
    '21',
    '08',
    '21',
],
    'text_data': '53b6102d2dc24075a111fec1b73da049',
    'rand_digit': 5,
    'rand_number': 0.06057,
    'rand_signed_int': 5,
    'rand_datetime': '2000-01-13 06:14:03-0900',
    'text_array': [
    '657ba08ccce84d79a4b238e696a13b2c',
    '05ef9b97056341e496b122257cf4c907',
],
    'words': 'cat zebra',
    'nested': {
    'id': 101,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
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
    'number': 7,
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
    'hello',
],
    'word': 'monkey',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'dog',
    'koala',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': [
    80,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'mosquito',
    'maybe_null': 'kangaroo',
},
},
    {
    'id': 46,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 146,
    'id_str': [
    '15',
    '16',
],
    'text_data': '283f9ee057e34b76a72fdb0fd40784c1',
    'rand_digit': 2,
    'rand_number': 0.93839,
    'rand_signed_int': 10,
    'rand_datetime': '2000-08-03T13:50:14',
    'text_array': [
    'add4548c92454c1dac9f2d80c5e4b827',
    'c0be064d8e054c0ebaf0790b229ba76f',
],
    'words': 'koala panda',
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
    'word': 'horse',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'leopard',
    'squid',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'chicken',
    'maybe_null': None,
},
},
    {
    'id': '4acc01ee-b6b9-4f06-a470-d1a0d54d1acf',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 116,
    'id_str': [
    '25',
    '24',
    '20',
    '29',
],
    'text_data': '382faf2df65c4d42bd188013f584ab9e',
    'rand_digit': 5,
    'rand_number': 0.24927,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-17 16:22:42.753444',
    'text_array': [
    'f659506439494b9abbc5fab50de002c0',
    'e2e539f442474367884776848f77a315',
],
    'words': 'gorilla dolphin',
    'nested': {
    'id': 116,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 10,
},
],
},
    'nested_array': [
    [
    -3,
],
    [
    9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fly',
    'dragonfly',
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
    'maybe': 'wolf',
    'maybe_null': None,
},
},
    {
    'id': 74,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 174,
    'id_str': [
    '01',
    '26',
    '05',
    '11',
],
    'text_data': '66d0185a8a62470abea27909d78666d6',
    'rand_digit': 1,
    'rand_number': 0.90503,
    'rand_signed_int': 3,
    'rand_datetime': '2000-07-19',
    'text_array': [
    '81417e0e467143dd85fce31868d361c4',
    'ef39abc7ee8247a3838268698d6d876f',
],
    'words': 'mosquito zebra',
    'nested': {
    'id': 174,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
    'number': 2,
},
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
    'word': 'giraffe',
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
    'number': 1,
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
    'nested_array': [
    [
],
],
    'two_words': [
    'chicken',
    'cheetah',
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
    'mixed_type': None,
    'maybe': 'mosquito',
},
},
    {
    'id': 72,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 172,
    'id_str': [
    '12',
    '28',
    '27',
    '16',
    '18',
],
    'text_data': '2935219227954c12b20f3ceabf634d45',
    'rand_digit': 1,
    'rand_number': 0.75605,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-29 13:11:59',
    'text_array': [
    '1ae09b40323a449a9ac75a1796e10b52',
    'e8e0770079b241b5bf37bf101899af1a',
],
    'words': 'deer duck',
    'nested': {
    'id': 172,
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
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'pig',
    'number': 10,
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
],
    'two_words': [
    'lizard',
    'gorilla',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': [
    92,
],
    'rand_bool': False,
    'mixed_type': 'lion',
    'maybe_null': 'snail',
},
},
    {
    'id': 54,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 154,
    'id_str': [
    '24',
    '30',
    '16',
    '24',
    '22',
],
    'text_data': '0bdcd04448a1437f99fd8cbe9c987fb0',
    'rand_digit': 3,
    'rand_number': 0.18425,
    'rand_signed_int': -9,
    'rand_datetime': '2000-07-19 17:47:39.814702',
    'text_array': [
    '6418721ddaf047698ae0e4d0ea84ed59',
    'd80f740fdcf440e4bb678deff5f92e8b',
],
    'words': 'cheetah cat',
    'nested': {
    'id': 154,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
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
    'word': 'lion',
    'number': 10,
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
    'crab',
    'butterfly',
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
    'mixed_type': None,
    'maybe': 'chicken',
    'maybe_null': None,
},
},
    {
    'id': 73,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 173,
    'id_str': [
],
    'text_data': '08433686830245768a3b6f665c414e33',
    'rand_digit': 4,
    'rand_number': 0.96176,
    'rand_signed_int': -8,
    'rand_datetime': '2000-07-25T08:30:28.767219',
    'text_array': [
    '33a132b1541a4116a2483d65d819c481',
    'a95b424e00974c9e994d059799623e2e',
],
    'words': 'giraffe fish',
    'nested': {
    'id': 173,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    8,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    6,
],
],
    'two_words': [
    'rhino',
    'jaguar',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': '4e721eb2-d3b1-4738-b14d-424b443b0553',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 126,
    'id_str': [
    '24',
    '04',
    '09',
],
    'text_data': 'a83b40d1318141c18193c92526c5393d',
    'rand_digit': 0,
    'rand_number': 0.87721,
    'rand_signed_int': -10,
    'rand_datetime': '2000-04-29',
    'text_array': [
    '689aaffcbca54644b94ba68d064219dd',
    'e2e1147526d84fd0a2cfac7d447a1ec5',
],
    'words': 'camel scorpion',
    'nested': {
    'id': 126,
    'rand_digit': 6,
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
],
    'word': 'fly',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'fox',
    'mouse',
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
    'mixed_type': True,
    'maybe': 'hippo',
    'maybe_null': 'crab',
},
},
    {
    'id': 92,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 192,
    'id_str': [
    '15',
    '05',
    '13',
    '25',
    '28',
],
    'text_data': 'f44a415cab2d400f902de1d7f8d33fbd',
    'rand_digit': 7,
    'rand_number': 0.79066,
    'rand_signed_int': -8,
    'rand_datetime': '2000-01-30 04:15:47',
    'text_array': [
    '22fb726d486545eea90748d4d245ae78',
    'e82139177eb545d59d13fb084edc572c',
],
    'words': 'octopus tiger',
    'nested': {
    'id': 192,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 4,
},
],
},
    'nested_array': [
    [
    -10,
],
    [
    4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'crab',
    'bird',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': [
    38,
],
    'rand_bool': False,
    'mixed_type': 0.74534,
    'maybe': 'deer',
    'maybe_null': None,
},
},
    {
    'id': '1aa233cb-f91f-40f7-9dd4-d4cf5383cf14',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 142,
    'id_str': [
    '12',
    '20',
],
    'text_data': '196d01eada5f4600beaa7ac0ab12092a',
    'rand_digit': 4,
    'rand_number': 0.52735,
    'rand_signed_int': -9,
    'rand_datetime': '2000-04-27',
    'text_array': [
    '4f3a3d9ebacb4655b7673f807514eaf7',
    'cf51ad661ae44081a809299b5d2870ed',
],
    'words': 'leopard monkey',
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
    'word': 'grasshopper',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'zebra',
    'mouse',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 'horse',
    'maybe_null': 'bird',
},
},
    {
    'id': '4ab1a611-8a63-453f-8da5-404473bdc6ea',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 184,
    'id_str': [
    '21',
    '25',
    '11',
],
    'text_data': 'd062e8424be747a18e574d372a53d338',
    'rand_digit': 2,
    'rand_number': 0.05042,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-12 21:34:35',
    'text_array': [
    'd6d0fe49a1354d5fb26e6ab1aebe51a5',
    '45f0db2d544848019c3dd777bf7a1ea5',
],
    'words': 'sloth deer',
    'nested': {
    'id': 184,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -4,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'snail',
    'zebra',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': 80,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 180,
    'id_str': [
    '08',
],
    'text_data': 'c43eb2e94ec24a85b5889aa0843d3c77',
    'rand_digit': 6,
    'rand_number': 0.83761,
    'rand_signed_int': -2,
    'rand_datetime': '2000-10-11',
    'text_array': [
    'be672024654b4864aeb0eacc08f53442',
    '88728f6dfc464e0f9ecbc54feecba1f9',
],
    'words': 'crab fox',
    'nested': {
    'id': 180,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 3,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'snake',
    'leopard',
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
    'mixed_type': 'octopus',
},
},
    {
    'id': 96,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 196,
    'id_str': [
    '30',
],
    'text_data': '07088c9b8e2148cba56713a24c138f1e',
    'rand_digit': 1,
    'rand_number': 0.1259,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-24 05:51:08',
    'text_array': [
    'dfb7bf119ffc420fb90fbda8efbfd51d',
    '61b6b8dc0f9c409d9172d259d486369c',
],
    'words': 'frog dolphin',
    'nested': {
    'id': 196,
    'rand_digit': 1,
    'array': [
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
],
    'word': 'lobster',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 6,
},
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    10,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'leopard',
    'horse',
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
    'maybe': 'shark',
    'maybe_null': 'giraffe',
},
},
    {
    'id': 83,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 183,
    'id_str': [
],
    'text_data': 'b588211cb36e4ddaaf8479fbd3ddabd2',
    'rand_digit': 0,
    'rand_number': 0.01969,
    'rand_signed_int': 0,
    'rand_datetime': '2000-07-31T05:43:43+0200',
    'text_array': [
    '8edcb9c04d2d461c90d4695aa6f87c70',
    '8c1d905c9b474dd9b1ab80330cce2efa',
],
    'words': 'ladybug gorilla',
    'nested': {
    'id': 183,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 1,
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
    'rhino',
    'mouse',
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
    'mixed_type': False,
    'maybe_null': 'fly',
},
},
    {
    'id': '1bbb0c62-3e32-4afa-b459-60005c9875bd',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 176,
    'id_str': [
    '12',
    '29',
    '20',
    '08',
],
    'text_data': '68eccf88be5b4f508f5abe5badc5fb1d',
    'rand_digit': 0,
    'rand_number': 0.32976,
    'rand_signed_int': -8,
    'rand_datetime': '2000-10-28 04:48:52-0500',
    'text_array': [
    '40520961b96c4b87a2e4de826d083df4',
    '8f96e6a123434c09a3379daea38ca678',
],
    'words': 'lion whale',
    'nested': {
    'id': 176,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
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
    'goat',
    'rabbit',
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
    'mixed_type': 2,
    'maybe_null': 'deer',
},
},
    {
    'id': 26,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 126,
    'id_str': [
    '06',
    '18',
    '02',
    '22',
    '04',
],
    'text_data': '942758f747334e15a11c861cd1814a9e',
    'rand_digit': 8,
    'rand_number': 0.92352,
    'rand_signed_int': 9,
    'rand_datetime': '2000-03-19T04:35:46',
    'text_array': [
    'a2a9dd71ab3b4781a9464cc2d291bdd3',
    'e46542995e164c2ea883b2900d1243ca',
],
    'words': 'leopard wolf',
    'nested': {
    'id': 126,
    'rand_digit': 0,
    'array': [
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
    'hello',
],
    'word': 'mouse',
    'number': 6,
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
    'snail',
    'sheep',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': [
    21,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'frog',
    'maybe_null': 'kangaroo',
},
},
    {
    'id': 76,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 176,
    'id_str': [
    '12',
    '10',
    '07',
    '16',
    '08',
],
    'text_data': '77fd609747df4648a9deddf8e64250e5',
    'rand_digit': 6,
    'rand_number': 0.80858,
    'rand_signed_int': 3,
    'rand_datetime': '2000-10-22 04:17',
    'text_array': [
    '34595ed8ba414e319177021e6578afbb',
    '02045c43d2d04566bcbf3e9aac0124f3',
],
    'words': 'dolphin fly',
    'nested': {
    'id': 176,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ant',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'kangaroo',
    'sheep',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'octopus',
},
},
    {
    'id': 90,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 190,
    'id_str': [
],
    'text_data': '960fcf6f9c4b449bbe9434853240076f',
    'rand_digit': 3,
    'rand_number': 0.60233,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-30T19:47:16.075418-06:00',
    'text_array': [
    'b2bfd4030cdd40b6aabad95318b9b8db',
    '7a99cc8a6b9b47ffb42bfd5d1b0f40fa',
],
    'words': 'cat wolf',
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
    'word': 'lobster',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -3,
],
],
    'two_words': [
    'sloth',
    'hyena',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': '1a32a61f-15be-412f-ab27-22cf5b88f40d',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 180,
    'id_str': [
    '30',
    '16',
    '29',
    '25',
],
    'text_data': '2dd087cdf78d4565850e87db19b5e53a',
    'rand_digit': 0,
    'rand_number': 0.78489,
    'rand_signed_int': -9,
    'rand_datetime': '2000-04-24 07:54:11.304621-1100',
    'text_array': [
    'a753f19a0dc74efc9794ea967c867f2b',
    '79e970786bcd44bcb4314e94a6edd8a6',
],
    'words': 'turtle leopard',
    'nested': {
    'id': 180,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'frog',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'grasshopper',
    'zebra',
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
    'id': '46ee78a6-e257-461a-8552-a70046591562',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 146,
    'id_str': [
],
    'text_data': 'd4d0eb5817734e2399b0676a2588a3aa',
    'rand_digit': 1,
    'rand_number': 0.26518,
    'rand_signed_int': -10,
    'rand_datetime': '2000-10-24T14:09:31',
    'text_array': [
    '5f342608320e43448c0a853d0896d81d',
    '0ac172b4f1784a5bbe4f6c6fa285ca51',
],
    'words': 'frog lizard',
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
    'word': 'lobster',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'goat',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 1,
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'horse',
    'fox',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'fox',
},
},
    {
    'id': 60,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 160,
    'id_str': [
    '18',
    '02',
    '22',
    '14',
],
    'text_data': '1810f94e63e342d9b4eb069cdf199ab5',
    'rand_digit': 2,
    'rand_number': 0.96984,
    'rand_signed_int': -5,
    'rand_datetime': '2000-02-26T12:33:02',
    'text_array': [
    '9416c107142c43a4b6879f9b38385053',
    'b784850dc7c04e2c901846ee298f8e86',
],
    'words': 'spider kangaroo',
    'nested': {
    'id': 160,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'snake',
    'dragonfly',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'ladybug',
    'maybe_null': 'cheetah',
},
},
    {
    'id': 75,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 175,
    'id_str': [
    '12',
    '21',
    '20',
    '21',
    '30',
],
    'text_data': '6a81ee110f7740b7bbd22464f34086d4',
    'rand_digit': 0,
    'rand_number': 0.82513,
    'rand_signed_int': -10,
    'rand_datetime': '2000-03-31T13:49:46.337743',
    'text_array': [
    '583ec9a972764d8f88b7a40e06731428',
    '4a9b0d68e68d4ee78e01894746365a8d',
],
    'words': 'deer squid',
    'nested': {
    'id': 175,
    'rand_digit': 8,
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
    'hello',
],
    'word': 'ladybug',
    'number': 10,
},
],
},
    'nested_array': [
    [
    10,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'hyena',
    'pig',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'panda',
},
},
    {
    'id': '52ca6f18-a776-406c-a49e-7bb4e3bf4c9d',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 115,
    'id_str': [
    '18',
    '17',
],
    'text_data': 'fb4bd097b4fe4c0099ce8e3c123c236b',
    'rand_digit': 4,
    'rand_number': 0.84243,
    'rand_signed_int': -5,
    'rand_datetime': '2001-01-08 14:36',
    'text_array': [
    'cd5b013feed444ff9573483edeea378d',
    '26c29d9561cc408a8c872671deb0f1ea',
],
    'words': 'spider ant',
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
    'word': 'jaguar',
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'deer',
    'crab',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': [
    38,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'fly',
},
},
    {
    'id': '2e68ed7e-3c06-4fbc-a61a-a73c864303f7',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 177,
    'id_str': [
    '19',
    '29',
    '08',
    '01',
    '10',
],
    'text_data': '352ab6ea413945b3af74f7f034c719c0',
    'rand_digit': 6,
    'rand_number': 0.04669,
    'rand_signed_int': -8,
    'rand_datetime': '2000-02-19 18:56:04.916546+0400',
    'text_array': [
    '72f0c2cdf8f3441c9a7ab92561094be5',
    'cd01c62f53f245b5a928b818cfdf5058',
],
    'words': 'shark spider',
    'nested': {
    'id': 177,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -3,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'dog',
    'goat',
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
    'mixed_type': None,
    'maybe': 'leopard',
    'maybe_null': None,
},
},
    {
    'id': '4b829e41-23bc-4372-a358-60a4bc4badab',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 162,
    'id_str': [
    '06',
    '02',
    '29',
],
    'text_data': '38b50c25f69b4ce3b1addc2a07f59611',
    'rand_digit': 2,
    'rand_number': 0.86973,
    'rand_signed_int': -9,
    'rand_datetime': '2001-01-17 15:19:21.065162',
    'text_array': [
    '331971ae8d5c4355855007324fc8adf2',
    '7be16fee7acb42b5a72c81e352e3b7b1',
],
    'words': 'chicken frog',
    'nested': {
    'id': 162,
    'rand_digit': 5,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
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
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hyena',
    'hyena',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': [
    64,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'snake',
    'maybe_null': None,
},
},
    {
    'id': '89558eca-a909-4e66-9705-cc49c160c5e5',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 132,
    'id_str': [
    '18',
    '22',
    '12',
    '17',
],
    'text_data': '04ac7bd9c70a42f68fd17360181f09a2',
    'rand_digit': 0,
    'rand_number': 0.62034,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-23 03:50',
    'text_array': [
    '9edc192dba774970ab138994503ae557',
    '9c26915f764b45539724111ff7ac1d1e',
],
    'words': 'scorpion duck',
    'nested': {
    'id': 132,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    3,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'cat',
    'giraffe',
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
    'maybe': 'rhino',
    'maybe_null': None,
},
},
    {
    'id': 6,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 106,
    'id_str': [
    '23',
    '27',
    '03',
    '06',
    '20',
],
    'text_data': 'a346f972567c47ff8d889e70f8fbcb44',
    'rand_digit': 1,
    'rand_number': 0.10356,
    'rand_signed_int': -1,
    'rand_datetime': '2000-02-05 21:21:17+1000',
    'text_array': [
    '155046d39c6242deb8582d7f4e1f75e0',
    '0a400b6069b84af1bce67a14bafebaf1',
],
    'words': 'cheetah frog',
    'nested': {
    'id': 106,
    'rand_digit': 1,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 3,
},
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
],
    'word': 'butterfly',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'elephant',
    'duck',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': [
    14,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'sloth',
},
},
    {
    'id': 78,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 178,
    'id_str': [
    '25',
    '29',
    '18',
    '25',
    '18',
],
    'text_data': '985dd4f9b9ad40cdb85674e0d5553f48',
    'rand_digit': 9,
    'rand_number': 0.03748,
    'rand_signed_int': -5,
    'rand_datetime': '2000-04-15 18:15:33-0300',
    'text_array': [
    'b7da67de36914570b8c7317d07289bf3',
    '93439d8e513144edb92f74d14575f60a',
],
    'words': 'panda hyena',
    'nested': {
    'id': 178,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fish',
    'cow',
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
    'maybe': 'panda',
    'maybe_null': 'fish',
},
},
    {
    'id': 12,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 112,
    'id_str': [
    '08',
    '01',
],
    'text_data': 'a27e4fd736834a9a83ff258367c6bee7',
    'rand_digit': 8,
    'rand_number': 0.37749,
    'rand_signed_int': -3,
    'rand_datetime': '2000-09-11T04:55:21.677930',
    'text_array': [
    '34e3e9282de14b209a518841286720e2',
    'c480549a1aef4e5085a376621e590bc0',
],
    'words': 'goat panda',
    'nested': {
    'id': 112,
    'rand_digit': 2,
    'array': [
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
    'word': 'gorilla',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    [
    9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dragonfly',
    'monkey',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'dolphin',
},
},
    {
    'id': '780d424f-6f40-4ef4-8c4c-95230b52b7e0',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 158,
    'id_str': [
    '14',
    '27',
    '08',
    '29',
],
    'text_data': 'b58477a77e584a52805eb83a7bd175de',
    'rand_digit': 2,
    'rand_number': 0.31198,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-13 20:05:55.365498-1100',
    'text_array': [
    '3dc644164a78487a84b1e1a7c3abb4f1',
    '3009489a26d94989a8fff2eda272873d',
],
    'words': 'fly fly',
    'nested': {
    'id': 158,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'fly',
    'number': 4,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 7,
},
],
},
    'nested_array': [
    [
    10,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'camel',
    'fly',
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
    'mixed_type': 'fox',
    'maybe': 'octopus',
},
},
    {
    'id': 69,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 169,
    'id_str': [
    '07',
    '17',
    '24',
],
    'text_data': 'a93aab8d400f47708a02520bb91970f1',
    'rand_digit': 0,
    'rand_number': 0.43199,
    'rand_signed_int': -3,
    'rand_datetime': '2000-02-23 13:21',
    'text_array': [
    '863236f480044e4f89b99f6b40ee5733',
    '65fb779b555548139d68d95764bbf9a6',
],
    'words': 'crab chicken',
    'nested': {
    'id': 169,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'dog',
    'mosquito',
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
    'mixed_type': 0.0054,
    'maybe_null': None,
},
},
    {
    'id': 'eef36b7d-99fb-4e2e-8499-337b0314699f',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 148,
    'id_str': [
    '18',
    '19',
    '24',
    '07',
    '12',
],
    'text_data': '8e6661859a6e4ab095953bacf06e3189',
    'rand_digit': 8,
    'rand_number': 0.68597,
    'rand_signed_int': 9,
    'rand_datetime': '2000-06-02T02:31:02-0800',
    'text_array': [
    'ff75358c46fd47369e235e060e02abcd',
    '4d400a72e9eb4ee0a21449c0e79c3574',
],
    'words': 'mouse frog',
    'nested': {
    'id': 148,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 8,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'butterfly',
    'chicken',
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
    'mixed_type': 0.78335,
    'maybe': 'wolf',
},
},
    {
    'id': 23,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 123,
    'id_str': [
],
    'text_data': '9a4da3ec635744c6a53913e75d22f456',
    'rand_digit': 6,
    'rand_number': 0.7985,
    'rand_signed_int': -9,
    'rand_datetime': '2000-02-02T12:08:30.000657-0800',
    'text_array': [
    'a813bd19b8714a25b44097d609b72882',
    '0fbb57b482f546e7b275a21bc552e782',
],
    'words': 'jaguar hyena',
    'nested': {
    'id': 123,
    'rand_digit': 0,
    'array': [
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
    'word': 'camel',
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'fox',
    'koala',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': [
    21,
],
    'rand_bool': False,
    'mixed_type': 9,
    'maybe_null': None,
},
},
    {
    'id': 98,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 198,
    'id_str': [
    '23',
    '25',
    '10',
],
    'text_data': 'a53817f1405048f691437e8d266aa1f9',
    'rand_digit': 6,
    'rand_number': 0.30241,
    'rand_signed_int': 1,
    'rand_datetime': '2000-08-28 15:40:44.788611',
    'text_array': [
    'd7d31beffc344e319068f5dc663c00c2',
    'ae671e3988a04c5e86434bf9463e0f4b',
],
    'words': 'crab squid',
    'nested': {
    'id': 198,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'kangaroo',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'hyena',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 5,
},
],
},
    'nested_array': [
    [
    -3,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -8,
],
],
    'two_words': [
    'mosquito',
    'panda',
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
    'maybe_null': 'koala',
},
},
    {
    'id': 'b1787434-e91a-4684-a233-abf52bbfad75',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 187,
    'id_str': [
    '11',
],
    'text_data': 'c3a7a1b2f5e14e368f8c912c22ea4530',
    'rand_digit': 4,
    'rand_number': 0.33654,
    'rand_signed_int': 9,
    'rand_datetime': '2000-05-29 04:33:15.811252+1000',
    'text_array': [
    'f89bbc05b52743a79ebf02aa9f983603',
    'd8aa1acac1a74edc81ff0f8fc55d4a40',
],
    'words': 'dolphin shark',
    'nested': {
    'id': 187,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'ape',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'duck',
    'hippo',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': [
    93,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'chicken',
    'maybe_null': 'cow',
},
},
    {
    'id': '159bc68d-a417-4f53-a56d-d706a52911d2',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 168,
    'id_str': [
    '19',
    '05',
    '09',
],
    'text_data': '7fcee779e323464d8597a6357d58c2fc',
    'rand_digit': 3,
    'rand_number': 0.9264,
    'rand_signed_int': -10,
    'rand_datetime': '2000-11-02 12:35',
    'text_array': [
    'c638b447b4df463f95631366e33df7fd',
    '3525a698ca64406ea79ba8706dcc1667',
],
    'words': 'crab squid',
    'nested': {
    'id': 168,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
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
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'scorpion',
    'sloth',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'ladybug',
},
},
    {
    'id': 37,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 137,
    'id_str': [
    '06',
    '17',
    '25',
],
    'text_data': '857782d17c614d5196a1ec4689442e09',
    'rand_digit': 9,
    'rand_number': 0.20088,
    'rand_signed_int': -8,
    'rand_datetime': '2000-07-23T06:14:01.304463',
    'text_array': [
    'c2508bf1646f41d8b874c7b64a7d6d59',
    '9649624026ed415e83e0ddc65a82faf1',
],
    'words': 'hyena grasshopper',
    'nested': {
    'id': 137,
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
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'chicken',
    'octopus',
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
    'mixed_type': 'spider',
},
},
    {
    'id': 35,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 135,
    'id_str': [
    '24',
    '26',
],
    'text_data': '05fe24fe83914178bc3add25384aab04',
    'rand_digit': 1,
    'rand_number': 0.17692,
    'rand_signed_int': 1,
    'rand_datetime': '2000-02-02 04:09:23',
    'text_array': [
    '94cd6e47baaf4983a17d4061b3d5637c',
    '7ed15b9a820e4e9181c9ba276a0a4688',
],
    'words': 'cat fish',
    'nested': {
    'id': 135,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fish',
    'horse',
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
    'mixed_type': 0.58742,
    'maybe_null': None,
},
},
    {
    'id': '7557501b-369b-41a7-b937-b91fa8412784',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 159,
    'id_str': [
],
    'text_data': '3e571b7a897d4a7ab92017d18d86c0f4',
    'rand_digit': 2,
    'rand_number': 0.7221,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-04 06:55:56',
    'text_array': [
    '8a36f9df78b34d86b0892ddca7b61dae',
    '72c11e83a7f9435e8767fdd5305cc800',
],
    'words': 'pig rhino',
    'nested': {
    'id': 159,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'fly',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fish',
    'wolf',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'dog',
},
},
    {
    'id': 5,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 105,
    'id_str': [
],
    'text_data': 'e150fb7dde064ef6949bdb5660983669',
    'rand_digit': 7,
    'rand_number': 0.07993,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-12 17:05:37',
    'text_array': [
    '4d4aeca7cd7745beb999cff47b82a6b3',
    '556c3e0f91fe476eaccdddb82792cce7',
],
    'words': 'rhino deer',
    'nested': {
    'id': 105,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'bird',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'frog',
    'lobster',
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
    'maybe': 'gorilla',
    'maybe_null': None,
},
},
    {
    'id': 'db3fa9fb-4861-48b9-a72a-73530241e4ad',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 113,
    'id_str': [
],
    'text_data': 'f60204b7aa9a49518d1304b7dbe734a0',
    'rand_digit': 1,
    'rand_number': 0.34654,
    'rand_signed_int': 6,
    'rand_datetime': '2001-01-06 12:14:59',
    'text_array': [
    'f420adf9769e41fa8e7188f5afc20c85',
    'ea58876ec45c4fa8a2260913ed216c5f',
],
    'words': 'bird sheep',
    'nested': {
    'id': 113,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dog',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    6,
],
],
    'two_words': [
    'sheep',
    'grasshopper',
],
    'city': {
    'name': 'London',
    'geo': {
    'lat': 51.507351,
    'lon': -0.127758,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'giraffe',
},
},
    {
    'id': '9ab997cc-1413-4e75-98d1-a81ae3ea0cd6',
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 110,
    'id_str': [
    '04',
    '17',
    '27',
    '27',
],
    'text_data': 'c63d319ca56f4e37acb1b604c1069937',
    'rand_digit': 9,
    'rand_number': 0.50771,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-05T13:12:00',
    'text_array': [
    '76bb7063acfb4d53ae810d376b6a7072',
    '26edf1bcb11e465f8674ecb781fb7229',
],
    'words': 'goat cat',
    'nested': {
    'id': 110,
    'rand_digit': 7,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -1,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dog',
    'cow',
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
    'mixed_type': 0.33869,
    'maybe': 'tiger',
},
},
    {
    'id': 7,
    'vector': {
    'sparse-text': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'sparse-image': {
    'indices': self.mutator.generate_float_array(dimension=200, normalized=True),
    'values': self.mutator.generate_float_array(dimension=200, normalized=True),
},
    'sparse-code': {
    'indices': self.mutator.generate_float_array(dimension=2000, normalized=True),
    'values': self.mutator.generate_float_array(dimension=2000, normalized=True),
},
},
    'payload': {
    'id': 107,
    'id_str': [
    '13',
],
    'text_data': '3483265db1ea4736b5ce0e7bda6957e9',
    'rand_digit': 4,
    'rand_number': 0.56961,
    'rand_signed_int': 7,
    'rand_datetime': '2000-06-01T12:40:07',
    'text_array': [
    'b89b323bab764e8ca249a2bf90cf4391',
    '17c7c65ab00a4d23bca697784c2144cc',
],
    'words': 'deer wolf',
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
    'word': 'kangaroo',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 5,
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
    [
],
    [
    -9,
],
],
    'two_words': [
    'horse',
    'pig',
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
    'mixed_type': False,
    'maybe': 'giraffe',
    'maybe_null': 'ladybug',
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
    'limit': 10,
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
    'content-length': '64',
}
        
        # 原始请求内容
        original_content = {
    'offset': 10,
    'limit': 20,
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
    'content-length': '200',
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
    'sparse_vectors': {
    'sparse-text': {
},
    'sparse-image': {
},
    'sparse-code': {
},
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_scroll.test_sparse_mixed_ids')
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
    test = TestScrolltestSparseMixedIds()
    test.run_tests()
