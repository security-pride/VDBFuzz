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
logger = logging.getLogger('vdb_fuzzer.test.test_group_search_test_group_search_types')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_group_search.test_group_search_types"
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



class TestGroupSearchtestGroupSearchTypes:
    """自动生成的VDB模糊测试类 - test_group_search.test_group_search_types"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_group_search.test_group_search_types"
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
    'content-length': '43',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'size': 50,
    'distance': 'Euclid',
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
    'content-length': '68486',
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
    '14',
    '07',
],
    'text_data': 'e7712f24840847199706ae47eea29b55',
    'rand_digit': 0,
    'rand_number': 0.96432,
    'rand_signed_int': 2,
    'rand_datetime': '2001-01-19T20:33:17.538900',
    'text_array': [
    'e4b1c96fbfa24892a9ef59f669798013',
    '40654a3cb27f4dbaa6b4a2432e8c6e27',
],
    'words': 'kangaroo giraffe',
    'nested': {
    'id': 100,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'cat',
    'duck',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': [
    25,
],
    'rand_bool': True,
    'mixed_type': 5,
    'maybe_null': 'tiger',
},
},
    {
    'id': 1,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 101,
    'id_str': [
    '30',
],
    'text_data': '62e60220d2664571b761adb4e0d37bc9',
    'rand_digit': 7,
    'rand_number': 0.17379,
    'rand_signed_int': 1,
    'rand_datetime': '2000-07-09T22:59:15',
    'text_array': [
    '2703036a33214bf0b43a8e270ed1a080',
    '954f6742925148988ec3053c5730f127',
],
    'words': 'jaguar camel',
    'nested': {
    'id': 101,
    'rand_digit': 8,
    'array': [
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
    'hyena',
    'zebra',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.82866,
    'maybe_null': 'dolphin',
},
},
    {
    'id': 2,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 102,
    'id_str': [
    '24',
    '02',
    '07',
    '04',
    '11',
],
    'text_data': 'a292e21e1bae476c8c842cc83815a09e',
    'rand_digit': 0,
    'rand_number': 0.1934,
    'rand_signed_int': -10,
    'rand_datetime': '2000-10-14T02:18:27.424229',
    'text_array': [
    '27a74e4db5f341e2a78916db9da48691',
    'de4e3ee25c574274a5765464464e4087',
],
    'words': 'sheep koala',
    'nested': {
    'id': 102,
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
],
},
    'nested_array': [
    [
    2,
],
    [
    -4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'fox',
    'giraffe',
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
    'mixed_type': True,
    'maybe_null': None,
},
},
    {
    'id': 3,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 103,
    'id_str': [
    '07',
],
    'text_data': 'a1f0962536fa4788afa1e8938a2fc777',
    'rand_digit': 2,
    'rand_number': 0.14414,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-13T10:33:40+0500',
    'text_array': [
    'f912f9f294c2414a9b8dc4f7a6603652',
    '24f9b5f04ed34690a0c6aebcf29752c9',
],
    'words': 'grasshopper sloth',
    'nested': {
    'id': 103,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'zebra',
    'jaguar',
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
    'mixed_type': 1,
},
},
    {
    'id': 4,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 104,
    'id_str': [
    '07',
    '23',
    '10',
    '29',
    '25',
],
    'text_data': 'd59e5cd88f844a97ab83be491735abe6',
    'rand_digit': 9,
    'rand_number': 0.84361,
    'rand_signed_int': 4,
    'rand_datetime': '2000-12-29T13:24:03.978717+0500',
    'text_array': [
    '348fbfd4b3f84a789d0c6b105d6fac69',
    '9dcdecc7e322435082952b1dfabc35d5',
],
    'words': 'rhino fly',
    'nested': {
    'id': 104,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    [
    6,
],
],
    'two_words': [
    'fish',
    'cow',
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
    'mixed_type': None,
    'maybe_null': 'spider',
},
},
    {
    'id': 5,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 105,
    'id_str': [
    '02',
    '19',
    '10',
],
    'text_data': '130fb8cbe5b94272a221514524b2f327',
    'rand_digit': 9,
    'rand_number': 0.5772,
    'rand_signed_int': 4,
    'rand_datetime': '2000-02-09 08:00:53',
    'text_array': [
    '8b4971c767184796bd284a2d175a582f',
    '74ce80dcad6b42a787927ad27e6e8313',
],
    'words': 'octopus ant',
    'nested': {
    'id': 105,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
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
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'snake',
    'rhino',
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
    'mixed_type': 0.89185,
    'maybe': 'hyena',
    'maybe_null': 'frog',
},
},
    {
    'id': 6,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 106,
    'id_str': [
    '30',
    '30',
    '20',
    '21',
    '01',
],
    'text_data': '9cddc95dcad04761bd33efb5d5d01682',
    'rand_digit': 4,
    'rand_number': 0.06661,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-19T15:49:38.822956-0400',
    'text_array': [
    '572e4277f07e455fb179d6d6036aed1b',
    'db4123e7f0ce4e61bd670321b3c0e9ad',
],
    'words': 'shark gorilla',
    'nested': {
    'id': 106,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'cow',
    'monkey',
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
    'mixed_type': 'butterfly',
    'maybe': 'wolf',
    'maybe_null': 'snake',
},
},
    {
    'id': 7,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 107,
    'id_str': [
    '05',
],
    'text_data': 'c12f7ea50753407a93c5451b4e9886d3',
    'rand_digit': 9,
    'rand_number': 0.99219,
    'rand_signed_int': 6,
    'rand_datetime': '2001-01-27 22:26:01',
    'text_array': [
    '7b038b3a6e4c468b9257f71edbbe47ec',
    'c285d6f953da41fcba8a4f1f4b655056',
],
    'words': 'kangaroo zebra',
    'nested': {
    'id': 107,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snail',
    'number': 1,
},
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'tiger',
    'lizard',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'deer',
    'maybe_null': 'rabbit',
},
},
    {
    'id': 8,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 108,
    'id_str': [
    '15',
    '22',
    '01',
    '01',
],
    'text_data': 'ad3d29e7e3a048b0bd25c2cb47e87b36',
    'rand_digit': 1,
    'rand_number': 0.87463,
    'rand_signed_int': -10,
    'rand_datetime': '2000-12-09T23:00:50.527931',
    'text_array': [
    '355191f75e2142d79a36c3a2b946d47c',
    '94d07423da6b400eae83e2f37beb08d3',
],
    'words': 'cheetah spider',
    'nested': {
    'id': 108,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'goat',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 4,
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
    'word': 'pig',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'tiger',
    'sloth',
],
    'city': {
    'name': 'Frankfurt',
    'geo': {
    'lat': 50.110922,
    'lon': 8.682127,
},
},
    'rand_tuple': [
    63,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'rhino',
    'maybe_null': 'mosquito',
},
},
    {
    'id': 9,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 109,
    'id_str': [
    '23',
],
    'text_data': 'a317b1f6efef456a9dcd43683bdf1b83',
    'rand_digit': 6,
    'rand_number': 0.16338,
    'rand_signed_int': -4,
    'rand_datetime': '2000-05-02 08:42:46.223670',
    'text_array': [
    'c22e999fd5514c2d9a2c87d3ce81c56f',
    '69d06dc5a9fc4cb79db898203d2ba038',
],
    'words': 'elephant dolphin',
    'nested': {
    'id': 109,
    'rand_digit': 7,
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
    'hello',
],
    'word': 'fly',
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
],
    'two_words': [
    'zebra',
    'bear',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': [
    80,
],
    'rand_bool': False,
    'mixed_type': None,
},
},
    {
    'id': 10,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 110,
    'id_str': [
    '14',
    '16',
    '19',
],
    'text_data': '943933b5832b4fe2ab23f5a92fd275cf',
    'rand_digit': 9,
    'rand_number': 0.25965,
    'rand_signed_int': 4,
    'rand_datetime': '2000-10-01T19:24:57',
    'text_array': [
    'b464e9056ca14a1b805bdb14c79a5b37',
    'c2feffbb0f0a44e3a9107f9cd5fb7078',
],
    'words': 'frog fish',
    'nested': {
    'id': 110,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 9,
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
    'word': 'snail',
    'number': 3,
},
],
},
    'nested_array': [
    [
    -1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'grasshopper',
    'frog',
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
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': 11,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 111,
    'id_str': [
    '15',
],
    'text_data': '8cc766af1bb7426195987d7168a5bed7',
    'rand_digit': 3,
    'rand_number': 0.18524,
    'rand_signed_int': -10,
    'rand_datetime': '2000-11-04 19:46:34-1100',
    'text_array': [
    'e79b333e532441cc8d1186882a07f719',
    '7358c623cecd4225b8b799cd9ca9003f',
],
    'words': 'dolphin fly',
    'nested': {
    'id': 111,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 2,
},
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
    'elephant',
    'sloth',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': [
    27,
],
    'rand_bool': False,
    'mixed_type': 'cheetah',
    'maybe': 'gorilla',
    'maybe_null': 'hyena',
},
},
    {
    'id': 12,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 112,
    'id_str': [
],
    'text_data': '62f94e2e7e80450992f1e253c0789d45',
    'rand_digit': 6,
    'rand_number': 0.90428,
    'rand_signed_int': 2,
    'rand_datetime': '2000-01-20T17:32:19.184412',
    'text_array': [
    '78556110b1d9464a9375b1747820617b',
    '328c862690c448f09f1410597ec43b86',
],
    'words': 'cow bird',
    'nested': {
    'id': 112,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ant',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'mouse',
    'wolf',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'octopus',
},
},
    {
    'id': 13,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 113,
    'id_str': [
    '29',
],
    'text_data': 'b9afbbba1e4349f28073ab06a32c25cf',
    'rand_digit': 4,
    'rand_number': 0.19609,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-24 23:19',
    'text_array': [
    'c9f0d2ea179e4ecf91e4e278c84e5521',
    '133c1f916907465fbd612068b88f633e',
],
    'words': 'octopus cheetah',
    'nested': {
    'id': 113,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 5,
},
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
],
    'two_words': [
    'bee',
    'fly',
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
    'mixed_type': 0,
    'maybe': 'squid',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 14,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 114,
    'id_str': [
    '21',
    '02',
],
    'text_data': '922f788f59a34ab39adc59f208f67878',
    'rand_digit': 9,
    'rand_number': 0.75897,
    'rand_signed_int': 1,
    'rand_datetime': '2000-03-17 05:52:12-1100',
    'text_array': [
    'c60c7c3ec5e64446852c8eaa86c596ef',
    '45b5c3d848c849658e8468d6c9ead359',
],
    'words': 'cheetah cheetah',
    'nested': {
    'id': 114,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 3,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lizard',
    'shark',
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
    'mixed_type': None,
    'maybe_null': 'fly',
},
},
    {
    'id': 15,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 115,
    'id_str': [
    '03',
    '05',
    '15',
    '25',
],
    'text_data': 'bb2af820846444b794f27ed34d8274dc',
    'rand_digit': 5,
    'rand_number': 0.65063,
    'rand_signed_int': -9,
    'rand_datetime': '2000-05-10T03:38:36+0800',
    'text_array': [
    'e2fe96a14d824e25a350d3dec89dee80',
    'a8bd827ec1654ba383116b927fd9a37a',
],
    'words': 'cheetah wolf',
    'nested': {
    'id': 115,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 9,
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
    'word': 'fox',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'sheep',
    'shark',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': [
    16,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'pig',
    'maybe_null': 'bee',
},
},
    {
    'id': 16,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 116,
    'id_str': [
    '24',
    '19',
    '13',
],
    'text_data': '8f9233a295e84bb08dd0b70d91574313',
    'rand_digit': 1,
    'rand_number': 0.61165,
    'rand_signed_int': 7,
    'rand_datetime': '2000-10-04 20:23:11.685023+0300',
    'text_array': [
    '0c633e23e00448c8b05391485a178765',
    '2355a231bf58455ca459ab6d9556687c',
],
    'words': 'giraffe pig',
    'nested': {
    'id': 116,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'chicken',
    'turtle',
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
    'mixed_type': False,
    'maybe_null': 'koala',
},
},
    {
    'id': 17,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 117,
    'id_str': [
],
    'text_data': '1a6876cc41d54e12949e0cff926a6d91',
    'rand_digit': 3,
    'rand_number': 0.17487,
    'rand_signed_int': -7,
    'rand_datetime': '2000-07-11T13:57:34.322155',
    'text_array': [
    'b3bcec41cc9349cc92e9da8ea84f0da2',
    '49e4da8f7da9479797f8ac43fb676355',
],
    'words': 'cow scorpion',
    'nested': {
    'id': 117,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'snake',
    'wolf',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
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
    'id': 18,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 118,
    'id_str': [
],
    'text_data': 'c7a041d2a2cf41ecbe0d208819b81b94',
    'rand_digit': 7,
    'rand_number': 0.1841,
    'rand_signed_int': 9,
    'rand_datetime': '2000-01-17T18:57:56.992076',
    'text_array': [
    'b208ff9bfb8a4c96a1a3c03ede740ff8',
    '5ebb7471aef748439dd4d4b7ff1da7b8',
],
    'words': 'tiger dog',
    'nested': {
    'id': 118,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'zebra',
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'chicken',
    'ant',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'cat',
},
},
    {
    'id': 19,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 119,
    'id_str': [
    '14',
    '01',
    '24',
    '06',
],
    'text_data': '5e94fbd666724de7951ee3808d5258a4',
    'rand_digit': 2,
    'rand_number': 0.42849,
    'rand_signed_int': -2,
    'rand_datetime': '2000-04-09T03:30:50.933073',
    'text_array': [
    '33b8623352164d78a6156919d97389d4',
    'b8fcc82f57cf4f899c085d722929822c',
],
    'words': 'rhino hyena',
    'nested': {
    'id': 119,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ape',
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
    'number': 10,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 3,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,3__',
    'two_words': [
    'elephant',
    'goat',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 6,
    'maybe': 'monkey',
    'maybe_null': 'jaguar',
},
},
    {
    'id': 20,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 120,
    'id_str': [
    '21',
    '22',
    '08',
    '30',
],
    'text_data': '840fa393a44841ea9c397c38726ec645',
    'rand_digit': 0,
    'rand_number': 0.77499,
    'rand_signed_int': -4,
    'rand_datetime': '2000-03-17T07:31:07+1100',
    'text_array': [
    'fabdc5fbe478466c91f258b1a32c1e61',
    '783b3bf5ebbc4d739873c3ec5cac4507',
],
    'words': 'gorilla hyena',
    'nested': {
    'id': 120,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
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
    'hello',
],
    'word': 'monkey',
    'number': 2,
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
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -8,
],
],
    'two_words': [
    'cat',
    'leopard',
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
    'mixed_type': 0.88537,
    'maybe_null': 'shark',
},
},
    {
    'id': 21,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 121,
    'id_str': [
    '18',
    '19',
    '16',
    '05',
],
    'text_data': '2a91316b62d849e9b64b00508c002630',
    'rand_digit': 3,
    'rand_number': 0.62951,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-30T21:45:06.669089+12:00',
    'text_array': [
    'c396f9c2159f4fb4bae1660bc3ca9215',
    '9fd6f1ef45114b318aed38fd5d29d071',
],
    'words': 'deer dragonfly',
    'nested': {
    'id': 121,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'dolphin',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ant',
    'number': 10,
},
],
},
    'nested_array': [
    [
    10,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'spider',
    'spider',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': [
    43,
],
    'rand_bool': False,
    'mixed_type': None,
},
},
    {
    'id': 22,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 122,
    'id_str': [
    '02',
    '09',
],
    'text_data': '81be403486084e86b4a265dc1d9b96d8',
    'rand_digit': 2,
    'rand_number': 0.0066,
    'rand_signed_int': 5,
    'rand_datetime': '2000-04-03 11:32:03',
    'text_array': [
    'e83e68aab20549bba01365843dcbe7ba',
    '8379481e8ddf4fa1a3d9828fc64295fc',
],
    'words': 'pig chicken',
    'nested': {
    'id': 122,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'ape',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 3,
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
    [
],
],
    'two_words': [
    'dolphin',
    'goat',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'horse',
},
},
    {
    'id': 23,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 123,
    'id_str': [
],
    'text_data': '54c3d84c4fbd49ada27149526ec8c442',
    'rand_digit': 9,
    'rand_number': 0.82499,
    'rand_signed_int': 1,
    'rand_datetime': '2000-08-27T11:11:31-0300',
    'text_array': [
    'e1b805d31d8046c4972e13cd6d3f6132',
    '8a07fc3199014edd89220865b5da5880',
],
    'words': 'fox mosquito',
    'nested': {
    'id': 123,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    [
    -7,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'tiger',
    'cow',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.31846,
    'maybe_null': None,
},
},
    {
    'id': 24,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 124,
    'id_str': [
    '11',
],
    'text_data': 'f1fe31bdd1954a8189f1df1392936e85',
    'rand_digit': 9,
    'rand_number': 0.28844,
    'rand_signed_int': -6,
    'rand_datetime': '2000-03-09 01:50:11.295799-0400',
    'text_array': [
    'ac8c77f3c76d45e28cd6a9c0fd24fcf0',
    '3ed429c5501a457fbc0e7e5124377c37',
],
    'words': 'duck zebra',
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
    'word': 'grasshopper',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'ape',
    'snake',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.89614,
    'maybe': 'wolf',
    'maybe_null': None,
},
},
    {
    'id': 25,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 125,
    'id_str': [
    '30',
    '19',
    '12',
],
    'text_data': '2df5e156a62646fa87c5790b326a1b0b',
    'rand_digit': 5,
    'rand_number': 0.96612,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-10 18:24:13',
    'text_array': [
    '704258407bde4b3fbfca633245eeea53',
    'c7684e8285314864b460ddd1910b042a',
],
    'words': 'leopard pig',
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
    'word': 'crab',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'hippo',
    'deer',
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
    'mixed_type': 'bear',
    'maybe': 'elephant',
    'maybe_null': 'frog',
},
},
    {
    'id': 26,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 126,
    'id_str': [
],
    'text_data': 'a1b94629a5784afbae3432b5b0f20fac',
    'rand_digit': 4,
    'rand_number': 0.69436,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-09T12:58:05',
    'text_array': [
    'f229884d08cf4cc29c8b58087fffe576',
    '9bc74d0910874993ab9e4301e542ebb6',
],
    'words': 'ape octopus',
    'nested': {
    'id': 126,
    'rand_digit': 5,
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
    'word': 'mosquito',
    'number': 2,
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
],
    'word': 'kangaroo',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'butterfly',
    'pig',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fly',
    'maybe_null': None,
},
},
    {
    'id': 27,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 127,
    'id_str': [
],
    'text_data': '2cf2ddee7d864e13ae5352276ee43b05',
    'rand_digit': 7,
    'rand_number': 0.31158,
    'rand_signed_int': 10,
    'rand_datetime': '2000-01-08 01:34:59+0400',
    'text_array': [
    '3555a09047bf494b9c641fcf7d5a276a',
    '5eb67f7953014be8844fadd831b7f84f',
],
    'words': 'leopard lizard',
    'nested': {
    'id': 127,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'cow',
    'squid',
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
    'mixed_type': 1,
    'maybe': 'octopus',
    'maybe_null': None,
},
},
    {
    'id': 28,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 128,
    'id_str': [
],
    'text_data': '1eb8503fce2c49f58fbf31e3757f0b3b',
    'rand_digit': 9,
    'rand_number': 0.81025,
    'rand_signed_int': -8,
    'rand_datetime': '2000-02-16T09:58:35.533682-07:00',
    'text_array': [
    'fca00589ffba4d4ca09942fa040f06ff',
    'd19b59fcf95e450494f09202b9ca2776',
],
    'words': 'squid hippo',
    'nested': {
    'id': 128,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'elephant',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
    -1,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'pig',
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
    42,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'shark',
    'maybe_null': None,
},
},
    {
    'id': 29,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 129,
    'id_str': [
    '05',
    '16',
    '06',
    '01',
],
    'text_data': '6dc0720e719d467183146553a2522cd0',
    'rand_digit': 8,
    'rand_number': 0.8368,
    'rand_signed_int': 5,
    'rand_datetime': '2000-08-04T01:53:43',
    'text_array': [
    '978b7aafc3b04a34936f0b86d3c7e2b4',
    'e05e47de45f444829d1b19f508001113',
],
    'words': 'cheetah ape',
    'nested': {
    'id': 129,
    'rand_digit': 0,
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
    'hello',
],
    'word': 'goat',
    'number': 7,
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
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'giraffe',
    'cheetah',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 7,
    'maybe_null': 'hippo',
},
},
    {
    'id': 30,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 130,
    'id_str': [
    '24',
],
    'text_data': 'a3e015a3e22345dc8fd152eea5c78197',
    'rand_digit': 3,
    'rand_number': 0.18534,
    'rand_signed_int': -8,
    'rand_datetime': '2000-07-30T02:02:50.393977-0400',
    'text_array': [
    '021070b6fd064aaab36f996e4a6e8673',
    '45f72d8f7fe54971834ba08cab8e5213',
],
    'words': 'lion chicken',
    'nested': {
    'id': 130,
    'rand_digit': 4,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
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
    'ladybug',
    'cow',
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
    'mixed_type': 9,
    'maybe': 'wolf',
    'maybe_null': 'cat',
},
},
    {
    'id': 31,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 131,
    'id_str': [
],
    'text_data': '6033aa10cb154f5289adf2329f621881',
    'rand_digit': 5,
    'rand_number': 0.9501,
    'rand_signed_int': 10,
    'rand_datetime': '2000-06-07 18:57:56-0700',
    'text_array': [
    '40a251c0d63047e8a473ba54eb539be3',
    '01cb835ec70f4c7fb02ac8c586f61f75',
],
    'words': 'chicken turtle',
    'nested': {
    'id': 131,
    'rand_digit': 0,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'fox',
    'leopard',
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
    'mixed_type': 0.77945,
    'maybe': 'cow',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 32,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 132,
    'id_str': [
    '07',
],
    'text_data': '801bb07e13e54e4bb8798b6c4f6da30c',
    'rand_digit': 0,
    'rand_number': 0.00395,
    'rand_signed_int': 0,
    'rand_datetime': '2000-03-05T09:06:57.797700',
    'text_array': [
    'e29c83712b0345a39f77a0c22ecdb621',
    'f55cdcc9c1d9466eb0fa6d9231cbee10',
],
    'words': 'cat horse',
    'nested': {
    'id': 132,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'rhino',
    'grasshopper',
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
    'mixed_type': True,
    'maybe_null': 'pig',
},
},
    {
    'id': 33,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 133,
    'id_str': [
    '27',
    '28',
],
    'text_data': 'f5db973f805a4998ba99dfa45220a93c',
    'rand_digit': 3,
    'rand_number': 0.2814,
    'rand_signed_int': 1,
    'rand_datetime': '2000-05-28T20:53:37.458981',
    'text_array': [
    'c4edd05c34f54b18ac6969b85e69dd93',
    'b526a47b39d6428aaad1622a2e6c254a',
],
    'words': 'sloth kangaroo',
    'nested': {
    'id': 133,
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
    0,
],
],
    'two_words': [
    'cow',
    'cat',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': [
    46,
],
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'squid',
    'maybe_null': 'zebra',
},
},
    {
    'id': 34,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 134,
    'id_str': [
    '10',
    '11',
    '19',
],
    'text_data': '29e31c5ca48e453a990fca2c15bff3ec',
    'rand_digit': 4,
    'rand_number': 0.28791,
    'rand_signed_int': -9,
    'rand_datetime': '2001-01-19T13:28:45',
    'text_array': [
    '173f340fbba24864b582622f897a1ce1',
    '847af14bf865408aa4c49bbe89dda9ec',
],
    'words': 'cheetah bear',
    'nested': {
    'id': 134,
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
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
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
    'dolphin',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 35,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 135,
    'id_str': [
    '30',
],
    'text_data': '2e2a97ba4fcf4757ae7f91bd206e27d1',
    'rand_digit': 3,
    'rand_number': 0.27441,
    'rand_signed_int': 2,
    'rand_datetime': '2000-09-18 02:44',
    'text_array': [
    'e563e0b2742e4e3eaff801b70b82e1e2',
    '7bbcf2c4faf14cf2a14bd7ae3c1a295d',
],
    'words': 'pig ladybug',
    'nested': {
    'id': 135,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 10,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'chicken',
    'whale',
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
    'mixed_type': 0.99979,
},
},
    {
    'id': 36,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 136,
    'id_str': [
    '06',
    '01',
    '22',
    '04',
    '05',
],
    'text_data': 'ee129b9feed2420eb76609ba08e6aaa8',
    'rand_digit': 7,
    'rand_number': 0.18012,
    'rand_signed_int': -10,
    'rand_datetime': '2000-06-18 16:00:06',
    'text_array': [
    'ab84c1d4f2984f1485668bc68716f658',
    '65128892409a47e18a92ef3aeaa16ecc',
],
    'words': 'jaguar bird',
    'nested': {
    'id': 136,
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
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    3,
],
    [
],
],
    'two_words': [
    'turtle',
    'sloth',
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
    'mixed_type': 0,
    'maybe_null': None,
},
},
    {
    'id': 37,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 137,
    'id_str': [
    '30',
    '09',
],
    'text_data': 'c8a3b62818944cdfae42a391e0523e60',
    'rand_digit': 2,
    'rand_number': 0.50875,
    'rand_signed_int': 3,
    'rand_datetime': '2000-12-04T09:38:33',
    'text_array': [
    'b7f9a77153224636b301c7dd39da56bb',
    'b2dc7caedfac41a4ad0ae0169a6cddf1',
],
    'words': 'lion gorilla',
    'nested': {
    'id': 137,
    'rand_digit': 2,
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
],
    'two_words': [
    'octopus',
    'bird',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.31817,
    'maybe': 'shark',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 38,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 138,
    'id_str': [
    '03',
    '28',
],
    'text_data': 'e9fd8980d12d4485bb6cd5a8bb8ca7cc',
    'rand_digit': 8,
    'rand_number': 0.21637,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-05T06:56:44.207456+12:00',
    'text_array': [
    'a8733f1d3e484412bc2768772616f9b5',
    '71258b1d31814d809fb0351d717008d9',
],
    'words': 'octopus whale',
    'nested': {
    'id': 138,
    'rand_digit': 4,
    'array': [
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
    'word': 'gorilla',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 5,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'jaguar',
    'horse',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': [
    61,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 39,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 139,
    'id_str': [
],
    'text_data': 'fb4cd568f596412b8494b3d412fd412e',
    'rand_digit': 4,
    'rand_number': 0.7152,
    'rand_signed_int': -6,
    'rand_datetime': '2000-09-12T08:55:29.425609',
    'text_array': [
    '193ee47360ab40fdb5a1a4686219ba96',
    '8866abc7096e413f8b14292e6112d842',
],
    'words': 'leopard fish',
    'nested': {
    'id': 139,
    'rand_digit': 5,
    'array': [
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'leopard',
    'goat',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'ladybug',
    'maybe_null': 'goat',
},
},
    {
    'id': 40,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 140,
    'id_str': [
    '02',
    '09',
    '09',
    '23',
    '21',
],
    'text_data': '8ce76aee4dcc466e8bd26d2e8806431c',
    'rand_digit': 1,
    'rand_number': 0.9947,
    'rand_signed_int': -2,
    'rand_datetime': '2000-03-22 01:34:44.619495-0500',
    'text_array': [
    'c56545fa28154c41bb33eb38a2f33ba0',
    '1790516c68014d43806655839c710210',
],
    'words': 'frog spider',
    'nested': {
    'id': 140,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'sloth',
    'ladybug',
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
    'mixed_type': True,
},
},
    {
    'id': 41,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 141,
    'id_str': [
    '29',
    '28',
    '18',
],
    'text_data': 'ed549f41a59a472286f293fc95ad9eed',
    'rand_digit': 7,
    'rand_number': 0.28348,
    'rand_signed_int': -4,
    'rand_datetime': '2000-09-12T08:23:54.542658',
    'text_array': [
    'e2637e9e14ee4fb4bc73bb162f6feeaa',
    'c783e9beca56446ea5fd0ddeafac4189',
],
    'words': 'mosquito fox',
    'nested': {
    'id': 141,
    'rand_digit': 1,
    'array': [
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'cheetah',
    'hyena',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': [
    49,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'whale',
},
},
    {
    'id': 42,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 142,
    'id_str': [
    '21',
    '17',
    '18',
],
    'text_data': 'b6716f319eea419e9f273a8a881a986a',
    'rand_digit': 4,
    'rand_number': 0.03401,
    'rand_signed_int': -9,
    'rand_datetime': '2000-07-29T19:13:34.863376',
    'text_array': [
    '78b33e43905e4e90983944b461def050',
    '37d8874795e140f38a9835746e0c733d',
],
    'words': 'sloth gorilla',
    'nested': {
    'id': 142,
    'rand_digit': 2,
    'array': [
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
    'hello',
],
    'word': 'fish',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -5,
],
],
    'two_words': [
    'rabbit',
    'gorilla',
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
    'mixed_type': 'goat',
},
},
    {
    'id': 43,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 143,
    'id_str': [
    '14',
    '07',
    '12',
    '11',
    '22',
],
    'text_data': 'ace9a0d05b3148d9936028f46c4e9ba2',
    'rand_digit': 3,
    'rand_number': 0.5713,
    'rand_signed_int': 10,
    'rand_datetime': '2000-07-16T08:37:11.155688+02:00',
    'text_array': [
    '4ad18631932b47d296e0bc04b6e67d5b',
    '7eba80bb639943a3bc285aea31ad470d',
],
    'words': 'ape bee',
    'nested': {
    'id': 143,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'dog',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
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
    'mouse',
    'butterfly',
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
    'mixed_type': 'elephant',
    'maybe': 'monkey',
    'maybe_null': None,
},
},
    {
    'id': 44,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 144,
    'id_str': [
    '13',
    '18',
],
    'text_data': '0551e84b997d44229c046a452930de0e',
    'rand_digit': 7,
    'rand_number': 0.0228,
    'rand_signed_int': 9,
    'rand_datetime': '2000-09-03 23:37:47',
    'text_array': [
    'bccfc918e81042d1805036b90d30d0c3',
    '0f3e32b3a3c041fea85927972e7c623f',
],
    'words': 'sloth fish',
    'nested': {
    'id': 144,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mouse',
    'lizard',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'pig',
},
},
    {
    'id': 45,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 145,
    'id_str': [
],
    'text_data': '5e39aaee6ce445c1a6a9cedccc42c9f0',
    'rand_digit': 0,
    'rand_number': 0.54481,
    'rand_signed_int': 5,
    'rand_datetime': '2000-07-03 09:42:53+0900',
    'text_array': [
    'd01d389345694886a7dcbefc75babea2',
    '4619345e2a724a92a5438c7d79ce2332',
],
    'words': 'duck chicken',
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
    'word': 'giraffe',
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
],
    'word': 'duck',
    'number': 5,
},
],
},
    'nested_array': [
    [
    2,
],
    [
    -9,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ladybug',
    'rabbit',
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
    'maybe_null': None,
},
},
    {
    'id': 46,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 146,
    'id_str': [
    '15',
    '30',
    '17',
],
    'text_data': '2a2e504cadab4b3da8e7b3dda84a421c',
    'rand_digit': 1,
    'rand_number': 0.57306,
    'rand_signed_int': 1,
    'rand_datetime': '2000-03-21 01:10',
    'text_array': [
    '74fd65b4bf7546ec8b14c059e635df7a',
    '506ed6b61caf4d7f85c90f125d89013f',
],
    'words': 'panda scorpion',
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
    'word': 'leopard',
    'number': 4,
},
    {
    'nested_empty': None,
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
    'word': 'dog',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    [
    3,
],
],
    'two_words': [
    'duck',
    'wolf',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': [
    67,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'mouse',
},
},
    {
    'id': 47,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 147,
    'id_str': [
],
    'text_data': 'dfc349824fd140afba7c7b12dd8d78b7',
    'rand_digit': 6,
    'rand_number': 0.43352,
    'rand_signed_int': -6,
    'rand_datetime': '2000-03-31T17:36:35.583860',
    'text_array': [
    'ad3538ac2751480ab484f2a3295c559f',
    'efe9df7818c84a26b15c9580c2395345',
],
    'words': 'elephant lizard',
    'nested': {
    'id': 147,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
    'number': 1,
},
],
},
    'nested_array': [
    [
    -8,
],
],
    'two_words': [
    'spider',
    'kangaroo',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': [
    7,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'crab',
},
},
    {
    'id': 48,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 148,
    'id_str': [
    '29',
    '11',
    '06',
    '18',
    '02',
],
    'text_data': '36d57d7886684a68ad4c116802394f90',
    'rand_digit': 9,
    'rand_number': 0.66268,
    'rand_signed_int': -7,
    'rand_datetime': '2000-05-12 16:06:31-0400',
    'text_array': [
    '0f3389c563964095944ee37b40bae117',
    '0ecfe790ec874c2dbaacb241c1785258',
],
    'words': 'pig spider',
    'nested': {
    'id': 148,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 4,
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
],
    'two_words': [
    'ape',
    'gorilla',
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
    'mixed_type': None,
    'maybe': 'rhino',
    'maybe_null': 'snake',
},
},
    {
    'id': 49,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 149,
    'id_str': [
    '13',
    '18',
    '08',
    '30',
],
    'text_data': 'fa864e4f9b6c4278a76c76b865c4486f',
    'rand_digit': 5,
    'rand_number': 0.07511,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-09T18:44:14.021146+0500',
    'text_array': [
    'c8d6497f1bbd49a7a569ab13b8937ae8',
    '06458a9dade348e8a11fe376f61ffeca',
],
    'words': 'hyena zebra',
    'nested': {
    'id': 149,
    'rand_digit': 3,
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
    'word': 'elephant',
    'number': 2,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'giraffe',
    'octopus',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
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
    'id': 50,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 150,
    'id_str': [
],
    'text_data': 'b0687add6f244cc4afdb7721c9064c31',
    'rand_digit': 5,
    'rand_number': 0.10428,
    'rand_signed_int': 10,
    'rand_datetime': '2000-09-08 00:50:20.928129',
    'text_array': [
    '319e26a7d0a34b5dad803a573810ad12',
    'f14bd2dbde6b4215b7c3f5a986e70385',
],
    'words': 'tiger hyena',
    'nested': {
    'id': 150,
    'rand_digit': 5,
    'array': [
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    7,
],
],
    'two_words': [
    'leopard',
    'ladybug',
],
    'city': {
    'name': 'London',
    'geo': {
    'lat': 51.507351,
    'lon': -0.127758,
},
},
    'rand_tuple': [
    21,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'ape',
    'maybe_null': 'elephant',
},
},
    {
    'id': 51,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 151,
    'id_str': [
    '08',
    '11',
    '13',
    '02',
    '02',
],
    'text_data': '09d65897cc504cb09a014bd44276f3a0',
    'rand_digit': 6,
    'rand_number': 0.61016,
    'rand_signed_int': 5,
    'rand_datetime': '2000-03-24T17:19:39.990549-0300',
    'text_array': [
    'e4b25cffdb804d7ab6a7c82c4a38c3f2',
    '15153574ba6b4e8b9f85f35f6944e16a',
],
    'words': 'pig pig',
    'nested': {
    'id': 151,
    'rand_digit': 7,
    'array': [
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
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    8,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'koala',
    'duck',
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
    'mixed_type': False,
    'maybe': 'snail',
},
},
    {
    'id': 52,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 152,
    'id_str': [
],
    'text_data': 'e6f414004c6644a1ac9b50b143b8baf3',
    'rand_digit': 2,
    'rand_number': 0.74266,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-14 19:05:52+0800',
    'text_array': [
    '381f324844f744dcafe5a3b2a619091c',
    '8df4041542714790a017db3f135c8b34',
],
    'words': 'sheep ant',
    'nested': {
    'id': 152,
    'rand_digit': 6,
    'array': [
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
    'word': 'tiger',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 1,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,5__',
    'two_words': [
    'camel',
    'snail',
],
    'city': {
    'name': 'Moscow',
    'geo': {
    'lat': 55.755826,
    'lon': 37.6173,
},
},
    'rand_tuple': [
    39,
],
    'rand_bool': False,
    'mixed_type': 'rhino',
    'maybe_null': None,
},
},
    {
    'id': 53,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 153,
    'id_str': [
    '29',
    '13',
    '25',
    '26',
],
    'text_data': 'ac4cf87d93a24347988d2c944c173eff',
    'rand_digit': 6,
    'rand_number': 0.73059,
    'rand_signed_int': -8,
    'rand_datetime': '2000-09-03T16:07:09-0700',
    'text_array': [
    'e0883437074f487e8ae16dd1aa500cbd',
    'ab80f0156db1427099cf26ca2bde358e',
],
    'words': 'elephant hyena',
    'nested': {
    'id': 153,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
    -10,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'bee',
    'rabbit',
],
    'city': {
    'name': 'Kharkiv',
    'geo': {
    'lat': 49.980812,
    'lon': 36.25272,
},
},
    'rand_tuple': [
    23,
],
    'rand_bool': False,
    'mixed_type': 'scorpion',
    'maybe_null': 'zebra',
},
},
    {
    'id': 54,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 154,
    'id_str': [
    '29',
    '27',
    '03',
    '25',
    '14',
],
    'text_data': 'c2b8904267a4424aa4014e7955d773e7',
    'rand_digit': 5,
    'rand_number': 0.69816,
    'rand_signed_int': 0,
    'rand_datetime': '2000-12-08 02:29:06',
    'text_array': [
    '53f086ff92ef48769403faf1afa4a649',
    '4d18e1aac71441c98d64c8e56b1360b2',
],
    'words': 'spider hyena',
    'nested': {
    'id': 154,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    5,
],
    [
],
],
    'two_words': [
    'bear',
    'butterfly',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'octopus',
    'maybe_null': 'hyena',
},
},
    {
    'id': 55,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 155,
    'id_str': [
    '21',
],
    'text_data': 'c3645de3092342bdbedf9dbf0e03a54e',
    'rand_digit': 1,
    'rand_number': 0.69677,
    'rand_signed_int': 7,
    'rand_datetime': '2000-03-24 12:04:28.783741-0900',
    'text_array': [
    '7542a32b916e447a8d78dfc17c9e3533',
    '69ff2668aea8472384fa0dccbb482f60',
],
    'words': 'kangaroo grasshopper',
    'nested': {
    'id': 155,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
    'number': 7,
},
    {
    'nested_empty': None,
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
    'word': 'ape',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dolphin',
    'ape',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': [
    82,
],
    'rand_bool': True,
    'mixed_type': 'goat',
    'maybe': 'ladybug',
    'maybe_null': 'lion',
},
},
    {
    'id': 56,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 156,
    'id_str': [
    '28',
    '20',
    '06',
    '06',
],
    'text_data': '02ce9372f9694994847b825a911d4604',
    'rand_digit': 7,
    'rand_number': 0.11895,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-12 07:37:37-0200',
    'text_array': [
    '933610f05efb47f29724cdb8fa464ce7',
    '61831188fbc940979a3cbea5a2c0da58',
],
    'words': 'cat cheetah',
    'nested': {
    'id': 156,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 1,
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
    'ant',
    'butterfly',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': [
    77,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'frog',
    'maybe_null': None,
},
},
    {
    'id': 57,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 157,
    'id_str': [
    '07',
    '25',
    '29',
    '26',
],
    'text_data': 'b8a7dc24a57b40459dc6f14c9fb1253b',
    'rand_digit': 2,
    'rand_number': 0.83688,
    'rand_signed_int': 3,
    'rand_datetime': '2000-12-02 11:24:29+1100',
    'text_array': [
    '84bcd3b06b7b444d80be6132ef6f43fd',
    'f1f20ff86d5c442bbaca528ede5440e6',
],
    'words': 'mouse giraffe',
    'nested': {
    'id': 157,
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
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'ape',
    'ladybug',
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
    'maybe_null': 'squid',
},
},
    {
    'id': 58,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 158,
    'id_str': [
    '18',
    '02',
    '20',
    '29',
    '20',
],
    'text_data': '5a27b4b835a54907b0e30d3e4a0ca2d4',
    'rand_digit': 4,
    'rand_number': 0.06161,
    'rand_signed_int': -5,
    'rand_datetime': '2000-02-17T13:44:07',
    'text_array': [
    '0b63c4ccfc16486e96871ac0099dc7a3',
    '6fa81bedc11d4509b2e1b31a31556048',
],
    'words': 'kangaroo fish',
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
    'word': 'rabbit',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
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
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'koala',
    'frog',
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
    'mixed_type': True,
},
},
    {
    'id': 59,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 159,
    'id_str': [
    '23',
    '01',
    '07',
    '29',
    '03',
],
    'text_data': 'b5e99d01fee54cd686bd6e4d9b6b5ae6',
    'rand_digit': 6,
    'rand_number': 0.96359,
    'rand_signed_int': 3,
    'rand_datetime': '2000-11-09 15:34',
    'text_array': [
    'e31c1d841a6b4490a01156d432443dfb',
    'c238203d68d24544ae35e5e17518c1cf',
],
    'words': 'squid lizard',
    'nested': {
    'id': 159,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 4,
},
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'lizard',
    'bear',
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
    'mixed_type': False,
    'maybe': 'ape',
    'maybe_null': 'snake',
},
},
    {
    'id': 60,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 160,
    'id_str': [
    '22',
    '24',
    '17',
    '28',
    '01',
],
    'text_data': '60636948b6df4a41b4495e888371060b',
    'rand_digit': 5,
    'rand_number': 0.61941,
    'rand_signed_int': 3,
    'rand_datetime': '2001-01-05T19:03:39',
    'text_array': [
    'fc0ff516469c4c21a64ddc60d6460424',
    '261a9e010caf4570858e180139dad417',
],
    'words': 'giraffe fox',
    'nested': {
    'id': 160,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 3,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'turtle',
    'mouse',
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
    'mixed_type': 7,
    'maybe_null': 'bee',
},
},
    {
    'id': 61,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 161,
    'id_str': [
    '10',
    '30',
],
    'text_data': 'fb1b38ca746e48619df9afd8ace8c6b7',
    'rand_digit': 8,
    'rand_number': 0.17547,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-10T06:59:54.802825',
    'text_array': [
    '359b01373fe34c4898cc8c8f44b82a15',
    '177015ff7994453da9bebf2e5114bae4',
],
    'words': 'crab dolphin',
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
    'word': 'koala',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'butterfly',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cheetah',
    'grasshopper',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
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
    'id': 62,
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'payload': {
    'id': 162,
    'id_str': [
    '22',
],
    'text_data': '57529719fc2c40deac7fcbe3d6ceeef3',
    'rand_digit': 3,
    'rand_number': 0.38377,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-30',
    'text_array': [
    '9ff711574b354256b155ff7638366613',
    'f2a76f20e8c540dca1f06565ae18f97c',
],
    'words': 'leopard mosquito',
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
    'word': 'bear',
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
    'number': 1,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'crab',
    'mosquito',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'ladybug',
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
],
    'text_data': 'f4a568b3845b45aa81f5cc2e6ca676c5',
    'rand_digit': 4,
    'rand_number': 0.11061,
    'rand_signed_int': -3,
    'rand_datetime': '2000-07-15 08:39:36.065685',
    'text_array': [
    '2eddaad101b84d45956e0965ae293b5b',
    'dd3e4be693494cd6810d3ef096e9cc8b',
],
    'words': 'elephant zebra',
    'nested': {
    'id': 163,
    'rand_digit': 9,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lobster',
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
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'kangaroo',
    'butterfly',
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
    'maybe': 'dragonfly',
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
        """测试请求 2 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1104',
}
        
        # 原始请求内容
        original_content = {
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'group_by': 'rand_digit',
    'group_size': 1,
    'limit': 10,
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
        """测试请求 3 - PUT http://localhost:6333/collections/congruence_test_collection?timeout=60"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/congruence_test_collection?timeout=60")
        
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
        """测试请求 4 - POST http://localhost:6333/collections/congruence_test_collection/points/search/groups"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/search/groups")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/search/groups'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '1129',
}
        
        # 原始请求内容
        original_content = {
    'vector': {
    'name': 'text',
    'vector': self.mutator.generate_float_array(dimension=50, normalized=True),
},
    'with_payload': {
    'exclude': [
    'city.geo',
    'rand_number',
],
},
    'with_vector': False,
    'group_by': 'rand_digit',
    'group_size': 1,
    'limit': 10,
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
    'content-length': '43',
}
        
        # 原始请求内容
        original_content = {
    'vectors': {
    'size': 50,
    'distance': 'Euclid',
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_group_search.test_group_search_types')
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
    test = TestGroupSearchtestGroupSearchTypes()
    test.run_tests()
