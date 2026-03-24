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
logger = logging.getLogger('vdb_fuzzer.test.test_qdrant_client_test_read_consistency')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_qdrant_client.test_read_consistency"
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


def send_request(content, request_type="PUT", url_path="http://localhost:6333/collections/client_test?timeout=60", custom_headers=None):
    """
    发送请求到目标服务器

    Args:
        content: 请求内容
        request_type: 请求方法，默认为"PUT"
        url_path: URL路径，默认为"http://localhost:6333/collections/client_test?timeout=60"
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



class TestQdrantClienttestReadConsistency:
    """自动生成的VDB模糊测试类 - test_qdrant_client.test_read_consistency"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_qdrant_client.test_read_consistency"
        self.test_count = 9  # 测试方法数量
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
        """测试请求 0 - PUT http://localhost:6333/collections/client_test?timeout=60"""
        logger.info(f"跳过非写请求或无内容请求: PUT http://localhost:6333/collections/client_test?timeout=60")
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/client_test?timeout=60'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '41',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'size': 100,
    'distance': 'Dot',
},
}


        send_request(original_content, method, url_path, headers)
        return True



    def test_request_1(self):
        """测试请求 1 - PUT http://localhost:6333/collections/client_test/points?wait=true"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/client_test/points?wait=true")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/client_test/points?wait=true'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '87560',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 100,
    'id_str': [
    '07',
    '21',
    '25',
    '19',
    '03',
],
    'text_data': '21b559a0c9ec44f891a58c1e9e51c238',
    'rand_digit': 4,
    'rand_number': 0.49241,
    'rand_signed_int': 9,
    'rand_datetime': '2000-08-10T14:44:07.318160-0900',
    'text_array': [
    '88ecd6d51a9449e3844544d8cc32ca8e',
    '77563d261c6346adb5ec3698d57c02ca',
],
    'words': 'sheep horse',
    'nested': {
    'id': 100,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'bear',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'sheep',
    'number': 5,
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
    [
    0,
],
    [
],
],
    'two_words': [
    'cat',
    'dolphin',
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
    'maybe_null': None,
},
},
    {
    'id': 1,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 101,
    'id_str': [
    '12',
    '10',
],
    'text_data': '06ed437f21ec4c6891191b25f93c5d4f',
    'rand_digit': 8,
    'rand_number': 0.21121,
    'rand_signed_int': 5,
    'rand_datetime': '2000-03-24T06:36:40+1000',
    'text_array': [
    '41b064ec1ce847c3b5895f77989fe972',
    'd6e82dab8d384381914718823a6f62b9',
],
    'words': 'lion cow',
    'nested': {
    'id': 101,
    'rand_digit': 1,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
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
    'number': 2,
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
    'cow',
    'bee',
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
    'mixed_type': 4,
    'maybe': 'scorpion',
    'maybe_null': 'sloth',
},
},
    {
    'id': 2,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 102,
    'id_str': [
    '15',
    '17',
    '24',
    '19',
],
    'text_data': 'e0b8ee1cb6664fdbb79d695b468d20da',
    'rand_digit': 9,
    'rand_number': 0.45266,
    'rand_signed_int': 8,
    'rand_datetime': '2000-06-20T08:55:32.878009-06:00',
    'text_array': [
    'c2c022b1852b4c80a397c3560aa2619a',
    '3d34404357c94a29801d493706de55f4',
],
    'words': 'grasshopper whale',
    'nested': {
    'id': 102,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'hippo',
    'ant',
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
    'maybe_null': 'frog',
},
},
    {
    'id': 3,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 103,
    'id_str': [
    '25',
    '17',
    '29',
    '26',
],
    'text_data': '4c02e3a9f08c4ba89a576eac6f8bbf7c',
    'rand_digit': 6,
    'rand_number': 0.48344,
    'rand_signed_int': -1,
    'rand_datetime': '2001-01-21 10:22:03.307756',
    'text_array': [
    '4e33081d253446ec8d6bb5ea8fa95893',
    '661160e75461466684e174bab3b21cc3',
],
    'words': 'fox cow',
    'nested': {
    'id': 103,
    'rand_digit': 5,
    'array': [
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 5,
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
    'word': 'crab',
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
    [
],
],
    'two_words': [
    'elephant',
    'ape',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': 'ape',
},
},
    {
    'id': 4,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 104,
    'id_str': [
    '26',
    '16',
    '21',
],
    'text_data': 'f9cd8e31d0cc4ed297f110d71789681b',
    'rand_digit': 1,
    'rand_number': 0.00462,
    'rand_signed_int': 8,
    'rand_datetime': '2000-05-05',
    'text_array': [
    'e8d8aa62f9e147c2bfedc569f4735686',
    'a865c4adcf274abfad96196018933e2f',
],
    'words': 'monkey octopus',
    'nested': {
    'id': 104,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'camel',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lobster',
    'ape',
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
    'mixed_type': 0,
},
},
    {
    'id': 5,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 105,
    'id_str': [
    '01',
],
    'text_data': '84424b03428d4033b9975a2395784cc1',
    'rand_digit': 3,
    'rand_number': 0.05412,
    'rand_signed_int': 9,
    'rand_datetime': '2000-03-24T05:09:16.935611',
    'text_array': [
    '0667f286dc994e6cab9b72e28280b43f',
    'fef2b89460a146fd9d9944313cf54317',
],
    'words': 'sloth chicken',
    'nested': {
    'id': 105,
    'rand_digit': 7,
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
    'word': 'tiger',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    [
    1,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'camel',
    'bear',
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
    'mixed_type': 4,
    'maybe_null': 'wolf',
},
},
    {
    'id': 6,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 106,
    'id_str': [
    '21',
    '01',
    '06',
    '24',
],
    'text_data': 'ed54de7b09ca4899a8b53b7c9293bfd7',
    'rand_digit': 7,
    'rand_number': 0.68185,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-29T09:51:43.272981',
    'text_array': [
    '8403796006144741a509b7df2860ef4c',
    'ec90670ac51e49aea7205441f15978e5',
],
    'words': 'bird panda',
    'nested': {
    'id': 106,
    'rand_digit': 2,
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
    'hello',
],
    'word': 'cat',
    'number': 10,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,3__',
    'two_words': [
    'wolf',
    'mosquito',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'tiger',
},
},
    {
    'id': 7,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 107,
    'id_str': [
    '07',
    '22',
    '15',
    '21',
    '07',
],
    'text_data': 'cd87e2361fe841818a52ee7d07e91a14',
    'rand_digit': 4,
    'rand_number': 0.44614,
    'rand_signed_int': -8,
    'rand_datetime': '2000-08-03T07:21:52.097346',
    'text_array': [
    '755d1856ebb54e1c84a11bf9870a6272',
    '92eb312518934c9db1e14dab103be4c3',
],
    'words': 'turtle panda',
    'nested': {
    'id': 107,
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
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'squid',
    'scorpion',
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
    'mixed_type': 0.36999,
    'maybe': 'sloth',
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 8,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 108,
    'id_str': [
    '12',
    '27',
    '20',
    '01',
],
    'text_data': '79de4fe8c09940f1a9503dcb73fcd881',
    'rand_digit': 2,
    'rand_number': 0.92966,
    'rand_signed_int': 7,
    'rand_datetime': '2000-08-26T18:21:21.173383-08:00',
    'text_array': [
    '046f0ea483794885b86ec892efb7c231',
    'aac7f8903e274eeaabb3399bce4cf3d9',
],
    'words': 'sloth koala',
    'nested': {
    'id': 108,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    8,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'squid',
    'spider',
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
    'mixed_type': 0.76952,
    'maybe': 'hippo',
    'maybe_null': 'shark',
},
},
    {
    'id': 9,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 109,
    'id_str': [
    '28',
    '24',
    '09',
    '18',
],
    'text_data': 'fac043f68dd24438ac4660699b4add55',
    'rand_digit': 1,
    'rand_number': 0.14148,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-18',
    'text_array': [
    '16727254cb424c9690ce5960c3450389',
    'af48f95c9f7f4cdb9177269aa1ae8e78',
],
    'words': 'hippo dog',
    'nested': {
    'id': 109,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    -5,
],
],
    'two_words': [
    'dolphin',
    'pig',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'horse',
    'maybe_null': None,
},
},
    {
    'id': 10,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 110,
    'id_str': [
    '12',
],
    'text_data': '0e98c300c8ad40008567a3d55eb115e4',
    'rand_digit': 1,
    'rand_number': 0.18755,
    'rand_signed_int': 0,
    'rand_datetime': '2000-05-13 18:27',
    'text_array': [
    '303124ce7488479691e488da34e08814',
    '9e5c554b7a6345c5aa720a09b7ecb334',
],
    'words': 'frog jaguar',
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
    'word': 'bird',
    'number': 8,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,5__',
    'two_words': [
    'duck',
    'grasshopper',
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
    'mixed_type': None,
    'maybe_null': 'spider',
},
},
    {
    'id': 11,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 111,
    'id_str': [
],
    'text_data': '948c37f4be8340bf827ff3a3313337b4',
    'rand_digit': 1,
    'rand_number': 0.65725,
    'rand_signed_int': 7,
    'rand_datetime': '2000-10-14 10:53:22',
    'text_array': [
    '075e14bef05743e28d9f7de0b3ac8833',
    '504f8af2b8754853b3f03720c5c791a6',
],
    'words': 'mouse spider',
    'nested': {
    'id': 111,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'koala',
    'elephant',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'octopus',
},
},
    {
    'id': 12,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 112,
    'id_str': [
    '02',
    '29',
    '18',
],
    'text_data': '31acf25bfbf641509d93d5ff2cee1bca',
    'rand_digit': 6,
    'rand_number': 0.19991,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-22 01:37:36',
    'text_array': [
    '60b125804743448296625ad534ee483a',
    'b82c2fa4816140d7a7f963ffed28fe67',
],
    'words': 'spider duck',
    'nested': {
    'id': 112,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'scorpion',
    'number': 9,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -8,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'snake',
    'hyena',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 13,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 113,
    'id_str': [
    '23',
    '20',
    '04',
    '22',
],
    'text_data': 'cd03e4a817434904adb7d72dfb356fee',
    'rand_digit': 5,
    'rand_number': 0.27363,
    'rand_signed_int': -2,
    'rand_datetime': '2000-10-22T03:01:03+0100',
    'text_array': [
    'a36bd11f6f0a4f8e9084e5efb0df0eab',
    '05ae3ad82e244fff85681ffde3fc2dd9',
],
    'words': 'sheep hippo',
    'nested': {
    'id': 113,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'sloth',
    'number': 10,
},
],
},
    'nested_array': [
    [
    1,
],
],
    'two_words': [
    'camel',
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
    49,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'ant',
},
},
    {
    'id': 14,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 114,
    'id_str': [
    '24',
    '05',
    '27',
],
    'text_data': '8c7a8369c0f846cc978dd264aba0dd1c',
    'rand_digit': 6,
    'rand_number': 0.29966,
    'rand_signed_int': -6,
    'rand_datetime': '2000-07-26T03:39:44.305300-0600',
    'text_array': [
    '4eab5d60c3ce4d109a955a40ceef56ef',
    'c706bd9c8d354610b91686a02c5e51c0',
],
    'words': 'ladybug leopard',
    'nested': {
    'id': 114,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'cheetah',
    'cat',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'tiger',
    'maybe_null': 'crab',
},
},
    {
    'id': 15,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 115,
    'id_str': [
    '05',
    '22',
    '05',
],
    'text_data': 'ec65e604c7e349d7a66a70b8976c96d4',
    'rand_digit': 1,
    'rand_number': 0.99711,
    'rand_signed_int': 7,
    'rand_datetime': '2000-10-25T18:55:46.776527',
    'text_array': [
    '1513ad41cd3a493c91b8e321fb5eed2a',
    '4303817abf82451ba3e80ef9577db1ec',
],
    'words': 'dragonfly frog',
    'nested': {
    'id': 115,
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
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'panda',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bear',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'duck',
    'rabbit',
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
    'id': 16,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 116,
    'id_str': [
    '15',
    '07',
    '05',
],
    'text_data': 'bcd43f1106f048f7a21fdc8e67ddc212',
    'rand_digit': 4,
    'rand_number': 0.65244,
    'rand_signed_int': 0,
    'rand_datetime': '2000-05-18 17:54:31.122132',
    'text_array': [
    '017a3f4691764358b9e8b1b418cf7bdc',
    '6c31cedd40a74132ae19c6f404d3029d',
],
    'words': 'jaguar giraffe',
    'nested': {
    'id': 116,
    'rand_digit': 7,
    'array': [
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
    'word': 'bee',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    1,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'ape',
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
    62,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'lizard',
    'maybe_null': 'snake',
},
},
    {
    'id': 17,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 117,
    'id_str': [
    '19',
],
    'text_data': '46ecc129dd454a609f177e4a85e566aa',
    'rand_digit': 5,
    'rand_number': 0.14148,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-08 01:47:41+0400',
    'text_array': [
    'c6e8cb38601b44379fdb151c0a378651',
    'd188b39f928d4f7caeb2142cbd224a02',
],
    'words': 'gorilla cat',
    'nested': {
    'id': 117,
    'rand_digit': 4,
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
    'word': 'zebra',
    'number': 10,
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
],
},
    'nested_array': [
],
    'two_words': [
    'hippo',
    'panda',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.91635,
    'maybe': 'deer',
    'maybe_null': 'fox',
},
},
    {
    'id': 18,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 118,
    'id_str': [
    '21',
    '29',
    '26',
],
    'text_data': 'c558cd36d4c0426baf341db9f49693f6',
    'rand_digit': 7,
    'rand_number': 0.73256,
    'rand_signed_int': -2,
    'rand_datetime': '2000-04-21T08:50:31.636574-08:00',
    'text_array': [
    '8990c9474a484d24bd27ed9ae232ed35',
    '9193320ff4c248a58240dc3bd60451c6',
],
    'words': 'grasshopper horse',
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
    'word': 'horse',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 5,
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
],
    'word': 'bee',
    'number': 5,
},
],
},
    'nested_array': [
    [
    -7,
],
    [
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'chicken',
    'panda',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': [
    51,
],
    'rand_bool': True,
    'mixed_type': 0.60352,
    'maybe': 'rhino',
    'maybe_null': 'grasshopper',
},
},
    {
    'id': 19,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 119,
    'id_str': [
    '28',
    '14',
    '13',
    '30',
],
    'text_data': '54d836c61b8d4f5fac47bc18f4c8847b',
    'rand_digit': 1,
    'rand_number': 0.34728,
    'rand_signed_int': 3,
    'rand_datetime': '2001-01-02T20:17:48+0300',
    'text_array': [
    'bac0290e0b844d5f9315b8522e4b71e6',
    'e37e3015ad1f4aaf8561c41923444761',
],
    'words': 'gorilla sloth',
    'nested': {
    'id': 119,
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
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
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
    'number': 10,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'octopus',
    'kangaroo',
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
    'mixed_type': 0.24032,
},
},
    {
    'id': 20,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 120,
    'id_str': [
    '04',
    '30',
],
    'text_data': '74ca73a3885548d7a22cfc549ecc219e',
    'rand_digit': 4,
    'rand_number': 0.10876,
    'rand_signed_int': -7,
    'rand_datetime': '2000-09-06T14:42:21.857270',
    'text_array': [
    'f006065be5a64821b86acaa6486160ab',
    '68555c3ee2ba4d68a347abf5db190d51',
],
    'words': 'rhino rhino',
    'nested': {
    'id': 120,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'ant',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'monkey',
    'whale',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': [
    34,
],
    'rand_bool': False,
    'mixed_type': 'cow',
},
},
    {
    'id': 21,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 121,
    'id_str': [
    '19',
    '17',
    '03',
    '13',
],
    'text_data': '3f0cd0d472284ddd84a2438b43a3c8d9',
    'rand_digit': 1,
    'rand_number': 0.33594,
    'rand_signed_int': -6,
    'rand_datetime': '2000-12-17T12:48:13.163467',
    'text_array': [
    'c891b0e5c61e439b8c0bd49eb54da7f7',
    'fc28413ae4df418d863bc7c252f7eb4a',
],
    'words': 'lobster cow',
    'nested': {
    'id': 121,
    'rand_digit': 4,
    'array': [
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
    'word': 'lizard',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 5,
},
],
},
    'nested_array': [
    [
    6,
],
],
    'two_words': [
    'chicken',
    'spider',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': [
    18,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'turtle',
    'maybe_null': 'tiger',
},
},
    {
    'id': 22,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 122,
    'id_str': [
    '12',
    '13',
    '13',
    '05',
],
    'text_data': '7599409bab1f472b9bfc8b126f5da3fe',
    'rand_digit': 5,
    'rand_number': 0.86805,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-14 08:36',
    'text_array': [
    '4db311ed67334a5d95e239436e9077a4',
    '30df2529b5a14abfbd8825b92918eace',
],
    'words': 'shark hyena',
    'nested': {
    'id': 122,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'pig',
    'number': 1,
},
    {
    'nested_empty': None,
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
    'word': 'scorpion',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'dragonfly',
    'chicken',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 'mouse',
    'maybe_null': 'lobster',
},
},
    {
    'id': 23,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 123,
    'id_str': [
    '14',
    '07',
    '12',
    '26',
    '24',
],
    'text_data': 'dce3c310bdd44cdd876e00710890d1bc',
    'rand_digit': 0,
    'rand_number': 0.5176,
    'rand_signed_int': 2,
    'rand_datetime': '2000-02-08T09:31:33',
    'text_array': [
    '3c90ea0ca94a455b92d2d0273d17e0cb',
    'e0fe1aa337d54f248c033cc632f907ae',
],
    'words': 'dog turtle',
    'nested': {
    'id': 123,
    'rand_digit': 1,
    'array': [
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
    'word': 'mosquito',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 8,
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
    'nested_array': '__FLOAT_MULTI_DIM_3,2__',
    'two_words': [
    'kangaroo',
    'bird',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'tiger',
},
},
    {
    'id': 24,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 124,
    'id_str': [
    '22',
    '14',
    '02',
],
    'text_data': 'ae6e530b40a7470ab8a7fea74d0cd9cf',
    'rand_digit': 7,
    'rand_number': 0.06307,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-23T23:51:08-1200',
    'text_array': [
    'f6cd21753ba24ecda8b2d7b1df797ae3',
    'a5a8bdb789b243a08e49309bac0f0f93',
],
    'words': 'snake fox',
    'nested': {
    'id': 124,
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
],
},
    'nested_array': [
    [
    -4,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fish',
    'frog',
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
    'maybe_null': 'rabbit',
},
},
    {
    'id': 25,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 125,
    'id_str': [
    '06',
],
    'text_data': 'b6c02b73ea954113b43ea7784aa1d65a',
    'rand_digit': 3,
    'rand_number': 0.67114,
    'rand_signed_int': -2,
    'rand_datetime': '2000-04-06T00:20:09.953051',
    'text_array': [
    '8fb912144e3648cfa386c588f7eb61ab',
    '82c3d75e9f8947b2a68b334cb36f8037',
],
    'words': 'dolphin fish',
    'nested': {
    'id': 125,
    'rand_digit': 2,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 7,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
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
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    0,
],
],
    'two_words': [
    'zebra',
    'ant',
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
    'mixed_type': 0.47141,
    'maybe_null': None,
},
},
    {
    'id': 26,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 126,
    'id_str': [
    '29',
    '05',
],
    'text_data': '415dd977c9c34e52acbd27781f9723c6',
    'rand_digit': 7,
    'rand_number': 0.30836,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-17 12:46',
    'text_array': [
    'a557da89bb604f9f8797a902c43c0103',
    '841e0494821b490bb875f9edf7141ba7',
],
    'words': 'crab cat',
    'nested': {
    'id': 126,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'whale',
    'sloth',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 6,
    'maybe': 'sheep',
    'maybe_null': None,
},
},
    {
    'id': 27,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 127,
    'id_str': [
    '19',
    '04',
    '22',
],
    'text_data': '380ce15a306b42659b6b720a3a7d8a4d',
    'rand_digit': 7,
    'rand_number': 0.28026,
    'rand_signed_int': -9,
    'rand_datetime': '2000-08-14T10:22:31.911739',
    'text_array': [
    'bc53d575740f43a79a1f8e9a920e418d',
    '68d4b8a85cee42a7801df8d8d4bb2f29',
],
    'words': 'pig squid',
    'nested': {
    'id': 127,
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
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'bear',
    'elephant',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': [
    62,
],
    'rand_bool': True,
    'mixed_type': 0,
    'maybe_null': 'fish',
},
},
    {
    'id': 28,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 128,
    'id_str': [
    '07',
    '08',
    '29',
],
    'text_data': '9ef14f5519494712a7540d49ef92c68c',
    'rand_digit': 7,
    'rand_number': 0.87496,
    'rand_signed_int': -7,
    'rand_datetime': '2000-03-01T11:14:29.406642-0200',
    'text_array': [
    '673a3d639aaf40889933040526af4b58',
    '45b130b715044daab6bafe58ca0ac0fa',
],
    'words': 'duck jaguar',
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
    'word': 'wolf',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 3,
},
    {
    'nested_empty': None,
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
    'word': 'ape',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snake',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'duck',
    'ape',
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
    'mixed_type': True,
    'maybe_null': None,
},
},
    {
    'id': 29,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 129,
    'id_str': [
    '28',
    '13',
    '16',
],
    'text_data': '4919400df2a748c49d9679908ae6e7db',
    'rand_digit': 7,
    'rand_number': 0.81832,
    'rand_signed_int': -2,
    'rand_datetime': '2000-12-10',
    'text_array': [
    '6c5edee12ac94bd9b67c449bd2ba9fe8',
    'cf2a0fbf36b24d208139c617efdcf4a3',
],
    'words': 'hyena cow',
    'nested': {
    'id': 129,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 2,
},
],
},
    'nested_array': [
    [
    4,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bird',
    'hyena',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'cow',
},
},
    {
    'id': 30,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 130,
    'id_str': [
    '11',
    '15',
],
    'text_data': '1917f92802d0432591ce6c466a47cc1d',
    'rand_digit': 0,
    'rand_number': 0.88107,
    'rand_signed_int': 4,
    'rand_datetime': '2000-07-18T15:44:49.941019+0700',
    'text_array': [
    'e1051d0352284d3bb9d447b8464f6f16',
    '9be2665d83e14ac8b96b69ca8d2ec48f',
],
    'words': 'lizard squid',
    'nested': {
    'id': 130,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'dog',
    'grasshopper',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'zebra',
    'maybe_null': 'tiger',
},
},
    {
    'id': 31,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 131,
    'id_str': [
    '13',
    '10',
],
    'text_data': 'c39f2168617a437c89236d7867cc90b5',
    'rand_digit': 8,
    'rand_number': 0.59627,
    'rand_signed_int': -9,
    'rand_datetime': '2000-04-15 15:51',
    'text_array': [
    'e757d58fbd1f43b2b51bb5cc64149ef1',
    '91b0ad96a0e24fd7a1a7236657019605',
],
    'words': 'pig gorilla',
    'nested': {
    'id': 131,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'mosquito',
    'goat',
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
    'mixed_type': 0.43991,
    'maybe_null': 'fox',
},
},
    {
    'id': 32,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 132,
    'id_str': [
    '03',
    '25',
    '05',
],
    'text_data': '35a2623f45214e29a49e514e0e1df8a3',
    'rand_digit': 6,
    'rand_number': 0.14092,
    'rand_signed_int': 0,
    'rand_datetime': '2000-01-17T07:19:46.454597-08:00',
    'text_array': [
    'd71c236b88e94633b2cf3d2236332d43',
    '1095b3ea523a433aa9856aa9d53d6123',
],
    'words': 'monkey ladybug',
    'nested': {
    'id': 132,
    'rand_digit': 8,
    'array': [
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
    'word': 'kangaroo',
    'number': 7,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'gorilla',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'mouse',
    'cheetah',
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
    'mixed_type': 'spider',
    'maybe': 'grasshopper',
},
},
    {
    'id': 33,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 133,
    'id_str': [
    '14',
],
    'text_data': '4e1f07ab999747e8a8c4fdea3027ac44',
    'rand_digit': 0,
    'rand_number': 0.46056,
    'rand_signed_int': 3,
    'rand_datetime': '2000-07-26T08:14:56-1200',
    'text_array': [
    'b8b4e15c7b664ce2ab13951a23b99631',
    'f78ef2a39002416a9d30388139b371a1',
],
    'words': 'lizard bee',
    'nested': {
    'id': 133,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'lion',
    'bird',
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
    'maybe_null': 'lion',
},
},
    {
    'id': 34,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 134,
    'id_str': [
    '26',
    '24',
    '14',
    '28',
],
    'text_data': 'ee47cbc689a34737ae1b9123ec71e480',
    'rand_digit': 1,
    'rand_number': 0.8501,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-08T07:31:32',
    'text_array': [
    '05855d29302b4f1ebcc6c59649935fe5',
    '5bbe78477a0045809c4fe91478439888',
],
    'words': 'spider rhino',
    'nested': {
    'id': 134,
    'rand_digit': 5,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'fish',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'hyena',
    'bee',
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
    'mixed_type': 'jaguar',
    'maybe': 'bird',
    'maybe_null': 'wolf',
},
},
    {
    'id': 35,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 135,
    'id_str': [
    '18',
    '07',
    '27',
    '08',
],
    'text_data': 'a7a3b6af7bf34fd5b496c64d735612a9',
    'rand_digit': 1,
    'rand_number': 0.35602,
    'rand_signed_int': -3,
    'rand_datetime': '2000-01-11 11:19:47.751422+1100',
    'text_array': [
    'a0004b338c8d4da28fd575eca680891b',
    '857ce367a2ca4664aeb67bcc44172bcf',
],
    'words': 'zebra snake',
    'nested': {
    'id': 135,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -3,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'rhino',
    'zebra',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.02326,
    'maybe': 'dragonfly',
    'maybe_null': 'zebra',
},
},
    {
    'id': 36,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 136,
    'id_str': [
    '04',
    '16',
],
    'text_data': '2d97b2cf170f44819befedb41ce5c1f9',
    'rand_digit': 9,
    'rand_number': 0.97954,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-07T23:24:00-0900',
    'text_array': [
    '9a79013594e445ee923a50a9ed3ab1a7',
    'a21c466abdd045f99b267355ef15a6be',
],
    'words': 'kangaroo scorpion',
    'nested': {
    'id': 136,
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
    'word': 'lion',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -5,
],
],
    'two_words': [
    'fish',
    'frog',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'deer',
    'maybe': 'fox',
    'maybe_null': None,
},
},
    {
    'id': 37,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 137,
    'id_str': [
    '06',
    '16',
],
    'text_data': 'e5f219bb45ad4bcb8f594bf82c406c7f',
    'rand_digit': 0,
    'rand_number': 0.57918,
    'rand_signed_int': 8,
    'rand_datetime': '2000-04-14T18:08:23.339892+05:00',
    'text_array': [
    '865ab9e5c24e44229606013b0c7c9596',
    '85f325f7cadf470ba4fd215a771a0a04',
],
    'words': 'camel deer',
    'nested': {
    'id': 137,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'ant',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
    'number': 10,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cat',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'snail',
    'hyena',
],
    'city': {
    'name': 'Athens',
    'geo': {
    'lat': 37.98381,
    'lon': 23.727539,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 9,
    'maybe_null': None,
},
},
    {
    'id': 38,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 138,
    'id_str': [
    '24',
    '24',
    '17',
    '22',
],
    'text_data': '5c9172946aa7471b9108ddf78ffd990b',
    'rand_digit': 2,
    'rand_number': 0.89245,
    'rand_signed_int': 7,
    'rand_datetime': '2000-09-08 21:49:47+0500',
    'text_array': [
    '36d0af6d3c444ee6be27d00ac9bc6697',
    '3ae75d869b404bbba741b2454e86eb45',
],
    'words': 'shark rhino',
    'nested': {
    'id': 138,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 3,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 8,
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
],
},
    'nested_array': [
    [
    -4,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'crab',
    'leopard',
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
    'mixed_type': 3,
    'maybe': 'lobster',
    'maybe_null': 'octopus',
},
},
    {
    'id': 39,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 139,
    'id_str': [
],
    'text_data': '94c28c0ac58549cf9dcab50246eb581a',
    'rand_digit': 9,
    'rand_number': 0.24331,
    'rand_signed_int': 4,
    'rand_datetime': '2000-07-09 08:55:49.455896-1100',
    'text_array': [
    '6126e28f262447f99a6068c0a1836666',
    '2827a1408d3443dd867fa9e7008f8500',
],
    'words': 'fly panda',
    'nested': {
    'id': 139,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'duck',
    'kangaroo',
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
    'mixed_type': 0,
},
},
    {
    'id': 40,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 140,
    'id_str': [
    '26',
    '26',
    '10',
    '27',
],
    'text_data': '1a2f64861371456d8680ae668853a883',
    'rand_digit': 5,
    'rand_number': 0.1126,
    'rand_signed_int': 0,
    'rand_datetime': '2000-12-31 09:26:18-0100',
    'text_array': [
    '88228f9c55324b799204911c951494a1',
    '261b8a6cd77b4b26948d30d0fe44c02d',
],
    'words': 'cheetah scorpion',
    'nested': {
    'id': 140,
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
    [
    1,
],
],
    'two_words': [
    'cat',
    'whale',
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
    'mixed_type': 0,
    'maybe': 'lobster',
},
},
    {
    'id': 41,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 141,
    'id_str': [
    '07',
    '16',
],
    'text_data': 'fb7a4c9c6e70446fa9192f7071334ce9',
    'rand_digit': 4,
    'rand_number': 0.06647,
    'rand_signed_int': -3,
    'rand_datetime': '2000-05-08 16:14:03',
    'text_array': [
    'e6f9427397a94f2ab99b5469cd490abf',
    '7915ddec845547928d0464e37e7d6f40',
],
    'words': 'dog fox',
    'nested': {
    'id': 141,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'lion',
    'octopus',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': [
    43,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'snake',
    'maybe_null': 'rabbit',
},
},
    {
    'id': 42,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 142,
    'id_str': [
    '27',
    '30',
    '30',
    '09',
    '10',
],
    'text_data': '802dad515df24ce5892a0fb305b399a1',
    'rand_digit': 9,
    'rand_number': 0.04962,
    'rand_signed_int': -2,
    'rand_datetime': '2000-01-23T22:35:21.363842+0000',
    'text_array': [
    '8d355421b5c54498a57682f0d73ca894',
    '4f2df2a9059c40f0990d4f173f706095',
],
    'words': 'snail leopard',
    'nested': {
    'id': 142,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 8,
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
    -2,
],
],
    'two_words': [
    'ladybug',
    'bird',
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
    'maybe_null': 'cheetah',
},
},
    {
    'id': 43,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 143,
    'id_str': [
    '11',
    '20',
    '11',
    '23',
],
    'text_data': 'f672cda5a5744a5d8a45a9a5ab851d6a',
    'rand_digit': 0,
    'rand_number': 0.54259,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-15T10:51:53.662540+0500',
    'text_array': [
    '79c5f1255cc84aa38801d81a2b61f86f',
    'c31ba8a1169c4a79bf3860833390e588',
],
    'words': 'hyena cheetah',
    'nested': {
    'id': 143,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'bear',
    'shark',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'rabbit',
    'maybe_null': None,
},
},
    {
    'id': 44,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 144,
    'id_str': [
    '22',
    '25',
    '20',
    '04',
    '12',
],
    'text_data': '47d1a9657c734e64a28e3f95b3675bdf',
    'rand_digit': 6,
    'rand_number': 0.2632,
    'rand_signed_int': 2,
    'rand_datetime': '2000-03-12T09:11:08.092863',
    'text_array': [
    'd9a2bd7e6fa541d588104c3d1f76a669',
    'e22701ba36e9437b9409c2b3f8881fbe',
],
    'words': 'hippo hippo',
    'nested': {
    'id': 144,
    'rand_digit': 2,
    'array': [
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
],
},
    'nested_array': [
],
    'two_words': [
    'sloth',
    'horse',
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
    'maybe_null': None,
},
},
    {
    'id': 45,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 145,
    'id_str': [
],
    'text_data': '3af4a1cf6df74156a6cc77bee443a5af',
    'rand_digit': 9,
    'rand_number': 0.05264,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-07T16:23:32+1000',
    'text_array': [
    'e8a28b90cd3743be882254ece0b2acee',
    '3a47f675c02c45b0b0bf0db9991f76d4',
],
    'words': 'goat rhino',
    'nested': {
    'id': 145,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 7,
},
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
],
    'word': 'snail',
    'number': 3,
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dog',
    'turtle',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'tiger',
},
},
    {
    'id': 46,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 146,
    'id_str': [
    '20',
    '23',
    '09',
],
    'text_data': '727c1fc19209461b9d3393dde7155c9c',
    'rand_digit': 0,
    'rand_number': 0.14325,
    'rand_signed_int': -3,
    'rand_datetime': '2000-12-18 11:53:39',
    'text_array': [
    '9c69df7ca51c40d0b23431b7bc3b88d0',
    '6fb075e40e0b4663b15b8821bbc79865',
],
    'words': 'snail ladybug',
    'nested': {
    'id': 146,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lion',
    'number': 8,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 4,
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
    'butterfly',
    'sloth',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 9,
    'maybe': 'bee',
    'maybe_null': None,
},
},
    {
    'id': 47,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 147,
    'id_str': [
    '14',
    '24',
    '23',
    '26',
],
    'text_data': 'b908d20fa41447dda60761bc1ad83186',
    'rand_digit': 3,
    'rand_number': 0.37212,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-08 20:07:35.029238',
    'text_array': [
    'a901de5d7d494ffc8065d61110ae3144',
    '45cf5fb3946c4cd08cb297fea21bd871',
],
    'words': 'dog mouse',
    'nested': {
    'id': 147,
    'rand_digit': 9,
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
    'word': 'panda',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    10,
],
    [
],
],
    'two_words': [
    'whale',
    'rabbit',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'turtle',
},
},
    {
    'id': 48,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 148,
    'id_str': [
    '08',
    '01',
    '20',
    '05',
    '13',
],
    'text_data': 'eec69ff79180414ba8619d2cd7c618fe',
    'rand_digit': 8,
    'rand_number': 0.99001,
    'rand_signed_int': 3,
    'rand_datetime': '2000-05-08T10:08:56.304957',
    'text_array': [
    '7dab671a7c0d406cb4e6d842632f1138',
    'e86792d3c7d14fefb8d7972ac7d57eb7',
],
    'words': 'sloth horse',
    'nested': {
    'id': 148,
    'rand_digit': 2,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'bear',
    'elephant',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': [
    25,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'spider',
    'maybe_null': 'snake',
},
},
    {
    'id': 49,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 149,
    'id_str': [
    '06',
    '03',
    '13',
    '24',
    '20',
],
    'text_data': '9281b423541842ed83d3fbd817aba72f',
    'rand_digit': 1,
    'rand_number': 0.1137,
    'rand_signed_int': 9,
    'rand_datetime': '2000-03-10 00:02:51.525640',
    'text_array': [
    '440a7f68d24741abb95465be0dfff1cb',
    'df61e33eccb348f1845f9f8b62a9577a',
],
    'words': 'bird dog',
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
    'word': 'pig',
    'number': 3,
},
],
},
    'nested_array': [
    [
    1,
],
    [
    6,
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'kangaroo',
    'hyena',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 50,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 150,
    'id_str': [
    '06',
    '01',
    '25',
],
    'text_data': '0d84f78c14344fd6a5185f6fb0d72e22',
    'rand_digit': 5,
    'rand_number': 0.41632,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-09 15:20:43.720234',
    'text_array': [
    'd5eb6b1ec0fa45138803a7938e379031',
    '8a35445d5fd44c0c9f840dc5494f3684',
],
    'words': 'monkey mouse',
    'nested': {
    'id': 150,
    'rand_digit': 2,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    [
    5,
],
],
    'two_words': [
    'ant',
    'wolf',
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
    'mixed_type': 0.5374,
    'maybe_null': 'dolphin',
},
},
    {
    'id': 51,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 151,
    'id_str': [
    '01',
    '22',
    '15',
    '24',
    '08',
],
    'text_data': '714b948ba3724cb3bd37f42ace8e4712',
    'rand_digit': 7,
    'rand_number': 0.9314,
    'rand_signed_int': 5,
    'rand_datetime': '2000-06-15T14:13:37.398588-09:00',
    'text_array': [
    '703ddc92bf88443fa65f9b1d88a72134',
    '1588c1a4d7af4e6786c945b0a637a17f',
],
    'words': 'spider monkey',
    'nested': {
    'id': 151,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    9,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'gorilla',
    'goat',
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
    'mixed_type': 'octopus',
},
},
    {
    'id': 52,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 152,
    'id_str': [
    '06',
],
    'text_data': 'a68cfbe6187e4a8fbf25ea5cb34b5f65',
    'rand_digit': 2,
    'rand_number': 0.71339,
    'rand_signed_int': -2,
    'rand_datetime': '2001-01-19 03:05:47+0600',
    'text_array': [
    '85e74846eb3d4a4dbd1d20fc063d4a83',
    'ed54756638d9445e987991504c9b26dd',
],
    'words': 'goat lion',
    'nested': {
    'id': 152,
    'rand_digit': 2,
    'array': [
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    3,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'butterfly',
    'bear',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'koala',
    'maybe_null': 'hyena',
},
},
    {
    'id': 53,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 153,
    'id_str': [
    '28',
    '26',
],
    'text_data': '5db6489665574958b77ad17efb21d522',
    'rand_digit': 0,
    'rand_number': 0.27491,
    'rand_signed_int': -10,
    'rand_datetime': '2000-10-08T05:28:51',
    'text_array': [
    '8953ba0e133f4f3f930894ece79338c4',
    'b2a3b542a36742c08c8bba0c15fd83fd',
],
    'words': 'crab duck',
    'nested': {
    'id': 153,
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
    'word': 'turtle',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    0,
],
],
    'two_words': [
    'dragonfly',
    'fox',
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
    'mixed_type': 7,
    'maybe': 'fish',
},
},
    {
    'id': 54,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 154,
    'id_str': [
],
    'text_data': '48fd678a001846aebe34b07104677298',
    'rand_digit': 1,
    'rand_number': 0.89579,
    'rand_signed_int': 5,
    'rand_datetime': '2000-08-22T10:45:46-0100',
    'text_array': [
    '9d3f891d49d84e5bbf7223cf947ab37e',
    '6274a31f3fa94ebeaa2c8060d520708d',
],
    'words': 'camel ant',
    'nested': {
    'id': 154,
    'rand_digit': 6,
    'array': [
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
    'hello',
],
    'word': 'pig',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 5,
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
    'word': 'sloth',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'panda',
    'mosquito',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'horse',
},
},
    {
    'id': 55,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 155,
    'id_str': [
    '11',
    '16',
    '15',
    '19',
],
    'text_data': '3a3ba01dbe4847d196fb3c8ed6916ce1',
    'rand_digit': 1,
    'rand_number': 0.38071,
    'rand_signed_int': 3,
    'rand_datetime': '2000-02-18T00:22:53-0600',
    'text_array': [
    'f9e7a08c86eb40fc876b9f40819bafe2',
    '960c9b44a51e4e308e9875571eacc842',
],
    'words': 'ape jaguar',
    'nested': {
    'id': 155,
    'rand_digit': 1,
    'array': [
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
    'word': 'fly',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'scorpion',
    'panda',
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
    'maybe_null': 'zebra',
},
},
    {
    'id': 56,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 156,
    'id_str': [
    '10',
    '12',
    '12',
    '19',
],
    'text_data': 'e4efe33751254c8cbbab88a679944298',
    'rand_digit': 0,
    'rand_number': 0.94504,
    'rand_signed_int': 6,
    'rand_datetime': '2000-08-15 11:47:22.254306-0800',
    'text_array': [
    '92f657d232564743b58a97e22a629a93',
    'b2ab30dc9b8146c9b1fffe947b7e05f6',
],
    'words': 'goat snake',
    'nested': {
    'id': 156,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bird',
    'number': 1,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fly',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'kangaroo',
    'leopard',
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
    'mixed_type': 0.75951,
    'maybe_null': 'snail',
},
},
    {
    'id': 57,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 157,
    'id_str': [
    '25',
    '04',
],
    'text_data': '9bfb511e78e94f3cbbc7122df8f0af97',
    'rand_digit': 8,
    'rand_number': 0.19369,
    'rand_signed_int': 1,
    'rand_datetime': '2000-07-03 19:18:40',
    'text_array': [
    'aa4c3fa3a91140e380c16379115a7625',
    '1888080105954f53a47fb6f7f1127bc4',
],
    'words': 'squid monkey',
    'nested': {
    'id': 157,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ant',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 1,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_3,2__',
    'two_words': [
    'fox',
    'cow',
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
    'mixed_type': 6,
    'maybe_null': 'duck',
},
},
    {
    'id': 58,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 158,
    'id_str': [
    '20',
    '02',
    '27',
],
    'text_data': 'd915016869dd41cd8846b4db32b9f108',
    'rand_digit': 7,
    'rand_number': 0.65108,
    'rand_signed_int': 1,
    'rand_datetime': '2000-07-29 15:22:22.012310+0100',
    'text_array': [
    'aa49bf0dd0f34eefa31fe9200cf7b3e4',
    '8dac9e0f28e74483b7c6deaf9148fec0',
],
    'words': 'shark lobster',
    'nested': {
    'id': 158,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'hyena',
    'snake',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 59,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 159,
    'id_str': [
    '03',
    '04',
],
    'text_data': 'b65d52801b9e4d75bc568e72db730e29',
    'rand_digit': 6,
    'rand_number': 0.18388,
    'rand_signed_int': -7,
    'rand_datetime': '2000-11-08 20:29',
    'text_array': [
    '6740f33259434336b330f89a2255e507',
    '780e2e783d744e57b586df5ec4836228',
],
    'words': 'rabbit leopard',
    'nested': {
    'id': 159,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 6,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 2,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cheetah',
    'fish',
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
    'maybe': 'frog',
    'maybe_null': 'deer',
},
},
    {
    'id': 60,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 160,
    'id_str': [
    '05',
    '24',
    '06',
    '03',
    '13',
],
    'text_data': '1a6813f337d747779e574a98fe675b24',
    'rand_digit': 3,
    'rand_number': 0.69112,
    'rand_signed_int': 2,
    'rand_datetime': '2000-08-05 00:04:42.485574-1100',
    'text_array': [
    '4b834c534f9c48fc82403abfd5aaeb7a',
    '0c8ae5c0e4e84672bf247797cd49cc75',
],
    'words': 'cheetah sloth',
    'nested': {
    'id': 160,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'turtle',
    'bee',
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
    'mixed_type': True,
},
},
    {
    'id': 61,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 161,
    'id_str': [
    '21',
    '01',
    '04',
    '07',
    '27',
],
    'text_data': '9fe334f6357d4d498f409c35505f9375',
    'rand_digit': 9,
    'rand_number': 0.38995,
    'rand_signed_int': -6,
    'rand_datetime': '2000-09-04T07:29:56.907721',
    'text_array': [
    'e8514aa34ba5485494f43622c693f378',
    '9a7306c6eddb45109766c6112afcba7e',
],
    'words': 'elephant cat',
    'nested': {
    'id': 161,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 10,
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
    'hello',
],
    'word': 'snail',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'mosquito',
    'spider',
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
    'mixed_type': 8,
    'maybe_null': None,
},
},
    {
    'id': 62,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 162,
    'id_str': [
    '20',
    '28',
    '04',
    '07',
],
    'text_data': '016c38ec5c9c46249d5007780a4260ce',
    'rand_digit': 7,
    'rand_number': 0.88618,
    'rand_signed_int': -8,
    'rand_datetime': '2000-09-17 11:43',
    'text_array': [
    'a61aee370ddc4d21aed80f0e328ad1b8',
    '4ba44e8c02844373998e51ad56d49212',
],
    'words': 'hyena hyena',
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
    'word': 'cow',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 7,
},
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
    'word': 'dolphin',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ant',
    'bird',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'spider',
    'maybe_null': 'bee',
},
},
    {
    'id': 63,
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'payload': {
    'id': 163,
    'id_str': [
    '06',
],
    'text_data': 'cbee2fd0bcf74b828114b4bfd407af74',
    'rand_digit': 4,
    'rand_number': 0.90406,
    'rand_signed_int': -7,
    'rand_datetime': '2000-06-12 01:52:11.474992+0400',
    'text_array': [
    'd4ada9e9f09941f2a7599b9f312b5938',
    '20eff710c1e04adfb59371cc9d38e96f',
],
    'words': 'ladybug lobster',
    'nested': {
    'id': 163,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'octopus',
    'dolphin',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'scorpion',
    'maybe_null': 'koala',
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
        """测试请求 2 - POST http://localhost:6333/collections/client_test/points/search?consistency=majority"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/client_test/points/search?consistency=majority")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/client_test/points/search?consistency=majority'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '649',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'limit': 5,
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
        """测试请求 3 - POST http://localhost:6333/collections/client_test/points/search?consistency=2"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/client_test/points/search?consistency=2")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/client_test/points/search?consistency=2'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '649',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'limit': 5,
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
        """测试请求 4 - POST http://localhost:6333/collections/client_test/points/search/batch"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/client_test/points/search/batch")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/client_test/points/search/batch'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '624',
}
        
        # 原始请求内容
        original_content = {
    'searches': [
    {
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'limit': 5,
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



    def test_request_5(self):
        """测试请求 5 - POST http://localhost:6333/collections/client_test/points/search/batch?consistency=majority"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/client_test/points/search/batch?consistency=majority")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/client_test/points/search/batch?consistency=majority'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '624',
}
        
        # 原始请求内容
        original_content = {
    'searches': [
    {
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'limit': 5,
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



    def test_request_6(self):
        """测试请求 6 - POST http://localhost:6333/collections/client_test/points/search/batch?consistency=2"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/client_test/points/search/batch?consistency=2")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/client_test/points/search/batch?consistency=2'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '624',
}
        
        # 原始请求内容
        original_content = {
    'searches': [
    {
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'limit': 5,
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



    def test_request_7(self):
        """测试请求 7 - POST http://localhost:6333/collections/client_test/points/search/groups?consistency=majority"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/client_test/points/search/groups?consistency=majority")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/client_test/points/search/groups?consistency=majority'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '682',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=100, normalized=True),
    'with_payload': True,
    'with_vector': False,
    'group_by': 'word',
    'group_size': 1,
    'limit': 5,
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
        """测试请求 8 - DELETE http://localhost:6333/collections/client_test?timeout=60"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://localhost:6333/collections/client_test?timeout=60")
        method = 'DELETE'
        url_path = 'http://localhost:6333/collections/client_test?timeout=60'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '41',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'size': 100,
    'distance': 'Dot',
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_qdrant_client.test_read_consistency')
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
    test = TestQdrantClienttestReadConsistency()
    test.run_tests()
