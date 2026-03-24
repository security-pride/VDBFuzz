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
logger = logging.getLogger('vdb_fuzzer.test.test_search_test_single_vector')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_search.test_single_vector"
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



class TestSearchtestSingleVector:
    """自动生成的VDB模糊测试类 - test_search.test_single_vector"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_search.test_single_vector"
        self.test_count = 33  # 测试方法数量
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
    'content-length': '40',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'size': 50,
    'distance': 'Dot',
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
    'content-length': '67001',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 100,
    'id_str': [
    '16',
    '19',
    '23',
    '19',
],
    'text_data': '17a02e56a6e541aeb080c889e7d26fe7',
    'rand_digit': 8,
    'rand_number': 0.00506,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-27 12:07:45.826653',
    'text_array': [
    '4a893c81909a4160b324b7bc772dd09f',
    '4428acf6fa2d426c84ede7608b7e2452',
],
    'words': 'kangaroo dog',
    'nested': {
    'id': 100,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'kangaroo',
    'frog',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'shark',
    'maybe_null': 'lion',
},
},
    {
    'id': 1,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 101,
    'id_str': [
    '06',
],
    'text_data': '5084f5771ab14fbe9cda8761c8f1dccd',
    'rand_digit': 3,
    'rand_number': 0.10364,
    'rand_signed_int': 0,
    'rand_datetime': '2000-04-29 15:55:09.111624+0000',
    'text_array': [
    '567b7f9fcb42459ebbd02742717fd560',
    '01e63cdff61f4333bb3aa23939ef065c',
],
    'words': 'horse whale',
    'nested': {
    'id': 101,
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
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'bear',
    'camel',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': [
    11,
],
    'rand_bool': False,
    'mixed_type': 0.4279,
    'maybe_null': 'snail',
},
},
    {
    'id': 2,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 102,
    'id_str': [
    '17',
    '02',
    '19',
    '12',
],
    'text_data': 'd007b2322d514a9fbf912fce54a3a606',
    'rand_digit': 3,
    'rand_number': 0.45646,
    'rand_signed_int': -8,
    'rand_datetime': '2000-07-19 10:39:00-0200',
    'text_array': [
    '5aa1b326f120474cabbec1d8054d5233',
    '6db12968230e474bbe423a827357ea41',
],
    'words': 'dog spider',
    'nested': {
    'id': 102,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'jaguar',
    'tiger',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'rabbit',
},
},
    {
    'id': 3,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 103,
    'id_str': [
    '19',
    '17',
    '01',
    '07',
],
    'text_data': '5b77f177da34404bbe376057d7068150',
    'rand_digit': 8,
    'rand_number': 0.54582,
    'rand_signed_int': -10,
    'rand_datetime': '2000-02-17T15:02:10-0800',
    'text_array': [
    'f561d56a27ce4b7492d96296c1606814',
    '9fb05a9f61c64405bb0b5c509cad2a15',
],
    'words': 'squid whale',
    'nested': {
    'id': 103,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'dragonfly',
    'number': 2,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'rabbit',
    'duck',
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
    'maybe': 'turtle',
    'maybe_null': 'lizard',
},
},
    {
    'id': 4,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 104,
    'id_str': [
    '19',
    '03',
    '13',
    '07',
],
    'text_data': '7dcf364cf0e541278d4b965f1455255d',
    'rand_digit': 9,
    'rand_number': 0.00316,
    'rand_signed_int': 9,
    'rand_datetime': '2001-01-27 00:28:38',
    'text_array': [
    '0a6ef1857c5f457fb72af8e5c5728735',
    '7b7da698f8344bd88c8b49fbd8a21482',
],
    'words': 'horse crab',
    'nested': {
    'id': 104,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'pig',
    'fish',
],
    'city': {
    'name': 'Seoul',
    'geo': {
    'lat': 37.566535,
    'lon': 126.977969,
},
},
    'rand_tuple': [
    50,
],
    'rand_bool': False,
    'mixed_type': 0.03854,
},
},
    {
    'id': 5,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 105,
    'id_str': [
    '23',
    '18',
    '29',
],
    'text_data': '603c735b90064e3a8269a4ef7198b1df',
    'rand_digit': 4,
    'rand_number': 0.14608,
    'rand_signed_int': -7,
    'rand_datetime': '2000-02-10 18:34:28-1200',
    'text_array': [
    'eb8fcbece64747d086a87e8b298b1b7f',
    '3477110b3a6e49e28ef76c548d09782d',
],
    'words': 'pig cat',
    'nested': {
    'id': 105,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'dragonfly',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 4,
},
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
],
    'two_words': [
    'elephant',
    'snake',
],
    'city': {
    'name': 'Johannesburg',
    'geo': {
    'lat': -26.204103,
    'lon': 28.047305,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 6,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 106,
    'id_str': [
    '07',
    '24',
    '08',
    '15',
],
    'text_data': 'a2df632a5bb249d7b935b8923dd1db19',
    'rand_digit': 5,
    'rand_number': 0.73158,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-04',
    'text_array': [
    '89d885f432694d129f1404257f15adfc',
    '167e0db3b5c446ada14d2a50c12ee7f0',
],
    'words': 'snake cheetah',
    'nested': {
    'id': 106,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -9,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'rabbit',
    'lobster',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'cheetah',
},
},
    {
    'id': 7,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 107,
    'id_str': [
],
    'text_data': 'e3933b4f85134bedb871df5234ab3736',
    'rand_digit': 6,
    'rand_number': 0.04944,
    'rand_signed_int': 3,
    'rand_datetime': '2000-06-28 09:59:20',
    'text_array': [
    '222d3ef05fe84264a3208c7ef5723ca2',
    '0a2522c917e644fe8bda383a0497fe52',
],
    'words': 'ape fish',
    'nested': {
    'id': 107,
    'rand_digit': 7,
    'array': [
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
],
    'word': 'grasshopper',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'ladybug',
    'bee',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'frog',
    'maybe_null': 'mosquito',
},
},
    {
    'id': 8,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 108,
    'id_str': [
    '25',
],
    'text_data': '4d62ab4f1316439e9d12d35315971106',
    'rand_digit': 3,
    'rand_number': 0.27515,
    'rand_signed_int': 9,
    'rand_datetime': '2000-06-09 12:33:09+0900',
    'text_array': [
    '0dc2822b84af49c6837e31035624f830',
    '8543684053914f1f8c430d3ad8b2b9c3',
],
    'words': 'elephant whale',
    'nested': {
    'id': 108,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'duck',
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
    'mixed_type': True,
    'maybe': 'shark',
},
},
    {
    'id': 9,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 109,
    'id_str': [
    '15',
    '19',
    '26',
],
    'text_data': '5b85221b96da4b53a4d6c8182242980b',
    'rand_digit': 7,
    'rand_number': 0.97845,
    'rand_signed_int': -5,
    'rand_datetime': '2000-02-14 22:35:15',
    'text_array': [
    '728e2e36067b4d62b17c8ce8dac74d2c',
    'af74eb7e7a5242e0a9822bc9fd092f09',
],
    'words': 'dragonfly bear',
    'nested': {
    'id': 109,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dolphin',
    'hippo',
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
    'maybe_null': 'tiger',
},
},
    {
    'id': 10,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 110,
    'id_str': [
    '02',
    '28',
    '07',
    '21',
    '16',
],
    'text_data': '6203162b73bc4a62b3be78ece2251356',
    'rand_digit': 8,
    'rand_number': 0.78227,
    'rand_signed_int': -1,
    'rand_datetime': '2000-05-17 20:38',
    'text_array': [
    '734bd1ca7ccd48cfbbd8ff63ba4d24c4',
    'ad8e9867dddb466fb9bed375d360b95b',
],
    'words': 'grasshopper wolf',
    'nested': {
    'id': 110,
    'rand_digit': 7,
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
],
},
    'nested_array': [
    [
    3,
],
    [
    7,
],
    [
],
],
    'two_words': [
    'turtle',
    'dog',
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
    'mixed_type': 3,
    'maybe_null': 'ape',
},
},
    {
    'id': 11,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 111,
    'id_str': [
    '03',
    '09',
],
    'text_data': '69e6d0c9b83042249624245cb4e53ca1',
    'rand_digit': 7,
    'rand_number': 0.96562,
    'rand_signed_int': 0,
    'rand_datetime': '2000-09-03 22:11',
    'text_array': [
    '28d93585acd24d29a07e973d0f43f1f2',
    '0567c0636c244f7d8fa8d34ba8d09e63',
],
    'words': 'frog camel',
    'nested': {
    'id': 111,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lion',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    2,
],
],
    'two_words': [
    'fish',
    'elephant',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'sheep',
    'maybe_null': None,
},
},
    {
    'id': 12,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 112,
    'id_str': [
    '23',
    '29',
    '25',
    '21',
],
    'text_data': '8ecad070a668444d84f5c1aeb99a458d',
    'rand_digit': 6,
    'rand_number': 0.70998,
    'rand_signed_int': -3,
    'rand_datetime': '2000-01-24 08:35:40.310555',
    'text_array': [
    '572927573c5a4586b9c7f8d254a4e650',
    '772449c8d2794b6ebbf104309e373b8f',
],
    'words': 'crab zebra',
    'nested': {
    'id': 112,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 6,
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
],
    'word': 'ladybug',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'octopus',
    'snake',
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
    'mixed_type': None,
    'maybe_null': 'ant',
},
},
    {
    'id': 13,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 113,
    'id_str': [
],
    'text_data': 'b83e6e2f73b046ceb829a0f3e877396c',
    'rand_digit': 2,
    'rand_number': 0.66631,
    'rand_signed_int': 10,
    'rand_datetime': '2000-10-02T12:26:57.890059-1200',
    'text_array': [
    'da2c73acc55e4dc7abfada67ecf11b89',
    '8193aec33bf24a6fb318295bf801451d',
],
    'words': 'ladybug camel',
    'nested': {
    'id': 113,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'hyena',
    'lion',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': [
    31,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'fish',
},
},
    {
    'id': 14,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 114,
    'id_str': [
],
    'text_data': 'b4484b35d6074f6488d2ffff967bb614',
    'rand_digit': 1,
    'rand_number': 0.98541,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-13',
    'text_array': [
    'fa1ed003aad9497ca30f78198c473e38',
    '663354d7f78846d3af8af83b14d25952',
],
    'words': 'frog rhino',
    'nested': {
    'id': 114,
    'rand_digit': 0,
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
    'word': 'leopard',
    'number': 8,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'wolf',
    'butterfly',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe_null': 'koala',
},
},
    {
    'id': 15,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 115,
    'id_str': [
    '17',
    '06',
    '22',
    '30',
],
    'text_data': '24d01442de714370aa446d5d10453eaf',
    'rand_digit': 2,
    'rand_number': 0.01916,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-24T19:10:31.003610-11:00',
    'text_array': [
    'd3ffde66e37c4ef0baae8d208e98bb3d',
    '35e557e9daa44b81bcf6affa6cbf751a',
],
    'words': 'bee monkey',
    'nested': {
    'id': 115,
    'rand_digit': 4,
    'array': [
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
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'frog',
    'scorpion',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': [
    12,
],
    'rand_bool': False,
    'mixed_type': 8,
    'maybe_null': None,
},
},
    {
    'id': 16,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 116,
    'id_str': [
    '10',
],
    'text_data': '84b8539997cd4769a9f294425eed3601',
    'rand_digit': 1,
    'rand_number': 0.58133,
    'rand_signed_int': -8,
    'rand_datetime': '2000-06-03T12:17:54.204963-09:00',
    'text_array': [
    '908ce28900d64c6ba17b17f563352dca',
    '449a5237e4e54c569e2b6a0fdf2e408d',
],
    'words': 'mosquito sloth',
    'nested': {
    'id': 116,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'frog',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'rabbit',
    'giraffe',
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
    'mixed_type': 7,
    'maybe': 'octopus',
},
},
    {
    'id': 17,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 117,
    'id_str': [
],
    'text_data': 'af92041a382940e2bcb5f707a6662f85',
    'rand_digit': 5,
    'rand_number': 0.0678,
    'rand_signed_int': 7,
    'rand_datetime': '2000-12-01T11:29:38',
    'text_array': [
    '554806f1318f4c5185d4ffde0984e7da',
    '252129fe33c54b13880e16c51b779b13',
],
    'words': 'bee dragonfly',
    'nested': {
    'id': 117,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 10,
},
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -3,
],
],
    'two_words': [
    'whale',
    'deer',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'jaguar',
    'maybe_null': 'ant',
},
},
    {
    'id': 18,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 118,
    'id_str': [
    '03',
    '09',
    '07',
    '16',
    '12',
],
    'text_data': '7b715b25f5b645509b51c7cd4bc4fcf3',
    'rand_digit': 0,
    'rand_number': 0.96471,
    'rand_signed_int': -9,
    'rand_datetime': '2000-02-12T14:50:05-0500',
    'text_array': [
    '0cf928b716b94162ae55d4c851d05876',
    '0b2e040a91334201ab4b067ddecd8e73',
],
    'words': 'frog ladybug',
    'nested': {
    'id': 118,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'deer',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'lobster',
    'koala',
],
    'city': {
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': [
    77,
],
    'rand_bool': True,
    'mixed_type': 0.08857,
    'maybe': 'snail',
    'maybe_null': 'giraffe',
},
},
    {
    'id': 19,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 119,
    'id_str': [
],
    'text_data': '06804365766b4092880da148e7a719c6',
    'rand_digit': 5,
    'rand_number': 0.11578,
    'rand_signed_int': -6,
    'rand_datetime': '2000-08-07 20:29:15+0700',
    'text_array': [
    'b624f83df2d04e8eb32f9756ee3f2f10',
    '5f108cd179a74c5e88a9122b250e3276',
],
    'words': 'hippo giraffe',
    'nested': {
    'id': 119,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'snail',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'cheetah',
    'turtle',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe': 'snake',
    'maybe_null': 'horse',
},
},
    {
    'id': 20,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 120,
    'id_str': [
    '13',
    '22',
    '20',
    '19',
    '20',
],
    'text_data': '1d822cd9ab694ae89d19ec8c1189a723',
    'rand_digit': 0,
    'rand_number': 0.07407,
    'rand_signed_int': 5,
    'rand_datetime': '2000-01-15 19:37:29.419849',
    'text_array': [
    '7a2a40b08d224aa69be30fae14f0edb9',
    '8220dc5593ba482d8a3d9698258084a4',
],
    'words': 'ape dolphin',
    'nested': {
    'id': 120,
    'rand_digit': 8,
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
    'hello',
],
    'word': 'horse',
    'number': 1,
},
],
},
    'nested_array': [
    [
    -5,
],
    [
    3,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'whale',
    'fly',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'giraffe',
},
},
    {
    'id': 21,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 121,
    'id_str': [
    '24',
    '17',
    '10',
    '13',
],
    'text_data': 'f6ead233d71445d0b9fed9669277cea5',
    'rand_digit': 6,
    'rand_number': 0.2925,
    'rand_signed_int': 7,
    'rand_datetime': '2000-05-09 04:26:10',
    'text_array': [
    'b39c0b1614334fa683553de9f3afeddd',
    'ea81e2b2feeb4e0483ede84cf72a0326',
],
    'words': 'rhino spider',
    'nested': {
    'id': 121,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
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
],
    'two_words': [
    'giraffe',
    'tiger',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': [
    1,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'camel',
},
},
    {
    'id': 22,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 122,
    'id_str': [
    '09',
    '18',
    '12',
],
    'text_data': '4c830b8e40d74a678f8a4bc1b09daec6',
    'rand_digit': 2,
    'rand_number': 0.003,
    'rand_signed_int': -10,
    'rand_datetime': '2000-12-30 13:46:43',
    'text_array': [
    'a94e83df3f4641049226c538ea037f45',
    '8221403a4a2f40f683df75ba3e676bdf',
],
    'words': 'ape dog',
    'nested': {
    'id': 122,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'cow',
    'mosquito',
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
    'mixed_type': True,
    'maybe_null': None,
},
},
    {
    'id': 23,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 123,
    'id_str': [
    '27',
],
    'text_data': '40f6e5a14cb348f49af26f0ee0b5376d',
    'rand_digit': 8,
    'rand_number': 0.0686,
    'rand_signed_int': 6,
    'rand_datetime': '2000-08-30T07:50:20.904098',
    'text_array': [
    'a9b3a2ddba974f8abce54e40d26484cc',
    'e77dc7d0f8f7435ea19209bb63376f1e',
],
    'words': 'hippo tiger',
    'nested': {
    'id': 123,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'whale',
    'ladybug',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'lobster',
    'maybe_null': 'lion',
},
},
    {
    'id': 24,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 124,
    'id_str': [
    '10',
],
    'text_data': 'd8e8f8e95af541b585f0cb2c7f442edc',
    'rand_digit': 1,
    'rand_number': 0.5326,
    'rand_signed_int': 3,
    'rand_datetime': '2000-04-02T12:51:31.143898',
    'text_array': [
    '59ba72ce3f104dae98f4467d625ef186',
    '33e940a33f254526b4d93189f73757f9',
],
    'words': 'gorilla jaguar',
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
    'word': 'snake',
    'number': 6,
},
    {
    'nested_empty': None,
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
],
    'word': 'hippo',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cat',
    'whale',
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
    'mixed_type': 'mosquito',
    'maybe_null': 'mosquito',
},
},
    {
    'id': 25,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 125,
    'id_str': [
    '03',
    '26',
],
    'text_data': '6927935f9aa74a36a69f34fb44fdf1ab',
    'rand_digit': 5,
    'rand_number': 0.58328,
    'rand_signed_int': -4,
    'rand_datetime': '2000-02-20',
    'text_array': [
    '17ff319d2b7944fcaf05aeb54c1101f1',
    'f70151b9c35443199737e5b39fc2c191',
],
    'words': 'rhino dog',
    'nested': {
    'id': 125,
    'rand_digit': 0,
    'array': [
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
    'word': 'gorilla',
    'number': 3,
},
    {
    'nested_empty': None,
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
    'word': 'squid',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    5,
],
],
    'two_words': [
    'lobster',
    'frog',
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
    'id': 26,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 126,
    'id_str': [
],
    'text_data': '0028603e1bfb4e5eb5580086a2797eef',
    'rand_digit': 6,
    'rand_number': 0.3172,
    'rand_signed_int': -1,
    'rand_datetime': '2001-01-03T21:39:41.483511+1000',
    'text_array': [
    'd142bde867a3439191014a5d75d45b3a',
    '0a8aaa47fec148759cfe8e0c764d9938',
],
    'words': 'scorpion turtle',
    'nested': {
    'id': 126,
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
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -3,
],
],
    'two_words': [
    'whale',
    'frog',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'monkey',
    'maybe_null': 'duck',
},
},
    {
    'id': 27,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 127,
    'id_str': [
    '08',
],
    'text_data': '0548a512f23e4e6ba59aa09c4c47c9ca',
    'rand_digit': 5,
    'rand_number': 0.98367,
    'rand_signed_int': 0,
    'rand_datetime': '2000-04-04T02:09:47.385791-0200',
    'text_array': [
    '742e24b52f00461081fd7d7ee349ecba',
    '29bd0cbf5a894f7ca18136acc14e6cab',
],
    'words': 'crab zebra',
    'nested': {
    'id': 127,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'jaguar',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 5,
},
],
},
    'nested_array': [
    [
    -2,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lion',
    'ladybug',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'cheetah',
},
},
    {
    'id': 28,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 128,
    'id_str': [
    '10',
],
    'text_data': '73c7a4ba94ca4d62b8fed9171dfe88f1',
    'rand_digit': 9,
    'rand_number': 0.68354,
    'rand_signed_int': -7,
    'rand_datetime': '2000-08-27 21:52:39.302925+0800',
    'text_array': [
    '3f76981a74eb4a3ca05f1b3ec01bcfe0',
    '5545cd9b28a5422ab4c6d4dcf45fddf9',
],
    'words': 'ladybug fox',
    'nested': {
    'id': 128,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    [
    -8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dog',
    'fox',
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
    'mixed_type': False,
    'maybe_null': 'cat',
},
},
    {
    'id': 29,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 129,
    'id_str': [
    '11',
],
    'text_data': '0ad417eb80b54ec3a9636325f27abe65',
    'rand_digit': 7,
    'rand_number': 0.16612,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-25T18:51:53',
    'text_array': [
    '078b6f2c063e4dbcb5ebcf3576c8d397',
    '7f7056a067d6429fb77b857a8e88c2d2',
],
    'words': 'grasshopper mosquito',
    'nested': {
    'id': 129,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'cow',
    'jaguar',
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
    'mixed_type': 0.78323,
    'maybe': 'snake',
},
},
    {
    'id': 30,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 130,
    'id_str': [
    '01',
],
    'text_data': '04a366906d284ec592b5220e394d9b99',
    'rand_digit': 8,
    'rand_number': 0.40758,
    'rand_signed_int': 9,
    'rand_datetime': '2000-07-10T08:47:06.878946',
    'text_array': [
    'f996f141cfbc48659db08e7f081b02cf',
    '80e6e6142cf54d65b4b4140a8bee1e1e',
],
    'words': 'scorpion hippo',
    'nested': {
    'id': 130,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 6,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -3,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ape',
    'cheetah',
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
    'mixed_type': 0.67701,
    'maybe': 'cow',
    'maybe_null': 'kangaroo',
},
},
    {
    'id': 31,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 131,
    'id_str': [
    '10',
    '21',
    '17',
],
    'text_data': '8dc61853190548bc8b8798dffbed1b82',
    'rand_digit': 0,
    'rand_number': 0.80589,
    'rand_signed_int': 9,
    'rand_datetime': '2000-06-14T02:51:10.255907',
    'text_array': [
    '3d09a31eb59340b2b60aca98807db508',
    '46b62284ab8f4608a0a3390b190d7aa9',
],
    'words': 'pig camel',
    'nested': {
    'id': 131,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'grasshopper',
    'scorpion',
],
    'city': {
    'name': 'Seoul',
    'geo': {
    'lat': 37.566535,
    'lon': 126.977969,
},
},
    'rand_tuple': [
    17,
],
    'rand_bool': False,
    'mixed_type': 0.32751,
},
},
    {
    'id': 32,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 132,
    'id_str': [
    '10',
    '05',
    '28',
    '29',
    '10',
],
    'text_data': 'aba3bbf9411f4c19bf07bda97d7ab84a',
    'rand_digit': 2,
    'rand_number': 0.52304,
    'rand_signed_int': 4,
    'rand_datetime': '2000-10-28',
    'text_array': [
    'c3857e6485684dc3880be82b42d1b5b2',
    'c698c5aacf58438eb5631a4e19416632',
],
    'words': 'shark hippo',
    'nested': {
    'id': 132,
    'rand_digit': 7,
    'array': [
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'octopus',
    'sheep',
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
    'maybe_null': None,
},
},
    {
    'id': 33,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 133,
    'id_str': [
    '04',
    '15',
    '21',
    '11',
    '29',
],
    'text_data': '2781ff90d1584c04a47a795817733bf9',
    'rand_digit': 7,
    'rand_number': 0.21604,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-16 07:03:02+0100',
    'text_array': [
    'a98f791a599c4b868d660ac1ebf63cdf',
    '1bdd98a33e78405b88bd33097663eadc',
],
    'words': 'leopard monkey',
    'nested': {
    'id': 133,
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
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'fox',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lizard',
    'snake',
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
    'mixed_type': 'horse',
    'maybe': 'fly',
    'maybe_null': 'octopus',
},
},
    {
    'id': 34,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 134,
    'id_str': [
    '26',
    '01',
    '19',
    '10',
    '04',
],
    'text_data': 'd43c9c36ff174456a807fc7d5ccce3e7',
    'rand_digit': 9,
    'rand_number': 0.81734,
    'rand_signed_int': -1,
    'rand_datetime': '2000-04-29 17:25:53.962216',
    'text_array': [
    '639f994fe76f452d90c43eacf1551a48',
    '0304bca3be444903917aa5a26991928c',
],
    'words': 'bird panda',
    'nested': {
    'id': 134,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'hyena',
    'panda',
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
    'mixed_type': 'lizard',
    'maybe': 'horse',
    'maybe_null': 'grasshopper',
},
},
    {
    'id': 35,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 135,
    'id_str': [
    '11',
],
    'text_data': '0704914a011949e9a3e39808acc1a456',
    'rand_digit': 5,
    'rand_number': 0.38842,
    'rand_signed_int': 5,
    'rand_datetime': '2000-08-31 06:12',
    'text_array': [
    '24c2964dcf384ad1a4a130e6f0e10d74',
    '05f5e32f16c54095ab0e7fed6e95a200',
],
    'words': 'panda cat',
    'nested': {
    'id': 135,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'crab',
    'number': 7,
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
    'word': 'giraffe',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'elephant',
    'snake',
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
    'maybe_null': 'ladybug',
},
},
    {
    'id': 36,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 136,
    'id_str': [
    '16',
    '09',
],
    'text_data': '6e8c0ce74e944f74959fb31570850b81',
    'rand_digit': 5,
    'rand_number': 0.30319,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-23 14:54:00',
    'text_array': [
    '8169a4a2907f4a6d9e7f705a33b9b74f',
    '3827b709424d4ab5814e67b63a401001',
],
    'words': 'chicken leopard',
    'nested': {
    'id': 136,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 9,
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
    'mouse',
    'octopus',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': [
    17,
],
    'rand_bool': False,
    'mixed_type': 'dolphin',
    'maybe': 'jaguar',
},
},
    {
    'id': 37,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 137,
    'id_str': [
    '19',
],
    'text_data': '5f5120d638f54dc28b190ea05a77444d',
    'rand_digit': 3,
    'rand_number': 0.39993,
    'rand_signed_int': 10,
    'rand_datetime': '2000-08-11T20:57:33.532739',
    'text_array': [
    'ae20640d8cba4a46a842bc016b21d8dd',
    'f5948d2a7f5b4d24be1484ad866a9a1b',
],
    'words': 'frog spider',
    'nested': {
    'id': 137,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'hippo',
    'snake',
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
    'mixed_type': 0.10132,
    'maybe': 'koala',
    'maybe_null': 'turtle',
},
},
    {
    'id': 38,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 138,
    'id_str': [
    '26',
    '02',
    '11',
],
    'text_data': 'e94e7b64902f47c8abaf694d9b50ee77',
    'rand_digit': 2,
    'rand_number': 0.07789,
    'rand_signed_int': 10,
    'rand_datetime': '2000-10-26T04:12:56',
    'text_array': [
    '5604d5562df94cdaa772cfecb48839de',
    '7c6ff91ecf784692a5945706966f8ad2',
],
    'words': 'kangaroo gorilla',
    'nested': {
    'id': 138,
    'rand_digit': 9,
    'array': [
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
    'word': 'leopard',
    'number': 8,
},
],
},
    'nested_array': [
    [
    5,
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'rhino',
    'duck',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 39,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 139,
    'id_str': [
    '06',
    '21',
    '14',
    '15',
    '22',
],
    'text_data': '52913b55b0864dc6b753336c2cc51233',
    'rand_digit': 0,
    'rand_number': 0.09176,
    'rand_signed_int': -3,
    'rand_datetime': '2000-07-28T00:13:23.885153+10:00',
    'text_array': [
    '2ab39134ab6d4b8eb19201318475dfde',
    '8b10adba02224bc38c0e2562bac59c9c',
],
    'words': 'lion wolf',
    'nested': {
    'id': 139,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'jaguar',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -8,
],
    [
    -3,
],
],
    'two_words': [
    'pig',
    'cheetah',
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
    'mixed_type': 0.9754,
},
},
    {
    'id': 40,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 140,
    'id_str': [
    '18',
    '09',
    '26',
    '26',
],
    'text_data': '8e260c06814246e79b4561ab8366a787',
    'rand_digit': 5,
    'rand_number': 0.392,
    'rand_signed_int': 0,
    'rand_datetime': '2000-07-12T12:03:36.462778',
    'text_array': [
    '52ca815a9a034c4787f008d51d35f42a',
    '812e5c5aeedf4da2831a97c6d2b96050',
],
    'words': 'ladybug frog',
    'nested': {
    'id': 140,
    'rand_digit': 1,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'scorpion',
    'ant',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'butterfly',
    'maybe_null': 'mouse',
},
},
    {
    'id': 41,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 141,
    'id_str': [
    '02',
],
    'text_data': 'c600dfe9e6914702ac50fcdd6684da1d',
    'rand_digit': 9,
    'rand_number': 0.73097,
    'rand_signed_int': 3,
    'rand_datetime': '2000-12-16T21:14:28',
    'text_array': [
    '5034337429ab442e897e17f2809b4147',
    '894ddc1380f34145b881aad2a27eeaa4',
],
    'words': 'lobster koala',
    'nested': {
    'id': 141,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'gorilla',
    'dolphin',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cheetah',
    'maybe_null': None,
},
},
    {
    'id': 42,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 142,
    'id_str': [
    '15',
    '01',
    '11',
    '10',
],
    'text_data': 'fd3800abf8c84290beb8ba63f7aaebe8',
    'rand_digit': 5,
    'rand_number': 0.68308,
    'rand_signed_int': 8,
    'rand_datetime': '2000-12-15 16:33:51.992043',
    'text_array': [
    '3339ba6b55d24c2aa14bd1550450d0a2',
    '707d43324eb441f09574ff8126d3b75b',
],
    'words': 'bee snake',
    'nested': {
    'id': 142,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cat',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'horse',
    'number': 7,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'koala',
    'rhino',
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
    'maybe': 'panda',
},
},
    {
    'id': 43,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 143,
    'id_str': [
    '26',
    '15',
    '20',
],
    'text_data': '877027c27e33498bb6c2971336dbe958',
    'rand_digit': 1,
    'rand_number': 0.31488,
    'rand_signed_int': -6,
    'rand_datetime': '2000-08-29',
    'text_array': [
    '2de65a03dfc743ccaf89d3a601c45094',
    'deb4e69198f3460e8657ef45ca999265',
],
    'words': 'butterfly gorilla',
    'nested': {
    'id': 143,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'tiger',
    'number': 1,
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
],
},
    'nested_array': [
],
    'two_words': [
    'hyena',
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
    'mixed_type': None,
    'maybe_null': 'shark',
},
},
    {
    'id': 44,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 144,
    'id_str': [
],
    'text_data': '5f8fed6643dc4fd58501b0316d0cb1ba',
    'rand_digit': 2,
    'rand_number': 0.68312,
    'rand_signed_int': -2,
    'rand_datetime': '2000-09-22 05:13:00',
    'text_array': [
    'c09fdc58cdc34619aa7f07dcae942ccb',
    '5a769582720d4baa8aa1524d7a00f4a2',
],
    'words': 'frog cow',
    'nested': {
    'id': 144,
    'rand_digit': 1,
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
],
    'word': 'sloth',
    'number': 7,
},
    {
    'nested_empty': None,
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
    [
    6,
],
    [
    4,
],
],
    'two_words': [
    'cat',
    'sloth',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': [
    26,
],
    'rand_bool': False,
    'mixed_type': 0.3517,
    'maybe_null': 'bear',
},
},
    {
    'id': 45,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 145,
    'id_str': [
    '13',
    '14',
    '30',
],
    'text_data': '0f99d9dc648a4851b281cddafef26638',
    'rand_digit': 1,
    'rand_number': 0.33256,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-11 13:59:39',
    'text_array': [
    '381a672bdfd44115b42d5a19e8867584',
    '11947a6d90c74303a0193dd0736acf6d',
],
    'words': 'cheetah lobster',
    'nested': {
    'id': 145,
    'rand_digit': 1,
    'array': [
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
    'word': 'ape',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'lobster',
    'tiger',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': [
    31,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 46,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 146,
    'id_str': [
    '04',
    '25',
    '17',
    '10',
],
    'text_data': '85fef3f9886945e8a45c8822e6beb777',
    'rand_digit': 1,
    'rand_number': 0.25055,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-21 20:05:26',
    'text_array': [
    '016593ca9015465a9a446c2f7f064fab',
    'bb4892beccb14c51aa0f032b059b2657',
],
    'words': 'duck giraffe',
    'nested': {
    'id': 146,
    'rand_digit': 0,
    'array': [
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
    'word': 'giraffe',
    'number': 9,
},
    {
    'nested_empty': None,
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
    'word': 'cow',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ape',
    'squid',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 47,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 147,
    'id_str': [
    '22',
    '16',
],
    'text_data': '54772711e1db412b848f559006c1e02b',
    'rand_digit': 8,
    'rand_number': 0.02414,
    'rand_signed_int': 1,
    'rand_datetime': '2001-01-12T12:29:04.007126',
    'text_array': [
    '2c9c3435e34d4fd9ae319ea130d45219',
    '6ef683bcaa424575a8d944c5ea634d99',
],
    'words': 'panda snake',
    'nested': {
    'id': 147,
    'rand_digit': 8,
    'array': [
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'deer',
    'crab',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'horse',
},
},
    {
    'id': 48,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 148,
    'id_str': [
    '25',
],
    'text_data': 'd20c92f7c14b406ba3e6abdeaa1dc0d3',
    'rand_digit': 2,
    'rand_number': 0.34076,
    'rand_signed_int': 8,
    'rand_datetime': '2000-05-10T11:12:40.904320',
    'text_array': [
    '9996cef5ca3744d786757af1341f9c46',
    '9672807865524eb5abdf5d7106ae3a49',
],
    'words': 'butterfly ladybug',
    'nested': {
    'id': 148,
    'rand_digit': 7,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'fly',
    'dolphin',
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
    'mixed_type': 'cheetah',
    'maybe': 'grasshopper',
    'maybe_null': 'panda',
},
},
    {
    'id': 49,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 149,
    'id_str': [
    '04',
    '14',
],
    'text_data': 'd2bd7f8d082d41a0b8b7767917da505b',
    'rand_digit': 8,
    'rand_number': 0.19613,
    'rand_signed_int': -8,
    'rand_datetime': '2000-03-17T17:39:42.220738-0600',
    'text_array': [
    '3f82fe0135c347ad97136cf50773bcf0',
    '973a52685c944edf8ba4d9acd1623b9d',
],
    'words': 'ladybug cat',
    'nested': {
    'id': 149,
    'rand_digit': 0,
    'array': [
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
    [
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
    10,
],
],
    'two_words': [
    'elephant',
    'turtle',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 50,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 150,
    'id_str': [
    '14',
    '11',
    '22',
    '06',
],
    'text_data': '1dea594692c34f23994f61fe75eb55d0',
    'rand_digit': 2,
    'rand_number': 0.35711,
    'rand_signed_int': -7,
    'rand_datetime': '2000-11-10T21:32:18.327564+12:00',
    'text_array': [
    '14287866133c49afa29e4007abb86e67',
    'ca45c055a07d48e3ac0cadc1418fd926',
],
    'words': 'gorilla cheetah',
    'nested': {
    'id': 150,
    'rand_digit': 8,
    'array': [
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
    'word': 'frog',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 5,
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
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'horse',
    'bee',
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
},
},
    {
    'id': 51,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 151,
    'id_str': [
    '17',
    '24',
],
    'text_data': '897a3d979da34459a4a7935611f1620d',
    'rand_digit': 8,
    'rand_number': 0.53154,
    'rand_signed_int': 1,
    'rand_datetime': '2000-12-07 06:39:17.503763',
    'text_array': [
    '2481534720684964a36d82af89923091',
    '32e0b76d54bc43b7a02e36e931abbdb3',
],
    'words': 'jaguar goat',
    'nested': {
    'id': 151,
    'rand_digit': 3,
    'array': [
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
    'word': 'camel',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
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
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    8,
],
    [
    -1,
],
],
    'two_words': [
    'hippo',
    'lion',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 52,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 152,
    'id_str': [
    '27',
    '16',
    '29',
    '14',
],
    'text_data': '0bdcd4b048324e9b9a352bf8db2a648b',
    'rand_digit': 9,
    'rand_number': 0.25577,
    'rand_signed_int': 4,
    'rand_datetime': '2000-11-01 11:50:19-0800',
    'text_array': [
    '6a92e711dd0949fcbbee253a74752baa',
    '288a3213844f4fb584467f2ff927039a',
],
    'words': 'shark leopard',
    'nested': {
    'id': 152,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ape',
    'bear',
],
    'city': {
    'name': 'Copenhagen',
    'geo': {
    'lat': 55.676097,
    'lon': 12.568337,
},
},
    'rand_tuple': [
    38,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'gorilla',
    'maybe_null': 'wolf',
},
},
    {
    'id': 53,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 153,
    'id_str': [
    '14',
    '22',
    '17',
    '22',
],
    'text_data': '388340ebdcfb4bab8b233c0b234e44e2',
    'rand_digit': 2,
    'rand_number': 0.48886,
    'rand_signed_int': -10,
    'rand_datetime': '2000-08-22T08:06:50.798242+0100',
    'text_array': [
    'd317fc502cf545cfb809445838cb79bd',
    '785743945a514070ae97343bb40f4f3a',
],
    'words': 'kangaroo lobster',
    'nested': {
    'id': 153,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'panda',
    'grasshopper',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': [
    33,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe_null': 'turtle',
},
},
    {
    'id': 54,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 154,
    'id_str': [
    '15',
    '21',
    '29',
],
    'text_data': 'a75a50add61345039e05e00c2a05d596',
    'rand_digit': 8,
    'rand_number': 0.1158,
    'rand_signed_int': 10,
    'rand_datetime': '2000-03-18T14:38:39.961375+10:00',
    'text_array': [
    '854ec1637ed8466fbf420ed40b95544d',
    'a291b420b6ac4e80a8f63c2a9b7c2042',
],
    'words': 'snail shark',
    'nested': {
    'id': 154,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'tiger',
    'fish',
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
    'mixed_type': 7,
},
},
    {
    'id': 55,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 155,
    'id_str': [
    '15',
],
    'text_data': '746ca375eed84d4cbc0093fe7d0e08b5',
    'rand_digit': 5,
    'rand_number': 0.22853,
    'rand_signed_int': -3,
    'rand_datetime': '2000-11-03T19:29:32.026577',
    'text_array': [
    'c68a3502bbc746eca69b0efd9fb3ab93',
    '0295defa51094691966a0b2e321bc26e',
],
    'words': 'butterfly bear',
    'nested': {
    'id': 155,
    'rand_digit': 9,
    'array': [
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
    'word': 'scorpion',
    'number': 10,
},
],
},
    'nested_array': [
    [
    8,
],
    [
    -3,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'turtle',
    'bear',
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
    'mixed_type': 0.20052,
},
},
    {
    'id': 56,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 156,
    'id_str': [
],
    'text_data': '31e88028735640778685a0ea62c8922f',
    'rand_digit': 4,
    'rand_number': 0.81772,
    'rand_signed_int': -8,
    'rand_datetime': '2000-04-20T19:24:17',
    'text_array': [
    'c7471f8826644f55baa8285c787a8865',
    'ead99d2d93ec4338882171212363a670',
],
    'words': 'bear duck',
    'nested': {
    'id': 156,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 7,
},
],
},
    'nested_array': [
    [
    2,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'butterfly',
    'bee',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'mouse',
    'maybe_null': 'octopus',
},
},
    {
    'id': 57,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 157,
    'id_str': [
    '26',
    '24',
    '17',
    '10',
],
    'text_data': '1aedb11c106d4de8b2ba5f24524c0755',
    'rand_digit': 6,
    'rand_number': 0.73006,
    'rand_signed_int': 1,
    'rand_datetime': '2000-08-11',
    'text_array': [
    '49ae7a8f3def4d4aa94ffb78cfd94da6',
    '0e1f37e5930d490f8b05452df55b2a8a',
],
    'words': 'pig koala',
    'nested': {
    'id': 157,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'hyena',
    'number': 1,
},
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
    'word': 'frog',
    'number': 8,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'snail',
    'kangaroo',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'cow',
},
},
    {
    'id': 58,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 158,
    'id_str': [
    '30',
],
    'text_data': '66ccaecb6b1c4392a7f3ecc363688aef',
    'rand_digit': 7,
    'rand_number': 0.92428,
    'rand_signed_int': 6,
    'rand_datetime': '2000-08-26 22:05:47.554357-0100',
    'text_array': [
    'c1f48bba9c5943b794617b8a52d45046',
    'e12a61f7401742aa8673decedd8abbbf',
],
    'words': 'ladybug jaguar',
    'nested': {
    'id': 158,
    'rand_digit': 8,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    [
    -3,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bird',
    'monkey',
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
    'mixed_type': True,
    'maybe_null': None,
},
},
    {
    'id': 59,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 159,
    'id_str': [
    '16',
    '14',
],
    'text_data': '00e8cedd0f4e4db78c869f7305ef0bf8',
    'rand_digit': 2,
    'rand_number': 0.67614,
    'rand_signed_int': -1,
    'rand_datetime': '2000-07-14T09:10:31.221840+0900',
    'text_array': [
    '368cb2d357944dd38f3c251690e756ff',
    '7062ae3a24e34fa3a67b10af65b7bbc6',
],
    'words': 'rhino jaguar',
    'nested': {
    'id': 159,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'sloth',
    'turtle',
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
    'maybe': 'ladybug',
    'maybe_null': 'zebra',
},
},
    {
    'id': 60,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 160,
    'id_str': [
    '16',
],
    'text_data': 'e059ea499f6b456a825a5fc4d94ca597',
    'rand_digit': 3,
    'rand_number': 0.40844,
    'rand_signed_int': 0,
    'rand_datetime': '2000-02-29T22:47:18+1000',
    'text_array': [
    '6440e0ce5e0b4b8bb6a0f2e47d46cf1e',
    '2955560382814e0e975018ad68620336',
],
    'words': 'pig hippo',
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
    'word': 'elephant',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    6,
],
],
    'two_words': [
    'whale',
    'snake',
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
    'mixed_type': 0.32807,
    'maybe': 'spider',
    'maybe_null': 'frog',
},
},
    {
    'id': 61,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 161,
    'id_str': [
    '24',
    '14',
    '23',
    '01',
],
    'text_data': 'ec257e4536f64229bdf2a0fc9ef30c29',
    'rand_digit': 3,
    'rand_number': 0.96859,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-10T21:59:29+0300',
    'text_array': [
    '29a5d004b5364248957cd086c6bc174a',
    'f0ef15d7364244cb9ca53b0f4e4bf35e',
],
    'words': 'cow dog',
    'nested': {
    'id': 161,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'pig',
    'goat',
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
    'mixed_type': 1,
    'maybe': 'butterfly',
},
},
    {
    'id': 62,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 162,
    'id_str': [
    '09',
    '07',
],
    'text_data': '3d3fa2a562b64f2184accb9975dc4ebf',
    'rand_digit': 9,
    'rand_number': 0.24693,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-30',
    'text_array': [
    '170bdebb9d9746359f791c241497fab5',
    '56fd412728c4468db72f17d0691b2a7b',
],
    'words': 'horse octopus',
    'nested': {
    'id': 162,
    'rand_digit': 5,
    'array': [
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 3,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'tiger',
    'rabbit',
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
    'mixed_type': True,
    'maybe_null': None,
},
},
    {
    'id': 63,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 163,
    'id_str': [
    '10',
    '16',
    '09',
    '28',
],
    'text_data': 'cd59a21cc5ca49549b1efc03b9dc71c0',
    'rand_digit': 8,
    'rand_number': 0.52659,
    'rand_signed_int': -8,
    'rand_datetime': '2000-01-17T15:35:49',
    'text_array': [
    '97dafc17d4d64f1189d561220c7620d2',
    '6fa49e7a603640e2b09c634fdc88ea83',
],
    'words': 'fly fish',
    'nested': {
    'id': 163,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 8,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
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
    'mixed_type': None,
    'maybe_null': 'duck',
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
        """测试请求 2 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1153',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': [
    {
    'key': 'nested_array[0][10]',
    'range': {
    'lt': -10.0,
},
},
    {
    'key': 'id_str',
    'match': {
    'any': [
    '30',
    '01',
    '05',
],
},
},
],
},
    'limit': 10,
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
        """测试请求 3 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1094',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': {
    'key': 'maybe',
    'match': {
    'value': 'dolphin',
},
},
},
    'limit': 10,
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
        """测试请求 4 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1105',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must': [
    {
    'key': 'rand_number',
    'range': {
    'gt': 0.22154198863509345,
},
},
],
},
    'limit': 10,
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
        """测试请求 5 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1254',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'min_should': {
    'conditions': [
    {
    'key': 'two_words',
    'match': {
    'except': [
    '18',
    '25',
    '13',
    '29',
    '07',
    '09',
    '26',
    '29',
    '08',
    '26',
],
},
},
    {
    'key': 'rand_number',
    'range': {
    'lt': 0.2990271678737052,
    'gt': 0.9234031284817791,
},
},
],
    'min_count': 1,
},
},
    'limit': 10,
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



    def test_request_6(self):
        """测试请求 6 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1110',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': [
    {
    'key': 'nested.array[].word',
    'match': {
    'value': 'dragonfly',
},
},
],
},
    'limit': 10,
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



    def test_request_7(self):
        """测试请求 7 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1210',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must': {
    'should': [
    {
    'key': 'rand_datetime',
    'range': {
    'lt': '2000-12-07T08:54:56.138433-11:00',
    'gt': '2000-11-23T00:00:00Z',
},
},
],
    'must': [
    {
    'key': 'id_str',
    'match': {
    'value': '26',
},
},
],
},
},
    'limit': 10,
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



    def test_request_8(self):
        """测试请求 8 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1195',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'scorpion',
},
},
],
    'must_not': [
    {
    'key': 'number',
    'range': {
    'lt': 3.0,
},
},
],
},
},
},
},
    'limit': 10,
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



    def test_request_9(self):
        """测试请求 9 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1218',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must': {
    'key': 'city.geo',
    'geo_bounding_box': {
    'top_left': {
    'lon': 40.257568471910076,
    'lat': 51.536919084426415,
},
    'bottom_right': {
    'lon': -132.94752837048122,
    'lat': -14.899293187959842,
},
},
},
},
    'limit': 10,
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



    def test_request_10(self):
        """测试请求 10 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1157',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': [
    {
    'key': 'id_str',
    'match': {
    'any': [
    '03',
    '13',
    '22',
],
},
},
],
    'must': {
    'key': 'nested_array[1][10]',
    'range': {
    'lt': 10.0,
},
},
},
    'limit': 10,
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



    def test_request_11(self):
        """测试请求 11 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1120',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must': {
    'key': 'rand_datetime',
    'range': {
    'gt': '2000-06-05T00:22:51.385641+04:00',
},
},
},
    'limit': 10,
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



    def test_request_12(self):
        """测试请求 12 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1206',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'two_words',
    'match': {
    'except': [
    '09',
    '12',
    '11',
    '17',
    '27',
    '22',
    '02',
    '19',
    '14',
    '29',
],
},
},
    'must': [
    {
    'key': 'nested.array[].word',
    'match': {
    'value': 'octopus',
},
},
],
},
    'limit': 10,
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



    def test_request_13(self):
        """测试请求 13 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1122',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'rand_datetime',
    'range': {
    'gt': '2000-09-20T19:04:14.679659+11:00',
},
},
},
    'limit': 10,
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



    def test_request_14(self):
        """测试请求 14 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1159',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': [
    {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
],
    'must': {
    'is_empty': {
    'key': 'nested.array[].nested_empty',
},
},
},
    'limit': 10,
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



    def test_request_15(self):
        """测试请求 15 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1194',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': [
    {
    'key': 'rand_datetime',
    'range': {
    'lt': '2000-03-08T00:00:00Z',
    'gt': '2000-10-28T11:18:03.198313-04:00',
},
},
],
    'must': [
    {
    'is_null': {
    'key': 'maybe_null',
},
},
],
},
    'limit': 10,
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



    def test_request_16(self):
        """测试请求 16 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1190',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must': {
    'nested': {
    'key': 'nested.array',
    'filter': {
    'must': [
    {
    'key': 'word',
    'match': {
    'value': 'bear',
},
},
],
    'must_not': [
    {
    'key': 'number',
    'range': {
    'lt': 10.0,
},
},
],
},
},
},
},
    'limit': 10,
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



    def test_request_17(self):
        """测试请求 17 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1081',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'is_null': {
    'key': 'maybe_null',
},
},
},
    'limit': 10,
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



    def test_request_18(self):
        """测试请求 18 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1083',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': {
    'is_null': {
    'key': 'maybe_null',
},
},
},
    'limit': 10,
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



    def test_request_19(self):
        """测试请求 19 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1089',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': {
    'key': 'words',
    'match': {
    'text': 'ant',
},
},
},
    'limit': 10,
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



    def test_request_20(self):
        """测试请求 20 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1214',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': [
    {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
],
    'must': {
    'key': 'city.geo',
    'geo_radius': {
    'center': {
    'lon': 30.314129,
    'lat': 59.938732,
},
    'radius': 1714418.5636289343,
},
},
},
    'limit': 10,
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



    def test_request_21(self):
        """测试请求 21 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1098',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': {
    'key': 'nested_array[0][]',
    'range': {
    'lt': -7.0,
},
},
},
    'limit': 10,
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



    def test_request_22(self):
        """测试请求 22 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1100',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': {
    'key': 'id_str',
    'match': {
    'any': [
    '29',
    '29',
    '09',
],
},
},
},
    'limit': 10,
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



    def test_request_23(self):
        """测试请求 23 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1101',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
},
    'limit': 10,
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



    def test_request_24(self):
        """测试请求 24 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1144',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'words',
    'match': {
    'text': 'dog',
},
},
    'must': [
    {
    'key': 'id_str',
    'values_count': {
    'lt': 1,
    'gt': 6,
},
},
],
},
    'limit': 10,
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



    def test_request_25(self):
        """测试请求 25 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1131',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': {
    'key': 'rand_number',
    'range': {
    'lt': 0.17341072443027405,
    'gt': 0.8627057214418157,
},
},
},
    'limit': 10,
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



    def test_request_26(self):
        """测试请求 26 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1201',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
    'must': [
    {
    'key': 'two_words',
    'match': {
    'except': [
    '25',
    '12',
    '13',
    '05',
    '29',
    '14',
    '18',
    '14',
    '28',
    '29',
],
},
},
],
},
    'limit': 10,
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



    def test_request_27(self):
        """测试请求 27 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1101',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': {
    'is_empty': {
    'key': 'nested.array[].nested_empty',
},
},
},
    'limit': 10,
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



    def test_request_28(self):
        """测试请求 28 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1139',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'two_words',
    'match': {
    'except': [
    '29',
    '20',
    '29',
    '10',
    '26',
    '11',
    '19',
    '15',
    '24',
    '02',
],
},
},
},
    'limit': 10,
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



    def test_request_29(self):
        """测试请求 29 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1102',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must_not': {
    'has_id': self.mutator.generate_float_array(dimension=10, normalized=True),
},
},
    'limit': 10,
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



    def test_request_30(self):
        """测试请求 30 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1098',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'should': {
    'key': 'nested_array[10][2]',
    'range': {
    'lt': -9.0,
},
},
},
    'limit': 10,
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



    def test_request_31(self):
        """测试请求 31 - POST http://localhost:6333/collections/congruence_test_collection/points/search"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1075',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'filter': {
    'must': {
    'is_empty': {
    'key': 'maybe',
},
},
},
    'limit': 10,
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



    def test_request_32(self):
        """测试请求 32 - DELETE http://localhost:6333/collections/congruence_test_collection?timeout=60"""
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
    'content-length': '40',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'size': 50,
    'distance': 'Dot',
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_search.test_single_vector')
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
    test = TestSearchtestSingleVector()
    test.run_tests()
