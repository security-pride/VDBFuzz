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
logger = logging.getLogger('vdb_fuzzer.test.test_multivector_discovery_queries_test_context_many_pairs')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_multivector_discovery_queries.test_context_many_pairs"
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



class TestMultivectorDiscoveryQueriestestContextManyPairs:
    """自动生成的VDB模糊测试类 - test_multivector_discovery_queries.test_context_many_pairs"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_multivector_discovery_queries.test_context_many_pairs"
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
    'content-length': '538597',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 100,
    'id_str': [
    '23',
    '05',
    '02',
],
    'text_data': '96dc16cf6a7143c28683da91d69eae36',
    'rand_digit': 2,
    'rand_number': 0.80056,
    'rand_signed_int': -4,
    'rand_datetime': '2000-08-22 09:23:21',
    'text_array': [
    'c8580b732c85469bba9cf98a55c9f38e',
    'e33b9ed0eb0b45bb9a46dd0b05e68c71',
],
    'words': 'elephant ladybug',
    'nested': {
    'id': 100,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    10,
],
],
    'two_words': [
    'fish',
    'hyena',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'cow',
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 101,
    'id_str': [
    '06',
],
    'text_data': '65f5b328c6df47068179766e811def6a',
    'rand_digit': 1,
    'rand_number': 0.00816,
    'rand_signed_int': 7,
    'rand_datetime': '2000-11-25',
    'text_array': [
    '32fba8f53f1345be98aa987f35595398',
    'e94e727daae2499e949411c8aca00b43',
],
    'words': 'cheetah deer',
    'nested': {
    'id': 101,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'zebra',
    'duck',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 2,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 102,
    'id_str': [
    '11',
    '01',
    '26',
],
    'text_data': '31b7b0dee9bd4e5daa9b21de5744e245',
    'rand_digit': 1,
    'rand_number': 0.37027,
    'rand_signed_int': 0,
    'rand_datetime': '2000-07-30T18:56:24.133834',
    'text_array': [
    'b45a380305a84de1bc33e5a95c795e3b',
    '28131a2717174ee384b450f9e6f6ee5a',
],
    'words': 'elephant wolf',
    'nested': {
    'id': 102,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'grasshopper',
    'zebra',
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
    'mixed_type': False,
    'maybe_null': 'bee',
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 103,
    'id_str': [
],
    'text_data': '2a3c6c723cad4eb386718a047de2aa6a',
    'rand_digit': 1,
    'rand_number': 0.8246,
    'rand_signed_int': -7,
    'rand_datetime': '2000-09-05T11:39:10',
    'text_array': [
    '7a49fb43f21b4ced821f003e0f637289',
    '5486dea19ba646689ac073bbd2e61910',
],
    'words': 'leopard butterfly',
    'nested': {
    'id': 103,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
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
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 7,
},
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
],
    'word': 'koala',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    5,
],
],
    'two_words': [
    'dolphin',
    'lion',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'scorpion',
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 104,
    'id_str': [
    '09',
    '05',
    '25',
    '17',
],
    'text_data': '8764e5b5b0ae40acb1ba41b50ea531a2',
    'rand_digit': 6,
    'rand_number': 0.36724,
    'rand_signed_int': 7,
    'rand_datetime': '2000-11-05',
    'text_array': [
    '4e8d2a4fec254f7a8cbd8b22d6f7f89e',
    '018452e2886d4329bd2adcf6ac05be32',
],
    'words': 'bird dragonfly',
    'nested': {
    'id': 104,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    [
    4,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'leopard',
    'crab',
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
    'mixed_type': 5,
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 105,
    'id_str': [
],
    'text_data': '7c7d31273c0645b087fc389e16740db5',
    'rand_digit': 6,
    'rand_number': 0.06026,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-29 02:50:54.537138',
    'text_array': [
    'd58e83e06c7c47069ac22508d82fdee4',
    '3d9dbd5b8e1f4ffea73cfe8a3ab94254',
],
    'words': 'frog whale',
    'nested': {
    'id': 105,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 1,
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
],
    'word': 'koala',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'zebra',
    'turtle',
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
    'mixed_type': 'fly',
    'maybe': 'ant',
    'maybe_null': 'pig',
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 106,
    'id_str': [
    '01',
    '02',
    '14',
    '20',
    '23',
],
    'text_data': '14ce8b0efb6c40e486facef380c5b595',
    'rand_digit': 3,
    'rand_number': 0.17483,
    'rand_signed_int': -2,
    'rand_datetime': '2000-10-30T18:41:10.566435-04:00',
    'text_array': [
    'b66cd2ffd61443deb86fed2ac0d969b9',
    'c219eb93e57c4f5bb58f272a96705037',
],
    'words': 'turtle horse',
    'nested': {
    'id': 106,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'snail',
    'dragonfly',
],
    'city': {
    'name': 'Prague',
    'geo': {
    'lat': 50.075538,
    'lon': 14.4378,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'zebra',
    'maybe_null': None,
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 107,
    'id_str': [
    '30',
    '15',
],
    'text_data': '1eb3e886835845b79e3a536f970b37b4',
    'rand_digit': 5,
    'rand_number': 0.12113,
    'rand_signed_int': 0,
    'rand_datetime': '2000-03-28 10:17:28.989928',
    'text_array': [
    'cd544165449e4949a5413cdf3433be4c',
    '691f8b1b59bc42bf975e4dba65fc3353',
],
    'words': 'fish octopus',
    'nested': {
    'id': 107,
    'rand_digit': 5,
    'array': [
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
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'sloth',
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
    'mixed_type': 0.01175,
    'maybe_null': None,
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 108,
    'id_str': [
    '11',
    '09',
    '16',
],
    'text_data': '510cffec349049ab88f88c64d61a2c15',
    'rand_digit': 9,
    'rand_number': 0.13377,
    'rand_signed_int': -9,
    'rand_datetime': '2000-03-02T20:07:43.483202+0200',
    'text_array': [
    '2c33329b816644358c31c84296718992',
    '4acbc26a586e41e69acdf43b3998d55a',
],
    'words': 'whale fly',
    'nested': {
    'id': 108,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'scorpion',
    'number': 2,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fox',
    'ladybug',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.26746,
    'maybe_null': 'butterfly',
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 109,
    'id_str': [
    '18',
    '19',
],
    'text_data': 'a5ed3af0062942f194dc4a6f9087f6e0',
    'rand_digit': 1,
    'rand_number': 0.13523,
    'rand_signed_int': 2,
    'rand_datetime': '2000-08-29 05:58',
    'text_array': [
    '5bd85de86f6e42e09c8a7d23e9c87615',
    'd58a491fe51142abb6b9fb504794ec11',
],
    'words': 'pig spider',
    'nested': {
    'id': 109,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ladybug',
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
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'lobster',
    'rabbit',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'spider',
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 110,
    'id_str': [
    '22',
    '09',
],
    'text_data': '6f565a622ade4ea8af53b91322d42d42',
    'rand_digit': 9,
    'rand_number': 0.40445,
    'rand_signed_int': -2,
    'rand_datetime': '2000-11-18 13:13:16-0100',
    'text_array': [
    'dec7ba228b5c4efb8632489e336463e7',
    'b2dab984276a45b999cbc1a09d99bcc9',
],
    'words': 'mosquito chicken',
    'nested': {
    'id': 110,
    'rand_digit': 1,
    'array': [
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
    [
],
    [
],
],
    'two_words': [
    'lion',
    'zebra',
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
    'mixed_type': True,
    'maybe_null': None,
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 111,
    'id_str': [
    '22',
    '07',
    '19',
    '13',
    '08',
],
    'text_data': 'e9f1848008554d8a9c0fc235b76b88b9',
    'rand_digit': 5,
    'rand_number': 0.22425,
    'rand_signed_int': -5,
    'rand_datetime': '2000-06-28 04:13',
    'text_array': [
    'cc1bead186254166bb1b3a660acd8183',
    'ed0113a6aeaf4f77853c07efba7220c7',
],
    'words': 'tiger mosquito',
    'nested': {
    'id': 111,
    'rand_digit': 1,
    'array': [
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
    'word': 'lizard',
    'number': 9,
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
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'whale',
    'mouse',
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
    'mixed_type': True,
    'maybe_null': 'shark',
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 112,
    'id_str': [
    '28',
],
    'text_data': '294a96c860474a088f32602c0ade47be',
    'rand_digit': 2,
    'rand_number': 0.86154,
    'rand_signed_int': -9,
    'rand_datetime': '2000-07-31T12:01:28+0600',
    'text_array': [
    '1bfc82dacac24daf8317cb7eac593414',
    '7c0075ea6c6940eebb4e59ba1a2c2ddd',
],
    'words': 'deer panda',
    'nested': {
    'id': 112,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'jaguar',
    'number': 8,
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
    'koala',
    'gorilla',
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
    'maybe_null': None,
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 113,
    'id_str': [
    '06',
    '15',
    '06',
],
    'text_data': '9ba489ccf0e5472cb7ba3797de25f232',
    'rand_digit': 8,
    'rand_number': 0.81393,
    'rand_signed_int': -8,
    'rand_datetime': '2000-03-09',
    'text_array': [
    'aebbfb16b0104ec3a29fd85f7063e493',
    'cafe52078105405780150865254c9d21',
],
    'words': 'deer fish',
    'nested': {
    'id': 113,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
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
],
    'word': 'sheep',
    'number': 3,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,2__',
    'two_words': [
    'giraffe',
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
    'mixed_type': 0.95604,
    'maybe': 'tiger',
    'maybe_null': None,
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 114,
    'id_str': [
    '03',
],
    'text_data': '63e0b9b5361c4f44aabea67e728fa4b6',
    'rand_digit': 0,
    'rand_number': 0.21703,
    'rand_signed_int': -3,
    'rand_datetime': '2000-12-07 21:48:56.489671',
    'text_array': [
    '8f03978daed8457fb7e75cc726d47709',
    '5e7717c2b46f4d46bcfee65897199ea9',
],
    'words': 'gorilla leopard',
    'nested': {
    'id': 114,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 3,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dolphin',
    'fly',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'goat',
    'maybe_null': 'fox',
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 115,
    'id_str': [
    '23',
],
    'text_data': 'ccd161c1805440d7b06fe61640d21e3e',
    'rand_digit': 5,
    'rand_number': 0.67436,
    'rand_signed_int': -7,
    'rand_datetime': '2000-09-02 05:03',
    'text_array': [
    '8fcd62a48b194e599867c91fd19be254',
    'd0077853c5304ac68036f88ecdd1bd9c',
],
    'words': 'horse shark',
    'nested': {
    'id': 115,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'elephant',
    'bird',
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
    'mixed_type': 'elephant',
    'maybe_null': 'kangaroo',
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 116,
    'id_str': [
],
    'text_data': '9e01f5b057f3459fb10fef3619de8f14',
    'rand_digit': 5,
    'rand_number': 0.83694,
    'rand_signed_int': 1,
    'rand_datetime': '2000-03-24 09:38:20.941860',
    'text_array': [
    '7b9d4854f4c14f51beeb7e7cf1bda9ca',
    '22f0c4e6520145b2a72df669931bd0a2',
],
    'words': 'fly lion',
    'nested': {
    'id': 116,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'fish',
    'fox',
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
    'mixed_type': 9,
    'maybe_null': 'lizard',
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 117,
    'id_str': [
    '01',
],
    'text_data': '573a6e6274684985a58696c0ea5fc156',
    'rand_digit': 6,
    'rand_number': 0.52567,
    'rand_signed_int': 0,
    'rand_datetime': '2000-03-09T04:44:18.792614',
    'text_array': [
    'ce1287bc95d24e12989fff9b8625f54e',
    'fd19d612ef9b452d9ec91970ffc333ee',
],
    'words': 'lobster lobster',
    'nested': {
    'id': 117,
    'rand_digit': 6,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 9,
},
],
},
    'nested_array': [
    [
    3,
],
],
    'two_words': [
    'snail',
    'panda',
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
    'maybe': 'monkey',
},
},
    {
    'id': 18,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 118,
    'id_str': [
    '13',
],
    'text_data': '2a5d49fc7b3e47d680b77da9e672b33f',
    'rand_digit': 4,
    'rand_number': 0.81255,
    'rand_signed_int': -8,
    'rand_datetime': '2000-06-19T20:52:07.424755',
    'text_array': [
    '3c0d9a7397fe4ca5889512cb8c8ce999',
    '92778aa8b075479fb9e82df3b699c60e',
],
    'words': 'scorpion dog',
    'nested': {
    'id': 118,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'dragonfly',
    'number': 9,
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
    'hello',
],
    'word': 'hyena',
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
],
    'two_words': [
    'dog',
    'giraffe',
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
    'maybe': 'koala',
    'maybe_null': 'fish',
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
    '23',
],
    'text_data': 'f2158e4e740e4b768b178bda597b7002',
    'rand_digit': 6,
    'rand_number': 0.11634,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-20 21:54:21-0800',
    'text_array': [
    '184cb96a270c4aa8a609e06bc1fafc1f',
    '4a010965f2cd4cc7a39ae5aecebf1895',
],
    'words': 'bee sheep',
    'nested': {
    'id': 119,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'duck',
    'pig',
],
    'city': {
    'name': 'Moscow',
    'geo': {
    'lat': 55.755826,
    'lon': 37.6173,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'fly',
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 120,
    'id_str': [
],
    'text_data': '72b66b453dfd407cbecbb56887113c94',
    'rand_digit': 8,
    'rand_number': 0.00762,
    'rand_signed_int': 4,
    'rand_datetime': '2000-10-09 16:16:28-0200',
    'text_array': [
    '3dfe2a4049cb4d148ca16ae8487356d2',
    'ca55c68122d2478b8b1ecf09e32f4685',
],
    'words': 'bear tiger',
    'nested': {
    'id': 120,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'camel',
    'fox',
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
    'mixed_type': False,
    'maybe': 'dragonfly',
    'maybe_null': None,
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 121,
    'id_str': [
    '29',
    '13',
    '13',
],
    'text_data': '006375781a114f8397f07e702b4922e7',
    'rand_digit': 8,
    'rand_number': 0.15173,
    'rand_signed_int': -9,
    'rand_datetime': '2000-12-17 04:48:15',
    'text_array': [
    '94d6868adedc41a7ad1ce99375c9fc96',
    '99b576f64f2242958183e4fccb5fd3b5',
],
    'words': 'rhino butterfly',
    'nested': {
    'id': 121,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 1,
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
    'nested_empty': [
    'hello',
],
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
    'word': 'frog',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    10,
],
],
    'two_words': [
    'butterfly',
    'gorilla',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': [
    14,
],
    'rand_bool': True,
    'mixed_type': 5,
    'maybe_null': 'fly',
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
    '22',
    '08',
    '25',
    '08',
],
    'text_data': 'e72d230621b340439f865a8481faa72e',
    'rand_digit': 9,
    'rand_number': 0.43336,
    'rand_signed_int': 0,
    'rand_datetime': '2000-02-07T18:44:50-0900',
    'text_array': [
    'e613137ee98a4e898677491ea4dac2b2',
    '095d27b9c22e4708bc1374fdc4dc0cac',
],
    'words': 'spider camel',
    'nested': {
    'id': 122,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'cow',
    'number': 10,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
    -1,
],
],
    'two_words': [
    'lizard',
    'ape',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': None,
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 123,
    'id_str': [
    '15',
    '18',
],
    'text_data': 'bb63c9481ee8474cab4a8b234263214f',
    'rand_digit': 7,
    'rand_number': 0.70018,
    'rand_signed_int': 0,
    'rand_datetime': '2000-10-07T02:49:48-0200',
    'text_array': [
    'aa16394c205043eaaabd3120683d5c2a',
    'c6632bccef0149acbc97df6009754510',
],
    'words': 'duck hyena',
    'nested': {
    'id': 123,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lion',
    'number': 9,
},
    {
    'nested_empty': None,
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
    'word': 'cat',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'snake',
    'horse',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'mosquito',
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 124,
    'id_str': [
    '28',
    '15',
    '10',
],
    'text_data': 'b71e7019f11b472883059e230c775469',
    'rand_digit': 3,
    'rand_number': 0.57756,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-17 03:06:37.480554',
    'text_array': [
    '483d0d6a590c4b2e8889fbf7facfb699',
    'd08e426178634af1b8d9510eea763455',
],
    'words': 'lizard crab',
    'nested': {
    'id': 124,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 6,
},
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -6,
],
    [
    -2,
],
],
    'two_words': [
    'mouse',
    'deer',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 'elephant',
    'maybe': 'spider',
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
    '23',
    '26',
    '28',
    '23',
    '02',
],
    'text_data': '43f5645e778d411c82c36e4b68041521',
    'rand_digit': 2,
    'rand_number': 0.49742,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-13T18:00:51.479283+1200',
    'text_array': [
    '889c1d7530a4471980b2953dae680b7a',
    '91d986402f3342f199a65d77923b2c63',
],
    'words': 'mosquito goat',
    'nested': {
    'id': 125,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'gorilla',
    'frog',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'hyena',
    'maybe_null': 'rhino',
},
},
    {
    'id': 26,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 126,
    'id_str': [
    '06',
],
    'text_data': '04d894d501f74a85b27ab606121b41ca',
    'rand_digit': 5,
    'rand_number': 0.67218,
    'rand_signed_int': 7,
    'rand_datetime': '2001-01-18T19:29:10+0800',
    'text_array': [
    '3805f6a06afb4110b859b7bfe61fcd4b',
    'f7e33045aa3d44218351aca5f724baef',
],
    'words': 'cheetah tiger',
    'nested': {
    'id': 126,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    [
    -3,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'ape',
    'lion',
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
    'maybe_null': 'lizard',
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 127,
    'id_str': [
],
    'text_data': 'cb6b1198d7434f2891f6f6ab17c0e9ca',
    'rand_digit': 1,
    'rand_number': 0.89619,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-20 01:24:27.051705-0400',
    'text_array': [
    '923bfc7774754505886619a0b8fb68e5',
    '18e41b0edb134bd6a4fad6acc2e919f7',
],
    'words': 'hyena mosquito',
    'nested': {
    'id': 127,
    'rand_digit': 4,
    'array': [
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'rhino',
    'lobster',
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
    'mixed_type': None,
    'maybe': 'lobster',
    'maybe_null': 'frog',
},
},
    {
    'id': 28,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 128,
    'id_str': [
    '30',
],
    'text_data': '6859f27316d646b0a3591d0f5c9ee7fa',
    'rand_digit': 8,
    'rand_number': 0.60524,
    'rand_signed_int': -4,
    'rand_datetime': '2000-03-16T09:40:46',
    'text_array': [
    '18d0ebb75add4b308e782aa8f82b3409',
    '67bfa66058b5465c8cc44e7b332e8f30',
],
    'words': 'spider ape',
    'nested': {
    'id': 128,
    'rand_digit': 1,
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
    'hello',
],
    'word': 'frog',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
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
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'koala',
    'lizard',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': [
    84,
],
    'rand_bool': True,
    'mixed_type': True,
    'maybe_null': 'grasshopper',
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
],
    'text_data': 'b26ffb66c5c84170a5e2c7857beccdb7',
    'rand_digit': 9,
    'rand_number': 0.23914,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-03T14:57:47.636139',
    'text_array': [
    '38f324ae603541018e03b3787ade9b1c',
    '17dea7a01f19457db04c85501cb68d29',
],
    'words': 'squid cheetah',
    'nested': {
    'id': 129,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
    -10,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'bear',
    'snake',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 6,
    'maybe': 'lion',
    'maybe_null': 'wolf',
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 130,
    'id_str': [
    '21',
    '25',
    '03',
    '28',
],
    'text_data': '3ae79289f91848a88e39b6021cf0adfe',
    'rand_digit': 7,
    'rand_number': 0.13427,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-18 10:32:18',
    'text_array': [
    '46cad612fe7148159d782ecc63c239e1',
    '114332fa99da45df85865fd279e0664c',
],
    'words': 'frog lizard',
    'nested': {
    'id': 130,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'panda',
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
    'mixed_type': None,
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 131,
    'id_str': [
    '23',
],
    'text_data': '9b080da294214ab4bede5499b9ff26a6',
    'rand_digit': 3,
    'rand_number': 0.25552,
    'rand_signed_int': 7,
    'rand_datetime': '2000-01-10T09:32:27.059976+05:00',
    'text_array': [
    '44a8955e95714e8c9f0f40d8f3379e83',
    '9d2f4228fc0949838c36cf2d73379729',
],
    'words': 'frog camel',
    'nested': {
    'id': 131,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
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
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bird',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -8,
],
],
    'two_words': [
    'snake',
    'lion',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 32,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 132,
    'id_str': [
],
    'text_data': 'f3cd1a7df0b745e586b7f7449d83819d',
    'rand_digit': 9,
    'rand_number': 0.07246,
    'rand_signed_int': -3,
    'rand_datetime': '2000-09-23T22:50:33.345713',
    'text_array': [
    '2fe42ce26706470682623a69eea54275',
    'a8d9f8982c454a00aaaeb8fa4e932473',
],
    'words': 'mouse spider',
    'nested': {
    'id': 132,
    'rand_digit': 9,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -4,
],
],
    'two_words': [
    'mouse',
    'mouse',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 2,
    'maybe': 'cat',
    'maybe_null': 'butterfly',
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 133,
    'id_str': [
    '09',
],
    'text_data': 'd7b83a3ec0f24679a032eb9e2f997d45',
    'rand_digit': 6,
    'rand_number': 0.6352,
    'rand_signed_int': 2,
    'rand_datetime': '2000-06-15T14:10:27.076298',
    'text_array': [
    'ef6731635e3e487cae6371dc60b269d3',
    '06398702acdc44ae805bb39617c44f5e',
],
    'words': 'pig ape',
    'nested': {
    'id': 133,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 9,
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
    'word': 'grasshopper',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    3,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'scorpion',
    'lizard',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'monkey',
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 134,
    'id_str': [
    '30',
    '06',
    '05',
    '07',
],
    'text_data': '400e97bb03dd46f5972300da40e7a86d',
    'rand_digit': 8,
    'rand_number': 0.08876,
    'rand_signed_int': -3,
    'rand_datetime': '2000-08-14 22:42:52.577123-0300',
    'text_array': [
    'f84915ccb2f44cfeb9e3017ebf5cbf55',
    'cfeec84649654330806905b8037f9d2f',
],
    'words': 'gorilla snake',
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
    'word': 'rhino',
    'number': 9,
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 2,
},
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
    'hello',
],
    'word': 'giraffe',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'horse',
    'mosquito',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': [
    3,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'lizard',
    'maybe_null': 'turtle',
},
},
    {
    'id': 35,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 135,
    'id_str': [
    '24',
    '27',
    '06',
    '23',
    '03',
],
    'text_data': 'edb68e22cf6549658f605219a53f75b4',
    'rand_digit': 5,
    'rand_number': 0.0501,
    'rand_signed_int': 3,
    'rand_datetime': '2000-02-18T02:58:51.143482+0200',
    'text_array': [
    '7417d50521e549daa0c4d6da5eec4052',
    'd9ccbdec3bd84cb98017d34c8f322dad',
],
    'words': 'mosquito scorpion',
    'nested': {
    'id': 135,
    'rand_digit': 8,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'cow',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'zebra',
    'kangaroo',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'hyena',
},
},
    {
    'id': 36,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 136,
    'id_str': [
    '06',
    '13',
    '16',
    '24',
    '08',
],
    'text_data': '2964e41be21e4e15876a63f3feddc4e0',
    'rand_digit': 2,
    'rand_number': 0.5332,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-17 21:36',
    'text_array': [
    '1efe279faa3749429cdf6b142f52d9a6',
    '45e58a0214a642faba768ffb4d09b795',
],
    'words': 'hippo dragonfly',
    'nested': {
    'id': 136,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'whale',
    'bird',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'turtle',
    'maybe_null': 'bee',
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
    '28',
    '19',
    '16',
    '25',
    '14',
],
    'text_data': 'd692686f306a41e4b4b7c86956c811db',
    'rand_digit': 4,
    'rand_number': 0.48583,
    'rand_signed_int': 2,
    'rand_datetime': '2000-01-08T12:01:29.176327+0900',
    'text_array': [
    '74f81e750e364596997ed29a8c5ecc9b',
    '9e1d504518004ab1a63771f64095ffd6',
],
    'words': 'squid giraffe',
    'nested': {
    'id': 137,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
    [
],
    [
    7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lizard',
    'dolphin',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': [
    68,
],
    'rand_bool': False,
    'mixed_type': 5,
    'maybe_null': 'scorpion',
},
},
    {
    'id': 38,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 138,
    'id_str': [
    '05',
    '13',
    '30',
    '07',
],
    'text_data': 'bc0d6ac205f24732a2f5ccfc2bd6ab37',
    'rand_digit': 8,
    'rand_number': 0.32435,
    'rand_signed_int': -2,
    'rand_datetime': '2000-11-11 05:53:20',
    'text_array': [
    '53685bd224a74ee3af7749f3cf8ae26e',
    'f29db83adfcc44c4a68af8dc5e34a80d',
],
    'words': 'lion wolf',
    'nested': {
    'id': 138,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 5,
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
    'hello',
],
    'word': 'rhino',
    'number': 3,
},
],
},
    'nested_array': [
    [
    4,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'leopard',
    'kangaroo',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': [
    32,
],
    'rand_bool': True,
    'mixed_type': True,
    'maybe_null': 'elephant',
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 139,
    'id_str': [
    '27',
    '19',
    '01',
    '11',
],
    'text_data': '45587e0d9d9c47abb2eb3e298b8bc69a',
    'rand_digit': 8,
    'rand_number': 0.67285,
    'rand_signed_int': -5,
    'rand_datetime': '2001-01-08T20:41:14.255421+0600',
    'text_array': [
    '5d2b3ea335084aee9e698825bd782b3e',
    'b936d3de431b413985825cf08e130bec',
],
    'words': 'koala sheep',
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
    'word': 'ladybug',
    'number': 6,
},
    {
    'nested_empty': None,
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
    'fly',
    'ape',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': [
    64,
],
    'rand_bool': False,
    'mixed_type': 0.55016,
    'maybe': 'lobster',
    'maybe_null': 'zebra',
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 140,
    'id_str': [
],
    'text_data': 'f142cdcff0ad4e28a71c92292ed5f44b',
    'rand_digit': 2,
    'rand_number': 0.82793,
    'rand_signed_int': -1,
    'rand_datetime': '2000-10-18T00:25:33.676820+0600',
    'text_array': [
    '056f808f71b84217a668334f1dcceb70',
    '1eccf79735064a5cba522947e5d2778c',
],
    'words': 'fish lion',
    'nested': {
    'id': 140,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'cow',
    'sheep',
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
    'mixed_type': False,
    'maybe_null': 'fox',
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 141,
    'id_str': [
    '15',
    '20',
    '27',
    '03',
],
    'text_data': '2ebfa06311e34893b8a3890599056a67',
    'rand_digit': 2,
    'rand_number': 0.85868,
    'rand_signed_int': -7,
    'rand_datetime': '2000-06-24 13:39:18.064836',
    'text_array': [
    'a74e0c086cc649148fff6cef47a0f99a',
    'caa25f03d81c4d958f9f6c182cc71654',
],
    'words': 'ladybug bird',
    'nested': {
    'id': 141,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    [
    7,
],
    [
    8,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dog',
    'cat',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': [
    56,
],
    'rand_bool': False,
    'mixed_type': 0.45826,
    'maybe': 'whale',
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 142,
    'id_str': [
    '05',
    '12',
    '16',
],
    'text_data': '293b4b45c980401999505116b8ae62f0',
    'rand_digit': 6,
    'rand_number': 0.55303,
    'rand_signed_int': -4,
    'rand_datetime': '2000-04-08 05:30:27-0300',
    'text_array': [
    '3c863f65cea24978a16228618e6bf376',
    'b58f20069b104baa895e649e3f6e3180',
],
    'words': 'monkey goat',
    'nested': {
    'id': 142,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fox',
    'lion',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 43,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 143,
    'id_str': [
    '30',
    '08',
],
    'text_data': '209bff54d79948b298906d1f8c7cb324',
    'rand_digit': 8,
    'rand_number': 0.60929,
    'rand_signed_int': -10,
    'rand_datetime': '2000-04-26',
    'text_array': [
    '0fa99da2bddc45cf9c41e7abee03f7e2',
    'b33ab0c0070f44728693b611babe3c30',
],
    'words': 'mouse lizard',
    'nested': {
    'id': 143,
    'rand_digit': 0,
    'array': [
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
],
},
    'nested_array': [
    [
    10,
],
],
    'two_words': [
    'kangaroo',
    'snail',
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
    'mixed_type': False,
    'maybe_null': 'frog',
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 144,
    'id_str': [
    '07',
    '24',
],
    'text_data': 'e2949b05cf504d8a9692033d5c4b4922',
    'rand_digit': 6,
    'rand_number': 0.02941,
    'rand_signed_int': -6,
    'rand_datetime': '2001-01-12 00:21:43.010917-0900',
    'text_array': [
    '2cda1f97d8494e7b8da2f2b0d1319320',
    '45ed9b9077bf47dab620b595eeda9461',
],
    'words': 'cat deer',
    'nested': {
    'id': 144,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 9,
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    4,
],
],
    'two_words': [
    'snake',
    'lizard',
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
    'mixed_type': 0.43748,
    'maybe_null': 'ape',
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 145,
    'id_str': [
    '03',
],
    'text_data': '76619b8ef36b4961aab4886b2763bae7',
    'rand_digit': 1,
    'rand_number': 0.57234,
    'rand_signed_int': 10,
    'rand_datetime': '2000-02-05T16:41:10.598290',
    'text_array': [
    '86770da12c5e4e04b3976c0ee660f63d',
    '4a920bb4ea5f439a8d1e75af7bc78ba6',
],
    'words': 'cat elephant',
    'nested': {
    'id': 145,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'crab',
    'panda',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fish',
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
    '18',
],
    'text_data': 'fb4a0274748c4fe4bfbfc5671414f44c',
    'rand_digit': 7,
    'rand_number': 0.09549,
    'rand_signed_int': -8,
    'rand_datetime': '2000-09-09 03:30:09.015009',
    'text_array': [
    'a6e50c7ec0e445cfa5a1b326b1904052',
    '0a5b3346b88c42819b6acbae66f788df',
],
    'words': 'kangaroo mouse',
    'nested': {
    'id': 146,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'deer',
    'pig',
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
},
},
    {
    'id': 47,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 147,
    'id_str': [
    '22',
    '24',
    '06',
],
    'text_data': 'ccbf2b71bc2d4e259312d0b2df7befa5',
    'rand_digit': 1,
    'rand_number': 0.56504,
    'rand_signed_int': 0,
    'rand_datetime': '2000-03-06T17:35:14',
    'text_array': [
    'b9921ead0a0d439e8cc8808e3236fd21',
    '7a58e64a163541dbafd1de6470d81089',
],
    'words': 'snail whale',
    'nested': {
    'id': 147,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
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
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lion',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'lion',
    'fox',
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
    'mixed_type': 'goat',
    'maybe': 'crab',
},
},
    {
    'id': 48,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 148,
    'id_str': [
    '12',
    '28',
    '14',
    '30',
],
    'text_data': 'd895952c0add4d9193ec6e604c8278a4',
    'rand_digit': 8,
    'rand_number': 0.77589,
    'rand_signed_int': -4,
    'rand_datetime': '2000-08-20 23:58:51',
    'text_array': [
    'fc90caa8c25343d8947ac5ecf80d5fea',
    '767570f2b5d1400d951135468fd1cb5f',
],
    'words': 'cow snake',
    'nested': {
    'id': 148,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'cheetah',
    'cow',
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
    'maybe': 'sloth',
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 149,
    'id_str': [
    '27',
    '21',
    '18',
    '25',
],
    'text_data': 'ddb5edd007094d6d99a18e74247733af',
    'rand_digit': 2,
    'rand_number': 0.3491,
    'rand_signed_int': -10,
    'rand_datetime': '2000-02-20',
    'text_array': [
    'b110fc1f19a04eea83feb21d539971ad',
    'd92a72e6022240fd8f688d9ac8544bce',
],
    'words': 'bird fox',
    'nested': {
    'id': 149,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ant',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 5,
},
    {
    'nested_empty': None,
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
    'word': 'monkey',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'grasshopper',
    'scorpion',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cheetah',
    'maybe_null': 'sheep',
},
},
    {
    'id': 50,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 150,
    'id_str': [
    '08',
    '27',
],
    'text_data': 'f45209a24a1a484c905a557620244516',
    'rand_digit': 0,
    'rand_number': 0.18093,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-26 07:11',
    'text_array': [
    '4c5b9d1370d74a9f911e9789d98acfe4',
    '48c38936afc244dba15b2007f44f567a',
],
    'words': 'cow jaguar',
    'nested': {
    'id': 150,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 9,
},
],
},
    'nested_array': [
    [
    2,
],
],
    'two_words': [
    'camel',
    'ladybug',
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
    'mixed_type': None,
    'maybe_null': 'lion',
},
},
    {
    'id': 51,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 151,
    'id_str': [
    '01',
    '23',
    '03',
    '24',
],
    'text_data': 'c4b596ef64cb435d93b0064d4ce3b56b',
    'rand_digit': 3,
    'rand_number': 0.83027,
    'rand_signed_int': -9,
    'rand_datetime': '2000-03-03 13:27:58.753610',
    'text_array': [
    '122fe2d65ae04342abeec1284990251d',
    '5fc7212c0c2b4d9cba5df9314f7178c3',
],
    'words': 'elephant fish',
    'nested': {
    'id': 151,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bee',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'jaguar',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'snake',
    'hyena',
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
    'maybe': 'duck',
},
},
    {
    'id': 52,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 152,
    'id_str': [
    '26',
    '19',
    '23',
    '01',
    '14',
],
    'text_data': '930dab8433e648fc9963fed22501411c',
    'rand_digit': 1,
    'rand_number': 0.22129,
    'rand_signed_int': 10,
    'rand_datetime': '2001-01-03T07:18:59.531086',
    'text_array': [
    '04cc1a97e93b4b848e05ea315b1f1df9',
    '81e676d64d6c43a297efbf561e1db277',
],
    'words': 'bee shark',
    'nested': {
    'id': 152,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 1,
},
],
},
    'nested_array': [
    [
    -7,
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'grasshopper',
    'jaguar',
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
    'mixed_type': 6,
    'maybe': 'elephant',
    'maybe_null': 'jaguar',
},
},
    {
    'id': 53,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 153,
    'id_str': [
    '03',
    '03',
    '02',
],
    'text_data': '172d49899eb54b55888ddc395b856a67',
    'rand_digit': 9,
    'rand_number': 0.14501,
    'rand_signed_int': 0,
    'rand_datetime': '2000-06-20T22:38:52.839629',
    'text_array': [
    '4a8c6b55e91a457aa0d2f203851bad83',
    '8cf9e93863f844269a9b0bdbd9d4e66e',
],
    'words': 'goat fly',
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
    'word': 'lizard',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'spider',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ape',
    'number': 1,
},
],
},
    'nested_array': [
    [
    -3,
],
    [
    -5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'hyena',
    'whale',
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
    'maybe_null': None,
},
},
    {
    'id': 54,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 154,
    'id_str': [
    '20',
    '13',
    '15',
    '07',
    '04',
],
    'text_data': 'c4ff6d90e17d4b328bd62516441eebda',
    'rand_digit': 1,
    'rand_number': 0.52082,
    'rand_signed_int': 7,
    'rand_datetime': '2000-03-14T04:33:17.673326+0300',
    'text_array': [
    '264fb3cf15c043bebc3235a291e722e6',
    '9602f29298cb418991f0a440a0ce008e',
],
    'words': 'scorpion whale',
    'nested': {
    'id': 154,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cat',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'deer',
    'ape',
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
    'mixed_type': False,
},
},
    {
    'id': 55,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 155,
    'id_str': [
    '11',
    '04',
    '18',
],
    'text_data': '94d5426bde58455980ee8fef6411de92',
    'rand_digit': 2,
    'rand_number': 0.45269,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-09 23:16',
    'text_array': [
    '3608907239664e879f76fdde66041835',
    'f0dd803a2caf4178b5765b86772a787f',
],
    'words': 'octopus sloth',
    'nested': {
    'id': 155,
    'rand_digit': 6,
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
    'word': 'ladybug',
    'number': 3,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    1,
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ladybug',
    'mouse',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 7,
    'maybe': 'snake',
},
},
    {
    'id': 56,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 156,
    'id_str': [
],
    'text_data': 'dce48381f67b451092795b031323a4a2',
    'rand_digit': 9,
    'rand_number': 0.45995,
    'rand_signed_int': -7,
    'rand_datetime': '2000-02-23 23:01:25',
    'text_array': [
    '220d40b14e09454ea76da76ce6f41577',
    '937aaa2806a94d4c81cc7da62135b23e',
],
    'words': 'camel rhino',
    'nested': {
    'id': 156,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'duck',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'ladybug',
    'camel',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': [
    80,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'fox',
},
},
    {
    'id': 57,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 157,
    'id_str': [
    '29',
],
    'text_data': 'f2d47264b1dd4159b306c85a601cf78a',
    'rand_digit': 4,
    'rand_number': 0.73264,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-19T14:07:35.689612+1200',
    'text_array': [
    'd4ff5840509645d9b0d3c8ec36d7158d',
    'aab6c35667184a318b7e1f11b4f9713d',
],
    'words': 'bird fish',
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
    'word': 'mosquito',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'panda',
    'ladybug',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': [
    98,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'grasshopper',
    'maybe_null': None,
},
},
    {
    'id': 58,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 158,
    'id_str': [
    '18',
    '23',
    '25',
    '17',
],
    'text_data': '596262bc12244129b9e7c10f1ecfa51a',
    'rand_digit': 4,
    'rand_number': 0.47962,
    'rand_signed_int': 0,
    'rand_datetime': '2000-03-20 13:29:49+0900',
    'text_array': [
    '604cba4ea2ed4335a59ba5ab0bdb3b0f',
    '3392b9e0adfb4e3baab344836591887c',
],
    'words': 'panda tiger',
    'nested': {
    'id': 158,
    'rand_digit': 4,
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
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'monkey',
    'scorpion',
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
    'mixed_type': True,
    'maybe_null': 'spider',
},
},
    {
    'id': 59,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 159,
    'id_str': [
    '05',
    '26',
    '09',
    '10',
    '17',
],
    'text_data': 'c60d89a6470d4243847ca2a376b88e20',
    'rand_digit': 9,
    'rand_number': 0.9096,
    'rand_signed_int': 10,
    'rand_datetime': '2000-03-29T07:54:52.588211',
    'text_array': [
    '975f1a40c95140698f82657e809cb73f',
    '5c4b51f8fa78425eb3606ebe7da99c0f',
],
    'words': 'koala sloth',
    'nested': {
    'id': 159,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 7,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mosquito',
    'hyena',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': [
    4,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'ant',
    'maybe_null': 'bird',
},
},
    {
    'id': 60,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 160,
    'id_str': [
],
    'text_data': '6e855e04302548129422bb80943c57a3',
    'rand_digit': 0,
    'rand_number': 0.01208,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-13 06:39:11',
    'text_array': [
    'f8fcd4b00eb6431e87dd101761805e12',
    'a842114f5a084df49ed628f391e8eba6',
],
    'words': 'dog ant',
    'nested': {
    'id': 160,
    'rand_digit': 3,
    'array': [
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
    'word': 'scorpion',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'rabbit',
    'zebra',
],
    'city': {
    'name': 'Frankfurt',
    'geo': {
    'lat': 50.110922,
    'lon': 8.682127,
},
},
    'rand_tuple': [
    59,
],
    'rand_bool': True,
    'mixed_type': 0.39408,
    'maybe_null': 'shark',
},
},
    {
    'id': 61,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 161,
    'id_str': [
],
    'text_data': '46ee316c38174c65bb5a41ec5b68c13b',
    'rand_digit': 3,
    'rand_number': 0.85855,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-12 04:30:10',
    'text_array': [
    'be52ad0210674cf58f050d0cd0c2a62b',
    '1ef7cadd7b2b4341a1729cdf8efe889e',
],
    'words': 'lobster giraffe',
    'nested': {
    'id': 161,
    'rand_digit': 0,
    'array': [
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
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fish',
    'cow',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': [
    67,
],
    'rand_bool': True,
    'mixed_type': 0.02791,
    'maybe': 'mouse',
    'maybe_null': None,
},
},
    {
    'id': 62,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 162,
    'id_str': [
    '24',
    '05',
    '06',
],
    'text_data': 'd718e5e2bfe241b294fde6790624474b',
    'rand_digit': 2,
    'rand_number': 0.01148,
    'rand_signed_int': 7,
    'rand_datetime': '2000-03-29 05:26:11+0000',
    'text_array': [
    '8e67b22067654c41a6328adddefc4a18',
    '396dbdce8f114c199e86dd094eca8e45',
],
    'words': 'giraffe octopus',
    'nested': {
    'id': 162,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'rabbit',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    [
    -8,
],
    [
    6,
],
],
    'two_words': [
    'dolphin',
    'kangaroo',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': [
    10,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 63,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 163,
    'id_str': [
    '27',
],
    'text_data': '32ad4b92b48c4604bb3cd3c183c6b8e2',
    'rand_digit': 1,
    'rand_number': 0.7719,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-12 20:24:53-0500',
    'text_array': [
    '307ffe120070410a91412d7bb925a9d8',
    '0e4d331d0f5f43f491bac4219d3af5d5',
],
    'words': 'giraffe kangaroo',
    'nested': {
    'id': 163,
    'rand_digit': 2,
    'array': [
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
    'nested_array': [
    [
    -2,
],
],
    'two_words': [
    'bear',
    'giraffe',
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
    'mixed_type': 'scorpion',
    'maybe_null': 'shark',
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
        """测试请求 2 - PUT http://localhost:6333/collections/congruence_secondary_collection?timeout=60"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/congruence_secondary_collection?timeout=60")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/congruence_secondary_collection?timeout=60'
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
        """测试请求 3 - PUT http://localhost:6333/collections/congruence_secondary_collection/points?wait=true"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/congruence_secondary_collection/points?wait=true")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/congruence_secondary_collection/points?wait=true'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '398106',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 100,
    'id_str': [
    '19',
    '19',
],
    'text_data': '2b0fc6b12c3f4a04adfa72686597ef68',
    'rand_digit': 7,
    'rand_number': 0.00218,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-28T09:02:23.968675+11:00',
    'text_array': [
    'cd320d668aba4bbbbf9d88ce5079d2c1',
    '3245afeaa7344540a2cf0db3ff884fd6',
],
    'words': 'sloth cheetah',
    'nested': {
    'id': 100,
    'rand_digit': 4,
    'array': [
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
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'sheep',
    'cat',
],
    'city': {
    'name': 'Kharkiv',
    'geo': {
    'lat': 49.980812,
    'lon': 36.25272,
},
},
    'rand_tuple': [
    96,
],
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'whale',
    'maybe_null': 'elephant',
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 101,
    'id_str': [
    '26',
    '28',
    '29',
    '11',
    '13',
],
    'text_data': 'de729847226b4f3c877160a83632eec2',
    'rand_digit': 6,
    'rand_number': 0.10741,
    'rand_signed_int': -10,
    'rand_datetime': '2000-04-01T12:48:36.936017',
    'text_array': [
    'ff850563fef841ce8de8d7a8009d2736',
    '0a944240a8b94e8cad845d935f37c455',
],
    'words': 'whale kangaroo',
    'nested': {
    'id': 101,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 3,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'mosquito',
    'number': 7,
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
    'word': 'bird',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'deer',
    'butterfly',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'ape',
},
},
    {
    'id': 2,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 102,
    'id_str': [
    '18',
    '30',
    '05',
    '11',
],
    'text_data': '60b84679f5cb41ee83e30a848cb42b80',
    'rand_digit': 4,
    'rand_number': 0.40484,
    'rand_signed_int': 6,
    'rand_datetime': '2000-10-04 04:16:55.548283',
    'text_array': [
    '9a8c4c648c24402b94744d289769ea09',
    '661569d5ab1846289b9a0db7cdf53ee8',
],
    'words': 'snail dog',
    'nested': {
    'id': 102,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'goat',
    'horse',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': [
    35,
],
    'rand_bool': False,
    'mixed_type': 6,
    'maybe_null': None,
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 103,
    'id_str': [
    '19',
    '10',
    '16',
],
    'text_data': '714cfe969c96461cb82912b518d53632',
    'rand_digit': 3,
    'rand_number': 0.23119,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-06T10:35:07',
    'text_array': [
    'fa0c540e77d44182be5ba2cb624da734',
    'f83cd943453440419ef8548a375b6056',
],
    'words': 'elephant crab',
    'nested': {
    'id': 103,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'snake',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    5,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'cheetah',
    'deer',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': [
    91,
],
    'rand_bool': False,
    'mixed_type': 'butterfly',
    'maybe_null': 'lobster',
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 104,
    'id_str': [
],
    'text_data': '41a625dcb30143429bd08f25724c079f',
    'rand_digit': 2,
    'rand_number': 0.27068,
    'rand_signed_int': -8,
    'rand_datetime': '2000-05-10 13:17:42.787835',
    'text_array': [
    '1184b87d6a184106b7dafa07eb6dcb36',
    '6f61556384d744e99567c702c9a83b80',
],
    'words': 'sheep elephant',
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
    'word': 'hippo',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'bear',
    'sheep',
],
    'city': {
    'name': 'Seoul',
    'geo': {
    'lat': 37.566535,
    'lon': 126.977969,
},
},
    'rand_tuple': [
    0,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 105,
    'id_str': [
    '30',
    '19',
    '13',
    '30',
    '04',
],
    'text_data': '0d3378a384564387b4434fa35f1e2dd1',
    'rand_digit': 3,
    'rand_number': 0.92543,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-15T13:57:39.406574',
    'text_array': [
    'ee8166add44b4032903bfe61200273e7',
    '52b94afd3a0f479681186fd2d27a5009',
],
    'words': 'rhino pig',
    'nested': {
    'id': 105,
    'rand_digit': 9,
    'array': [
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
    'word': 'squid',
    'number': 4,
},
],
},
    'nested_array': [
    [
    5,
],
    [
    8,
],
    [
],
    [
],
],
    'two_words': [
    'lizard',
    'fly',
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
    'mixed_type': False,
    'maybe': 'bird',
    'maybe_null': 'ape',
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 106,
    'id_str': [
],
    'text_data': '511ea824834b4102b777334dd8fe6a86',
    'rand_digit': 0,
    'rand_number': 0.94247,
    'rand_signed_int': 9,
    'rand_datetime': '2000-04-12T13:08:49.529874+0500',
    'text_array': [
    '4377e7ea0a6b4730a9e232649d945330',
    'cb9d47a5d85d4ff7b3ac5ad31e025cb6',
],
    'words': 'ape jaguar',
    'nested': {
    'id': 106,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'jaguar',
    'number': 3,
},
],
},
    'nested_array': [
    [
    -3,
],
],
    'two_words': [
    'shark',
    'bird',
],
    'city': {
    'name': 'Jakarta',
    'geo': {
    'lat': -6.208763,
    'lon': 106.845599,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0,
    'maybe_null': None,
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 107,
    'id_str': [
    '05',
],
    'text_data': '4551c595d6244276bfd0f3404d5f5ff7',
    'rand_digit': 4,
    'rand_number': 0.6957,
    'rand_signed_int': -5,
    'rand_datetime': '2000-01-20T14:26:46.584938-1000',
    'text_array': [
    '8a1aeb423c5d420f88950e5587bf9679',
    '277d5613b5c9422a893714c93f0edcc0',
],
    'words': 'octopus hippo',
    'nested': {
    'id': 107,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 8,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'horse',
    'number': 1,
},
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'chicken',
    'fish',
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
    'mixed_type': 'cow',
    'maybe': 'elephant',
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 108,
    'id_str': [
    '23',
    '18',
    '24',
    '01',
    '04',
],
    'text_data': 'eaa6ab22daeb471ca2be09b876b89cbe',
    'rand_digit': 9,
    'rand_number': 0.12324,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-01T02:40:50-1000',
    'text_array': [
    'c4543c7decc247e9bf1e00a5113e8f65',
    '9690deb38a95438092ea2cd2aa0786c4',
],
    'words': 'octopus bird',
    'nested': {
    'id': 108,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'panda',
    'number': 3,
},
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
],
    'word': 'squid',
    'number': 1,
},
],
},
    'nested_array': [
    [
    10,
],
],
    'two_words': [
    'mouse',
    'giraffe',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'fly',
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 109,
    'id_str': [
    '11',
    '10',
    '02',
],
    'text_data': '4a929a184efd4aed8f0a6dff004a0587',
    'rand_digit': 7,
    'rand_number': 0.57692,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-29T07:10:57.554015',
    'text_array': [
    '39bccf90bb524c8fbeda4e13b803b218',
    '8ca1686d3b684185a9218fd55cfab609',
],
    'words': 'mouse grasshopper',
    'nested': {
    'id': 109,
    'rand_digit': 2,
    'array': [
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
    'word': 'goat',
    'number': 6,
},
],
},
    'nested_array': [
    [
    -10,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'monkey',
    'kangaroo',
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
    'mixed_type': 'elephant',
    'maybe': 'grasshopper',
    'maybe_null': 'dolphin',
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 110,
    'id_str': [
    '03',
    '13',
    '06',
    '02',
],
    'text_data': '21ee494876f44b8f90c68a002beb5f5b',
    'rand_digit': 4,
    'rand_number': 0.86111,
    'rand_signed_int': -1,
    'rand_datetime': '2000-01-23T01:48:52',
    'text_array': [
    'e141ac1df45d480e8f2c5b611c4a0dfb',
    '4d4c9ab2a8774e86b5af12818ed736d2',
],
    'words': 'lizard dolphin',
    'nested': {
    'id': 110,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 3,
},
    {
    'nested_empty': None,
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
    'word': 'rabbit',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    7,
],
],
    'two_words': [
    'scorpion',
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
    'rand_bool': True,
    'mixed_type': 0,
    'maybe': 'crab',
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 111,
    'id_str': [
    '06',
    '21',
    '06',
],
    'text_data': 'b3acce9d74be4a54a66732e15f350909',
    'rand_digit': 7,
    'rand_number': 0.83693,
    'rand_signed_int': -5,
    'rand_datetime': '2000-12-14T09:51:25.398519',
    'text_array': [
    '31775ce4bdbe4bcfa4183578c01517ab',
    '6e5d32a98d8c4c94b782fe895c1e2251',
],
    'words': 'squid kangaroo',
    'nested': {
    'id': 111,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'whale',
    'giraffe',
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
    'maybe': 'deer',
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 112,
    'id_str': [
    '03',
    '23',
    '30',
    '18',
],
    'text_data': 'c81ab7b438be41b38a355d9a8869fa75',
    'rand_digit': 7,
    'rand_number': 0.0108,
    'rand_signed_int': 7,
    'rand_datetime': '2000-09-22T20:35:22.174752',
    'text_array': [
    '04cd2fe9f9ae48b28314d63bcb4c9653',
    '1f43241604fd49a8b8a259bc0eb16be3',
],
    'words': 'kangaroo jaguar',
    'nested': {
    'id': 112,
    'rand_digit': 1,
    'array': [
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'panda',
    'dolphin',
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
    'maybe_null': 'goat',
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 113,
    'id_str': [
    '21',
    '28',
    '03',
    '21',
    '21',
],
    'text_data': '260481afe7d3400592035cbaf0654d2b',
    'rand_digit': 1,
    'rand_number': 0.50474,
    'rand_signed_int': -5,
    'rand_datetime': '2000-10-02 06:23:56+1000',
    'text_array': [
    'f7c84bde766d4404922ac49b4f1f6beb',
    '1a23d313717b4d27a57923e57f26867d',
],
    'words': 'fly panda',
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
    'word': 'ladybug',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'spider',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ant',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'scorpion',
    'snake',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': [
    0,
],
    'rand_bool': False,
    'mixed_type': 'sheep',
    'maybe_null': 'kangaroo',
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 114,
    'id_str': [
    '11',
    '30',
],
    'text_data': '20e7ac1b7e5a4e3cb16c412ef6ff02f1',
    'rand_digit': 4,
    'rand_number': 0.28712,
    'rand_signed_int': 6,
    'rand_datetime': '2001-01-16 16:49:24.198168',
    'text_array': [
    'a38dd91b3ce44bf6b68288d8fb4610d5',
    'cffb4631212d409ebec52a3afdd5aad8',
],
    'words': 'rhino monkey',
    'nested': {
    'id': 114,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -3,
],
],
    'two_words': [
    'kangaroo',
    'tiger',
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
    'mixed_type': False,
    'maybe': 'spider',
    'maybe_null': None,
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 115,
    'id_str': [
    '13',
],
    'text_data': 'f60fc871ed5641dbbf5600da64805c3d',
    'rand_digit': 4,
    'rand_number': 0.14078,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-27T12:43:36.119156-12:00',
    'text_array': [
    '53aea4d1901844f19c2f3da8ab44d950',
    'd29d098c59d942f89946c9b4a01b8a76',
],
    'words': 'lizard shark',
    'nested': {
    'id': 115,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'chicken',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'wolf',
    'lobster',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 116,
    'id_str': [
    '24',
    '12',
],
    'text_data': '8f10377b713f4c0abf55e7c29a3a96ff',
    'rand_digit': 8,
    'rand_number': 0.02028,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-21T21:21:29.174774-0200',
    'text_array': [
    'd4ee0d08112d45af9ec39debe68a262d',
    '4a4e181d38214992a8e5604309467144',
],
    'words': 'goat cow',
    'nested': {
    'id': 116,
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
    'word': 'monkey',
    'number': 10,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'mosquito',
    'number': 9,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'gorilla',
    'ladybug',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'elephant',
    'maybe_null': 'bear',
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 117,
    'id_str': [
    '20',
    '27',
    '01',
    '27',
    '19',
],
    'text_data': '8232acbbb2064c5699834bc1dc22d492',
    'rand_digit': 4,
    'rand_number': 0.94555,
    'rand_signed_int': -7,
    'rand_datetime': '2000-03-09 20:43:55',
    'text_array': [
    '4bd1cb53a1d2496bb29fbcd593323f78',
    'd982ffcb9b11461a93a555c07cd3a661',
],
    'words': 'kangaroo ant',
    'nested': {
    'id': 117,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'number': 7,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'sheep',
    'ant',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 8,
    'maybe_null': 'snail',
},
},
    {
    'id': 18,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 118,
    'id_str': [
    '06',
    '30',
],
    'text_data': '4d1c1943613e4c37bd4d0b2e9ec43179',
    'rand_digit': 0,
    'rand_number': 0.73629,
    'rand_signed_int': -8,
    'rand_datetime': '2000-02-17T02:24:02',
    'text_array': [
    '3eba0c191d894a3b99955fe0a925cc40',
    '0d8a73be5ef24b9393838f5cf8d42b73',
],
    'words': 'horse deer',
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
    'word': 'rhino',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 8,
},
],
},
    'nested_array': [
    [
    -8,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dragonfly',
    'camel',
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
    'maybe_null': 'jaguar',
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
    '20',
    '09',
],
    'text_data': '34907612f0104862987c2d9603bcc17b',
    'rand_digit': 0,
    'rand_number': 0.94318,
    'rand_signed_int': 9,
    'rand_datetime': '2000-05-03 16:19',
    'text_array': [
    '7708f38330d343098556e32b5d0302f8',
    '09f1f509d7c241a8863222b3d0e1a1e1',
],
    'words': 'crab dragonfly',
    'nested': {
    'id': 119,
    'rand_digit': 3,
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
],
    'word': 'lizard',
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
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'crab',
    'number': 6,
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
    'jaguar',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 120,
    'id_str': [
    '22',
],
    'text_data': '95deb0a0cbec4ebc8dcb23f432604fa8',
    'rand_digit': 1,
    'rand_number': 0.88403,
    'rand_signed_int': 1,
    'rand_datetime': '2000-05-19',
    'text_array': [
    'cd2e345a694c434c97c4c233e1c8a709',
    '3e6fca76ea37478e92aa34da32ebc0cd',
],
    'words': 'rhino ladybug',
    'nested': {
    'id': 120,
    'rand_digit': 3,
    'array': [
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
    'word': 'butterfly',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'squid',
    'kangaroo',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'turtle',
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 121,
    'id_str': [
],
    'text_data': '2bff5e746ac74ec69bca6fa03a707009',
    'rand_digit': 1,
    'rand_number': 0.44533,
    'rand_signed_int': 10,
    'rand_datetime': '2001-01-27 08:27:45.784092+0600',
    'text_array': [
    '7f4f074a785b42cda579340492f1ff61',
    '75254ed087cd479eb43a28e3f84e0b57',
],
    'words': 'ladybug crab',
    'nested': {
    'id': 121,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 3,
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
    [
],
    [
    -4,
],
],
    'two_words': [
    'rhino',
    'crab',
],
    'city': {
    'name': 'Helsinki',
    'geo': {
    'lat': 60.169856,
    'lon': 24.938379,
},
},
    'rand_tuple': [
    23,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'snake',
    'maybe_null': 'spider',
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
    '30',
    '08',
    '10',
    '04',
],
    'text_data': '06566d4d359749238efc8877d8884728',
    'rand_digit': 8,
    'rand_number': 0.28778,
    'rand_signed_int': 7,
    'rand_datetime': '2000-07-29T19:36:02.878274-0600',
    'text_array': [
    '8fc415d7acbd4104affb5afa285e29bf',
    'd769517ea2d84b65a5a0a1cf58275dac',
],
    'words': 'jaguar ant',
    'nested': {
    'id': 122,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'spider',
    'bear',
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
    'mixed_type': 'sheep',
    'maybe': 'kangaroo',
    'maybe_null': 'lion',
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 123,
    'id_str': [
    '03',
    '29',
    '03',
    '24',
],
    'text_data': 'f90845db1f724148a0baacfa602fe518',
    'rand_digit': 9,
    'rand_number': 0.43142,
    'rand_signed_int': -6,
    'rand_datetime': '2001-01-08T19:50:43.227848',
    'text_array': [
    '4d305e8fe4994af6a4c72645500874f1',
    '78ba002833fa4591ba5889f7e83adf6d',
],
    'words': 'ant pig',
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
    'word': 'squid',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'butterfly',
    'grasshopper',
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
    'mixed_type': 0.0527,
    'maybe': 'mosquito',
    'maybe_null': None,
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 124,
    'id_str': [
],
    'text_data': '53581bd839804b17b0489b039c5c345d',
    'rand_digit': 2,
    'rand_number': 0.66656,
    'rand_signed_int': -1,
    'rand_datetime': '2000-12-11 08:42:48',
    'text_array': [
    '6e72f0efc4d84e06993a5fa48e418829',
    'b16edfcd0d014b9d84b9e0a75bdab02c',
],
    'words': 'fish camel',
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
    'word': 'turtle',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'octopus',
    'sloth',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
    '08',
    '14',
],
    'text_data': '26d667861d6f406b80a2b4e8f810b41b',
    'rand_digit': 3,
    'rand_number': 0.77947,
    'rand_signed_int': 2,
    'rand_datetime': '2000-12-16 08:56:14-0900',
    'text_array': [
    '62d4d251e26d4f28bfd6b75d43787a60',
    'b6e6214f818145a093cd57729e8f43d4',
],
    'words': 'jaguar hippo',
    'nested': {
    'id': 125,
    'rand_digit': 5,
    'array': [
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
    'word': 'elephant',
    'number': 4,
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
],
    'word': 'fox',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'wolf',
    'monkey',
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
    'maybe': 'butterfly',
},
},
    {
    'id': 26,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 126,
    'id_str': [
    '02',
],
    'text_data': 'afa5670deab943f0a85b67fa3be3db85',
    'rand_digit': 7,
    'rand_number': 0.05356,
    'rand_signed_int': -7,
    'rand_datetime': '2000-10-31T03:30:53+0500',
    'text_array': [
    'a8d824a69ad8488987bc37941785f644',
    'd7bd6287de314cddb2c12acca08ba34e',
],
    'words': 'leopard lizard',
    'nested': {
    'id': 126,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
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
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -3,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'turtle',
    'wolf',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'panda',
    'maybe': 'goat',
    'maybe_null': 'elephant',
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 127,
    'id_str': [
    '30',
    '18',
],
    'text_data': 'ee3c92fb900f4428917fec65601d93ae',
    'rand_digit': 9,
    'rand_number': 0.75699,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-27T01:31:25.963383',
    'text_array': [
    'ecb7430052cb484ab01ce464f20e1eeb',
    'ad73308cd4e642e1a70816c108e91ba3',
],
    'words': 'pig grasshopper',
    'nested': {
    'id': 127,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    [
    -4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lobster',
    'crab',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'pig',
    'maybe_null': None,
},
},
    {
    'id': 28,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 128,
    'id_str': [
    '03',
],
    'text_data': 'fe5d7994f98a4545b4073db4f6c2772e',
    'rand_digit': 5,
    'rand_number': 0.36805,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-06 05:26:05-0600',
    'text_array': [
    '024e33bb805244b2aa3ebb1427219dd2',
    'bdae30f2c3304e36aecae7afa913f41b',
],
    'words': 'scorpion squid',
    'nested': {
    'id': 128,
    'rand_digit': 8,
    'array': [
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
    [
],
    [
    1,
],
    [
],
],
    'two_words': [
    'panda',
    'duck',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'chicken',
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
    '20',
    '09',
],
    'text_data': '891845509c874163a9c855072c7eb07c',
    'rand_digit': 0,
    'rand_number': 0.6912,
    'rand_signed_int': -5,
    'rand_datetime': '2000-03-12 11:18:56+1000',
    'text_array': [
    '1f32a9ce1e5b48b79f0ec5c6519ce9df',
    '5240988023da41dc9f874a3ede9ff0c6',
],
    'words': 'cat lion',
    'nested': {
    'id': 129,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'shark',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -6,
],
],
    'two_words': [
    'fly',
    'mosquito',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'fox',
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 130,
    'id_str': [
    '12',
    '11',
],
    'text_data': '00bc602106f140a4b870c26710c8a2aa',
    'rand_digit': 8,
    'rand_number': 0.95335,
    'rand_signed_int': 7,
    'rand_datetime': '2000-03-30T22:00:11.573566+0700',
    'text_array': [
    '99604228852047da9ec7a38d3d4e8fb3',
    '0aa44d67f7af4a248a77bc202d6b8b39',
],
    'words': 'sheep lion',
    'nested': {
    'id': 130,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 9,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ape',
    'wolf',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': [
    62,
],
    'rand_bool': False,
    'mixed_type': 0.57039,
    'maybe': 'grasshopper',
    'maybe_null': None,
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 131,
    'id_str': [
],
    'text_data': '3e31150135ef4811adcfb0e3750b813a',
    'rand_digit': 8,
    'rand_number': 0.76607,
    'rand_signed_int': -3,
    'rand_datetime': '2000-06-25 19:22',
    'text_array': [
    '3d9faba1b81c4f0f898223035e539b3f',
    'e49d7b70de8b4f8eb2d370310772af68',
],
    'words': 'rhino lion',
    'nested': {
    'id': 131,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'sheep',
    'mouse',
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
},
},
    {
    'id': 32,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 132,
    'id_str': [
    '05',
    '04',
    '22',
    '26',
    '30',
],
    'text_data': '2e4c2a2853444e8ca7eb14cd187da8bc',
    'rand_digit': 1,
    'rand_number': 0.15242,
    'rand_signed_int': 3,
    'rand_datetime': '2000-01-08 14:47:33.110168-0500',
    'text_array': [
    '5580c774e5d145dcaeb82b9c61dff026',
    '11f1f361f0d746d2813fb503258272ab',
],
    'words': 'elephant snail',
    'nested': {
    'id': 132,
    'rand_digit': 8,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    0,
],
],
    'two_words': [
    'snake',
    'sheep',
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
    'mixed_type': 'bear',
    'maybe': 'bear',
    'maybe_null': 'scorpion',
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 133,
    'id_str': [
    '25',
    '26',
],
    'text_data': 'f46e759f78244d7fa86b948370163033',
    'rand_digit': 6,
    'rand_number': 0.89836,
    'rand_signed_int': -10,
    'rand_datetime': '2000-12-15T15:11:39+0400',
    'text_array': [
    'fce898f832aa483ab7ccf53e0b12fd59',
    '95e382f9cd3b42dd97ca2451f23eb2d1',
],
    'words': 'ape giraffe',
    'nested': {
    'id': 133,
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
    'word': 'panda',
    'number': 2,
},
    {
    'nested_empty': None,
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
],
    'word': 'squid',
    'number': 3,
},
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
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'ape',
    'tiger',
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
    'mixed_type': None,
    'maybe': 'mouse',
    'maybe_null': None,
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 134,
    'id_str': [
    '24',
    '23',
],
    'text_data': '7aae2c92ce174bc09089f0ff593dd4f0',
    'rand_digit': 8,
    'rand_number': 0.40286,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-25 01:13',
    'text_array': [
    'b5e60dcdafde4931bb15233b8db50dd9',
    '22e3c815a5454b0b8ab604731ae9527e',
],
    'words': 'koala mouse',
    'nested': {
    'id': 134,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 5,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -4,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'rhino',
    'dog',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'turtle',
},
},
    {
    'id': 35,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 135,
    'id_str': [
    '06',
    '19',
    '16',
    '15',
],
    'text_data': 'b1502afd00b9433086e5be74e8beb197',
    'rand_digit': 9,
    'rand_number': 0.82166,
    'rand_signed_int': 9,
    'rand_datetime': '2001-01-01 16:07:41+0800',
    'text_array': [
    '56393a6230004555ad68ff0dfd56ecf3',
    'cf4df7f5083e49c7a1b23187934213fd',
],
    'words': 'koala ladybug',
    'nested': {
    'id': 135,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 9,
},
],
},
    'nested_array': [
    [
    -9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'bear',
    'fish',
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
    'mixed_type': 0.24799,
    'maybe_null': 'frog',
},
},
    {
    'id': 36,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 136,
    'id_str': [
    '30',
    '18',
    '13',
    '28',
],
    'text_data': 'f0b83d85507f493cb06add04a823c565',
    'rand_digit': 9,
    'rand_number': 0.76383,
    'rand_signed_int': 10,
    'rand_datetime': '2000-09-17T08:56:06',
    'text_array': [
    '883dcb275fba42839b6892fbfeae6c45',
    '848f4823b62b4b7ba0171eb9574cce15',
],
    'words': 'shark wolf',
    'nested': {
    'id': 136,
    'rand_digit': 6,
    'array': [
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'wolf',
    'duck',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bird',
    'maybe_null': None,
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
    '04',
    '27',
    '23',
    '14',
],
    'text_data': 'f902002a98354c6ca51e0b9f7d46d877',
    'rand_digit': 2,
    'rand_number': 0.03997,
    'rand_signed_int': -6,
    'rand_datetime': '2000-01-29T11:59:45',
    'text_array': [
    '7b002b4c2502480682a1c59488c8cdf0',
    '451156d1e21c4544ab779f6789951a43',
],
    'words': 'lobster cat',
    'nested': {
    'id': 137,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    [
    6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'tiger',
    'sloth',
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
    'mixed_type': True,
    'maybe_null': 'mouse',
},
},
    {
    'id': 38,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 138,
    'id_str': [
    '17',
    '05',
    '19',
],
    'text_data': '199c82e61b06459e8412af978a4df87c',
    'rand_digit': 4,
    'rand_number': 0.29058,
    'rand_signed_int': 8,
    'rand_datetime': '2000-04-15T02:36:13-0800',
    'text_array': [
    '3729574d9a1542228f8acf6602e28c71',
    'c448825853894951803c23eb4067b2f1',
],
    'words': 'snake zebra',
    'nested': {
    'id': 138,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 4,
},
    {
    'nested_empty': None,
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
    'word': 'mosquito',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'zebra',
    'dolphin',
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
    'mixed_type': None,
    'maybe': 'mouse',
    'maybe_null': 'lobster',
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 139,
    'id_str': [
    '10',
    '01',
],
    'text_data': '8f95ba6cf2c14aa994c7fc53513681ab',
    'rand_digit': 7,
    'rand_number': 0.70671,
    'rand_signed_int': -6,
    'rand_datetime': '2000-04-06 18:57:47-0300',
    'text_array': [
    'eeb5d45f9c3a45e28080fe81da3f5879',
    '5cbd20fe4ddd457da8bea0ade37e8f37',
],
    'words': 'tiger fox',
    'nested': {
    'id': 139,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    [
    -3,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'zebra',
    'cow',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 140,
    'id_str': [
    '07',
    '17',
    '29',
    '03',
    '22',
],
    'text_data': '7a814c3925e24d4799d31b5cd8e98067',
    'rand_digit': 2,
    'rand_number': 0.47135,
    'rand_signed_int': 4,
    'rand_datetime': '2000-11-11 17:31:21.771692',
    'text_array': [
    '9d32c9ce174e40ebae711ae7cebb0f7d',
    'f822950a82924354933dd007c39bc6c6',
],
    'words': 'gorilla snail',
    'nested': {
    'id': 140,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'sheep',
    'number': 9,
},
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
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'hippo',
    'spider',
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
    'mixed_type': 0.50976,
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 141,
    'id_str': [
    '22',
    '07',
],
    'text_data': 'ec2e1e53655c4272a92e1f97cdd5b86c',
    'rand_digit': 6,
    'rand_number': 0.20669,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-31T20:09:45+1000',
    'text_array': [
    '16632190a71a44c68944ff51573a1fa0',
    '062ae2cde3a9448eb4781d4f95d5b332',
],
    'words': 'rabbit cheetah',
    'nested': {
    'id': 141,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'hyena',
    'butterfly',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': [
    29,
],
    'rand_bool': False,
    'mixed_type': 1,
    'maybe_null': 'cheetah',
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 142,
    'id_str': [
],
    'text_data': '1d05dfd9d4d9405893200b6b152b38b3',
    'rand_digit': 9,
    'rand_number': 0.01495,
    'rand_signed_int': 10,
    'rand_datetime': '2000-08-18 11:29',
    'text_array': [
    '1b7489d33fc643808b20b6f0da3fe931',
    '95b280b5208d47579dc8acb833972cea',
],
    'words': 'snake horse',
    'nested': {
    'id': 142,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'scorpion',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
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
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'rhino',
    'leopard',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'pig',
    'maybe': 'hippo',
    'maybe_null': 'shark',
},
},
    {
    'id': 43,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 143,
    'id_str': [
    '30',
    '11',
    '13',
    '19',
    '19',
],
    'text_data': '251a4314d74740b1800ac45eb136df04',
    'rand_digit': 1,
    'rand_number': 0.85069,
    'rand_signed_int': -2,
    'rand_datetime': '2000-01-17T23:50:48.412155',
    'text_array': [
    'cd5e9577386c4078b55bd65f27901047',
    '1914d225fd9248b9aeff1350838d6637',
],
    'words': 'squid squid',
    'nested': {
    'id': 143,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 3,
},
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
    'word': 'monkey',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'horse',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'gorilla',
    'lobster',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'turtle',
    'maybe_null': 'kangaroo',
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 144,
    'id_str': [
    '19',
],
    'text_data': '8b7bb1c5fa3b4b18b2dd0de6758b4703',
    'rand_digit': 6,
    'rand_number': 0.25415,
    'rand_signed_int': 9,
    'rand_datetime': '2000-01-07 04:47:12',
    'text_array': [
    '111b7b4bb7be42c2bf3ab121ed3299df',
    '0ce606270a834238b162c53ab43d2b39',
],
    'words': 'shark koala',
    'nested': {
    'id': 144,
    'rand_digit': 5,
    'array': [
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
    'word': 'monkey',
    'number': 2,
},
],
},
    'nested_array': [
    [
    -9,
],
],
    'two_words': [
    'cheetah',
    'camel',
],
    'city': {
    'name': 'Copenhagen',
    'geo': {
    'lat': 55.676097,
    'lon': 12.568337,
},
},
    'rand_tuple': [
    12,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'leopard',
    'maybe_null': 'mosquito',
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 145,
    'id_str': [
],
    'text_data': 'ae8212c999fc401087ef4870867b1732',
    'rand_digit': 8,
    'rand_number': 0.92801,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-18T21:58:27.499415+0400',
    'text_array': [
    '14bed874d5014a07855e6abe0ece1d9f',
    '764392c9b3354bf5b94ba5ac9fa89333',
],
    'words': 'giraffe mosquito',
    'nested': {
    'id': 145,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
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
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'sheep',
    'cheetah',
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
    'mixed_type': 'turtle',
    'maybe': 'koala',
    'maybe_null': None,
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
    '04',
    '05',
    '25',
],
    'text_data': '14d33820ec63419789491038091b8c78',
    'rand_digit': 3,
    'rand_number': 0.25101,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-02T18:59:30.494702+11:00',
    'text_array': [
    'ca800b97b53f407baf6b1eb8d1c3bf5a',
    'e7566c67cc34409d96171a282f700e33',
],
    'words': 'ape dragonfly',
    'nested': {
    'id': 146,
    'rand_digit': 4,
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
    'word': 'hyena',
    'number': 3,
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
],
},
    'nested_array': [
    [
    -2,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'cat',
    'cow',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'tiger',
    'maybe_null': 'dog',
},
},
    {
    'id': 47,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 147,
    'id_str': [
    '06',
],
    'text_data': '840586827d9a44838eb60c8b65aa1151',
    'rand_digit': 4,
    'rand_number': 0.501,
    'rand_signed_int': -10,
    'rand_datetime': '2000-08-13T08:11:08.077772',
    'text_array': [
    '2b9085d533d5425b962aebadce489c49',
    'bb4944dd4c874da8a56fc8d600718ffa',
],
    'words': 'goat panda',
    'nested': {
    'id': 147,
    'rand_digit': 4,
    'array': [
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'rabbit',
    'fish',
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
    'mixed_type': None,
    'maybe': 'squid',
},
},
    {
    'id': 48,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 148,
    'id_str': [
    '17',
    '16',
    '21',
    '25',
    '09',
],
    'text_data': 'ba79d8a042894099b05aa34706f0ec6b',
    'rand_digit': 6,
    'rand_number': 0.49138,
    'rand_signed_int': 10,
    'rand_datetime': '2000-11-24T22:31:09+0700',
    'text_array': [
    'e75e87731ca4441f8efa5b8f45629fd2',
    'f7405d7281eb4a39a8293622d3bf4d36',
],
    'words': 'jaguar dog',
    'nested': {
    'id': 148,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'horse',
    'fly',
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
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 149,
    'id_str': [
    '11',
    '10',
    '15',
],
    'text_data': '3009d88feea84580bdd0ee757f80eae4',
    'rand_digit': 7,
    'rand_number': 0.44659,
    'rand_signed_int': 3,
    'rand_datetime': '2000-05-27',
    'text_array': [
    'cf3e3cd9ff0d40eb8a4a797239a4af3d',
    'ba5e072c5fef4136a8fdc7f5ce0fa478',
],
    'words': 'goat giraffe',
    'nested': {
    'id': 149,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'leopard',
    'rhino',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'rhino',
    'maybe_null': 'scorpion',
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
        """测试请求 4 - POST http://localhost:6333/collections/congruence_test_collection/points/query"""
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
    'content-length': '34481',
}
        
        # 原始请求内容
        original_content = {
    'query': {
    'context': [
    {
    'positive': 11,
    'negative': 19,
},
    {
    'positive': 42,
    'negative': 50,
},
    {
    'positive': '__FLOAT_MULTI_DIM_20,100__',
    'negative': '__FLOAT_MULTI_DIM_9,100__',
},
    {
    'positive': 30,
    'negative': '__FLOAT_MULTI_DIM_9,100__',
},
    {
    'positive': '__FLOAT_MULTI_DIM_20,100__',
    'negative': 15,
},
],
},
    'using': 'multi-image',
    'limit': 100,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_multivector_discovery_queries.test_context_many_pairs')
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
    test = TestMultivectorDiscoveryQueriestestContextManyPairs()
    test.run_tests()
