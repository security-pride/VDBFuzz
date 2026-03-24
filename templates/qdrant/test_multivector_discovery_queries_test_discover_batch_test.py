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
logger = logging.getLogger('vdb_fuzzer.test.test_multivector_discovery_queries_test_discover_batch')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_multivector_discovery_queries.test_discover_batch"
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



class TestMultivectorDiscoveryQueriestestDiscoverBatch:
    """自动生成的VDB模糊测试类 - test_multivector_discovery_queries.test_discover_batch"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_multivector_discovery_queries.test_discover_batch"
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
    'content-length': '521487',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 100,
    'id_str': [
],
    'text_data': 'fea269d9d9f649c9a29b0ea0cd0208b8',
    'rand_digit': 1,
    'rand_number': 0.43629,
    'rand_signed_int': 9,
    'rand_datetime': '2000-03-14T20:01:48.179443-0400',
    'text_array': [
    '8b08d0bd9b7549f488e7a38996ffae0c',
    '57a2386a9f0543bc8b4772cdb8954c44',
],
    'words': 'leopard leopard',
    'nested': {
    'id': 100,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bee',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'kangaroo',
    'spider',
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
    'mixed_type': 8,
    'maybe_null': 'fly',
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 101,
    'id_str': [
    '04',
    '26',
],
    'text_data': '89d5a31a5f5248cd9333774106b58803',
    'rand_digit': 1,
    'rand_number': 0.96076,
    'rand_signed_int': -5,
    'rand_datetime': '2000-08-10 21:00:58.626646+0600',
    'text_array': [
    '5f566faf744044b0b5975c69030601a4',
    '8e499f5bdd0746ee9b49f40d276fc29d',
],
    'words': 'mouse ladybug',
    'nested': {
    'id': 101,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'hippo',
    'giraffe',
],
    'city': {
    'name': 'Zurich',
    'geo': {
    'lat': 47.376887,
    'lon': 8.541694,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.65773,
    'maybe_null': 'snail',
},
},
    {
    'id': 2,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 102,
    'id_str': [
],
    'text_data': '7495f79105414aaabd7fc0ff4e501a9e',
    'rand_digit': 1,
    'rand_number': 0.05596,
    'rand_signed_int': 6,
    'rand_datetime': '2000-08-08T21:52:40-1000',
    'text_array': [
    '3ff4555f24a546d987404f7bd3896c08',
    '60868c8b90f64c17907ac1c4f6f03902',
],
    'words': 'octopus fox',
    'nested': {
    'id': 102,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -5,
],
],
    'two_words': [
    'snake',
    'crab',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': [
    38,
],
    'rand_bool': False,
    'mixed_type': None,
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 103,
    'id_str': [
    '16',
    '03',
    '24',
    '05',
],
    'text_data': '4174a3b895394e868df89786d7da0aad',
    'rand_digit': 8,
    'rand_number': 0.15432,
    'rand_signed_int': -5,
    'rand_datetime': '2000-12-30 01:11:54.912626',
    'text_array': [
    '6bbfdb3e3c9d41799a025f34941e48f2',
    '4b5745c7e9014f72a3c7961932bce8fe',
],
    'words': 'mouse lion',
    'nested': {
    'id': 103,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'jaguar',
    'bear',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': [
    75,
],
    'rand_bool': True,
    'mixed_type': 'butterfly',
    'maybe': 'jaguar',
    'maybe_null': 'bee',
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 104,
    'id_str': [
    '11',
    '13',
    '14',
    '10',
],
    'text_data': '0636c92ea4894191879390374fcfd336',
    'rand_digit': 8,
    'rand_number': 0.34155,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-04T13:44:55.396503',
    'text_array': [
    '3bf2de7183b44925b5aad219ca6007f9',
    'f87b2dc3969a41158b07646224c001af',
],
    'words': 'bird fox',
    'nested': {
    'id': 104,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'monkey',
    'rabbit',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'dog',
    'maybe_null': 'frog',
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 105,
    'id_str': [
],
    'text_data': '9eb6cfc4845b4ddeae28423d775c0acf',
    'rand_digit': 5,
    'rand_number': 0.62138,
    'rand_signed_int': 7,
    'rand_datetime': '2000-10-15T18:53:28.305463-1100',
    'text_array': [
    '833a648b254047799c1e891be5c33214',
    '0a75449ad8684a1d9f6ff262a32cbfb9',
],
    'words': 'chicken dragonfly',
    'nested': {
    'id': 105,
    'rand_digit': 4,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fox',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'wolf',
    'ladybug',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': [
    39,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 106,
    'id_str': [
    '18',
    '22',
    '29',
],
    'text_data': '3e9a484542824a8780cc706032180078',
    'rand_digit': 3,
    'rand_number': 0.34355,
    'rand_signed_int': 1,
    'rand_datetime': '2000-12-10 22:43:09-1000',
    'text_array': [
    '1ff306ca9d944d1ab54078f550f9fd34',
    '3b553eb8d8274d1389cbb8d85db61240',
],
    'words': 'rabbit ape',
    'nested': {
    'id': 106,
    'rand_digit': 4,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'tiger',
    'number': 7,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'crab',
    'snail',
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
    'mixed_type': None,
    'maybe': 'camel',
    'maybe_null': 'monkey',
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 107,
    'id_str': [
    '11',
    '17',
    '13',
],
    'text_data': '8b68ca8d1cfb4a7aac44845c476f0969',
    'rand_digit': 1,
    'rand_number': 0.18402,
    'rand_signed_int': -2,
    'rand_datetime': '2001-01-22T02:01:24.712468',
    'text_array': [
    'b4643da69a9448e4acc43a32c0cdd4be',
    '8ac340d286654f47bf457c30d13637bf',
],
    'words': 'mosquito bird',
    'nested': {
    'id': 107,
    'rand_digit': 4,
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
    'word': 'ant',
    'number': 5,
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
    'word': 'snail',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    7,
],
    [
],
],
    'two_words': [
    'elephant',
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
    56,
],
    'rand_bool': False,
    'mixed_type': 0.99954,
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 108,
    'id_str': [
],
    'text_data': 'aa1836c7db544d9f841c8abff7e036ec',
    'rand_digit': 0,
    'rand_number': 0.55508,
    'rand_signed_int': -3,
    'rand_datetime': '2000-04-21 22:32:47.684390',
    'text_array': [
    '26321b8016574a8c85e8a1de38922641',
    'edacda0ade7e4aecbeab8f5dde5ec737',
],
    'words': 'ape squid',
    'nested': {
    'id': 108,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'camel',
    'camel',
],
    'city': {
    'name': 'Riga',
    'geo': {
    'lat': 56.949649,
    'lon': 24.105186,
},
},
    'rand_tuple': [
    76,
],
    'rand_bool': False,
    'mixed_type': 0.14808,
    'maybe': 'hippo',
    'maybe_null': 'hyena',
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 109,
    'id_str': [
    '26',
    '09',
],
    'text_data': '90bd6ff8ca55446ba86b2f0596f8cd42',
    'rand_digit': 2,
    'rand_number': 0.01841,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-14 22:35:58.435052+0400',
    'text_array': [
    '36e7fdbe1f6241b6ac044cac9a23834d',
    'b0798ac092ba4fcfbfc0550ffbb1518d',
],
    'words': 'fish camel',
    'nested': {
    'id': 109,
    'rand_digit': 8,
    'array': [
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'camel',
    'bear',
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
    'mixed_type': False,
    'maybe_null': None,
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 110,
    'id_str': [
    '30',
    '17',
    '17',
    '01',
],
    'text_data': 'fb0b9836ffa747db8e44495dd028f7d7',
    'rand_digit': 8,
    'rand_number': 0.92355,
    'rand_signed_int': -4,
    'rand_datetime': '2000-09-06',
    'text_array': [
    '5feaf3fb59204ab4881ccbdbfa76b978',
    '60394c975a6a485caac9e4a933470170',
],
    'words': 'fish pig',
    'nested': {
    'id': 110,
    'rand_digit': 5,
    'array': [
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
    'word': 'rhino',
    'number': 1,
},
    {
    'nested_empty': None,
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
],
    'word': 'crab',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -6,
],
],
    'two_words': [
    'pig',
    'ape',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': [
    11,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'giraffe',
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 111,
    'id_str': [
    '01',
    '11',
    '13',
],
    'text_data': '6818590412a246c2aa9aadba15a3df75',
    'rand_digit': 1,
    'rand_number': 0.43405,
    'rand_signed_int': -9,
    'rand_datetime': '2000-06-27 20:57:30.908048-0300',
    'text_array': [
    'bb4531a2c06343d6aba9129b7233e8d0',
    '4d37f1cd4b8a435899d0e5e3a4dcda2c',
],
    'words': 'dolphin ape',
    'nested': {
    'id': 111,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    5,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dog',
    'dolphin',
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
    'mixed_type': None,
    'maybe': 'ant',
    'maybe_null': 'kangaroo',
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 112,
    'id_str': [
    '16',
],
    'text_data': '39fb2aa8092c4a97ae4759e8b2b0e3e2',
    'rand_digit': 6,
    'rand_number': 0.14165,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-03T14:51:34.016873',
    'text_array': [
    '0abc5b5c98bb4d4da123aedf763d21b2',
    '7d73b5e9dfc442158d4338530fa69185',
],
    'words': 'turtle wolf',
    'nested': {
    'id': 112,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'turtle',
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
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 7,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'snake',
    'sheep',
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
    'mixed_type': 0.47267,
    'maybe': 'frog',
    'maybe_null': 'ape',
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 113,
    'id_str': [
    '05',
    '05',
    '10',
    '10',
],
    'text_data': 'f762120deddb407d84a9df3ed766d88a',
    'rand_digit': 1,
    'rand_number': 0.48781,
    'rand_signed_int': -3,
    'rand_datetime': '2000-05-21',
    'text_array': [
    'f0670e2e94e54b37849cdf15039f47ec',
    'd6837e0b369245c8ac5dff2fb1dbfe4a',
],
    'words': 'cat bear',
    'nested': {
    'id': 113,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 7,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'horse',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': [
    14,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'goat',
    'maybe_null': None,
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 114,
    'id_str': [
    '26',
    '16',
    '18',
    '29',
],
    'text_data': '882cf87d3e294b88a4aeddab429d2f4c',
    'rand_digit': 2,
    'rand_number': 0.5624,
    'rand_signed_int': -9,
    'rand_datetime': '2000-09-15T01:26:03.991693',
    'text_array': [
    '3834435dbb584e7fa83c7555644bf1cf',
    '2f49a966d3914d55ba25cd53d986915f',
],
    'words': 'butterfly sheep',
    'nested': {
    'id': 114,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'fish',
    'frog',
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
    'mixed_type': None,
    'maybe': 'dolphin',
    'maybe_null': 'jaguar',
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 115,
    'id_str': [
],
    'text_data': '2bbe590554cb4941acb06e04b9874bda',
    'rand_digit': 5,
    'rand_number': 0.06594,
    'rand_signed_int': -10,
    'rand_datetime': '2000-04-05 23:04:35.104262',
    'text_array': [
    '369448fedcd240aba661a538c94ff8e1',
    'dba97bdcf4f64d21b676964007f6a1df',
],
    'words': 'turtle giraffe',
    'nested': {
    'id': 115,
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
    'number': 1,
},
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fly',
    'crab',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'butterfly',
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 116,
    'id_str': [
    '01',
    '07',
    '07',
    '24',
],
    'text_data': 'f932d798c32d415c97e32af9bed8f430',
    'rand_digit': 4,
    'rand_number': 0.98451,
    'rand_signed_int': -9,
    'rand_datetime': '2000-09-15 03:38',
    'text_array': [
    'ca5c947dca6246d7b75eefa92365d583',
    '20fcb2c45a054e1eb5c60e04964307cb',
],
    'words': 'bird bee',
    'nested': {
    'id': 116,
    'rand_digit': 7,
    'array': [
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
],
    'word': 'fish',
    'number': 9,
},
    {
    'nested_empty': None,
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
    'word': 'frog',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    3,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cheetah',
    'deer',
],
    'city': {
    'name': 'Johannesburg',
    'geo': {
    'lat': -26.204103,
    'lon': 28.047305,
},
},
    'rand_tuple': [
    41,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'fox',
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 117,
    'id_str': [
    '03',
    '10',
    '26',
],
    'text_data': '9787f35420c14612abb563ffd57f4f06',
    'rand_digit': 9,
    'rand_number': 0.83343,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-11T22:58:13.677521+0500',
    'text_array': [
    '6f3f83f28d964e84999d6c108d801b45',
    '04872fdd13324d7882093fb2d15b8ef8',
],
    'words': 'cow goat',
    'nested': {
    'id': 117,
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
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'butterfly',
    'elephant',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 18,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 118,
    'id_str': [
    '27',
    '07',
    '28',
],
    'text_data': 'b2bfd370f6fa4a27a973af90ed88f110',
    'rand_digit': 1,
    'rand_number': 0.50475,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-04T02:52:42.061992+07:00',
    'text_array': [
    'a5450745618a4c6abedde2f747ae3639',
    '4fbadd2ca3704d939dacfa9cbae305cd',
],
    'words': 'sloth fly',
    'nested': {
    'id': 118,
    'rand_digit': 0,
    'array': [
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
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'dog',
    'cow',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bee',
    'maybe_null': 'koala',
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
    '17',
    '01',
    '30',
    '06',
    '22',
],
    'text_data': 'e8c0730f3d2b4a47a8c1bfa3c98e8335',
    'rand_digit': 6,
    'rand_number': 0.97425,
    'rand_signed_int': 1,
    'rand_datetime': '2000-07-18T21:18:50-0600',
    'text_array': [
    'e26fa683cf5e4a428e96ea1d23990410',
    '68386a5cc7874e5b865b7443b596525a',
],
    'words': 'mouse wolf',
    'nested': {
    'id': 119,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'hyena',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ladybug',
    'whale',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 120,
    'id_str': [
    '14',
    '19',
],
    'text_data': '1081393e41434a3e8433b7212e862d9e',
    'rand_digit': 3,
    'rand_number': 0.68256,
    'rand_signed_int': -9,
    'rand_datetime': '2000-08-21T17:56:59.537415',
    'text_array': [
    'c9af4d9b90c54fd88950c319bb969002',
    '1bb8a524e2ff474da507523c3526ec2c',
],
    'words': 'spider mouse',
    'nested': {
    'id': 120,
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
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'hippo',
    'turtle',
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
    'mixed_type': True,
    'maybe_null': 'fish',
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 121,
    'id_str': [
],
    'text_data': 'd1eb4531c945403cadb90c790acb3667',
    'rand_digit': 0,
    'rand_number': 0.73536,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-01 10:49',
    'text_array': [
    '0f053a6cadcc42e0b718c67377845a57',
    '7e637a96d2e64dab9d1a2d955d9ee837',
],
    'words': 'bee bird',
    'nested': {
    'id': 121,
    'rand_digit': 8,
    'array': [
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    4,
],
],
    'two_words': [
    'whale',
    'sloth',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'sheep',
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
    '10',
    '07',
    '11',
    '22',
],
    'text_data': 'be4673666857438281b31ffbb25f0a89',
    'rand_digit': 9,
    'rand_number': 0.9816,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-28 21:27:16.251761',
    'text_array': [
    '5fc4fad58f8243e796007fe078d1f1d8',
    '43aaa5a67b3246ae995ccc423774783c',
],
    'words': 'dolphin zebra',
    'nested': {
    'id': 122,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'butterfly',
    'fish',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'deer',
    'maybe_null': 'camel',
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 123,
    'id_str': [
    '25',
],
    'text_data': 'e8fe4073608e4630b4b4ba1e1cb27a03',
    'rand_digit': 7,
    'rand_number': 0.67471,
    'rand_signed_int': -8,
    'rand_datetime': '2000-08-24T12:48:04',
    'text_array': [
    '933e3b6654f94764a479e9aad8bcf5cc',
    'f98fa44b780d485abd32370c5a62306e',
],
    'words': 'spider butterfly',
    'nested': {
    'id': 123,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'hyena',
    'bird',
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
    'mixed_type': 7,
    'maybe': 'scorpion',
    'maybe_null': 'koala',
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 124,
    'id_str': [
    '04',
    '29',
    '22',
    '07',
],
    'text_data': '41f002d2c77d47c8a278dacf95d44796',
    'rand_digit': 3,
    'rand_number': 0.34628,
    'rand_signed_int': 9,
    'rand_datetime': '2000-05-26 11:19',
    'text_array': [
    '4612765cb61340a38637fc87ed7644ec',
    '34d04bb905ac4a9fbdf581b61ab0b5f9',
],
    'words': 'mouse bird',
    'nested': {
    'id': 124,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 1,
},
    {
    'nested_empty': None,
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
    'word': 'cheetah',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'goat',
    'fly',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'horse',
    'maybe_null': 'turtle',
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
],
    'text_data': '187610adacb14ac4bd40310205e5c6d3',
    'rand_digit': 8,
    'rand_number': 0.62299,
    'rand_signed_int': 2,
    'rand_datetime': '2000-11-09',
    'text_array': [
    'ee528881149846ef8fe291ae1b44f811',
    '7e17045facab4962bf3bf76a577e8db4',
],
    'words': 'hyena frog',
    'nested': {
    'id': 125,
    'rand_digit': 2,
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
    'hello',
],
    'word': 'zebra',
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
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fox',
    'hippo',
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
    'maybe_null': 'monkey',
},
},
    {
    'id': 26,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 126,
    'id_str': [
],
    'text_data': 'c2d4ecd45111473eb01d9c0b0488ba48',
    'rand_digit': 6,
    'rand_number': 0.36613,
    'rand_signed_int': -4,
    'rand_datetime': '2000-12-28 17:23:01',
    'text_array': [
    'b5eb9d0f6aa442c7ab427c5c036bb09c',
    '8bc74a8c257348d384b10c8aa93eccca',
],
    'words': 'spider wolf',
    'nested': {
    'id': 126,
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
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dog',
    'number': 10,
},
    {
    'nested_empty': None,
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
    'word': 'squid',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'dog',
    'bird',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.02873,
    'maybe': 'dolphin',
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 127,
    'id_str': [
    '10',
    '26',
    '23',
],
    'text_data': 'dc2d0dcccd754a7e88054726960cc190',
    'rand_digit': 9,
    'rand_number': 0.47122,
    'rand_signed_int': -4,
    'rand_datetime': '2000-09-14T23:08:54.531917-07:00',
    'text_array': [
    '1bade942d8b047b08bab45aae1c952a8',
    'aca7bdb29b7345a99ef4489d6a96b079',
],
    'words': 'panda horse',
    'nested': {
    'id': 127,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'spider',
    'mouse',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 28,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 128,
    'id_str': [
    '02',
    '22',
    '24',
],
    'text_data': '4eb78a1541c24a6d80799cf500fbadef',
    'rand_digit': 5,
    'rand_number': 0.51824,
    'rand_signed_int': 0,
    'rand_datetime': '2000-06-06T06:09:10.256309',
    'text_array': [
    'd208a948700c488f97569223c4fdb504',
    '2a7c599e972f4372bb22bff0bb455458',
],
    'words': 'dolphin horse',
    'nested': {
    'id': 128,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'hippo',
    'panda',
],
    'city': {
    'name': 'Lisbon',
    'geo': {
    'lat': 38.722252,
    'lon': -9.139337,
},
},
    'rand_tuple': [
    84,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'pig',
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
],
    'text_data': '6f7cc500395941b68b22211f8d7f29d0',
    'rand_digit': 4,
    'rand_number': 0.25334,
    'rand_signed_int': 10,
    'rand_datetime': '2000-12-19T02:56:06+0600',
    'text_array': [
    '86c397e310c64f53a74cdd43d5f24d6b',
    'a694c05a2054447394dd58209451e5ae',
],
    'words': 'leopard squid',
    'nested': {
    'id': 129,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'chicken',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'fly',
    'crab',
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
    'mixed_type': 0.28381,
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 130,
    'id_str': [
    '07',
    '04',
    '11',
    '09',
],
    'text_data': 'd3070736b22946449c5de5f98179532e',
    'rand_digit': 2,
    'rand_number': 0.16711,
    'rand_signed_int': 9,
    'rand_datetime': '2000-12-30T03:14:47',
    'text_array': [
    'd8cd93f6895146998b322683ea29bd1b',
    '3c4dc7b75612450da930eeefda3f556a',
],
    'words': 'bear jaguar',
    'nested': {
    'id': 130,
    'rand_digit': 2,
    'array': [
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
    [
],
],
    'two_words': [
    'shark',
    'gorilla',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'fish',
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 131,
    'id_str': [
    '12',
    '18',
    '12',
],
    'text_data': '80eba8ac281241f38f90f15cf73e6718',
    'rand_digit': 4,
    'rand_number': 0.35156,
    'rand_signed_int': 4,
    'rand_datetime': '2000-12-23T03:21:07.129611',
    'text_array': [
    'f688a2286cad4ebbb025ff36c22abb0b',
    '16f01a19c8234a2e8865f4d0ac950088',
],
    'words': 'ape butterfly',
    'nested': {
    'id': 131,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'leopard',
    'number': 7,
},
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'panda',
    'scorpion',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
},
},
    'rand_tuple': [
    59,
],
    'rand_bool': False,
    'mixed_type': 6,
    'maybe_null': None,
},
},
    {
    'id': 32,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 132,
    'id_str': [
    '11',
    '03',
    '01',
    '03',
    '20',
],
    'text_data': '4d19ea5c258e4b77a81dd2d2d9d41127',
    'rand_digit': 8,
    'rand_number': 0.90695,
    'rand_signed_int': -3,
    'rand_datetime': '2000-10-19 23:45:44+0200',
    'text_array': [
    '82043b89f0bb4d61a99b00d126215285',
    '9eb221afebf24f6588651f427eb487fb',
],
    'words': 'squid monkey',
    'nested': {
    'id': 132,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 4,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'kangaroo',
    'fly',
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
    'mixed_type': 0.96227,
    'maybe': 'turtle',
    'maybe_null': 'fox',
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 133,
    'id_str': [
    '17',
    '26',
    '15',
    '17',
],
    'text_data': 'f7ed40317dd64ecea383d0c0857a2380',
    'rand_digit': 9,
    'rand_number': 0.18844,
    'rand_signed_int': 3,
    'rand_datetime': '2000-02-10 19:55:45.455661+1100',
    'text_array': [
    '38c61e49edc2405392c82084001ebff5',
    '304a8797aaed446bbc18cd1d2c4d359b',
],
    'words': 'sheep bear',
    'nested': {
    'id': 133,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sloth',
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
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
],
    [
],
],
    'two_words': [
    'sheep',
    'rhino',
],
    'city': {
    'name': 'Birmingham',
    'geo': {
    'lat': 52.486243,
    'lon': -1.890401,
},
},
    'rand_tuple': [
    92,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'rabbit',
    'maybe_null': None,
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 134,
    'id_str': [
    '13',
    '25',
    '02',
    '07',
    '05',
],
    'text_data': '8aa4293a905847da9cc3b49f0627df9a',
    'rand_digit': 7,
    'rand_number': 0.97093,
    'rand_signed_int': -6,
    'rand_datetime': '2000-05-15T08:13:06.737688',
    'text_array': [
    'f6de5cd75e3c408b8d2ef5293131cb80',
    '8467e50d6ad1409e85fb9828c445c5ec',
],
    'words': 'duck zebra',
    'nested': {
    'id': 134,
    'rand_digit': 2,
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
],
    'word': 'sheep',
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
    [
    9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lion',
    'leopard',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
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
    'id': 35,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 135,
    'id_str': [
    '17',
    '19',
],
    'text_data': '9a4cf88e2c694f3aac9775374f2ec20c',
    'rand_digit': 3,
    'rand_number': 0.19184,
    'rand_signed_int': 2,
    'rand_datetime': '2000-09-01 06:01',
    'text_array': [
    '13076aa74fec41d6bcd39dc4cf936572',
    '9460d68176de4182a27738ff39a7e0ca',
],
    'words': 'duck leopard',
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
    'word': 'fly',
    'number': 8,
},
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 1,
},
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
    'word': 'scorpion',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    [
    -3,
],
],
    'two_words': [
    'mosquito',
    'pig',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'snake',
},
},
    {
    'id': 36,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 136,
    'id_str': [
    '12',
],
    'text_data': '94856f1ba0944f3183236a2ff2519d7b',
    'rand_digit': 5,
    'rand_number': 0.56008,
    'rand_signed_int': -2,
    'rand_datetime': '2000-01-11 11:21:53',
    'text_array': [
    '3540b98b8b784475a048b4eeaf127f0f',
    'a1325c5f69c1463fa1b1f51588916ff0',
],
    'words': 'duck kangaroo',
    'nested': {
    'id': 136,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 5,
},
    {
    'nested_empty': None,
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
    'word': 'cheetah',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bee',
    'elephant',
],
    'city': {
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'snail',
    'maybe_null': 'mouse',
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
    '01',
],
    'text_data': '84e91e41cfa343358cab76d90ab79cfc',
    'rand_digit': 6,
    'rand_number': 0.88189,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-08 02:31:00.253417',
    'text_array': [
    '477802d621904fc885181415fd19b217',
    '90ce9b48f54147e28b65a206f11c1560',
],
    'words': 'goat bird',
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
    'word': 'giraffe',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 8,
},
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
],
    'word': 'horse',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'squid',
    'turtle',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'giraffe',
},
},
    {
    'id': 38,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 138,
    'id_str': [
    '26',
    '17',
    '11',
    '19',
],
    'text_data': '16b0c090b11f4691b2999d2023403253',
    'rand_digit': 4,
    'rand_number': 0.13607,
    'rand_signed_int': -3,
    'rand_datetime': '2000-01-17 22:40',
    'text_array': [
    'b2fce119c55441c49cb4a75c3252e804',
    '5eb21eee38e34335af47e415e8085f1e',
],
    'words': 'cheetah dog',
    'nested': {
    'id': 138,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'ant',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'goat',
    'number': 4,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'frog',
    'horse',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'duck',
    'maybe_null': None,
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 139,
    'id_str': [
    '17',
],
    'text_data': '3cbe01b815364ab7b97d969aeed78d76',
    'rand_digit': 3,
    'rand_number': 0.26203,
    'rand_signed_int': 8,
    'rand_datetime': '2001-01-09 08:53:48+1100',
    'text_array': [
    'e848fd50f11b441888fc4ff65a6e4753',
    'ba78c846842a4f97ade3ca65fb980080',
],
    'words': 'pig deer',
    'nested': {
    'id': 139,
    'rand_digit': 1,
    'array': [
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    1,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'squid',
    'kangaroo',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'koala',
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 140,
    'id_str': [
],
    'text_data': '3dd2947e32964179929852eb47c4d77f',
    'rand_digit': 9,
    'rand_number': 0.43473,
    'rand_signed_int': 0,
    'rand_datetime': '2000-09-15 03:11:12.640683',
    'text_array': [
    'c429f6a8bb774a85b096a7cda3fb7857',
    '1045b383efbd4cb296c87627367bd799',
],
    'words': 'spider dog',
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
    'word': 'squid',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 5,
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
    'lizard',
    'sloth',
],
    'city': {
    'name': 'Rome',
    'geo': {
    'lat': 41.902782,
    'lon': 12.496366,
},
},
    'rand_tuple': [
    97,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'turtle',
    'maybe_null': 'snail',
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 141,
    'id_str': [
    '26',
    '09',
    '09',
    '08',
    '26',
],
    'text_data': '733bf4038d1f419ab5e4bc3c8d481828',
    'rand_digit': 3,
    'rand_number': 0.61933,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-08 07:32',
    'text_array': [
    '194cdab7a59d4fbaaef89a0685c35714',
    '5ae56c6c94cb452a9b85eda0bbbf2bef',
],
    'words': 'deer cheetah',
    'nested': {
    'id': 141,
    'rand_digit': 6,
    'array': [
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
    'word': 'snail',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'horse',
    'turtle',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 2,
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 142,
    'id_str': [
    '06',
    '04',
],
    'text_data': '07fbc93c40ed4562877d962c8b5f7ffc',
    'rand_digit': 4,
    'rand_number': 0.43141,
    'rand_signed_int': 0,
    'rand_datetime': '2000-10-19T08:48:34.727590+0400',
    'text_array': [
    '21a506210b2944518ac6b8734f53c6c5',
    '32f2043150bf44099c9da06b5c652d8f',
],
    'words': 'chicken dragonfly',
    'nested': {
    'id': 142,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'camel',
    'snail',
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
    'mixed_type': 0.1141,
    'maybe_null': 'spider',
},
},
    {
    'id': 43,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 143,
    'id_str': [
],
    'text_data': '535feef431e24b8c9006cc11d6fd2d92',
    'rand_digit': 5,
    'rand_number': 0.39309,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-20 13:59:07-0300',
    'text_array': [
    '9c6f682c628842f391b13832c2a78c6e',
    '36e155b5bce74f3da7f94906be7a8502',
],
    'words': 'dog bird',
    'nested': {
    'id': 143,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lizard',
    'rhino',
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
    'mixed_type': 0.42103,
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 144,
    'id_str': [
    '07',
],
    'text_data': '8c519a53ffe140aa9c7cb4e9b4523019',
    'rand_digit': 2,
    'rand_number': 0.14127,
    'rand_signed_int': 1,
    'rand_datetime': '2000-09-13 02:43',
    'text_array': [
    '2ec5ff1156844a71b8fde14f4106153b',
    'a5a2cabb606c496a9ef04de3f22dba77',
],
    'words': 'monkey cow',
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
    'word': 'lizard',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 10,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,2__',
    'two_words': [
    'dog',
    'dragonfly',
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
    'mixed_type': True,
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 145,
    'id_str': [
    '27',
    '01',
    '11',
    '23',
],
    'text_data': 'f95904e97275441f805a3843f5bedded',
    'rand_digit': 3,
    'rand_number': 0.06105,
    'rand_signed_int': -1,
    'rand_datetime': '2000-02-18T00:43:54.646724',
    'text_array': [
    '705c9fd44f9a49d6a76d9e3848bd1686',
    '11cfdda55feb48059f7ef27514c0e9ff',
],
    'words': 'lion horse',
    'nested': {
    'id': 145,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'rabbit',
    'deer',
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
    'mixed_type': None,
    'maybe': 'ladybug',
    'maybe_null': 'bee',
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
],
    'text_data': 'a696d0fc5c664c3c953915021265b9a0',
    'rand_digit': 2,
    'rand_number': 0.57342,
    'rand_signed_int': 3,
    'rand_datetime': '2000-10-17T21:55:51',
    'text_array': [
    'b6e07770a4154aada95888e7379e18af',
    '6c7089a74340454487523c7cbceffb27',
],
    'words': 'hyena ant',
    'nested': {
    'id': 146,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snake',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'scorpion',
    'camel',
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
    'mixed_type': 'ant',
},
},
    {
    'id': 47,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 147,
    'id_str': [
    '28',
    '18',
    '19',
],
    'text_data': '84ec6ab270c74591855eb27366428d93',
    'rand_digit': 5,
    'rand_number': 0.5266,
    'rand_signed_int': -5,
    'rand_datetime': '2000-06-15T19:30:54.272179',
    'text_array': [
    'edd52a2979d741e9bf6492ceb15ca345',
    'fa869f34a05844e29622daaa6d6b6622',
],
    'words': 'jaguar ant',
    'nested': {
    'id': 147,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -1,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'hippo',
    'hyena',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 8,
    'maybe_null': 'kangaroo',
},
},
    {
    'id': 48,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 148,
    'id_str': [
    '06',
    '13',
    '26',
],
    'text_data': 'd6374b794c3f48459b8a4305b7cb26fd',
    'rand_digit': 0,
    'rand_number': 0.4444,
    'rand_signed_int': 5,
    'rand_datetime': '2000-07-05 11:39:11+0100',
    'text_array': [
    'b161a2203cab4fe3bc54a5e0a845125a',
    '3f1fffe3992e48bd91b310eb171d9a6a',
],
    'words': 'hyena deer',
    'nested': {
    'id': 148,
    'rand_digit': 0,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bee',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 3,
},
    {
    'nested_empty': None,
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
],
    [
],
],
    'two_words': [
    'cheetah',
    'tiger',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'scorpion',
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 149,
    'id_str': [
    '13',
    '28',
    '29',
],
    'text_data': '2c20f9694be347b29146c9693b55ef0f',
    'rand_digit': 5,
    'rand_number': 0.56473,
    'rand_signed_int': -2,
    'rand_datetime': '2001-01-26',
    'text_array': [
    'b5fb40aa040b4b4291b52e6315b00317',
    '9d6f5fd813d248339edf35d5dad3635a',
],
    'words': 'mosquito fish',
    'nested': {
    'id': 149,
    'rand_digit': 1,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 5,
},
    {
    'nested_empty': None,
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
    'word': 'crab',
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
    'number': 6,
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
    'mouse',
    'crab',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'hippo',
},
},
    {
    'id': 50,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 150,
    'id_str': [
    '12',
    '05',
],
    'text_data': '02ec25fcb16643788b1f1fa3fc828644',
    'rand_digit': 9,
    'rand_number': 0.11811,
    'rand_signed_int': 4,
    'rand_datetime': '2000-12-02T22:22:05.915757',
    'text_array': [
    'b7aa9c7936b548419cfb5deef1b2109f',
    '9a6f921e964743d7b8d3b260208c3d74',
],
    'words': 'goat bee',
    'nested': {
    'id': 150,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    [
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'snake',
    'fox',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'panda',
},
},
    {
    'id': 51,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 151,
    'id_str': [
    '04',
    '14',
    '24',
],
    'text_data': '371c71c2c5454516920f1737e017d07f',
    'rand_digit': 4,
    'rand_number': 0.05229,
    'rand_signed_int': 2,
    'rand_datetime': '2000-01-10T23:41:33',
    'text_array': [
    '093610118bf549cabeb720227b254fcd',
    'a26f86e734f7481d9651035fc6ef4f56',
],
    'words': 'turtle mouse',
    'nested': {
    'id': 151,
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
    'nested_empty': None,
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
    'word': 'dragonfly',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'shark',
    'bird',
],
    'city': {
    'name': 'Copenhagen',
    'geo': {
    'lat': 55.676097,
    'lon': 12.568337,
},
},
    'rand_tuple': [
    79,
],
    'rand_bool': False,
    'mixed_type': 0.33741,
    'maybe_null': 'panda',
},
},
    {
    'id': 52,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 152,
    'id_str': [
    '19',
    '12',
    '15',
],
    'text_data': '9c59c8ae0d7a4628b770241f3a5680e4',
    'rand_digit': 6,
    'rand_number': 0.35959,
    'rand_signed_int': 8,
    'rand_datetime': '2000-04-13T04:38:28',
    'text_array': [
    '0e742a0bdc25450a9cf6c0c093fae5a5',
    'f8a960cc156a48f2ac55030454c00c23',
],
    'words': 'fly rhino',
    'nested': {
    'id': 152,
    'rand_digit': 8,
    'array': [
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
    'word': 'fish',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'lobster',
    'giraffe',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'sheep',
},
},
    {
    'id': 53,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 153,
    'id_str': [
    '26',
    '28',
    '19',
    '07',
],
    'text_data': 'ab5cd2bb43844babb9251bfdc64a4225',
    'rand_digit': 1,
    'rand_number': 0.56486,
    'rand_signed_int': -9,
    'rand_datetime': '2000-07-26',
    'text_array': [
    '1a964ce7292348beb534ab2e374844dd',
    'c88f45ce89284c6d857c0d987a79a58d',
],
    'words': 'grasshopper ladybug',
    'nested': {
    'id': 153,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 8,
},
],
},
    'nested_array': [
    [
    -10,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'lizard',
    'cow',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'goat',
},
},
    {
    'id': 54,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 154,
    'id_str': [
    '10',
    '04',
    '11',
    '30',
    '18',
],
    'text_data': 'ffa0c719a3174a2fa3be2477c6446e6f',
    'rand_digit': 1,
    'rand_number': 0.90838,
    'rand_signed_int': -2,
    'rand_datetime': '2000-04-13',
    'text_array': [
    '68667fa53c5e430db34ce8a46f9b4066',
    '3be966eb43214017883bf11fdce1a1f5',
],
    'words': 'fox crab',
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
    'word': 'dragonfly',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dragonfly',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
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
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'squid',
    'bee',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'tiger',
    'maybe_null': None,
},
},
    {
    'id': 55,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 155,
    'id_str': [
    '02',
    '20',
    '18',
    '24',
    '23',
],
    'text_data': '9ee0d08368674e4db9f089c7c08b2c2a',
    'rand_digit': 4,
    'rand_number': 0.09769,
    'rand_signed_int': 8,
    'rand_datetime': '2000-02-21T03:01:07.083927',
    'text_array': [
    'a386638d9ca2495d9e7578f905644cf8',
    '27a500a1b2bc4f469c4006babeec066c',
],
    'words': 'koala monkey',
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
    'word': 'duck',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'crab',
    'butterfly',
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
    'mixed_type': 0.22201,
    'maybe': 'snail',
    'maybe_null': None,
},
},
    {
    'id': 56,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 156,
    'id_str': [
    '23',
],
    'text_data': '03446a2514a54473a0bff41d742bcc27',
    'rand_digit': 5,
    'rand_number': 0.93967,
    'rand_signed_int': -1,
    'rand_datetime': '2000-03-03T21:43:24.246482',
    'text_array': [
    '80e1dfe6c6184f30b6ada4362c7d4188',
    'feb6dba3646d4e19960de0e3cb3ea34f',
],
    'words': 'mouse hyena',
    'nested': {
    'id': 156,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'bee',
    'ape',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'mosquito',
    'maybe_null': None,
},
},
    {
    'id': 57,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 157,
    'id_str': [
    '26',
],
    'text_data': 'b8cf7cf0f215478b90436cd49966aad1',
    'rand_digit': 5,
    'rand_number': 0.64723,
    'rand_signed_int': 8,
    'rand_datetime': '2000-03-29 00:26:27.387383',
    'text_array': [
    '8485c6b7772f45668f7ac4466e413104',
    '3944ac7d0f0149ca82f15584064f9639',
],
    'words': 'fox butterfly',
    'nested': {
    'id': 157,
    'rand_digit': 0,
    'array': [
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
    'word': 'horse',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bear',
    'chicken',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
},
    {
    'id': 58,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 158,
    'id_str': [
    '19',
    '21',
    '06',
    '21',
    '03',
],
    'text_data': 'b739cf44a47b402ab6d208dee36b51c7',
    'rand_digit': 1,
    'rand_number': 0.11675,
    'rand_signed_int': -3,
    'rand_datetime': '2000-11-14T14:00:54-0400',
    'text_array': [
    'cc2aac19d9c84366aaf5b2352c189b44',
    '648b255b34ee4413ab15ce61cc5e591a',
],
    'words': 'rhino ladybug',
    'nested': {
    'id': 158,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'goat',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
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
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    10,
],
    [
    7,
],
],
    'two_words': [
    'fish',
    'jaguar',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'rabbit',
    'maybe_null': None,
},
},
    {
    'id': 59,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 159,
    'id_str': [
    '08',
],
    'text_data': '65e547247ec34371bf06e616c52805cf',
    'rand_digit': 0,
    'rand_number': 0.07107,
    'rand_signed_int': 3,
    'rand_datetime': '2000-02-09 01:46:54.337273+1100',
    'text_array': [
    '11231fd078174de3b8244e4c562a0385',
    'e35fcf6edb854b208aac4aa60f4cf83b',
],
    'words': 'grasshopper fish',
    'nested': {
    'id': 159,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'panda',
    'sloth',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'chicken',
    'maybe_null': 'mosquito',
},
},
    {
    'id': 60,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 160,
    'id_str': [
],
    'text_data': 'ce4bb338ef914d9b9e0785780d4950bd',
    'rand_digit': 6,
    'rand_number': 0.84546,
    'rand_signed_int': 0,
    'rand_datetime': '2001-01-28 03:40:40-0200',
    'text_array': [
    '16bf53fe24dc48f98ff05ab223c511f1',
    '995007397e2d4b018369e8d4cd233cfa',
],
    'words': 'whale leopard',
    'nested': {
    'id': 160,
    'rand_digit': 2,
    'array': [
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
],
    'word': 'bird',
    'number': 2,
},
],
},
    'nested_array': [
    [
    5,
],
],
    'two_words': [
    'deer',
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
    'mixed_type': 7,
    'maybe': 'squid',
    'maybe_null': 'ant',
},
},
    {
    'id': 61,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 161,
    'id_str': [
    '13',
],
    'text_data': '820f79fa034344efa1ef556c55ff0147',
    'rand_digit': 6,
    'rand_number': 0.6135,
    'rand_signed_int': -1,
    'rand_datetime': '2000-07-11 11:55:09',
    'text_array': [
    'de980f42b1284f04bfff7de8af74f520',
    'a878343bb4574429a3f7b0161f05695c',
],
    'words': 'fly bird',
    'nested': {
    'id': 161,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
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
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'squid',
    'crab',
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
    'mixed_type': 'sloth',
    'maybe': 'mouse',
    'maybe_null': 'jaguar',
},
},
    {
    'id': 62,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 162,
    'id_str': [
    '16',
    '23',
],
    'text_data': '061c0420141f49cbb7ad6952cb8c443a',
    'rand_digit': 8,
    'rand_number': 0.6892,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-29 18:52:04.139482+1000',
    'text_array': [
    'efcff83b723946f59775f46a5b2513e6',
    '42fadfb002e84ee9b5616a24f95489da',
],
    'words': 'kangaroo grasshopper',
    'nested': {
    'id': 162,
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
    'number': 6,
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
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'hippo',
    'mosquito',
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
    'mixed_type': 4,
    'maybe': 'octopus',
    'maybe_null': None,
},
},
    {
    'id': 63,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 163,
    'id_str': [
    '16',
    '04',
    '27',
    '12',
    '23',
],
    'text_data': '6622db19dffb409aa12816c146213248',
    'rand_digit': 3,
    'rand_number': 0.96485,
    'rand_signed_int': 10,
    'rand_datetime': '2000-10-07T12:55:12.776820',
    'text_array': [
    'fc09d4be184d42b59f89ed58719c46c2',
    '4a19a46d6b1f45c7bb619ee9bdbf0bfc',
],
    'words': 'jaguar turtle',
    'nested': {
    'id': 163,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'octopus',
    'panda',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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
    'content-length': '406233',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 100,
    'id_str': [
    '18',
    '02',
    '08',
    '20',
    '20',
],
    'text_data': '683fd994dd614b94972b1fd2dafe07eb',
    'rand_digit': 1,
    'rand_number': 0.07218,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-24T01:53:38.907969',
    'text_array': [
    '2c56498764d24332ac5572aa5b482e37',
    '92d8696f690a4110bf48699c27296a86',
],
    'words': 'bee octopus',
    'nested': {
    'id': 100,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'frog',
    'fly',
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
    'mixed_type': None,
    'maybe_null': 'kangaroo',
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 101,
    'id_str': [
],
    'text_data': 'f184539d50e7429e9a72e21e02b86cff',
    'rand_digit': 5,
    'rand_number': 0.76896,
    'rand_signed_int': 0,
    'rand_datetime': '2000-03-23T00:51:31.014476+0300',
    'text_array': [
    '8ca31a5bb76e46b5b5949d6788c85ac2',
    'b4ca288179af49f7bd007f043ff85eb7',
],
    'words': 'giraffe dog',
    'nested': {
    'id': 101,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 1,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 3,
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
    [
    -5,
],
],
    'two_words': [
    'dolphin',
    'leopard',
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
    'mixed_type': 1,
    'maybe': 'snake',
    'maybe_null': 'panda',
},
},
    {
    'id': 2,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 102,
    'id_str': [
    '05',
    '18',
],
    'text_data': '33cc4c98f93640ccb29865e29665fa44',
    'rand_digit': 4,
    'rand_number': 0.7006,
    'rand_signed_int': 1,
    'rand_datetime': '2000-10-05T18:26:47.539843',
    'text_array': [
    'a6183e70c7e049f5aaa9aae6bab2407d',
    'a0e40ea8b3634d54b167a0dcc29f3582',
],
    'words': 'sheep spider',
    'nested': {
    'id': 102,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'wolf',
    'ladybug',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'shark',
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 103,
    'id_str': [
    '21',
    '22',
    '20',
    '21',
],
    'text_data': 'd396447f26034f9299d213622974ee1c',
    'rand_digit': 8,
    'rand_number': 0.35461,
    'rand_signed_int': 0,
    'rand_datetime': '2000-05-13T21:46:42.144725+02:00',
    'text_array': [
    'f18944a6afb340dfa45edd0d837c9db7',
    'c003749a0bfa41d38eab575bc67e8bf6',
],
    'words': 'frog duck',
    'nested': {
    'id': 103,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 9,
},
],
},
    'nested_array': [
    [
    -10,
],
    [
    1,
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'gorilla',
    'monkey',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'goat',
    'maybe_null': 'jaguar',
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 104,
    'id_str': [
    '21',
    '12',
    '28',
    '30',
],
    'text_data': '860938806ec3491f913d5b877a21e5cd',
    'rand_digit': 6,
    'rand_number': 0.35685,
    'rand_signed_int': -9,
    'rand_datetime': '2000-08-08T13:35:27+0500',
    'text_array': [
    '7f91af92a81c420ab40f11541be65790',
    '014d98fe41504fbcae66ef554aad05a6',
],
    'words': 'grasshopper panda',
    'nested': {
    'id': 104,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'grasshopper',
    'lobster',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': [
    0,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'grasshopper',
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 105,
    'id_str': [
    '15',
    '11',
    '15',
    '22',
],
    'text_data': '0086049413394eba81670d8f77e0b58b',
    'rand_digit': 0,
    'rand_number': 0.34787,
    'rand_signed_int': -2,
    'rand_datetime': '2001-01-24 03:36:58-0100',
    'text_array': [
    '9966919f976e4aa7bc60b4b019c1146e',
    '2a33ede1cf2f4b3a8ef119f3deeaae5a',
],
    'words': 'hippo dog',
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
    'word': 'cheetah',
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
    'number': 5,
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
],
    'two_words': [
    'fox',
    'lizard',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 8,
    'maybe_null': 'bear',
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 106,
    'id_str': [
    '06',
    '22',
    '20',
],
    'text_data': '61dda7c256264e48967d6e5c120cf101',
    'rand_digit': 9,
    'rand_number': 0.16938,
    'rand_signed_int': -8,
    'rand_datetime': '2000-03-16 22:39:41.147526',
    'text_array': [
    'ec32a0ad61e94594884c64687ab886e4',
    '16e6fedd50c04d8d9c3f3e32c1faff48',
],
    'words': 'ant jaguar',
    'nested': {
    'id': 106,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'mouse',
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
    'mixed_type': 0.18656,
    'maybe_null': 'rabbit',
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 107,
    'id_str': [
    '19',
    '22',
    '22',
    '15',
    '19',
],
    'text_data': 'd411236af5fc43b3b6843001964009a6',
    'rand_digit': 8,
    'rand_number': 0.50268,
    'rand_signed_int': -9,
    'rand_datetime': '2000-06-04 10:04:06+0300',
    'text_array': [
    '6e51f4e0dd704356b70e0c0440f84955',
    '080c4cbada8f42a59290bddd2a98edf9',
],
    'words': 'scorpion rabbit',
    'nested': {
    'id': 107,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'butterfly',
    'ladybug',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'dolphin',
    'maybe_null': 'dolphin',
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 108,
    'id_str': [
    '06',
    '27',
    '22',
    '04',
    '19',
],
    'text_data': '40d99d13e6134cd69cfb87a3c28e69a4',
    'rand_digit': 3,
    'rand_number': 0.38611,
    'rand_signed_int': 0,
    'rand_datetime': '2001-01-09T06:02:04.395641',
    'text_array': [
    '2830a8b47f7049d8a32befa5451084e0',
    '0e51118931324ee098ed873fd637374a',
],
    'words': 'ape hippo',
    'nested': {
    'id': 108,
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
    'number': 8,
},
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
    'word': 'shark',
    'number': 7,
},
],
},
    'nested_array': [
    [
    7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -9,
],
],
    'two_words': [
    'goat',
    'panda',
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
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 109,
    'id_str': [
    '07',
    '30',
],
    'text_data': '02b67c92cd2942d48639e1966e0836c5',
    'rand_digit': 0,
    'rand_number': 0.03793,
    'rand_signed_int': 7,
    'rand_datetime': '2000-11-14T05:45:36',
    'text_array': [
    '52ae6466b61148288999c287d9467d59',
    'd2d9e478e83249ce8e7cfb7a2ae24c00',
],
    'words': 'mouse chicken',
    'nested': {
    'id': 109,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'wolf',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 8,
},
    {
    'nested_empty': None,
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
    'word': 'giraffe',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'cow',
    'hyena',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.31977,
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 110,
    'id_str': [
    '27',
    '12',
    '01',
],
    'text_data': '82b2c8f1bb8442379fa59b428da4ff42',
    'rand_digit': 5,
    'rand_number': 0.01128,
    'rand_signed_int': -9,
    'rand_datetime': '2000-12-06 09:39:59-1100',
    'text_array': [
    'c50358bdcfd64bf383c368e9a674077a',
    'a1dbffea16664bf69fbf079b40ca4375',
],
    'words': 'bee hyena',
    'nested': {
    'id': 110,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'dragonfly',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 5,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_3,5__',
    'two_words': [
    'frog',
    'koala',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'grasshopper',
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 111,
    'id_str': [
    '18',
    '23',
    '27',
    '02',
],
    'text_data': '095ed13534cf49c78782916fba1b2e10',
    'rand_digit': 9,
    'rand_number': 0.58192,
    'rand_signed_int': -8,
    'rand_datetime': '2000-02-14 05:21:42+0700',
    'text_array': [
    '43353f3bb89c4ad9b2a46179631cb139',
    '400b609e56c145aea830e5f532654635',
],
    'words': 'bear koala',
    'nested': {
    'id': 111,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 9,
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
    'name': 'Kharkiv',
    'geo': {
    'lat': 49.980812,
    'lon': 36.25272,
},
},
    'rand_tuple': [
    97,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 112,
    'id_str': [
    '05',
    '03',
    '06',
    '27',
],
    'text_data': 'adab4e94dcf943f6805f5a5a54269fe3',
    'rand_digit': 8,
    'rand_number': 0.13073,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-24 08:10',
    'text_array': [
    '1350651d2139478c99267ce5fb6e21ea',
    '148a7f1c5ed44333bc5f55f2bf0c07e6',
],
    'words': 'ape bee',
    'nested': {
    'id': 112,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
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
    'ape',
    'cat',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe_null': 'dolphin',
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 113,
    'id_str': [
    '27',
    '13',
],
    'text_data': 'c68db735d6da4e3a89bc19c76551171e',
    'rand_digit': 6,
    'rand_number': 0.36849,
    'rand_signed_int': -4,
    'rand_datetime': '2001-01-24T19:08:20.670058Z',
    'text_array': [
    '6c6397c6393b4e8a885e2abcd54dd614',
    '915d93a2a2d845f9b576682cc2d26dd9',
],
    'words': 'goat horse',
    'nested': {
    'id': 113,
    'rand_digit': 3,
    'array': [
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'spider',
    'bear',
],
    'city': {
    'name': 'Paris',
    'geo': {
    'lat': 48.856614,
    'lon': 2.352222,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': True,
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 114,
    'id_str': [
    '26',
    '08',
    '19',
],
    'text_data': '89d0669e884b492791888452e36cee9e',
    'rand_digit': 8,
    'rand_number': 0.8534,
    'rand_signed_int': 10,
    'rand_datetime': '2000-12-26T11:28:02',
    'text_array': [
    '96312ec060894751a89fc911dfee1867',
    'c5bf2165901841d0b8843fc285838f36',
],
    'words': 'wolf ape',
    'nested': {
    'id': 114,
    'rand_digit': 8,
    'array': [
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
    'word': 'sheep',
    'number': 10,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -6,
],
    [
    -8,
],
],
    'two_words': [
    'crab',
    'horse',
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
    'maybe_null': 'cow',
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 115,
    'id_str': [
    '05',
    '25',
    '16',
    '15',
    '05',
],
    'text_data': 'cd0672012fb6418996074c9d9812d6d6',
    'rand_digit': 2,
    'rand_number': 0.97913,
    'rand_signed_int': 6,
    'rand_datetime': '2000-02-09T22:49:05.606884-10:00',
    'text_array': [
    'a238a3dd2a0848f1831bdf6945bf5280',
    '2d2cc30cdf88470696d32b4b36b11e4d',
],
    'words': 'pig octopus',
    'nested': {
    'id': 115,
    'rand_digit': 9,
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
],
},
    'nested_array': [
],
    'two_words': [
    'gorilla',
    'cow',
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
    'maybe_null': 'camel',
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 116,
    'id_str': [
    '23',
],
    'text_data': 'd826883da9fc4e4486a36888db987b73',
    'rand_digit': 0,
    'rand_number': 0.99641,
    'rand_signed_int': 3,
    'rand_datetime': '2000-06-15T19:09:52.455116+09:00',
    'text_array': [
    'b9a2f48c593c47e1bff64a9be65aae8e',
    '08fd5680ae2e4308b67bad9603f4fc57',
],
    'words': 'leopard frog',
    'nested': {
    'id': 116,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
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
],
    'word': 'chicken',
    'number': 9,
},
],
},
    'nested_array': [
    [
    -6,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'snake',
    'whale',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': [
    54,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'duck',
    'maybe_null': None,
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 117,
    'id_str': [
    '17',
    '22',
    '28',
    '22',
],
    'text_data': '9396d66e8bd444e79ba47cad06f72be6',
    'rand_digit': 0,
    'rand_number': 0.56568,
    'rand_signed_int': -7,
    'rand_datetime': '2000-03-03',
    'text_array': [
    '643fcbcaf87945d19932fc3b465a1ef1',
    '897edea7e7e04d8d9b8d60b6df679d8a',
],
    'words': 'lizard zebra',
    'nested': {
    'id': 117,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 7,
},
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
    'hello',
],
    'word': 'chicken',
    'number': 4,
},
],
},
    'nested_array': [
    [
    9,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -2,
],
],
    'two_words': [
    'kangaroo',
    'turtle',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'crab',
    'maybe_null': 'wolf',
},
},
    {
    'id': 18,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 118,
    'id_str': [
    '18',
    '13',
    '30',
    '14',
],
    'text_data': '49ef67f9831645b9a2d2d00e09adf661',
    'rand_digit': 0,
    'rand_number': 0.50289,
    'rand_signed_int': 8,
    'rand_datetime': '2000-09-30T18:27:50',
    'text_array': [
    '0439d12a27334f328aacd54453a88de8',
    '372ca510845243e6a44aeb9deff116aa',
],
    'words': 'sheep dog',
    'nested': {
    'id': 118,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'elephant',
    'ant',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': [
    0,
],
    'rand_bool': False,
    'mixed_type': 0.31344,
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
    '07',
    '26',
    '11',
],
    'text_data': '89d19ad2cbc441648fcf6dd40e17347d',
    'rand_digit': 9,
    'rand_number': 0.22457,
    'rand_signed_int': -5,
    'rand_datetime': '2001-01-05T18:53:41.603989+1000',
    'text_array': [
    'c35c2c852fd04539927a73b40fd9251e',
    '3c8b5364636e42fc8407c1e61f2258a5',
],
    'words': 'octopus lobster',
    'nested': {
    'id': 119,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 3,
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
    'word': 'giraffe',
    'number': 10,
},
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
    'word': 'monkey',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'tiger',
    'cow',
],
    'city': {
    'name': 'Barcelona',
    'geo': {
    'lat': 41.385064,
    'lon': 2.173403,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'hippo',
    'maybe_null': 'turtle',
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 120,
    'id_str': [
    '29',
    '11',
],
    'text_data': '95b34de7147e424cad2342fb12523bf4',
    'rand_digit': 6,
    'rand_number': 0.64525,
    'rand_signed_int': -3,
    'rand_datetime': '2000-02-27T00:01:37.553530-0500',
    'text_array': [
    '64a1545ec5db411e9bbf21e8b8f82e77',
    '677fafb17f4541de97c23aa4445f87e7',
],
    'words': 'octopus spider',
    'nested': {
    'id': 120,
    'rand_digit': 7,
    'array': [
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
    'hello',
],
    'word': 'cat',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dragonfly',
    'mouse',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': [
    1,
],
    'rand_bool': False,
    'mixed_type': 0.1398,
    'maybe_null': None,
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 121,
    'id_str': [
],
    'text_data': '5ae807d2b59e484ea20cd520f136c96e',
    'rand_digit': 9,
    'rand_number': 0.83714,
    'rand_signed_int': 5,
    'rand_datetime': '2000-12-31T20:40:07.909532+04:00',
    'text_array': [
    '3928aaf4a3bb458893dac276a0be235b',
    'd6cae8ee44404b649042d96f14823cff',
],
    'words': 'deer cheetah',
    'nested': {
    'id': 121,
    'rand_digit': 5,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    -5,
],
],
    'two_words': [
    'panda',
    'ant',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'fish',
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
    '12',
    '17',
    '02',
    '29',
],
    'text_data': 'fd1e87a2ad0a4b96b0ec9b6175cb44ad',
    'rand_digit': 2,
    'rand_number': 0.81308,
    'rand_signed_int': -1,
    'rand_datetime': '2000-03-12T15:53:07-0200',
    'text_array': [
    '0c6522e89a87498b8e23a0af8b629ae9',
    '50ee9f35eba840968ccecf55f71e7e5a',
],
    'words': 'elephant scorpion',
    'nested': {
    'id': 122,
    'rand_digit': 8,
    'array': [
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
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'gorilla',
    'horse',
],
    'city': {
    'name': 'Kuala Lumpur',
    'geo': {
    'lat': 3.139003,
    'lon': 101.686855,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fox',
    'maybe_null': None,
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 123,
    'id_str': [
    '10',
],
    'text_data': 'c9a701173e994e16944edab8353f4f39',
    'rand_digit': 2,
    'rand_number': 0.22574,
    'rand_signed_int': -7,
    'rand_datetime': '2000-01-31 10:15:05',
    'text_array': [
    '80005602500c4cb6821da3d7b8f75700',
    'd3476a1149ec4c4abf4358378cc1aa2d',
],
    'words': 'horse gorilla',
    'nested': {
    'id': 123,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'jaguar',
    'number': 8,
},
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'frog',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dragonfly',
    'elephant',
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
    'mixed_type': 0.58944,
    'maybe': 'monkey',
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 124,
    'id_str': [
    '21',
    '01',
    '30',
],
    'text_data': '62bb50d5fc504d45bbeafbfb0fa8cbe2',
    'rand_digit': 0,
    'rand_number': 0.25029,
    'rand_signed_int': -8,
    'rand_datetime': '2000-05-22T11:17:14.354835-0700',
    'text_array': [
    '8f8f859355bf411aa7b07924a34ffa2e',
    'fd534181581e4cc7b273aa7534cbf7c1',
],
    'words': 'mouse elephant',
    'nested': {
    'id': 124,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 4,
},
],
},
    'nested_array': [
    [
    7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'leopard',
    'frog',
],
    'city': {
    'name': 'Melbourne',
    'geo': {
    'lat': -37.813628,
    'lon': 144.963058,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'sloth',
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
    '27',
],
    'text_data': '99a68ab5f1b24f96b423d797bdb8249a',
    'rand_digit': 6,
    'rand_number': 0.95594,
    'rand_signed_int': -3,
    'rand_datetime': '2000-11-26 19:06:27',
    'text_array': [
    '5681adcb773743838eefad9f171ec965',
    '9bfd0ac16a85400b89f95586dab12ae1',
],
    'words': 'sheep chicken',
    'nested': {
    'id': 125,
    'rand_digit': 4,
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
    'nested_empty': None,
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
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lion',
    'mouse',
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
    'id': 26,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 126,
    'id_str': [
    '22',
    '10',
    '04',
    '17',
    '09',
],
    'text_data': '39d53225b6114629a8c7fac88402a316',
    'rand_digit': 9,
    'rand_number': 0.16052,
    'rand_signed_int': -5,
    'rand_datetime': '2000-07-31 13:18',
    'text_array': [
    '89501dbb70b848b3b538ccbba43787a7',
    '43395eb3e5ff4a968642b5d0bbf0b1fb',
],
    'words': 'rabbit snake',
    'nested': {
    'id': 126,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -10,
],
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'scorpion',
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
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'crab',
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 127,
    'id_str': [
    '15',
    '10',
    '10',
],
    'text_data': 'b5d1e5a1a4df4ddcae3d757f84def3e0',
    'rand_digit': 0,
    'rand_number': 0.87468,
    'rand_signed_int': -5,
    'rand_datetime': '2000-03-11T06:26:52.405869-0200',
    'text_array': [
    '710133e2aba14abf9058136801bee44e',
    'ba72d7acb82c4571b4bbbfa690d232f5',
],
    'words': 'monkey goat',
    'nested': {
    'id': 127,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 1,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
    -10,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'chicken',
    'zebra',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': [
    80,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'elephant',
},
},
    {
    'id': 28,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 128,
    'id_str': [
],
    'text_data': 'ed5e2008a2fd4ac89e707d314003ad94',
    'rand_digit': 5,
    'rand_number': 0.1451,
    'rand_signed_int': -4,
    'rand_datetime': '2000-11-28T15:35:10.316853',
    'text_array': [
    'd7487aa4a9fa429792f06fb3b3b914a7',
    '3b4d8d9fb44a42e0ad701d0324350516',
],
    'words': 'sloth fox',
    'nested': {
    'id': 128,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'lobster',
    'kangaroo',
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
    'mixed_type': 0.96175,
    'maybe': 'bird',
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
    '19',
    '02',
    '14',
],
    'text_data': '18b544161e9f4ab39e8b3946c580a211',
    'rand_digit': 1,
    'rand_number': 0.80453,
    'rand_signed_int': -7,
    'rand_datetime': '2000-04-14T01:05:45.722818-11:00',
    'text_array': [
    'bc181659eb504e9fb46df7b5cd90700f',
    '08f24df6f6d44a37897190945fda6d4c',
],
    'words': 'ape snake',
    'nested': {
    'id': 129,
    'rand_digit': 7,
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    1,
],
],
    'two_words': [
    'octopus',
    'leopard',
],
    'city': {
    'name': 'Kiev',
    'geo': {
    'lat': 50.4501,
    'lon': 30.5234,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'fly',
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 130,
    'id_str': [
    '11',
    '01',
    '26',
    '26',
    '25',
],
    'text_data': 'a8b91111d8ec4b09ad3046b05a8dd43e',
    'rand_digit': 0,
    'rand_number': 0.02794,
    'rand_signed_int': -6,
    'rand_datetime': '2000-03-20 19:15:28.410456',
    'text_array': [
    'd61a7fd733714c6eac55a1ce60d9c97c',
    '12dc061f175747068c7efb785f675134',
],
    'words': 'rabbit camel',
    'nested': {
    'id': 130,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 7,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snake',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -5,
],
],
    'two_words': [
    'kangaroo',
    'horse',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': 3,
    'maybe': 'duck',
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 131,
    'id_str': [
    '22',
],
    'text_data': '728db90406da405db406594364ecbbc0',
    'rand_digit': 7,
    'rand_number': 0.65839,
    'rand_signed_int': 5,
    'rand_datetime': '2000-06-14 08:21',
    'text_array': [
    'f2484de5cd9a4f54b939032876480eb5',
    '33bc9b0e70834cdfa4f381d8838a4d96',
],
    'words': 'frog leopard',
    'nested': {
    'id': 131,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'bird',
    'number': 5,
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
    'nested_empty': [
    'hello',
],
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
    'word': 'sloth',
    'number': 3,
},
],
},
    'nested_array': [
    [
    10,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'deer',
    'shark',
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
    'mixed_type': 0.61769,
    'maybe': 'whale',
    'maybe_null': 'hyena',
},
},
    {
    'id': 32,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 132,
    'id_str': [
    '29',
    '08',
    '01',
],
    'text_data': '4fde8663e4574375b9d0c503548c4de5',
    'rand_digit': 6,
    'rand_number': 0.24428,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-16T13:12:59.832845',
    'text_array': [
    'c0985e1367c649cebac5be86e8cfc31f',
    '550412310b1d4af2a08932fedd28c421',
],
    'words': 'giraffe goat',
    'nested': {
    'id': 132,
    'rand_digit': 4,
    'array': [
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
    'word': 'octopus',
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
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
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    [
    8,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'sloth',
    'ant',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'cat',
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 133,
    'id_str': [
    '02',
    '18',
    '24',
    '20',
    '30',
],
    'text_data': '67b3ae6d13544e0786a16da32e5ccb0e',
    'rand_digit': 5,
    'rand_number': 0.11542,
    'rand_signed_int': -7,
    'rand_datetime': '2000-03-21',
    'text_array': [
    'a610756352eb4cd1be71da40b6a4cce7',
    '08741e3617584ce981db2516bbae28d7',
],
    'words': 'panda scorpion',
    'nested': {
    'id': 133,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'duck',
    'number': 4,
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
    'word': 'ladybug',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'bee',
    'gorilla',
],
    'city': {
    'name': 'Moscow',
    'geo': {
    'lat': 55.755826,
    'lon': 37.6173,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.70825,
    'maybe': 'goat',
    'maybe_null': None,
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 134,
    'id_str': [
    '01',
],
    'text_data': 'c2207622991546a1a3eaaf44f03203f6',
    'rand_digit': 0,
    'rand_number': 0.27075,
    'rand_signed_int': 10,
    'rand_datetime': '2000-08-14T14:17:05',
    'text_array': [
    'f81a6dda99014448a070cfc42466bc73',
    '90b00642cb614942979f1922ebabd4be',
],
    'words': 'scorpion horse',
    'nested': {
    'id': 134,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bear',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bee',
    'number': 8,
},
    {
    'nested_empty': None,
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
],
    'word': 'rhino',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'pig',
    'mouse',
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
    'maybe_null': None,
},
},
    {
    'id': 35,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 135,
    'id_str': [
    '06',
    '08',
],
    'text_data': 'e7e5c7cb29b84b49823c2d5cc69a0530',
    'rand_digit': 1,
    'rand_number': 0.25644,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-29T06:32:59+0100',
    'text_array': [
    '171663d054c747f2808143a300285f4f',
    'fc5434e6ca244ffab32e5d800c95333f',
],
    'words': 'goat shark',
    'nested': {
    'id': 135,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 6,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 10,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'mosquito',
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
    'maybe': 'spider',
    'maybe_null': 'ladybug',
},
},
    {
    'id': 36,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 136,
    'id_str': [
    '16',
    '16',
    '07',
    '11',
],
    'text_data': 'bfae902e805f4c6fb943bd5686e2b91d',
    'rand_digit': 6,
    'rand_number': 0.69033,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-26T20:49:56',
    'text_array': [
    '6962d8727bdd4ef39d64fb765858e075',
    '0d62fde83a7d48f6a03e7f205cc1a7e0',
],
    'words': 'sloth shark',
    'nested': {
    'id': 136,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'spider',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'spider',
    'squid',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 7,
    'maybe': 'fish',
    'maybe_null': 'goat',
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
    '10',
    '24',
    '17',
    '15',
],
    'text_data': 'ccac2575b47f40cc99b5ef8396d60c3a',
    'rand_digit': 4,
    'rand_number': 0.47869,
    'rand_signed_int': 3,
    'rand_datetime': '2000-07-26T12:57:05.559234',
    'text_array': [
    '1255e572b84e477bbe066c77275094ac',
    '6e1d038c4fb84e6d89f92db1d8cf6c5c',
],
    'words': 'shark bear',
    'nested': {
    'id': 137,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    3,
],
    [
    -3,
],
],
    'two_words': [
    'dolphin',
    'mouse',
],
    'city': {
    'name': 'Johannesburg',
    'geo': {
    'lat': -26.204103,
    'lon': 28.047305,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 7,
    'maybe_null': 'hippo',
},
},
    {
    'id': 38,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 138,
    'id_str': [
    '02',
],
    'text_data': '63f37f787d764c9591d5e6c98e3416c1',
    'rand_digit': 2,
    'rand_number': 0.1442,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-21T14:46:54',
    'text_array': [
    'f9fda0cc72684b5598b55a1e20c44398',
    '740c07b1288147ab9c1e2dd11ca1aba1',
],
    'words': 'fly wolf',
    'nested': {
    'id': 138,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 10,
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
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'gorilla',
    'cat',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'dolphin',
    'maybe': 'octopus',
    'maybe_null': 'tiger',
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 139,
    'id_str': [
    '13',
],
    'text_data': '58d6ab949491453d8c0b2390240c2d53',
    'rand_digit': 2,
    'rand_number': 0.12977,
    'rand_signed_int': -4,
    'rand_datetime': '2000-12-19T09:39:42',
    'text_array': [
    'e316ae094e47475b91a0408b519e830e',
    '95aa0196a41f4f4986c0025adc245bfc',
],
    'words': 'ant ant',
    'nested': {
    'id': 139,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 8,
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
    [
    -10,
],
],
    'two_words': [
    'pig',
    'snake',
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
    'mixed_type': 0.97151,
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 140,
    'id_str': [
    '21',
    '10',
],
    'text_data': '750fbb0df78c413b9f25fd6575be9b8f',
    'rand_digit': 3,
    'rand_number': 0.42076,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-15 13:26:43.622284',
    'text_array': [
    'e02a3f3ddd0d410fac683c2e69ed0b04',
    '6f8a8b8e803745308871f5ccadce0e8c',
],
    'words': 'turtle frog',
    'nested': {
    'id': 140,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'camel',
    'number': 1,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'rhino',
    'octopus',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': [
    70,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'elephant',
    'maybe_null': 'bee',
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 141,
    'id_str': [
    '10',
],
    'text_data': 'c468e1069cd24f15a9516f1947f0e1ac',
    'rand_digit': 8,
    'rand_number': 0.23199,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-17 07:56',
    'text_array': [
    '14c1874251df4209b34b0713ed757686',
    'f6c7ad647b1a4d208a6fcddf03a22c4e',
],
    'words': 'cat chicken',
    'nested': {
    'id': 141,
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
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bee',
    'snail',
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
    'mixed_type': None,
    'maybe': 'ladybug',
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 142,
    'id_str': [
    '14',
    '22',
    '10',
],
    'text_data': '83af0d7b127f4c6194f060715d7a4e41',
    'rand_digit': 0,
    'rand_number': 0.62697,
    'rand_signed_int': 0,
    'rand_datetime': '2000-09-15T23:26:28.817255',
    'text_array': [
    '33f4ef8d215e4ab1a07ec53efebca244',
    'da8986e9971c4b17b5683d178b408917',
],
    'words': 'lizard deer',
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
    'word': 'zebra',
    'number': 10,
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
],
    'two_words': [
    'dog',
    'horse',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'dolphin',
},
},
    {
    'id': 43,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 143,
    'id_str': [
],
    'text_data': '040d6a1789814b92ac5fa53bfc8335b0',
    'rand_digit': 6,
    'rand_number': 0.55615,
    'rand_signed_int': 10,
    'rand_datetime': '2000-10-06T14:44:53',
    'text_array': [
    '5d111e476c63402db86e2b4ef896a08b',
    '352bda427f2f486da0b64c727c30b37a',
],
    'words': 'wolf tiger',
    'nested': {
    'id': 143,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    5,
],
],
    'two_words': [
    'fly',
    'elephant',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'horse',
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 144,
    'id_str': [
    '06',
    '05',
],
    'text_data': '0abbda69eade413d868cff45c56eeaf2',
    'rand_digit': 7,
    'rand_number': 0.82848,
    'rand_signed_int': -7,
    'rand_datetime': '2000-11-13T07:37:08.518029',
    'text_array': [
    'e52765b4f21345e48a6e0d43f7b4e5fb',
    '898097fe7ea84d5982a3fbd3a22dcffc',
],
    'words': 'bee goat',
    'nested': {
    'id': 144,
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
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'snail',
    'number': 1,
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
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'dragonfly',
    'chicken',
],
    'city': {
    'name': 'Munich',
    'geo': {
    'lat': 48.135125,
    'lon': 11.581981,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'squid',
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 145,
    'id_str': [
    '09',
    '05',
    '16',
    '21',
],
    'text_data': '7541be874b9f48ae8f93ea7d2843295f',
    'rand_digit': 3,
    'rand_number': 0.6554,
    'rand_signed_int': 1,
    'rand_datetime': '2000-07-24T02:03:00',
    'text_array': [
    '671fb4557a364046926740c114e763f9',
    'da31ce4cd7344259b78812ec79c5ce10',
],
    'words': 'leopard cow',
    'nested': {
    'id': 145,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'spider',
    'bee',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bird',
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
    '07',
    '28',
    '29',
    '16',
],
    'text_data': 'b0badf812cc141678c2a52ac49c9c2e8',
    'rand_digit': 5,
    'rand_number': 0.59211,
    'rand_signed_int': -1,
    'rand_datetime': '2000-10-29T17:37:14.661534',
    'text_array': [
    'bf43466b30aa4b19be3bbc89788d0a89',
    '0fd66b6e97164eb8938ac60bc2f9be83',
],
    'words': 'elephant rhino',
    'nested': {
    'id': 146,
    'rand_digit': 6,
    'array': [
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
],
    'word': 'snake',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 10,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'hippo',
    'bear',
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
    'maybe_null': 'deer',
},
},
    {
    'id': 47,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 147,
    'id_str': [
    '25',
    '22',
],
    'text_data': 'bb462ac0135e4dc991c4a4d706772b43',
    'rand_digit': 0,
    'rand_number': 0.96969,
    'rand_signed_int': -1,
    'rand_datetime': '2000-01-23T10:32:59.550912',
    'text_array': [
    'b49a62d4a9db4b0fa5c7f22c5e52540a',
    'e0b81dcea1534cf59f57d22f80954799',
],
    'words': 'zebra butterfly',
    'nested': {
    'id': 147,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ape',
    'duck',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fly',
},
},
    {
    'id': 48,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 148,
    'id_str': [
    '17',
    '30',
    '15',
    '28',
],
    'text_data': '431622151fd74632aa89987d77f27254',
    'rand_digit': 3,
    'rand_number': 0.7738,
    'rand_signed_int': 7,
    'rand_datetime': '2000-01-15 18:18',
    'text_array': [
    'de558aea965a44b0b84da6acdf2d48c4',
    '0918194c78b646978a69db7d7e57de6d',
],
    'words': 'deer elephant',
    'nested': {
    'id': 148,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'camel',
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
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'cat',
    'duck',
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
    'mixed_type': 7,
    'maybe_null': None,
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 149,
    'id_str': [
    '08',
    '03',
    '03',
    '17',
    '03',
],
    'text_data': '3525a17a46a540a9a85f6f80fd870e6b',
    'rand_digit': 5,
    'rand_number': 0.57036,
    'rand_signed_int': 0,
    'rand_datetime': '2000-06-05T00:14:24.720642-07:00',
    'text_array': [
    '8fe7e2e0279c4f4a9fb833052cd56cc5',
    '62539305bdc04d6699fd51f8c49b9027',
],
    'words': 'lobster koala',
    'nested': {
    'id': 149,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    [
    9,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
    2,
],
    [
    1,
],
],
    'two_words': [
    'leopard',
    'octopus',
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
    'mixed_type': False,
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



    def test_request_4(self):
        """测试请求 4 - POST http://localhost:6333/collections/congruence_test_collection/points/query/batch"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/congruence_test_collection/points/query/batch")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/congruence_test_collection/points/query/batch'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '321',
}
        
        # 原始请求内容
        original_content = {
    'searches': [
    {
    'query': {
    'discover': {
    'target': 10,
    'context': [
    {
    'positive': 15,
    'negative': 7,
},
],
},
},
    'using': 'multi-image',
    'limit': 5,
},
    {
    'query': {
    'discover': {
    'target': 11,
    'context': [
    {
    'positive': 15,
    'negative': 17,
},
],
},
},
    'using': 'multi-image',
    'limit': 6,
    'lookup_from': {
    'collection': 'congruence_secondary_collection',
    'vector': 'multi-image',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_multivector_discovery_queries.test_discover_batch')
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
    test = TestMultivectorDiscoveryQueriestestDiscoverBatch()
    test.run_tests()
