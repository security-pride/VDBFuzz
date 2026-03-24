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
logger = logging.getLogger('vdb_fuzzer.test.test_multivector_search_queries_test_single_vector')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_multivector_search_queries.test_single_vector"
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



class TestMultivectorSearchQueriestestSingleVector:
    """自动生成的VDB模糊测试类 - test_multivector_search_queries.test_single_vector"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_multivector_search_queries.test_single_vector"
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
    'content-length': '86',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'size': 50,
    'distance': 'Dot',
    'multivector_config': {
    'comparator': 'max_sim',
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
    'content-length': '160290',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': '__FLOAT_MULTI_DIM_6,50__',
    'payload': {
    'id': 100,
    'id_str': [
    '08',
    '25',
    '10',
    '16',
],
    'text_data': '53e778d6ed1f480688016047fe942b13',
    'rand_digit': 7,
    'rand_number': 0.81851,
    'rand_signed_int': -5,
    'rand_datetime': '2000-10-29T02:51:07.119952+0200',
    'text_array': [
    '3aa2436e714a43d8ac02108e30b76b60',
    '5a545c75fed94b068bc00a1d9b607f18',
],
    'words': 'cat bird',
    'nested': {
    'id': 100,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 10,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'ladybug',
    'leopard',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'horse',
    'maybe_null': 'crab',
},
},
    {
    'id': 1,
    'vector': '__FLOAT_MULTI_DIM_3,50__',
    'payload': {
    'id': 101,
    'id_str': [
    '07',
    '02',
    '30',
    '02',
],
    'text_data': 'e0d9913354c14c71ac8311f2ce84c5be',
    'rand_digit': 9,
    'rand_number': 0.62854,
    'rand_signed_int': -2,
    'rand_datetime': '2000-03-28 23:49:39-0600',
    'text_array': [
    '179c551208934082a440dfefec8c8f6d',
    '5db2df36473e4c10be88335ab0ddef89',
],
    'words': 'lobster turtle',
    'nested': {
    'id': 101,
    'rand_digit': 6,
    'array': [
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
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ladybug',
    'turtle',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'giraffe',
    'maybe_null': None,
},
},
    {
    'id': 2,
    'vector': '__FLOAT_MULTI_DIM_2,50__',
    'payload': {
    'id': 102,
    'id_str': [
    '06',
    '30',
],
    'text_data': 'f6458ef36932462cab44e556b5d0ebf6',
    'rand_digit': 7,
    'rand_number': 0.27782,
    'rand_signed_int': 10,
    'rand_datetime': '2000-12-08 04:46:49.925265',
    'text_array': [
    'c49753cd12924b2ea18a849dfc0fbed5',
    '36efe9273ded40fdbdea6d69cb4d1085',
],
    'words': 'leopard crab',
    'nested': {
    'id': 102,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ape',
    'giraffe',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bird',
    'maybe_null': 'panda',
},
},
    {
    'id': 3,
    'vector': '__FLOAT_MULTI_DIM_5,50__',
    'payload': {
    'id': 103,
    'id_str': [
    '06',
    '14',
    '24',
    '03',
    '21',
],
    'text_data': '0b80c0fd26e24258b87892217670c616',
    'rand_digit': 2,
    'rand_number': 0.66023,
    'rand_signed_int': -3,
    'rand_datetime': '2000-07-11T21:44:29.865170',
    'text_array': [
    '2efca350f0124653816da0cd6d08c9c9',
    '905989d534e14823ba3a7a2b75767620',
],
    'words': 'spider crab',
    'nested': {
    'id': 103,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'sloth',
    'number': 9,
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
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'crab',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'panda',
    'horse',
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
    'mixed_type': 2,
    'maybe': 'lion',
    'maybe_null': 'kangaroo',
},
},
    {
    'id': 4,
    'vector': '__FLOAT_MULTI_DIM_6,50__',
    'payload': {
    'id': 104,
    'id_str': [
    '16',
    '28',
],
    'text_data': '5e3ab7dc09cf4959b19c6551d8c8fcce',
    'rand_digit': 6,
    'rand_number': 0.54086,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-22T21:45:59+0100',
    'text_array': [
    '008b3ffb639b490e8b78a216779c776a',
    '2fddf200a301434c9183eeeb138339f6',
],
    'words': 'octopus leopard',
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
    'word': 'frog',
    'number': 8,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    7,
],
],
    'two_words': [
    'camel',
    'giraffe',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'ant',
},
},
    {
    'id': 5,
    'vector': '__FLOAT_MULTI_DIM_5,50__',
    'payload': {
    'id': 105,
    'id_str': [
    '20',
    '17',
    '08',
    '02',
    '06',
],
    'text_data': 'fe27ce213243469c8cd429dfe3a30b94',
    'rand_digit': 5,
    'rand_number': 0.64681,
    'rand_signed_int': 5,
    'rand_datetime': '2000-09-01T21:09:18.202879',
    'text_array': [
    '176247b841be4167a34b2a6b144d5cd5',
    'eea5a5184851491184d460d1b821ab6a',
],
    'words': 'turtle mosquito',
    'nested': {
    'id': 105,
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
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 3,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'dolphin',
    'tiger',
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
    'mixed_type': 4,
    'maybe': 'sheep',
    'maybe_null': 'lion',
},
},
    {
    'id': 6,
    'vector': '__FLOAT_MULTI_DIM_3,50__',
    'payload': {
    'id': 106,
    'id_str': [
    '03',
    '29',
    '16',
    '04',
    '27',
],
    'text_data': '81661f2809754d1fb25c3d25eb378079',
    'rand_digit': 4,
    'rand_number': 0.3667,
    'rand_signed_int': -10,
    'rand_datetime': '2000-10-21 02:19:28.923845',
    'text_array': [
    '0ba91286d705454f85bc0a773ab59617',
    '357573fbdafe438ba6158e988d7c8742',
],
    'words': 'sheep ladybug',
    'nested': {
    'id': 106,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'shark',
    'number': 2,
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
    'word': 'grasshopper',
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
    'butterfly',
    'grasshopper',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
},
},
    'rand_tuple': [
    64,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'fly',
},
},
    {
    'id': 7,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 107,
    'id_str': [
    '14',
    '26',
    '16',
    '05',
],
    'text_data': 'b944f8b6870a4bad91e2d19edfd3c072',
    'rand_digit': 9,
    'rand_number': 0.69311,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-14 20:51:02.005208',
    'text_array': [
    'bd8f05f6508e4c4f912170850e8ca2f4',
    'd845267da41448bb82cbf64beb28470e',
],
    'words': 'hippo fly',
    'nested': {
    'id': 107,
    'rand_digit': 7,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'grasshopper',
    'dolphin',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'gorilla',
    'maybe_null': 'bear',
},
},
    {
    'id': 8,
    'vector': '__FLOAT_MULTI_DIM_2,50__',
    'payload': {
    'id': 108,
    'id_str': [
    '17',
],
    'text_data': '76145849599d42a7bb2948ab8fb90fd7',
    'rand_digit': 5,
    'rand_number': 0.1122,
    'rand_signed_int': 9,
    'rand_datetime': '2000-12-04T13:37:30.004403+0000',
    'text_array': [
    'fafcdf5de5c8479a9fda6b4b064593f6',
    'f0971efa12ad4bb1b8820ce9f08d2bfe',
],
    'words': 'fly panda',
    'nested': {
    'id': 108,
    'rand_digit': 1,
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
    'word': 'fish',
    'number': 8,
},
    {
    'nested_empty': None,
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
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'shark',
    'dog',
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
    'maybe': 'shark',
    'maybe_null': 'mosquito',
},
},
    {
    'id': 9,
    'vector': '__FLOAT_MULTI_DIM_9,50__',
    'payload': {
    'id': 109,
    'id_str': [
    '01',
    '20',
],
    'text_data': '8045a706b1e14df2a636c99477975c36',
    'rand_digit': 1,
    'rand_number': 0.88191,
    'rand_signed_int': 8,
    'rand_datetime': '2000-01-19 02:03:57.753743-0100',
    'text_array': [
    '0e4666ed709e48c3ae906be64db5bbca',
    '1e183fa46e76486fb35506d120cb1013',
],
    'words': 'leopard rhino',
    'nested': {
    'id': 109,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'pig',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 2,
},
],
},
    'nested_array': [
    [
    -1,
],
],
    'two_words': [
    'koala',
    'ape',
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
    'maybe_null': None,
},
},
    {
    'id': 10,
    'vector': '__FLOAT_MULTI_DIM_9,50__',
    'payload': {
    'id': 110,
    'id_str': [
    '18',
    '08',
],
    'text_data': '4b32d94eccca4787a20139efb45ac1d5',
    'rand_digit': 7,
    'rand_number': 0.452,
    'rand_signed_int': -3,
    'rand_datetime': '2000-01-11T08:29:37',
    'text_array': [
    '5656b603d2c24023b2c4acaa4160794e',
    'ef8c824028d14936add71031c8a5d10d',
],
    'words': 'jaguar crab',
    'nested': {
    'id': 110,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
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
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'octopus',
    'frog',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
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
    'id': 11,
    'vector': '__FLOAT_MULTI_DIM_2,50__',
    'payload': {
    'id': 111,
    'id_str': [
    '05',
],
    'text_data': '96c877dd963540f4a2f0abc5fcce4422',
    'rand_digit': 8,
    'rand_number': 0.13766,
    'rand_signed_int': 2,
    'rand_datetime': '2000-04-01',
    'text_array': [
    '3ef6707bb77b4e2b9950c16df6c9883b',
    '998eec0c86134daf9b99001e86c834d3',
],
    'words': 'mosquito koala',
    'nested': {
    'id': 111,
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
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 2,
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
    'word': 'butterfly',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'monkey',
    'hyena',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'koala',
    'maybe_null': None,
},
},
    {
    'id': 12,
    'vector': '__FLOAT_MULTI_DIM_3,50__',
    'payload': {
    'id': 112,
    'id_str': [
    '03',
],
    'text_data': '3a5ec171fc5e45f1822da13102ebfb84',
    'rand_digit': 0,
    'rand_number': 0.05182,
    'rand_signed_int': 0,
    'rand_datetime': '2000-03-23T04:39:16.276911',
    'text_array': [
    '7c576058a1974ff0a1bce474b8c537fb',
    '2153e121051a4d8d964dea6b71066856',
],
    'words': 'koala gorilla',
    'nested': {
    'id': 112,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 8,
},
],
},
    'nested_array': [
    [
    6,
],
    [
    0,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'bee',
    'mouse',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': [
    86,
],
    'rand_bool': False,
    'mixed_type': 'gorilla',
    'maybe': 'scorpion',
    'maybe_null': None,
},
},
    {
    'id': 13,
    'vector': '__FLOAT_MULTI_DIM_7,50__',
    'payload': {
    'id': 113,
    'id_str': [
    '05',
    '05',
    '26',
],
    'text_data': 'b839e7b2ba70412393ecb6e99fb09b95',
    'rand_digit': 1,
    'rand_number': 0.06274,
    'rand_signed_int': -8,
    'rand_datetime': '2000-05-03 11:27:43.737270',
    'text_array': [
    '5bfdf2f398b34a8f973ebf0d63f776aa',
    '78e2fe6fdd4c45aea5c06a3d1db801d5',
],
    'words': 'ladybug cat',
    'nested': {
    'id': 113,
    'rand_digit': 6,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'hippo',
    'number': 6,
},
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'grasshopper',
    'ladybug',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': [
    96,
],
    'rand_bool': True,
    'mixed_type': 0.54838,
    'maybe_null': 'cheetah',
},
},
    {
    'id': 14,
    'vector': '__FLOAT_MULTI_DIM_2,50__',
    'payload': {
    'id': 114,
    'id_str': [
    '15',
],
    'text_data': 'c1d24bc815994db2a2fcf9b23460903d',
    'rand_digit': 4,
    'rand_number': 0.99367,
    'rand_signed_int': 9,
    'rand_datetime': '2000-02-05',
    'text_array': [
    '14f77a9b9cfb4600a601eaf07ebb9790',
    'aec74b26845b47b390906fd8231fb7ba',
],
    'words': 'cow turtle',
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
    'word': 'tiger',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'mouse',
    'scorpion',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': [
    83,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'hippo',
    'maybe_null': 'cat',
},
},
    {
    'id': 15,
    'vector': '__FLOAT_MULTI_DIM_6,50__',
    'payload': {
    'id': 115,
    'id_str': [
    '08',
    '14',
    '24',
],
    'text_data': '46c909a4f4e54e67812d98cc0a4684e8',
    'rand_digit': 5,
    'rand_number': 0.0988,
    'rand_signed_int': 10,
    'rand_datetime': '2000-06-03T06:47:44.772209-1100',
    'text_array': [
    '2a673834760f4cf0b9334f5beb532480',
    'a2cc35cea6bb40caaffa90b2391f2e43',
],
    'words': 'turtle ant',
    'nested': {
    'id': 115,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'sheep',
    'pig',
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
    'mixed_type': 2,
},
},
    {
    'id': 16,
    'vector': '__FLOAT_MULTI_DIM_8,50__',
    'payload': {
    'id': 116,
    'id_str': [
    '17',
],
    'text_data': 'e709b4d434e64281b26cd81a34d215aa',
    'rand_digit': 6,
    'rand_number': 0.74322,
    'rand_signed_int': -6,
    'rand_datetime': '2000-04-12 11:08:17.853779',
    'text_array': [
    '66f4670ef743498592f8416a494a18eb',
    'f7f789f51e1c45019e804893f62ade75',
],
    'words': 'squid rabbit',
    'nested': {
    'id': 116,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    5,
],
],
    'two_words': [
    'cheetah',
    'bird',
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
    'maybe': 'lion',
    'maybe_null': None,
},
},
    {
    'id': 17,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 117,
    'id_str': [
    '26',
    '05',
],
    'text_data': 'fbd731304ded49408040bc1a84442e98',
    'rand_digit': 4,
    'rand_number': 0.26635,
    'rand_signed_int': 10,
    'rand_datetime': '2000-02-05 20:10',
    'text_array': [
    '487a5f7a8a0249f5a872db2f9f59c022',
    'bdf1a594cb6047e68377a25690b76f70',
],
    'words': 'lobster deer',
    'nested': {
    'id': 117,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'rhino',
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
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lobster',
    'fish',
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
    'mixed_type': 'lizard',
    'maybe_null': None,
},
},
    {
    'id': 18,
    'vector': '__FLOAT_MULTI_DIM_6,50__',
    'payload': {
    'id': 118,
    'id_str': [
    '14',
],
    'text_data': '7e68a5118aab4b3db389f7f21c910f1d',
    'rand_digit': 1,
    'rand_number': 0.43551,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-19T11:28:49.861559',
    'text_array': [
    '2e9a090a12244d2697f7cb9d73ab5f85',
    '6c7e627527604ad7a57710e39ef6b4db',
],
    'words': 'wolf leopard',
    'nested': {
    'id': 118,
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
],
},
    'nested_array': [
    [
    0,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'hippo',
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
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'ladybug',
},
},
    {
    'id': 19,
    'vector': '__FLOAT_MULTI_DIM_9,50__',
    'payload': {
    'id': 119,
    'id_str': [
    '08',
    '03',
],
    'text_data': 'cd986b111e2a4a89aa273ce923e3c839',
    'rand_digit': 5,
    'rand_number': 0.35271,
    'rand_signed_int': -1,
    'rand_datetime': '2000-01-26 23:13',
    'text_array': [
    '59569efd159046eeb5204eef7a1efe56',
    '0c4b296197c44a7687a4ea7bfd0097a9',
],
    'words': 'octopus dragonfly',
    'nested': {
    'id': 119,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fish',
    'duck',
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
    'mixed_type': 0.20378,
    'maybe_null': None,
},
},
    {
    'id': 20,
    'vector': '__FLOAT_MULTI_DIM_7,50__',
    'payload': {
    'id': 120,
    'id_str': [
    '14',
    '01',
],
    'text_data': 'e0ee7fff7b7945f297c7f7872fc5e02d',
    'rand_digit': 7,
    'rand_number': 0.03822,
    'rand_signed_int': -5,
    'rand_datetime': '2000-04-12 09:00:40',
    'text_array': [
    '9efa1753d8994acc95bcc88842cf8e13',
    '9c8104251258487ab93265f2dff5e7b1',
],
    'words': 'ladybug duck',
    'nested': {
    'id': 120,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 9,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'ape',
    'elephant',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'camel',
    'maybe_null': 'shark',
},
},
    {
    'id': 21,
    'vector': '__FLOAT_MULTI_DIM_10,50__',
    'payload': {
    'id': 121,
    'id_str': [
    '09',
    '24',
],
    'text_data': 'bd84f33b5a1b4a2e964ec0bbda150082',
    'rand_digit': 1,
    'rand_number': 0.04657,
    'rand_signed_int': 3,
    'rand_datetime': '2000-09-24T04:48:55.271395-1000',
    'text_array': [
    '9116ebcacc914d43971086f439e4ef9e',
    '987f612eb82c4787a353be298f4e5b17',
],
    'words': 'cat sheep',
    'nested': {
    'id': 121,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 3,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 7,
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
    'koala',
    'snake',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'deer',
},
},
    {
    'id': 22,
    'vector': '__FLOAT_MULTI_DIM_10,50__',
    'payload': {
    'id': 122,
    'id_str': [
    '05',
    '08',
    '14',
    '09',
],
    'text_data': 'c883084f29974c60a9f68b213efc5675',
    'rand_digit': 9,
    'rand_number': 0.44729,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-17 11:33:59+1100',
    'text_array': [
    '2ab6a345a5434f819c8a4cd81f02f63a',
    '5d9a96baf420445487e7da3e3f24f309',
],
    'words': 'bird lobster',
    'nested': {
    'id': 122,
    'rand_digit': 2,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'hippo',
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
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bird',
    'chicken',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'hyena',
},
},
    {
    'id': 23,
    'vector': '__FLOAT_MULTI_DIM_10,50__',
    'payload': {
    'id': 123,
    'id_str': [
    '04',
    '17',
    '02',
    '09',
],
    'text_data': 'a010c71103e64c018002d67deec9f56c',
    'rand_digit': 9,
    'rand_number': 0.56104,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-31T11:18:33+0100',
    'text_array': [
    '8d82e53b70824d3b900c1dd49e1a5fff',
    'aa6addc6dc2a4d7fab001f737e7b422e',
],
    'words': 'wolf spider',
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
    'word': 'bear',
    'number': 7,
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fox',
    'dog',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 24,
    'vector': '__FLOAT_MULTI_DIM_6,50__',
    'payload': {
    'id': 124,
    'id_str': [
    '26',
    '20',
    '19',
    '02',
],
    'text_data': '733027957eea47bb88febbc45d19578c',
    'rand_digit': 2,
    'rand_number': 0.12885,
    'rand_signed_int': 10,
    'rand_datetime': '2000-08-26 16:10',
    'text_array': [
    '1b9fb6994de14428ad81f2bfb61b99bc',
    '6e11d5a604c64f4d82197a4562f4c079',
],
    'words': 'spider tiger',
    'nested': {
    'id': 124,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
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
    'elephant',
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
    'mixed_type': 0.06715,
    'maybe': 'hippo',
    'maybe_null': 'crab',
},
},
    {
    'id': 25,
    'vector': '__FLOAT_MULTI_DIM_5,50__',
    'payload': {
    'id': 125,
    'id_str': [
    '07',
    '15',
    '10',
    '12',
],
    'text_data': 'a39fd18b7a7b4ebebc57cd40d6e5ed69',
    'rand_digit': 8,
    'rand_number': 0.17834,
    'rand_signed_int': -10,
    'rand_datetime': '2000-09-18T10:13:19.059307+0700',
    'text_array': [
    'e796c82c1926409db6389171f0f978e7',
    '51c521ebd22047a9ab6afc3e245612e3',
],
    'words': 'deer ladybug',
    'nested': {
    'id': 125,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'grasshopper',
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
    'leopard',
    'dolphin',
],
    'city': {
    'name': 'Rome',
    'geo': {
    'lat': 41.902782,
    'lon': 12.496366,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 'jaguar',
},
},
    {
    'id': 26,
    'vector': '__FLOAT_MULTI_DIM_5,50__',
    'payload': {
    'id': 126,
    'id_str': [
    '12',
    '10',
    '18',
    '17',
],
    'text_data': 'bc37b59de74c4b9ca18adeeebf881108',
    'rand_digit': 5,
    'rand_number': 0.02891,
    'rand_signed_int': -8,
    'rand_datetime': '2000-07-01T21:54:53.475825',
    'text_array': [
    '4032fa7aa0864142885f8f6c74990308',
    'dff61588f083446a995085e1fc4ac718',
],
    'words': 'cat panda',
    'nested': {
    'id': 126,
    'rand_digit': 7,
    'array': [
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'panda',
    'ape',
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
    'mixed_type': 'mouse',
    'maybe': 'duck',
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 27,
    'vector': '__FLOAT_MULTI_DIM_6,50__',
    'payload': {
    'id': 127,
    'id_str': [
    '19',
],
    'text_data': '662cdcc1cfc04f3b8ecf19b6084c37c3',
    'rand_digit': 7,
    'rand_number': 0.71047,
    'rand_signed_int': 0,
    'rand_datetime': '2000-12-23 10:14:09-1200',
    'text_array': [
    'ab1961a566f940758e26044e61acfa27',
    '4b9b77ee5ae144deb34059a613e6ea09',
],
    'words': 'bee horse',
    'nested': {
    'id': 127,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'ant',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'shark',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'sheep',
    'gorilla',
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
    'mixed_type': 'tiger',
    'maybe_null': 'whale',
},
},
    {
    'id': 28,
    'vector': '__FLOAT_MULTI_DIM_5,50__',
    'payload': {
    'id': 128,
    'id_str': [
    '10',
    '03',
    '18',
],
    'text_data': 'cb91921a8bad417eb53336479ed2277b',
    'rand_digit': 0,
    'rand_number': 0.99456,
    'rand_signed_int': 9,
    'rand_datetime': '2000-01-02T20:31:33.395548',
    'text_array': [
    '27e4a1a6ec2540879de16320c96308c5',
    'd1f8a6da1a6f4ea0b4d50121fe429233',
],
    'words': 'sheep ant',
    'nested': {
    'id': 128,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
    8,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fish',
    'ladybug',
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
    'maybe': 'bear',
},
},
    {
    'id': 29,
    'vector': '__FLOAT_MULTI_DIM_6,50__',
    'payload': {
    'id': 129,
    'id_str': [
    '01',
    '04',
    '28',
    '25',
    '24',
],
    'text_data': 'b27f5798714d4ef5a2de11119a0ac1ae',
    'rand_digit': 5,
    'rand_number': 0.85499,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-12 15:37:27.017207+1000',
    'text_array': [
    '2d535e459bc9456ab879a780374ecc5f',
    'e641aaf85d574e93a8ddfd8d54461cef',
],
    'words': 'ant dog',
    'nested': {
    'id': 129,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'horse',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'horse',
    'crab',
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
    'maybe': 'sheep',
    'maybe_null': None,
},
},
    {
    'id': 30,
    'vector': '__FLOAT_MULTI_DIM_8,50__',
    'payload': {
    'id': 130,
    'id_str': [
    '10',
    '28',
    '23',
    '17',
    '21',
],
    'text_data': 'd8926b1301734af880a0c376f2b2067c',
    'rand_digit': 2,
    'rand_number': 0.90633,
    'rand_signed_int': -3,
    'rand_datetime': '2000-09-02 11:17:25.069963',
    'text_array': [
    '5c88f5a17de1461f87611269b9f9f3b8',
    '606ee141c32e471d9b7ff586e49da68c',
],
    'words': 'ant tiger',
    'nested': {
    'id': 130,
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
    'lobster',
    'jaguar',
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
    'maybe_null': 'dog',
},
},
    {
    'id': 31,
    'vector': '__FLOAT_MULTI_DIM_10,50__',
    'payload': {
    'id': 131,
    'id_str': [
    '04',
    '05',
    '01',
    '30',
    '11',
],
    'text_data': '897c6a6e50294df881609099ed5ce2d4',
    'rand_digit': 7,
    'rand_number': 0.53391,
    'rand_signed_int': 10,
    'rand_datetime': '2001-01-21 23:05:55',
    'text_array': [
    '5d99d5062955460c953f8967ec7d4a90',
    'f595ec2cb8e64d37bf8e6c746c3f2bf4',
],
    'words': 'crab bird',
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
    'word': 'goat',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
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
    'lizard',
    'lion',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': [
    80,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 32,
    'vector': '__FLOAT_MULTI_DIM_3,50__',
    'payload': {
    'id': 132,
    'id_str': [
],
    'text_data': 'b89c959eae1d4379a28742da46f25526',
    'rand_digit': 4,
    'rand_number': 0.34514,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-16T18:25:39',
    'text_array': [
    'ad820d709dc841d3af0b900a646fbd2f',
    'deb52dc7048643b49ec8d4650d0ab199',
],
    'words': 'gorilla duck',
    'nested': {
    'id': 132,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 9,
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
    'hello',
],
    'word': 'rabbit',
    'number': 4,
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
    'grasshopper',
    'crab',
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
    'mixed_type': 'elephant',
    'maybe': 'chicken',
    'maybe_null': None,
},
},
    {
    'id': 33,
    'vector': '__FLOAT_MULTI_DIM_7,50__',
    'payload': {
    'id': 133,
    'id_str': [
    '03',
    '15',
    '07',
],
    'text_data': '5e08511a910f406dbe854f7ddd5d2c8d',
    'rand_digit': 8,
    'rand_number': 0.63786,
    'rand_signed_int': 2,
    'rand_datetime': '2000-02-19T03:09:57.805848',
    'text_array': [
    '0bd242410da04301a43aa3e3921bf9bf',
    'abad399230904a759576c16ab8b3d117',
],
    'words': 'bird goat',
    'nested': {
    'id': 133,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 4,
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
],
},
    'nested_array': [
],
    'two_words': [
    'dragonfly',
    'chicken',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
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
    'id': 34,
    'vector': '__FLOAT_MULTI_DIM_8,50__',
    'payload': {
    'id': 134,
    'id_str': [
    '19',
    '17',
    '18',
],
    'text_data': 'be961e83930d4bc495fee1ecfb618ae2',
    'rand_digit': 6,
    'rand_number': 0.32202,
    'rand_signed_int': -7,
    'rand_datetime': '2001-01-08',
    'text_array': [
    'b95b84c3964a4cca859ea49aafc09c5d',
    'aa777a6c2da947ef86517dd608c8c3e7',
],
    'words': 'jaguar duck',
    'nested': {
    'id': 134,
    'rand_digit': 7,
    'array': [
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
    'word': 'frog',
    'number': 4,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'whale',
    'horse',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': [
    84,
],
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'mosquito',
},
},
    {
    'id': 35,
    'vector': '__FLOAT_MULTI_DIM_10,50__',
    'payload': {
    'id': 135,
    'id_str': [
    '22',
    '25',
    '16',
    '05',
    '18',
],
    'text_data': '72efd51b5b2f4d77b46b3741608f9f74',
    'rand_digit': 6,
    'rand_number': 0.312,
    'rand_signed_int': -10,
    'rand_datetime': '2000-10-11T00:52:55.259877',
    'text_array': [
    '3e0b8a446fdd4bb5a68d7a44448b9642',
    '3be9455fa86e4c6b83f8e9e0a670731e',
],
    'words': 'zebra lion',
    'nested': {
    'id': 135,
    'rand_digit': 0,
    'array': [
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'gorilla',
    'turtle',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 36,
    'vector': '__FLOAT_MULTI_DIM_6,50__',
    'payload': {
    'id': 136,
    'id_str': [
    '14',
    '19',
    '16',
    '11',
],
    'text_data': 'e727ac274b144e028b78729c2043d168',
    'rand_digit': 8,
    'rand_number': 0.8603,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-18 21:19:31-0200',
    'text_array': [
    'bcee1d52aeb5469f9276f34adec0b185',
    '3867c9f7bc6d407f8d44667863a8d606',
],
    'words': 'spider bee',
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
    'word': 'turtle',
    'number': 2,
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
    [
    2,
],
    [
    -7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fly',
    'koala',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'dog',
},
},
    {
    'id': 37,
    'vector': '__FLOAT_MULTI_DIM_9,50__',
    'payload': {
    'id': 137,
    'id_str': [
],
    'text_data': '9796b85309ee46a1822f624040ea201b',
    'rand_digit': 5,
    'rand_number': 0.74674,
    'rand_signed_int': 10,
    'rand_datetime': '2001-01-04T15:49:25.732614',
    'text_array': [
    '1954d7b7804240268382cc3e4ef58df9',
    '91d80b978cd5478c832f3aa80cb5617c',
],
    'words': 'butterfly lizard',
    'nested': {
    'id': 137,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'dog',
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
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fox',
    'turtle',
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
    'mixed_type': 'duck',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 38,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 138,
    'id_str': [
    '14',
],
    'text_data': '85384a34e2ab4606a7f3e86a52bb1688',
    'rand_digit': 4,
    'rand_number': 0.69997,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-07T10:42:56.900286+06:00',
    'text_array': [
    '5eefe86cb493467ba43159c492ddacfc',
    '15cc8e2769a74f13aa5a9d3e6d9c612d',
],
    'words': 'snake fish',
    'nested': {
    'id': 138,
    'rand_digit': 1,
    'array': [
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
    'word': 'pig',
    'number': 2,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'wolf',
    'sheep',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': [
    100,
],
    'rand_bool': False,
    'mixed_type': True,
},
},
    {
    'id': 39,
    'vector': '__FLOAT_MULTI_DIM_8,50__',
    'payload': {
    'id': 139,
    'id_str': [
    '16',
    '08',
    '13',
    '23',
],
    'text_data': 'd691611239674587840cf59344811090',
    'rand_digit': 8,
    'rand_number': 0.03538,
    'rand_signed_int': -9,
    'rand_datetime': '2000-11-16 16:48:31',
    'text_array': [
    'ec3f8b1a789441a085b8142a3bcdfa84',
    '1f0fb1c27f294650aa7dbacfb861fba4',
],
    'words': 'snail bear',
    'nested': {
    'id': 139,
    'rand_digit': 5,
    'array': [
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
],
},
    'nested_array': [
],
    'two_words': [
    'squid',
    'bear',
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
    'mixed_type': 1,
    'maybe': 'butterfly',
    'maybe_null': 'whale',
},
},
    {
    'id': 40,
    'vector': '__FLOAT_MULTI_DIM_9,50__',
    'payload': {
    'id': 140,
    'id_str': [
],
    'text_data': '53a367839b504644aa542150d33a18a6',
    'rand_digit': 9,
    'rand_number': 0.01402,
    'rand_signed_int': -1,
    'rand_datetime': '2000-10-31 15:11',
    'text_array': [
    'd96e3ce84cc242c7a48150225f888ac0',
    '4990a2ca8c41497a9c5204310d800013',
],
    'words': 'bird cheetah',
    'nested': {
    'id': 140,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'grasshopper',
    'mosquito',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'monkey',
},
},
    {
    'id': 41,
    'vector': '__FLOAT_MULTI_DIM_6,50__',
    'payload': {
    'id': 141,
    'id_str': [
],
    'text_data': '80b39f51097d493c8727209c100df0aa',
    'rand_digit': 4,
    'rand_number': 0.97806,
    'rand_signed_int': -6,
    'rand_datetime': '2001-01-06T02:17:47.093513',
    'text_array': [
    '77201ff0bfb0436a8795b494e4a0dca8',
    'f7294ef8e7bd432dad0d80a25ee81917',
],
    'words': 'giraffe tiger',
    'nested': {
    'id': 141,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 1,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'spider',
    'dog',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'rhino',
},
},
    {
    'id': 42,
    'vector': '__FLOAT_MULTI_DIM_4,50__',
    'payload': {
    'id': 142,
    'id_str': [
    '21',
    '04',
    '20',
],
    'text_data': '41aed54776c34698a740893bb4388df6',
    'rand_digit': 1,
    'rand_number': 0.10084,
    'rand_signed_int': 3,
    'rand_datetime': '2000-10-24 03:43:45',
    'text_array': [
    'f51b4a13f1ba459e8ee9f3aa958d616a',
    'd99240b62fae44d3a0198824bc0925cf',
],
    'words': 'spider deer',
    'nested': {
    'id': 142,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 1,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'mouse',
    'goat',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': [
    68,
],
    'rand_bool': False,
    'mixed_type': 'tiger',
    'maybe': 'scorpion',
    'maybe_null': 'cheetah',
},
},
    {
    'id': 43,
    'vector': '__FLOAT_MULTI_DIM_5,50__',
    'payload': {
    'id': 143,
    'id_str': [
    '07',
    '09',
    '06',
    '16',
],
    'text_data': '3ec9442d75d24c3195c33722a4be633a',
    'rand_digit': 2,
    'rand_number': 0.94614,
    'rand_signed_int': -7,
    'rand_datetime': '2000-01-06 16:34',
    'text_array': [
    '35993ac96b5d41878d7678da520dc791',
    '2561e7b29b434a2c8fdc9e22c751a99c',
],
    'words': 'hyena fly',
    'nested': {
    'id': 143,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    [
    -1,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'crab',
    'sheep',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': [
    68,
],
    'rand_bool': False,
    'mixed_type': 'cheetah',
    'maybe_null': 'chicken',
},
},
    {
    'id': 44,
    'vector': '__FLOAT_MULTI_DIM_3,50__',
    'payload': {
    'id': 144,
    'id_str': [
    '01',
    '11',
    '18',
],
    'text_data': '4fb522b7ac3b4b179547a8b06b511ff3',
    'rand_digit': 0,
    'rand_number': 0.23034,
    'rand_signed_int': -3,
    'rand_datetime': '2000-06-18T19:37:36.444747+1200',
    'text_array': [
    '53ab6222d53641988c0c56ed66fdb50b',
    'ea600ea0c8b340658e1ebbdd9c2bec7b',
],
    'words': 'lion lobster',
    'nested': {
    'id': 144,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'pig',
    'kangaroo',
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
    'mixed_type': 9,
    'maybe_null': 'dog',
},
},
    {
    'id': 45,
    'vector': '__FLOAT_MULTI_DIM_9,50__',
    'payload': {
    'id': 145,
    'id_str': [
    '03',
    '01',
],
    'text_data': '82ee680b6b2d41a0825616c7daa91768',
    'rand_digit': 0,
    'rand_number': 0.87336,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-06T10:42:58.626126+03:00',
    'text_array': [
    'f4fd4f38b66d47a498b26836a6739b96',
    '957162510f37478aa84070e1533da59f',
],
    'words': 'elephant gorilla',
    'nested': {
    'id': 145,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -5,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'tiger',
    'kangaroo',
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
    'mixed_type': None,
    'maybe': 'zebra',
    'maybe_null': 'goat',
},
},
    {
    'id': 46,
    'vector': '__FLOAT_MULTI_DIM_3,50__',
    'payload': {
    'id': 146,
    'id_str': [
    '17',
],
    'text_data': 'c10430790f65448eb033efb5b0f32250',
    'rand_digit': 7,
    'rand_number': 0.06129,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-03 05:42:27.646986+0500',
    'text_array': [
    '34e5484ed3c14c26b6cffc7919f984a8',
    'da03025d68a04a6da58fac8357678293',
],
    'words': 'rabbit cat',
    'nested': {
    'id': 146,
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
    'number': 3,
},
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
    'word': 'goat',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
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
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    7,
],
],
    'two_words': [
    'snail',
    'whale',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'lizard',
    'maybe_null': 'grasshopper',
},
},
    {
    'id': 47,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 147,
    'id_str': [
    '12',
    '27',
    '02',
    '13',
    '06',
],
    'text_data': 'c8ad789ce3b545f0b63c8a60eb07e5b0',
    'rand_digit': 9,
    'rand_number': 0.48727,
    'rand_signed_int': -7,
    'rand_datetime': '2001-01-27 09:59',
    'text_array': [
    '68218c01f7c0469f91371ab8293de425',
    '5bfa89f77f614a458ec1bc932d233167',
],
    'words': 'kangaroo kangaroo',
    'nested': {
    'id': 147,
    'rand_digit': 9,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'hyena',
    'dragonfly',
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
    'mixed_type': True,
    'maybe': 'cow',
},
},
    {
    'id': 48,
    'vector': '__FLOAT_MULTI_DIM_5,50__',
    'payload': {
    'id': 148,
    'id_str': [
    '19',
    '11',
    '05',
    '13',
    '29',
],
    'text_data': '39a08e89a4434967849cd42f049ccf74',
    'rand_digit': 4,
    'rand_number': 0.29355,
    'rand_signed_int': 10,
    'rand_datetime': '2000-02-10 03:06:30+0900',
    'text_array': [
    'bd0e13a0b013446fae51b16ed64ce158',
    'd145fcc579d5494b91e78da5cc28b4d0',
],
    'words': 'lizard panda',
    'nested': {
    'id': 148,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
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
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 1,
},
    {
    'nested_empty': None,
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
    2,
],
    [
],
],
    'two_words': [
    'rhino',
    'grasshopper',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'cat',
},
},
    {
    'id': 49,
    'vector': '__FLOAT_MULTI_DIM_10,50__',
    'payload': {
    'id': 149,
    'id_str': [
    '14',
],
    'text_data': 'c9788592e7ff483bb7d882cc916dfb2d',
    'rand_digit': 1,
    'rand_number': 0.92622,
    'rand_signed_int': 1,
    'rand_datetime': '2000-04-05T08:31:16-0500',
    'text_array': [
    'e2da2a3d5f6b459f936aaf04d69a2b17',
    '44ce9941815a43ffb76cba603cc50c98',
],
    'words': 'bird bee',
    'nested': {
    'id': 149,
    'rand_digit': 5,
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
    'nested_empty': [
    'hello',
],
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
    'word': 'squid',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'rhino',
    'lizard',
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
    'mixed_type': None,
    'maybe': 'elephant',
    'maybe_null': None,
},
},
    {
    'id': 50,
    'vector': '__FLOAT_MULTI_DIM_10,50__',
    'payload': {
    'id': 150,
    'id_str': [
    '12',
    '16',
    '11',
],
    'text_data': '397c75f70d1d493db2bb025c35604d28',
    'rand_digit': 6,
    'rand_number': 0.04598,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-13 11:26:51',
    'text_array': [
    '24f3387c299e4e1aa13623cb29e68a3e',
    'd11b08cc11e7438794e8ed954f8102aa',
],
    'words': 'hyena gorilla',
    'nested': {
    'id': 150,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'elephant',
    'bird',
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
    'mixed_type': False,
    'maybe_null': 'grasshopper',
},
},
    {
    'id': 51,
    'vector': '__FLOAT_MULTI_DIM_5,50__',
    'payload': {
    'id': 151,
    'id_str': [
    '04',
    '25',
    '08',
    '28',
],
    'text_data': '5fa78fa1377b45d695df1e6f74b1a8d1',
    'rand_digit': 6,
    'rand_number': 0.07952,
    'rand_signed_int': 2,
    'rand_datetime': '2000-02-10 19:04:41+0800',
    'text_array': [
    'f314a200882d4d8b96cee109f49917dd',
    '5ae3a1d1ed5549c38eef1ee501e77512',
],
    'words': 'elephant bird',
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
    'word': 'spider',
    'number': 8,
},
    {
    'nested_empty': None,
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
    'word': 'hippo',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    5,
],
],
    'two_words': [
    'snake',
    'frog',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': [
    87,
],
    'rand_bool': True,
    'mixed_type': 8,
    'maybe_null': 'bear',
},
},
    {
    'id': 52,
    'vector': '__FLOAT_MULTI_DIM_4,50__',
    'payload': {
    'id': 152,
    'id_str': [
    '10',
    '21',
    '18',
],
    'text_data': 'df7e425ec92d49728d997f9ebe296b96',
    'rand_digit': 7,
    'rand_number': 0.08188,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-05 07:27:17+0900',
    'text_array': [
    'ea235d56422141e099e3bc373c082088',
    '4382501ce7eb436e96c3b73d175a3104',
],
    'words': 'cow deer',
    'nested': {
    'id': 152,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'spider',
    'number': 1,
},
],
},
    'nested_array': [
    [
    -8,
],
    [
    -2,
],
    [
    -3,
],
],
    'two_words': [
    'whale',
    'panda',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': [
    84,
],
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'dog',
    'maybe_null': 'bear',
},
},
    {
    'id': 53,
    'vector': '__FLOAT_MULTI_DIM_6,50__',
    'payload': {
    'id': 153,
    'id_str': [
    '15',
    '18',
],
    'text_data': 'f3487638807b423da6ed8090018d883a',
    'rand_digit': 7,
    'rand_number': 0.65751,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-16T12:22:03.631052',
    'text_array': [
    '1e08441fe68949cf8b2d3dc88256efd1',
    '149c9753a04d456ca6a7e9fe2e41b056',
],
    'words': 'rhino squid',
    'nested': {
    'id': 153,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'butterfly',
    'spider',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.38176,
},
},
    {
    'id': 54,
    'vector': '__FLOAT_MULTI_DIM_3,50__',
    'payload': {
    'id': 154,
    'id_str': [
    '07',
    '28',
    '15',
    '03',
    '08',
],
    'text_data': '8a5ecc20dd5c4c7ab086d5b8ab6a1fb0',
    'rand_digit': 6,
    'rand_number': 0.38043,
    'rand_signed_int': 5,
    'rand_datetime': '2000-11-25T00:55:14.500975',
    'text_array': [
    '92291e0318f84f87bb59ed39113f3845',
    'ebe5cff2563b4d53ac33ebaec7331ed5',
],
    'words': 'deer ape',
    'nested': {
    'id': 154,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'bird',
    'rhino',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'zebra',
    'maybe_null': None,
},
},
    {
    'id': 55,
    'vector': '__FLOAT_MULTI_DIM_10,50__',
    'payload': {
    'id': 155,
    'id_str': [
    '06',
    '22',
    '18',
    '17',
    '24',
],
    'text_data': '8f7bbe4bab024315a0f51a91f7d18ab4',
    'rand_digit': 7,
    'rand_number': 0.69196,
    'rand_signed_int': -8,
    'rand_datetime': '2000-07-10T02:03:58.316444-04:00',
    'text_array': [
    '5070e058074f42308087dfa99dbf8506',
    '7a5272209e06427d816f488986b6375e',
],
    'words': 'camel chicken',
    'nested': {
    'id': 155,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'sloth',
    'squid',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'chicken',
},
},
    {
    'id': 56,
    'vector': '__FLOAT_MULTI_DIM_9,50__',
    'payload': {
    'id': 156,
    'id_str': [
],
    'text_data': '66cdf7b82ebd49f9b940b014a8402c07',
    'rand_digit': 1,
    'rand_number': 0.17988,
    'rand_signed_int': -3,
    'rand_datetime': '2000-05-25 03:41:16.340027',
    'text_array': [
    '7bfecac8e2e14078961278e99073e798',
    '3198ee40ba0242178e397960c94345e5',
],
    'words': 'gorilla hyena',
    'nested': {
    'id': 156,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
    'number': 6,
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
    'octopus',
    'leopard',
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
    'mixed_type': False,
},
},
    {
    'id': 57,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 157,
    'id_str': [
    '16',
],
    'text_data': 'ecaadfc775ee4bc7934251e6a2ac4d06',
    'rand_digit': 3,
    'rand_number': 0.95435,
    'rand_signed_int': 8,
    'rand_datetime': '2000-05-06 23:48:17',
    'text_array': [
    '029290a147114e1a806551e2ccbff8e4',
    '8d00fa77dca4480aa798f574ad606141',
],
    'words': 'fly gorilla',
    'nested': {
    'id': 157,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'butterfly',
    'number': 1,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'lobster',
    'butterfly',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'pig',
},
},
    {
    'id': 58,
    'vector': '__FLOAT_MULTI_DIM_8,50__',
    'payload': {
    'id': 158,
    'id_str': [
    '16',
    '30',
    '11',
    '11',
],
    'text_data': '6f45f6e3814249678731b58704986f97',
    'rand_digit': 1,
    'rand_number': 0.28777,
    'rand_signed_int': 9,
    'rand_datetime': '2000-06-20T17:34:48.740444-11:00',
    'text_array': [
    '35ce9ceff670496896950dcf594e084d',
    '1b8b2fe425cb4741b908b0ad6b8455b0',
],
    'words': 'sloth elephant',
    'nested': {
    'id': 158,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 4,
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
    'word': 'grasshopper',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'gorilla',
    'chicken',
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
    'maybe_null': 'whale',
},
},
    {
    'id': 59,
    'vector': '__FLOAT_MULTI_DIM_2,50__',
    'payload': {
    'id': 159,
    'id_str': [
    '24',
    '21',
],
    'text_data': '6ae9130ec3d84476a5fe4b7ce16c9a93',
    'rand_digit': 6,
    'rand_number': 0.32252,
    'rand_signed_int': 10,
    'rand_datetime': '2000-10-30 14:16',
    'text_array': [
    'e41721dd7e274967a4856484866d2bf0',
    '057178e0adf54edb902b616c11e19582',
],
    'words': 'elephant hyena',
    'nested': {
    'id': 159,
    'rand_digit': 9,
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
],
},
    'nested_array': [
    [
    -3,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'whale',
    'octopus',
],
    'city': {
    'name': 'Rome',
    'geo': {
    'lat': 41.902782,
    'lon': 12.496366,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'deer',
    'maybe_null': 'sheep',
},
},
    {
    'id': 60,
    'vector': '__FLOAT_MULTI_DIM_4,50__',
    'payload': {
    'id': 160,
    'id_str': [
    '22',
    '12',
],
    'text_data': '4bf7475976be4b1eb154d4e6d69120c5',
    'rand_digit': 5,
    'rand_number': 0.75742,
    'rand_signed_int': 5,
    'rand_datetime': '2001-01-26',
    'text_array': [
    '4bb6b681433d468b93bc628535a3dfef',
    '7e5735077a134d3b842ea5c8a4203676',
],
    'words': 'octopus rhino',
    'nested': {
    'id': 160,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'ladybug',
    'number': 7,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    8,
],
],
    'two_words': [
    'hyena',
    'kangaroo',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'ladybug',
    'maybe_null': None,
},
},
    {
    'id': 61,
    'vector': '__FLOAT_MULTI_DIM_6,50__',
    'payload': {
    'id': 161,
    'id_str': [
    '08',
    '06',
    '17',
    '07',
    '16',
],
    'text_data': '083936d79b7347bf9c697f88083debb8',
    'rand_digit': 5,
    'rand_number': 0.68777,
    'rand_signed_int': -7,
    'rand_datetime': '2000-09-19T07:43:59+0500',
    'text_array': [
    '5ed096ccb848436f9a23ab41b0ce3780',
    '99d911544ad34a2b94c041bc688ac325',
],
    'words': 'dolphin sheep',
    'nested': {
    'id': 161,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
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
    'word': 'spider',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -4,
],
],
    'two_words': [
    'hyena',
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
    59,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'snail',
    'maybe_null': 'cow',
},
},
    {
    'id': 62,
    'vector': '__FLOAT_MULTI_DIM_6,50__',
    'payload': {
    'id': 162,
    'id_str': [
    '18',
    '29',
    '29',
    '02',
],
    'text_data': 'df58c76395d94d0d9d0834aa34285eb5',
    'rand_digit': 7,
    'rand_number': 0.39914,
    'rand_signed_int': 0,
    'rand_datetime': '2000-01-17T04:22:41.354427',
    'text_array': [
    '517b207347554ba194f1fedbf474e4b3',
    'ee70a4234ba54e3cb928eba66010423e',
],
    'words': 'octopus rhino',
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
    'word': 'bear',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'leopard',
    'fish',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': [
    96,
],
    'rand_bool': False,
    'mixed_type': 'cow',
    'maybe': 'hyena',
},
},
    {
    'id': 63,
    'vector': '__FLOAT_MULTI_DIM_10,50__',
    'payload': {
    'id': 163,
    'id_str': [
    '16',
    '01',
    '10',
    '26',
],
    'text_data': '2d71863ac58f4a8e8a3d5f2ddec60565',
    'rand_digit': 9,
    'rand_number': 0.98691,
    'rand_signed_int': -8,
    'rand_datetime': '2000-06-14 06:10:26.768240',
    'text_array': [
    '60093212da9a4fab9b58beb84c104257',
    'c9735a5d2a974bc6b9dee4481c23eb6d',
],
    'words': 'camel grasshopper',
    'nested': {
    'id': 163,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
    -9,
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'shark',
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
    27,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'snail',
    'maybe_null': 'cow',
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
    'content-length': '3043',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'nearest': '__FLOAT_MULTI_DIM_10,50__',
},
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
    'content-length': '86',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'size': 50,
    'distance': 'Dot',
    'multivector_config': {
    'comparator': 'max_sim',
},
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_multivector_search_queries.test_single_vector')
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
    test = TestMultivectorSearchQueriestestSingleVector()
    test.run_tests()
