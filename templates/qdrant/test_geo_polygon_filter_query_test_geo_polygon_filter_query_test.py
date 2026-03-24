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
logger = logging.getLogger('vdb_fuzzer.test.test_geo_polygon_filter_query_test_geo_polygon_filter_query')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_geo_polygon_filter_query.test_geo_polygon_filter_query"
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



class TestGeoPolygonFilterQuerytestGeoPolygonFilterQuery:
    """自动生成的VDB模糊测试类 - test_geo_polygon_filter_query.test_geo_polygon_filter_query"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_geo_polygon_filter_query.test_geo_polygon_filter_query"
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
    'content-length': '138384',
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
    '04',
    '01',
    '24',
    '09',
    '08',
],
    'text_data': '5572b14282b14215ae95af97be62babf',
    'rand_digit': 3,
    'rand_number': 0.13954,
    'rand_signed_int': -7,
    'rand_datetime': '2000-03-08T12:39:26.619176',
    'text_array': [
    '814699219c7442abaff6cf5cb54244d2',
    'df6e920e69404d3096da87c289acb4b4',
],
    'words': 'horse frog',
    'nested': {
    'id': 100,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 9,
},
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'ant',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'horse',
    'rhino',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'snake',
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
    '03',
    '28',
],
    'text_data': '3dec4df450ad498d952261edd9bdd809',
    'rand_digit': 3,
    'rand_number': 0.86648,
    'rand_signed_int': 2,
    'rand_datetime': '2000-08-03 21:48:12.475435',
    'text_array': [
    '2f813beb1d304c92a03e2bb2dcaffa5e',
    '24e3056df2cd42afb1d676267010c07c',
],
    'words': 'gorilla frog',
    'nested': {
    'id': 101,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'squid',
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
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    [
    8,
],
],
    'two_words': [
    'scorpion',
    'crab',
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
    'mixed_type': False,
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
],
    'text_data': '280c1405de294c278985a66b62ad2284',
    'rand_digit': 1,
    'rand_number': 0.15284,
    'rand_signed_int': -5,
    'rand_datetime': '2000-11-23 21:37:55.625380+0000',
    'text_array': [
    '5da10e3f8d1b483f85dd7397bc987bf2',
    'b5a193bceaf74c50a63fb36db2a46ef0',
],
    'words': 'lion jaguar',
    'nested': {
    'id': 102,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'lion',
    'number': 1,
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
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'hyena',
    'sloth',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'scorpion',
    'maybe_null': None,
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
    '16',
    '27',
    '03',
    '25',
    '18',
],
    'text_data': '370f39f02d1b45c9be34ed852362d1ad',
    'rand_digit': 2,
    'rand_number': 0.12839,
    'rand_signed_int': 5,
    'rand_datetime': '2000-05-08 06:11',
    'text_array': [
    '7be58bfa0a2643018c7264b1808b0149',
    'ae99af3867324b71875541c232da869f',
],
    'words': 'deer frog',
    'nested': {
    'id': 103,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'panda',
    'number': 9,
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
    'word': 'spider',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'hyena',
    'lizard',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'dolphin',
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
    '04',
    '02',
    '13',
    '24',
    '11',
],
    'text_data': 'f107b3d02a1849b0adccade675226631',
    'rand_digit': 1,
    'rand_number': 0.24866,
    'rand_signed_int': -4,
    'rand_datetime': '2000-12-14T10:45:45',
    'text_array': [
    '9c7637817b0540c48a49372dc97e5c52',
    'e208853772ca4792a0dfa89cf971920a',
],
    'words': 'lion lizard',
    'nested': {
    'id': 104,
    'rand_digit': 1,
    'array': [
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
    'word': 'cat',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    2,
],
    [
],
],
    'two_words': [
    'rhino',
    'turtle',
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
    'mixed_type': None,
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
    '02',
],
    'text_data': 'e58d5ea1dae54dcca6c6f77b9d0683a2',
    'rand_digit': 8,
    'rand_number': 0.08011,
    'rand_signed_int': -5,
    'rand_datetime': '2000-02-23 05:19:48.623939+0900',
    'text_array': [
    '06776f2f047a45e0a416ec3485f19564',
    'ec7a5b97f3cf45a7a51221b3f1147eac',
],
    'words': 'giraffe pig',
    'nested': {
    'id': 105,
    'rand_digit': 9,
    'array': [
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    0,
],
    [
    -2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lion',
    'hippo',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': [
    9,
],
    'rand_bool': False,
    'mixed_type': None,
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
    'text_data': '9f7a569f1f4443488c2634f794b64526',
    'rand_digit': 2,
    'rand_number': 0.26447,
    'rand_signed_int': -7,
    'rand_datetime': '2000-04-30T17:45:32.285577',
    'text_array': [
    '621d40206a2f46bfb60d089d34f90447',
    'ebfdf4c4c6764b8b9fe247322c34b776',
],
    'words': 'crab ape',
    'nested': {
    'id': 106,
    'rand_digit': 3,
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
    'word': 'ape',
    'number': 3,
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
    'word': 'cat',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'scorpion',
    'squid',
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
    'mixed_type': False,
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
    '28',
],
    'text_data': 'b3506c2d8f84472bb3d2a60b0ab96e51',
    'rand_digit': 2,
    'rand_number': 0.97621,
    'rand_signed_int': -5,
    'rand_datetime': '2000-11-16T05:43:29+1100',
    'text_array': [
    '5df2848c7ae343fcb4283b3705da8a77',
    'e09d77bb2e484073ad21b9773c4895bf',
],
    'words': 'butterfly zebra',
    'nested': {
    'id': 107,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
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
    'shark',
    'rabbit',
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
    'mixed_type': 0.93924,
    'maybe': 'sloth',
    'maybe_null': 'lobster',
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
    '14',
    '20',
],
    'text_data': 'a8ba9fa3b7cb4c87ae0e2b60fdc757ea',
    'rand_digit': 8,
    'rand_number': 0.11565,
    'rand_signed_int': 8,
    'rand_datetime': '2000-05-27T15:19:30.267095+1000',
    'text_array': [
    '239688f50f374a458c326535baf0f3e4',
    'cb890772921c41468d72b7518f7b953a',
],
    'words': 'jaguar dragonfly',
    'nested': {
    'id': 108,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'shark',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'monkey',
    'lion',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.66385,
    'maybe': 'rabbit',
    'maybe_null': 'mouse',
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
    '16',
],
    'text_data': 'a829341deca74bd9a14e7c90bdfd6cae',
    'rand_digit': 9,
    'rand_number': 0.84974,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-19',
    'text_array': [
    '4b4e540738404c47bbaae2ffe886c551',
    'e39b7ac2e7f3484c8e3e9806d85b32ad',
],
    'words': 'squid rhino',
    'nested': {
    'id': 109,
    'rand_digit': 7,
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
    'hello',
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
    'word': 'grasshopper',
    'number': 2,
},
],
},
    'nested_array': [
    [
    4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ladybug',
    'chicken',
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
    'mixed_type': 'bee',
    'maybe': 'snake',
    'maybe_null': 'goat',
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
    '07',
    '03',
    '14',
    '14',
    '11',
],
    'text_data': '47f9cda9181a4b15a8256fd569704f44',
    'rand_digit': 8,
    'rand_number': 0.46592,
    'rand_signed_int': -9,
    'rand_datetime': '2000-06-09T15:40:20',
    'text_array': [
    '12ebdb7e0416402a9c13f45a21e50493',
    'd569612939d6449ab3f8d29d5ab9dfbd',
],
    'words': 'bee panda',
    'nested': {
    'id': 110,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'fly',
    'number': 7,
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
    'word': 'bear',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dog',
    'giraffe',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'horse',
    'maybe_null': 'snail',
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
    '02',
    '12',
    '08',
    '21',
],
    'text_data': 'ae4870973d2143149688986df09037cf',
    'rand_digit': 1,
    'rand_number': 0.78123,
    'rand_signed_int': 10,
    'rand_datetime': '2000-02-01T06:27:57.790870-0500',
    'text_array': [
    'b427e1bebeec421598662b59a1023444',
    '541c123bfcff476cbaf0c43ef6c0e8b7',
],
    'words': 'dog hippo',
    'nested': {
    'id': 111,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'fox',
    'koala',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'dolphin',
    'maybe_null': 'grasshopper',
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
    '27',
    '16',
    '04',
],
    'text_data': 'eadb519037094913be28d9011e1dff85',
    'rand_digit': 6,
    'rand_number': 0.96079,
    'rand_signed_int': 10,
    'rand_datetime': '2000-12-23T02:09:45+0100',
    'text_array': [
    '21f6078c7e794e98887ecfef2166d34b',
    'bfba3772c8e54307af6bbe7073d69ccf',
],
    'words': 'jaguar dolphin',
    'nested': {
    'id': 112,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 8,
},
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    5,
],
    [
    1,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'scorpion',
    'sloth',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'jaguar',
    'maybe_null': 'snail',
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
    '11',
    '12',
    '23',
    '15',
],
    'text_data': '7fec0de8957447299561045e35e311a0',
    'rand_digit': 4,
    'rand_number': 0.30662,
    'rand_signed_int': -3,
    'rand_datetime': '2000-04-03T17:11:19.756321-02:00',
    'text_array': [
    '7aa204510618419d924eb61c7dcedbd7',
    '43b69b289e66447095a9a87842deadb6',
],
    'words': 'cheetah ant',
    'nested': {
    'id': 113,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    1,
],
    [
    -1,
],
    [
],
],
    'two_words': [
    'crab',
    'cheetah',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'fish',
    'maybe_null': 'fish',
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
    '21',
    '22',
    '02',
    '05',
],
    'text_data': 'e9d4dcf6e7da4bedb78e0884b1883284',
    'rand_digit': 2,
    'rand_number': 0.81114,
    'rand_signed_int': -1,
    'rand_datetime': '2000-03-07 03:53:13.260247+0500',
    'text_array': [
    'e4d92c768c9b40f8bcb507d388fb7d57',
    '30714cf77854451d95c40fa43fb21e89',
],
    'words': 'sloth sloth',
    'nested': {
    'id': 114,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
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
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lizard',
    'duck',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': [
    20,
],
    'rand_bool': True,
    'mixed_type': 0.23148,
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
    '14',
],
    'text_data': '0d31d29debb24ee9bd8761e81c03c4cf',
    'rand_digit': 1,
    'rand_number': 0.54456,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-25T17:21:49.952538',
    'text_array': [
    'b53a661c8e4f46109c5712466275acb5',
    '2f3a1f8f06d34c3c840955665995261d',
],
    'words': 'fish bird',
    'nested': {
    'id': 115,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'squid',
    'number': 7,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'turtle',
    'dog',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'zebra',
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
    '11',
    '22',
],
    'text_data': 'e52b9cc5b8954dce96bd1f5011519b71',
    'rand_digit': 1,
    'rand_number': 0.85773,
    'rand_signed_int': 0,
    'rand_datetime': '2000-11-15 17:37:14',
    'text_array': [
    '7f4b3b531da44e049d311f5275f41cf9',
    '15a57c741c8a416d83a4c2dc378d992f',
],
    'words': 'giraffe mosquito',
    'nested': {
    'id': 116,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'bee',
    'giraffe',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': [
    84,
],
    'rand_bool': False,
    'mixed_type': 6,
    'maybe_null': 'squid',
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
    '04',
    '01',
    '21',
],
    'text_data': '56db334bb704449490a4bad29686663a',
    'rand_digit': 9,
    'rand_number': 0.79931,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-29T08:48:08.577596+0500',
    'text_array': [
    'fcc4fa447e3d44f6a074b84029955ae5',
    '2debf00c7d404dfead8045d027b68c7a',
],
    'words': 'snake fly',
    'nested': {
    'id': 117,
    'rand_digit': 1,
    'array': [
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
    'hello',
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
    'word': 'tiger',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'mosquito',
    'cat',
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
    'maybe_null': 'bee',
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
    '02',
    '11',
    '24',
],
    'text_data': '51b0bd6111fc40c8bba8244c4caaeb47',
    'rand_digit': 7,
    'rand_number': 0.70523,
    'rand_signed_int': 2,
    'rand_datetime': '2000-10-26T21:01:46+0300',
    'text_array': [
    'e11a1394fa8e48cf95516f8919e11889',
    '54184ff48d974ed89d5038f99ce3af71',
],
    'words': 'sheep hyena',
    'nested': {
    'id': 118,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'spider',
    'cheetah',
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
    'mixed_type': 0.44368,
    'maybe': 'deer',
    'maybe_null': 'jaguar',
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
    '19',
    '22',
    '26',
],
    'text_data': '1b643dd39bfc478e9e6d103cc0db9042',
    'rand_digit': 2,
    'rand_number': 0.16998,
    'rand_signed_int': -8,
    'rand_datetime': '2000-10-24 03:08:33+0300',
    'text_array': [
    '9fa03b4482054b63811c3a64f5b3f956',
    'ca5b899da4b249029efc7a15a010efab',
],
    'words': 'goat snake',
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
    'word': 'cat',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
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
    'number': 5,
},
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
    'hello',
],
    'word': 'rhino',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lizard',
    'rhino',
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
    'mixed_type': 0.86507,
    'maybe_null': 'dragonfly',
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
    '08',
    '21',
],
    'text_data': 'eb3c0744bb2f4a32b5fe496374a10fe1',
    'rand_digit': 3,
    'rand_number': 0.62089,
    'rand_signed_int': -6,
    'rand_datetime': '2000-03-16T11:16:00.947287-0300',
    'text_array': [
    '56e5d9ece67b49298b1a6407be1ea851',
    '633eb22ff30b4a488fee512e536e6299',
],
    'words': 'mouse panda',
    'nested': {
    'id': 120,
    'rand_digit': 5,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 6,
},
    {
    'nested_empty': None,
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
    'word': 'tiger',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'goat',
    'ant',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
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
    '08',
    '21',
    '03',
    '21',
],
    'text_data': '4dd7feb2c2fb4d5e8eb30ec731e829a6',
    'rand_digit': 7,
    'rand_number': 0.90939,
    'rand_signed_int': -1,
    'rand_datetime': '2000-11-13T03:11:11-1100',
    'text_array': [
    'b3e6e5c8ebb74b61a0b36bc3e624a962',
    '6816aa9ef9274bc892cc54e515919f0f',
],
    'words': 'fox leopard',
    'nested': {
    'id': 121,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'shark',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'octopus',
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
    '18',
    '29',
],
    'text_data': '32b2d368db244bb5b9ba1fdf8d8deeb9',
    'rand_digit': 5,
    'rand_number': 0.06055,
    'rand_signed_int': -2,
    'rand_datetime': '2000-05-27T10:17:16.128093',
    'text_array': [
    '0be56889c8e848888d84d201858566de',
    'b5276c2b79344e74892bdae27c3110ba',
],
    'words': 'frog dolphin',
    'nested': {
    'id': 122,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'butterfly',
    'ape',
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
    'mixed_type': 0.81305,
    'maybe_null': 'sheep',
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
    '09',
    '26',
    '06',
    '04',
],
    'text_data': '76fcada150944f708e7f2b9a43e37d65',
    'rand_digit': 0,
    'rand_number': 0.1318,
    'rand_signed_int': 1,
    'rand_datetime': '2000-07-03T19:21:59.617457',
    'text_array': [
    '506d3fbe2d9343508152ff2de3ad1708',
    '3c620ed7c9cf43ca991235077389a06e',
],
    'words': 'turtle bird',
    'nested': {
    'id': 123,
    'rand_digit': 2,
    'array': [
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
    'word': 'shark',
    'number': 9,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -8,
],
],
    'two_words': [
    'sheep',
    'bear',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'scorpion',
    'maybe_null': 'ape',
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
    '13',
    '14',
    '24',
],
    'text_data': 'b9e30974429b4d40b492418c53f148bf',
    'rand_digit': 1,
    'rand_number': 0.31255,
    'rand_signed_int': 0,
    'rand_datetime': '2000-07-16T23:29:24+0900',
    'text_array': [
    '86435f4191c547079e7f4486166f8479',
    '8df383189934498aa5f6e31d0f4dfd6c',
],
    'words': 'fish horse',
    'nested': {
    'id': 124,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'gorilla',
    'spider',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': [
    36,
],
    'rand_bool': False,
    'mixed_type': 'gorilla',
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
    '25',
    '27',
    '20',
    '20',
],
    'text_data': '3895e61888c245289fa2ed2e5695eed4',
    'rand_digit': 8,
    'rand_number': 0.02625,
    'rand_signed_int': -2,
    'rand_datetime': '2000-01-23T11:43:35.189179',
    'text_array': [
    '107dfd6be4e74def9779a2e263a387b0',
    '95cb811176ec4e6c9a88eddf32303b32',
],
    'words': 'fox ape',
    'nested': {
    'id': 125,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
    8,
],
],
    'two_words': [
    'shark',
    'giraffe',
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
    'mixed_type': 'horse',
    'maybe_null': 'ant',
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
    '02',
    '22',
    '03',
    '09',
],
    'text_data': '479c7241f30a4f69ace9242c339bf572',
    'rand_digit': 7,
    'rand_number': 0.66194,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-09T08:18:03.434303',
    'text_array': [
    '7b340257e4e24e3896e23cfe5e481472',
    '57d7ab0a2576464c83c99d50ebf15c02',
],
    'words': 'hyena pig',
    'nested': {
    'id': 126,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'panda',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 7,
},
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
    -2,
],
],
    'two_words': [
    'wolf',
    'monkey',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': [
    63,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'lion',
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
    '14',
    '19',
    '13',
    '23',
],
    'text_data': '633883fef5bf424e955af1015ff69ded',
    'rand_digit': 6,
    'rand_number': 0.28952,
    'rand_signed_int': 2,
    'rand_datetime': '2000-01-17T04:47:39+0700',
    'text_array': [
    '9f637eb9868a42de9a60f5190e23931e',
    'a6e83258cc264dd6bb20a57b11387c65',
],
    'words': 'squid elephant',
    'nested': {
    'id': 127,
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
    'word': 'fish',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bee',
    'whale',
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
    'mixed_type': None,
    'maybe': 'fish',
    'maybe_null': 'camel',
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
],
    'text_data': '4047c035cf774fad9cb1fafe27f542b8',
    'rand_digit': 0,
    'rand_number': 0.36874,
    'rand_signed_int': -1,
    'rand_datetime': '2000-02-29 14:22:10.675981+0700',
    'text_array': [
    '937aacf414114d11ab7ad8db1be37813',
    'bf2231c03eb34551ba6f467892df829b',
],
    'words': 'rhino lion',
    'nested': {
    'id': 128,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 8,
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
    'word': 'ape',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'butterfly',
    'whale',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': [
    42,
],
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'crab',
    'maybe_null': None,
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
    '21',
    '26',
    '11',
],
    'text_data': '94c5797e3bdc47d5ae0931afb1888a03',
    'rand_digit': 2,
    'rand_number': 0.67012,
    'rand_signed_int': 6,
    'rand_datetime': '2000-03-13T14:05:22',
    'text_array': [
    'f2e2aeaad1f84bc78a25f289abce7dca',
    '357778d3f08640c2a98ef6c68064d69f',
],
    'words': 'dog elephant',
    'nested': {
    'id': 129,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 8,
},
],
},
    'nested_array': [
    [
    -6,
],
],
    'two_words': [
    'goat',
    'fish',
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
    'mixed_type': 8,
    'maybe_null': 'elephant',
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
    '24',
    '08',
    '15',
    '20',
    '10',
],
    'text_data': '54e48da3583743cd8d0287a14030a83f',
    'rand_digit': 7,
    'rand_number': 0.234,
    'rand_signed_int': -3,
    'rand_datetime': '2000-08-28 08:53:58',
    'text_array': [
    '3ae316bfa3434097bf1d620a30e9757b',
    'd398da4e54784838b12a8f2fc772fd84',
],
    'words': 'rabbit elephant',
    'nested': {
    'id': 130,
    'rand_digit': 9,
    'array': [
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
    {
    'nested_empty': None,
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
    'word': 'turtle',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    3,
],
    [
],
],
    'two_words': [
    'snake',
    'mosquito',
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
    'mixed_type': 3,
    'maybe': 'wolf',
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
    '25',
],
    'text_data': 'b282fb21e0eb42e4bc20d162d9bb840f',
    'rand_digit': 7,
    'rand_number': 0.4486,
    'rand_signed_int': -10,
    'rand_datetime': '2000-03-02T12:52:31.019927',
    'text_array': [
    'd9b4b961745c4329ad281ed40c8787cf',
    'e081173d536e4d2bb27ccd4bbefbe718',
],
    'words': 'goat kangaroo',
    'nested': {
    'id': 131,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lizard',
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
    'hello',
],
    'word': 'hyena',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'gorilla',
    'lizard',
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
    'mixed_type': True,
    'maybe_null': 'dog',
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
    '26',
    '03',
],
    'text_data': 'c3099f2df5b24e189279ac9f025b6808',
    'rand_digit': 5,
    'rand_number': 0.24113,
    'rand_signed_int': 10,
    'rand_datetime': '2000-03-21',
    'text_array': [
    'f3a7663ddd3b4f319eaed8b307b5e4fa',
    '93fb8630e00e403fbe1f1b544eedee75',
],
    'words': 'ape sheep',
    'nested': {
    'id': 132,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'crab',
    'bee',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': [
    37,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'spider',
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
    '09',
    '04',
],
    'text_data': 'bb090afffa774a97a83c9983884255b3',
    'rand_digit': 5,
    'rand_number': 0.43695,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-07T13:17:05',
    'text_array': [
    'a4bf3bed140c453680f5a453e9da2764',
    'f1b921ac83c340f9b6158f9c3ef17f8c',
],
    'words': 'duck leopard',
    'nested': {
    'id': 133,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'squid',
    'camel',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'fish',
    'maybe_null': 'dolphin',
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
    '12',
    '13',
],
    'text_data': '8d527a1d45ef4a92875ae9f394727f58',
    'rand_digit': 9,
    'rand_number': 0.03239,
    'rand_signed_int': -6,
    'rand_datetime': '2000-12-15 11:09:52.994913',
    'text_array': [
    'c4c7674fc7604f20bfc667cf73047219',
    '944cc2d6f376450e80d96009b9d0cf76',
],
    'words': 'ant fish',
    'nested': {
    'id': 134,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'dog',
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
    'mixed_type': 7,
    'maybe_null': 'horse',
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
    '28',
    '11',
    '22',
    '12',
    '23',
],
    'text_data': 'cb13d670a48d41f4b0a375e6ad1de1b4',
    'rand_digit': 1,
    'rand_number': 0.55,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-20T23:35:51+1000',
    'text_array': [
    '8599ae870fa14f96a9e97a0d7a3ba1fb',
    'f89f45866eff495d9329454da7bd6bdd',
],
    'words': 'squid whale',
    'nested': {
    'id': 135,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
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
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    9,
],
    [
],
    [
],
],
    'two_words': [
    'fox',
    'giraffe',
],
    'city': {
    'name': 'Cardiff',
    'geo': {
    'lat': 51.481581,
    'lon': -3.17909,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 1,
    'maybe': 'spider',
    'maybe_null': 'pig',
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
    '05',
    '10',
    '06',
    '06',
],
    'text_data': 'b33d6c680b8e487785148b15f473b814',
    'rand_digit': 5,
    'rand_number': 0.93474,
    'rand_signed_int': -3,
    'rand_datetime': '2000-09-25 18:20',
    'text_array': [
    'ce9df6fd4c2c457599c936d4a4051f7a',
    '52fdcc1173254b0e94e6fcc51ff23e04',
],
    'words': 'grasshopper horse',
    'nested': {
    'id': 136,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'mouse',
    'dolphin',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'bird',
    'maybe_null': 'zebra',
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
    '15',
    '07',
    '11',
],
    'text_data': '214479b7717f45aca7d313048b678a09',
    'rand_digit': 9,
    'rand_number': 0.14367,
    'rand_signed_int': 0,
    'rand_datetime': '2000-09-25T06:10:25+1200',
    'text_array': [
    'fde7758c02d8480dbe65e6f3246549ce',
    'b1dbbfa0975e4df28a4ee476d26b68c1',
],
    'words': 'kangaroo cow',
    'nested': {
    'id': 137,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'bird',
    'wolf',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'gorilla',
    'maybe_null': 'wolf',
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
    '20',
    '29',
    '27',
],
    'text_data': '20e3956c2c35474ea03a14c8695e6106',
    'rand_digit': 7,
    'rand_number': 0.28575,
    'rand_signed_int': -10,
    'rand_datetime': '2000-03-24T11:53:27-0400',
    'text_array': [
    '9ac31f5c00b64947bd27595d3a5897bb',
    '2d39f15597d34a71aa5b8b7c5866a56c',
],
    'words': 'ant giraffe',
    'nested': {
    'id': 138,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'hyena',
    'camel',
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
    'maybe': 'crab',
    'maybe_null': 'tiger',
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
    '05',
    '20',
    '29',
],
    'text_data': 'a3ba88c3c57c489e8f4d4be1a57c4e42',
    'rand_digit': 8,
    'rand_number': 0.13978,
    'rand_signed_int': 9,
    'rand_datetime': '2000-09-04T09:49:48',
    'text_array': [
    '2cfb36635ca64e6dbcf365e6571b6f96',
    '8eead5ed82d946cd80ed9941a84b3e79',
],
    'words': 'snail fly',
    'nested': {
    'id': 139,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 1,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    6,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'koala',
    'squid',
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
    'mixed_type': 6,
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
    '17',
    '13',
    '11',
],
    'text_data': '18af7f14593943e6aee476aee6573e48',
    'rand_digit': 2,
    'rand_number': 0.45966,
    'rand_signed_int': 7,
    'rand_datetime': '2000-09-22 21:26:17.572808',
    'text_array': [
    '306dd85b0081421e8fbac0305750587c',
    '4cc4e98f69a64853aaa2ff117904b366',
],
    'words': 'spider lobster',
    'nested': {
    'id': 140,
    'rand_digit': 4,
    'array': [
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
    'word': 'fox',
    'number': 5,
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
],
    'word': 'butterfly',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bee',
    'dragonfly',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'shark',
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
    '02',
],
    'text_data': 'ccfdf4707adc4195b8436d2c558920a9',
    'rand_digit': 1,
    'rand_number': 0.4133,
    'rand_signed_int': 5,
    'rand_datetime': '2000-03-19T02:17:34-1200',
    'text_array': [
    '161edc28ffb94b38827787ac1b59ba2d',
    'fded6fed1ab2418bb3f84c63b09348d4',
],
    'words': 'chicken zebra',
    'nested': {
    'id': 141,
    'rand_digit': 7,
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
    'word': 'bee',
    'number': 2,
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
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'butterfly',
    'leopard',
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
    'mixed_type': 'cow',
    'maybe': 'lobster',
    'maybe_null': 'turtle',
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
    '06',
    '01',
    '24',
    '11',
    '26',
],
    'text_data': '53be12249a06489191e46b5ae2e2576f',
    'rand_digit': 4,
    'rand_number': 0.56778,
    'rand_signed_int': -4,
    'rand_datetime': '2000-05-16T07:27:44',
    'text_array': [
    'a8dc0a7f3e9442468dfa2d00818751aa',
    '19788401cbe240c29b3033da4fd8fd0e',
],
    'words': 'hyena monkey',
    'nested': {
    'id': 142,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'turtle',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'elephant',
    'hippo',
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
    'mixed_type': 'snail',
    'maybe_null': None,
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
    '04',
    '02',
    '27',
    '18',
],
    'text_data': 'a9efd89994df474ba1b5718eb8539697',
    'rand_digit': 8,
    'rand_number': 0.20216,
    'rand_signed_int': 7,
    'rand_datetime': '2000-04-26 09:27:03.172529',
    'text_array': [
    'c7467804eb1b44a3b1d5875ab0d906ba',
    '427565e90bf84e1983a56dfb564f14c8',
],
    'words': 'camel pig',
    'nested': {
    'id': 143,
    'rand_digit': 3,
    'array': [
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
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 1,
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
    [
],
],
    'two_words': [
    'wolf',
    'zebra',
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
    'mixed_type': 6,
    'maybe_null': 'duck',
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
    '13',
    '17',
    '05',
    '24',
],
    'text_data': '9e7e2f5f493b4467abefa48009cb364f',
    'rand_digit': 3,
    'rand_number': 0.83482,
    'rand_signed_int': -10,
    'rand_datetime': '2000-08-19 17:53',
    'text_array': [
    '82e3c28d5ef64506a46aff3b1d5e1e42',
    'c54fdc157a4746c28c08615741a3fde8',
],
    'words': 'rhino mosquito',
    'nested': {
    'id': 144,
    'rand_digit': 3,
    'array': [
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
],
    'two_words': [
    'dragonfly',
    'shark',
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
    'mixed_type': None,
    'maybe': 'wolf',
    'maybe_null': 'lobster',
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
    '11',
    '19',
    '20',
    '25',
],
    'text_data': '345c1af788184a91ba94527b1cead837',
    'rand_digit': 5,
    'rand_number': 0.2369,
    'rand_signed_int': -6,
    'rand_datetime': '2000-06-20T16:32:07.433649',
    'text_array': [
    '5a5e32d7e6e8456fa90d43bb5efff87b',
    'a29f70983be84adf9ec5a54f736313db',
],
    'words': 'kangaroo panda',
    'nested': {
    'id': 145,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 6,
},
    {
    'nested_empty': None,
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
],
    'word': 'tiger',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    2,
],
],
    'two_words': [
    'lizard',
    'turtle',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'spider',
    'maybe_null': None,
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
],
    'text_data': '998378a7fbee4625910e81947f7cc057',
    'rand_digit': 3,
    'rand_number': 0.93716,
    'rand_signed_int': -7,
    'rand_datetime': '2001-01-06 23:43:55+1000',
    'text_array': [
    '6afdca94fc674bb79b8fb5620fb163dc',
    '98dbf1d676dd40579d29878aa99ed47e',
],
    'words': 'frog giraffe',
    'nested': {
    'id': 146,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 9,
},
    {
    'nested_empty': None,
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
    'word': 'frog',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'panda',
    'lobster',
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
    'mixed_type': 3,
    'maybe_null': 'sheep',
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
    '18',
    '16',
    '06',
    '30',
    '29',
],
    'text_data': 'f4ab5113f08d429eb0ea5f522d6f557a',
    'rand_digit': 8,
    'rand_number': 0.99032,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-27T06:31:13.879827+09:00',
    'text_array': [
    '717364c4988845eca7c54edf0a10aa95',
    '34babf74c78d4acbb6a8ab0f5563efc8',
],
    'words': 'cat zebra',
    'nested': {
    'id': 147,
    'rand_digit': 2,
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
    'word': 'hippo',
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
    'hello',
],
    'word': 'dog',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -3,
],
    [
    9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'horse',
    'elephant',
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
    'mixed_type': {
    'key': 'value',
},
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
],
    'text_data': '3c4874d29994410698b8a19f1b81bea0',
    'rand_digit': 8,
    'rand_number': 0.91915,
    'rand_signed_int': -3,
    'rand_datetime': '2000-06-13',
    'text_array': [
    'af0f3add0e954fd4a7efa3f01ebec3f4',
    'e04e7c33017c457a9c6a8cee815c2a45',
],
    'words': 'mouse fish',
    'nested': {
    'id': 148,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'goat',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fly',
    'fish',
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
    'mixed_type': 'whale',
    'maybe_null': 'lizard',
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
    '03',
    '03',
    '09',
    '05',
    '13',
],
    'text_data': '9c867016f2de41ccb844f6e030bcde5f',
    'rand_digit': 2,
    'rand_number': 0.73966,
    'rand_signed_int': 0,
    'rand_datetime': '2000-10-07 03:56:22.111726-1200',
    'text_array': [
    '8291b1d10e504fd4b239d837b86fdbfe',
    '5d9a685eac694ad6a73fb2e27dc23395',
],
    'words': 'camel elephant',
    'nested': {
    'id': 149,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'duck',
    'deer',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'rhino',
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
    '05',
],
    'text_data': '48f6925f90df4ba9b9ee23a32be4edb6',
    'rand_digit': 4,
    'rand_number': 0.30113,
    'rand_signed_int': 5,
    'rand_datetime': '2000-04-23T08:25:20+0100',
    'text_array': [
    '45869aa5d14f4cc7a5f9362021655618',
    '609877a10cfb491fa38d42ca018681e9',
],
    'words': 'fox tiger',
    'nested': {
    'id': 150,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 8,
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
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dragonfly',
    'spider',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bear',
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
],
    'text_data': 'af21bce6ea6046769a95c906fbdcba91',
    'rand_digit': 9,
    'rand_number': 0.1998,
    'rand_signed_int': 7,
    'rand_datetime': '2000-05-19T18:05:10.714827',
    'text_array': [
    '9ceb21c157bb4270a3cfcbe75af235eb',
    'd7ae730ccc4b4613bf7d22582486f4b5',
],
    'words': 'lobster lion',
    'nested': {
    'id': 151,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
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
    'number': 7,
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
    'name': 'Cardiff',
    'geo': {
    'lat': 51.481581,
    'lon': -3.17909,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': 'butterfly',
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
    '01',
    '04',
],
    'text_data': '19071ae133284f77b2a2918e56b83f23',
    'rand_digit': 4,
    'rand_number': 0.222,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-20 16:19:48.467432',
    'text_array': [
    'c2e68fc129894de9ab950540f1ac57bd',
    '934a32a765154227a15142e8eb8b3562',
],
    'words': 'bee octopus',
    'nested': {
    'id': 152,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
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
    'number': 2,
},
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
],
    'word': 'jaguar',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dog',
    'grasshopper',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': [
    86,
],
    'rand_bool': False,
    'mixed_type': 3,
    'maybe': 'shark',
    'maybe_null': 'dog',
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
    '20',
    '29',
    '07',
    '15',
    '19',
],
    'text_data': 'c237230866cf47d28c37394734858510',
    'rand_digit': 6,
    'rand_number': 0.38884,
    'rand_signed_int': -4,
    'rand_datetime': '2000-06-08T20:06:02.291865+06:00',
    'text_array': [
    '2b47172ecae34e14b5e317a4d6b275df',
    '1faa7344baf64e558b4f673a342ee6e1',
],
    'words': 'spider cheetah',
    'nested': {
    'id': 153,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'sloth',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -1,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'pig',
    'lizard',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': [
    23,
],
    'rand_bool': False,
    'mixed_type': 8,
    'maybe_null': 'sheep',
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
    '11',
],
    'text_data': '809a68a549b94fbb9475a447b75914d7',
    'rand_digit': 7,
    'rand_number': 0.61941,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-08T10:38:53-0600',
    'text_array': [
    '9d8a3a9103004a3f912ca2ab80f72982',
    '82ae1b75e2a64b96868f4f681eaa4d87',
],
    'words': 'kangaroo hyena',
    'nested': {
    'id': 154,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'cheetah',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'hyena',
    'pig',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': [
    34,
],
    'rand_bool': False,
    'mixed_type': 0.54635,
    'maybe_null': 'turtle',
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
    '28',
    '27',
],
    'text_data': '8f902f961f2a4816962a1ac6d3531e0e',
    'rand_digit': 1,
    'rand_number': 0.43907,
    'rand_signed_int': -7,
    'rand_datetime': '2000-07-03',
    'text_array': [
    'a941515bc5ef447280902c2f74e8767d',
    'f05ea4a1133f46eeaae7b9741a619dc4',
],
    'words': 'spider crab',
    'nested': {
    'id': 155,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'number': 6,
},
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
    'hello',
],
    'word': 'koala',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'sheep',
    'squid',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'lizard',
    'maybe': 'snail',
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
    '15',
    '16',
],
    'text_data': 'f7447d9636bb411286765532b097c410',
    'rand_digit': 5,
    'rand_number': 0.58196,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-22 02:06:48.665678',
    'text_array': [
    '1c1bd73a2c53457abb6ba62447c1185b',
    'c6334e41ebc84b7ebe1cdefa48fb99c5',
],
    'words': 'butterfly cheetah',
    'nested': {
    'id': 156,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ladybug',
    'octopus',
],
    'city': {
    'name': 'Barcelona',
    'geo': {
    'lat': 41.385064,
    'lon': 2.173403,
},
},
    'rand_tuple': [
    12,
],
    'rand_bool': False,
    'mixed_type': 7,
    'maybe_null': 'spider',
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
    '03',
    '21',
],
    'text_data': 'e5ae98c32a614cf68da4bf2caf4c3a48',
    'rand_digit': 5,
    'rand_number': 0.25039,
    'rand_signed_int': 1,
    'rand_datetime': '2000-05-08T13:36:40',
    'text_array': [
    '5c448909a98e4b4f8ed8501bacedb507',
    '6133860185f249c1b3cea7800b4a607b',
],
    'words': 'lobster squid',
    'nested': {
    'id': 157,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 9,
},
    {
    'nested_empty': None,
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
    'spider',
    'deer',
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
    'mixed_type': 1,
    'maybe': 'koala',
    'maybe_null': 'dolphin',
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
    '15',
],
    'text_data': '268925f4c7574a029bed29232e45ccc1',
    'rand_digit': 5,
    'rand_number': 0.72243,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-27T13:49:05',
    'text_array': [
    '695c18f8112342eb8f24727e7f001b1d',
    '9fc0887579d84c6eadef7e4f95c5af76',
],
    'words': 'camel spider',
    'nested': {
    'id': 158,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'sheep',
    'ant',
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
    'mixed_type': 0.601,
    'maybe': 'sloth',
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
    '21',
    '02',
],
    'text_data': '1ab0103b08074410b557e06d7adf1456',
    'rand_digit': 3,
    'rand_number': 0.49489,
    'rand_signed_int': -7,
    'rand_datetime': '2000-07-06T06:05:22.523850',
    'text_array': [
    '1f3294b43780437f9ee1528ebdffa7fd',
    '492f76e93bf441ff8084d362f389f5f4',
],
    'words': 'scorpion cat',
    'nested': {
    'id': 159,
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
],
    'two_words': [
    'dog',
    'panda',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': [
    33,
],
    'rand_bool': False,
    'mixed_type': 6,
    'maybe': 'fox',
    'maybe_null': 'frog',
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
    '18',
],
    'text_data': '947d375434fd4df8a8b5463a1348ca30',
    'rand_digit': 5,
    'rand_number': 0.39073,
    'rand_signed_int': 10,
    'rand_datetime': '2000-02-21T08:28:28',
    'text_array': [
    '7c24aeb422164a579b189982af939168',
    '16839f4acce449919039f91ce81b1fe7',
],
    'words': 'grasshopper lizard',
    'nested': {
    'id': 160,
    'rand_digit': 0,
    'array': [
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
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'jaguar',
    'jaguar',
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
    'mixed_type': 'spider',
    'maybe': 'hyena',
    'maybe_null': 'leopard',
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
    '06',
    '12',
    '06',
    '09',
],
    'text_data': 'c1155fa77ce442f59426dca58e144cce',
    'rand_digit': 1,
    'rand_number': 0.89427,
    'rand_signed_int': -7,
    'rand_datetime': '2000-06-26T09:46:01.776764',
    'text_array': [
    'efa44d1982f345e8a30cd0f5591ec104',
    'a640a48ccf454b01bba55c06845e6443',
],
    'words': 'grasshopper spider',
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
    'word': 'goat',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'kangaroo',
    'dragonfly',
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
    'maybe_null': 'lion',
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
    '25',
    '28',
],
    'text_data': '1d11d58a354d4c90b7bbcb80520e868a',
    'rand_digit': 4,
    'rand_number': 0.3273,
    'rand_signed_int': 7,
    'rand_datetime': '2000-12-20 18:21:57.008356',
    'text_array': [
    '38b48856f92a4150a4ee0ef4e85ea087',
    'b5bfe749e484404b84e2c23ae6286291',
],
    'words': 'koala butterfly',
    'nested': {
    'id': 162,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'shark',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'mosquito',
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
    'rand_bool': False,
    'mixed_type': 'turtle',
    'maybe': 'chicken',
    'maybe_null': 'monkey',
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
    '04',
    '18',
    '12',
],
    'text_data': 'c7f82228c03146ea820ee8266023b029',
    'rand_digit': 3,
    'rand_number': 0.45192,
    'rand_signed_int': 4,
    'rand_datetime': '2000-07-24 20:06:20.893892-1000',
    'text_array': [
    'a98b121e166f494daededee154444dd7',
    '3923d73ffeb747d7b97a928537e8d559',
],
    'words': 'octopus fox',
    'nested': {
    'id': 163,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'crab',
    'lizard',
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
    'mixed_type': None,
    'maybe': 'bee',
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
    'content-length': '441',
}
        
        # 原始请求内容
        original_content = {
    'limit': 100,
    'filter': {
    'should': [
    {
    'key': 'city.geo',
    'geo_polygon': {
    'exterior': {
    'points': [
    {
    'lon': -55.0,
    'lat': -55.0,
},
    {
    'lon': 65.0,
    'lat': -55.0,
},
    {
    'lon': 65.0,
    'lat': 65.0,
},
    {
    'lon': 55.0,
    'lat': -65.0,
},
    {
    'lon': -55.0,
    'lat': -55.0,
},
],
},
},
},
    {
    'key': 'city.geo',
    'geo_polygon': {
    'exterior': {
    'points': [
    {
    'lon': 75.0,
    'lat': 75.0,
},
    {
    'lon': 155.0,
    'lat': 75.0,
},
    {
    'lon': 155.0,
    'lat': 85.0,
},
    {
    'lon': 75.0,
    'lat': 85.0,
},
    {
    'lon': 75.0,
    'lat': 75.0,
},
],
},
},
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_geo_polygon_filter_query.test_geo_polygon_filter_query')
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
    test = TestGeoPolygonFilterQuerytestGeoPolygonFilterQuery()
    test.run_tests()
