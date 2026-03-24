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
logger = logging.getLogger('vdb_fuzzer.test.test_multivector_updates_test_upload_points')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_multivector_updates.test_upload_points"
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



class TestMultivectorUpdatestestUploadPoints:
    """自动生成的VDB模糊测试类 - test_multivector_updates.test_upload_points"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_multivector_updates.test_upload_points"
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
    'content-length': '530671',
}
        
        # 原始请求内容
        original_content = {
    'points': [
    {
    'id': 0,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 100,
    'id_str': [
    '18',
],
    'text_data': 'ccb082a64666401f8b223ccf278fba3f',
    'rand_digit': 6,
    'rand_number': 0.05745,
    'rand_signed_int': 0,
    'rand_datetime': '2000-05-26 12:06:34',
    'text_array': [
    '6ac96f1e6c224395a25c6135604fb0eb',
    '79effe0799824a1e94b4e75d1d08df62',
],
    'words': 'bear snake',
    'nested': {
    'id': 100,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cat',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'monkey',
    'koala',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': [
    60,
],
    'rand_bool': True,
    'mixed_type': 'bird',
    'maybe': 'hyena',
    'maybe_null': 'hippo',
},
},
    {
    'id': 1,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 101,
    'id_str': [
    '07',
    '15',
    '06',
    '08',
],
    'text_data': 'ddaa57e3b2db4b72a7ddb38ad37fb348',
    'rand_digit': 2,
    'rand_number': 0.04175,
    'rand_signed_int': -9,
    'rand_datetime': '2000-11-20 05:55:20.240856',
    'text_array': [
    'bc3c857afec6412dad8536a9ce6d6c66',
    '6c1791edd49e45d5a72eb0a772e4d086',
],
    'words': 'ape dog',
    'nested': {
    'id': 101,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'sheep',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
    -7,
],
    [
],
],
    'two_words': [
    'zebra',
    'mosquito',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
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
    'id': 2,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 102,
    'id_str': [
    '21',
    '23',
],
    'text_data': 'ce2723deb6bf4726b5cb817dad2492eb',
    'rand_digit': 0,
    'rand_number': 0.70641,
    'rand_signed_int': 2,
    'rand_datetime': '2000-04-25 09:39',
    'text_array': [
    'ffa152a9cbf145998946663b7605062c',
    '77aa232813f64126a4084acd9e7abf8b',
],
    'words': 'tiger octopus',
    'nested': {
    'id': 102,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 1,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -4,
],
    [
    -8,
],
],
    'two_words': [
    'jaguar',
    'cow',
],
    'city': {
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': [
    6,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'lizard',
},
},
    {
    'id': 3,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 103,
    'id_str': [
    '02',
],
    'text_data': 'd047f96c24cc43beb9bef4705173e7c7',
    'rand_digit': 0,
    'rand_number': 0.1624,
    'rand_signed_int': 0,
    'rand_datetime': '2000-12-30T10:08:55.947591-01:00',
    'text_array': [
    '5066667702aa4edcb509774136e24c7e',
    'd4820807f67243a1a931a70d41d9833c',
],
    'words': 'pig monkey',
    'nested': {
    'id': 103,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'fly',
    'number': 10,
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'crab',
    'ape',
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
    'maybe_null': None,
},
},
    {
    'id': 4,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 104,
    'id_str': [
    '22',
    '22',
    '22',
    '03',
    '08',
],
    'text_data': '4885a63ca17148ca9809df361ead88e6',
    'rand_digit': 8,
    'rand_number': 0.72247,
    'rand_signed_int': -5,
    'rand_datetime': '2000-02-28T02:33:42.685031-0800',
    'text_array': [
    '09077615676e42d5a89aaaf5fe6c05b8',
    'c131c35b325c4204865d1f3b1d38ab0e',
],
    'words': 'fly ant',
    'nested': {
    'id': 104,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'spider',
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
    'number': 5,
},
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
    'hello',
],
    'word': 'dog',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'sheep',
    'camel',
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
    'mixed_type': 0.79395,
    'maybe': 'fish',
},
},
    {
    'id': 5,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 105,
    'id_str': [
    '12',
    '11',
    '11',
],
    'text_data': '84b3b686a5e4470099756e0170187292',
    'rand_digit': 7,
    'rand_number': 0.22695,
    'rand_signed_int': -6,
    'rand_datetime': '2000-06-29 08:14:22.252447+0500',
    'text_array': [
    'be8e7923ff924209998ee12f1ea8231b',
    'c8520d9012864a97b98304e850587dc4',
],
    'words': 'bird fish',
    'nested': {
    'id': 105,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'shark',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    4,
],
],
    'two_words': [
    'bee',
    'snake',
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
    'mixed_type': None,
},
},
    {
    'id': 6,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 106,
    'id_str': [
    '06',
],
    'text_data': 'b2c3e050356e4fb29ad5b52a4d97f844',
    'rand_digit': 3,
    'rand_number': 0.3187,
    'rand_signed_int': 5,
    'rand_datetime': '2000-05-23 18:47',
    'text_array': [
    'ce4fb407e7dc45c49239a38b96ac0ef0',
    '5baffda4d8db44baa42a8261172e1445',
],
    'words': 'dolphin squid',
    'nested': {
    'id': 106,
    'rand_digit': 5,
    'array': [
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
],
    'two_words': [
    'zebra',
    'snake',
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
    'mixed_type': 9,
    'maybe': 'octopus',
    'maybe_null': 'turtle',
},
},
    {
    'id': 7,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 107,
    'id_str': [
    '13',
    '17',
],
    'text_data': 'cdf3c87003314907b3fdb72f8a5dec51',
    'rand_digit': 6,
    'rand_number': 0.31616,
    'rand_signed_int': -10,
    'rand_datetime': '2000-11-22 17:17:28',
    'text_array': [
    '03a9dac506cd41f2b9a6c063d9a76c96',
    '095a78c4f1c446e5a9bdf24d7bec9a97',
],
    'words': 'lion sheep',
    'nested': {
    'id': 107,
    'rand_digit': 8,
    'array': [
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
],
    'word': 'dragonfly',
    'number': 5,
},
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
    'hello',
],
    'word': 'wolf',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
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
    'frog',
    'butterfly',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': [
    17,
],
    'rand_bool': False,
    'mixed_type': 'giraffe',
},
},
    {
    'id': 8,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 108,
    'id_str': [
    '06',
],
    'text_data': '33c81b622cbc4230b48c93a880b24317',
    'rand_digit': 3,
    'rand_number': 0.65173,
    'rand_signed_int': -8,
    'rand_datetime': '2000-06-28 21:04',
    'text_array': [
    'b96e28a9a9494bc59bccb4f4a6323464',
    'dda58af3d24241de94381086389e4e8d',
],
    'words': 'wolf snake',
    'nested': {
    'id': 108,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dolphin',
    'monkey',
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
    'maybe_null': 'fly',
},
},
    {
    'id': 9,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 109,
    'id_str': [
    '05',
],
    'text_data': '7678965841ee4a90ba55de3f2e93d2fe',
    'rand_digit': 7,
    'rand_number': 0.09285,
    'rand_signed_int': 0,
    'rand_datetime': '2000-01-10T08:59:13.273095+0800',
    'text_array': [
    'f9d24cb424f6447898859de17609aa53',
    'aafd70eb213c4c959a6b62cd2895510c',
],
    'words': 'goat monkey',
    'nested': {
    'id': 109,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -1,
],
],
    'two_words': [
    'dragonfly',
    'bear',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 2,
    'maybe': 'shark',
    'maybe_null': 'bird',
},
},
    {
    'id': 10,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 110,
    'id_str': [
    '24',
    '12',
],
    'text_data': '0d9e5ad17bf94d2697cc73f1f098d058',
    'rand_digit': 9,
    'rand_number': 0.45464,
    'rand_signed_int': 1,
    'rand_datetime': '2000-10-05T02:37:34.732729+04:00',
    'text_array': [
    'c751de4d5bfe4447804fbed1f004b323',
    'e103f77f3058441abc89506281ce896c',
],
    'words': 'ladybug ant',
    'nested': {
    'id': 110,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    [
    4,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'sheep',
    'deer',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': [
    66,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'fly',
    'maybe_null': None,
},
},
    {
    'id': 11,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 111,
    'id_str': [
    '11',
],
    'text_data': '0ad477bc5a5b41d38c6a86bdd4ffb780',
    'rand_digit': 6,
    'rand_number': 0.17194,
    'rand_signed_int': 0,
    'rand_datetime': '2001-01-17 00:52:58.331277+0100',
    'text_array': [
    'ae45a25da40d483e95aa3b4cec1e5ce7',
    '92e10cdc469845e58ea65cc9caa2fac7',
],
    'words': 'scorpion crab',
    'nested': {
    'id': 111,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'mosquito',
    'spider',
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
    'mixed_type': 0.95695,
    'maybe_null': 'fly',
},
},
    {
    'id': 12,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 112,
    'id_str': [
    '10',
    '28',
    '30',
],
    'text_data': 'e23c64a833cf43b5801efb54537657e0',
    'rand_digit': 3,
    'rand_number': 0.69107,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-19T12:39:51',
    'text_array': [
    '8a3ffe568b5e402da177c47fe51287e0',
    '900dac27461d4f2d818e46088afc3131',
],
    'words': 'chicken horse',
    'nested': {
    'id': 112,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 6,
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 7,
},
    {
    'nested_empty': None,
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
],
    'word': 'rabbit',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'pig',
    'rhino',
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
    'mixed_type': {
    'key': 'value',
},
},
},
    {
    'id': 13,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 113,
    'id_str': [
    '16',
    '30',
],
    'text_data': 'fdeec80398d74475878c936b8fbed709',
    'rand_digit': 8,
    'rand_number': 0.11927,
    'rand_signed_int': -8,
    'rand_datetime': '2000-10-22T11:14:48-1100',
    'text_array': [
    '5811a354e5bb407abc051623cbaf18a4',
    '1d65bd041ac94227ab965d1cbc291bf6',
],
    'words': 'snake fly',
    'nested': {
    'id': 113,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
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
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 5,
},
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
    'hello',
],
    'word': 'snail',
    'number': 5,
},
],
},
    'nested_array': [
    [
    -7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -9,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'lobster',
    'camel',
],
    'city': {
    'name': 'Geneva',
    'geo': {
    'lat': 46.204391,
    'lon': 6.143158,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 14,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 114,
    'id_str': [
    '04',
],
    'text_data': 'c1da2d4462f9451ea25262fd684b8423',
    'rand_digit': 5,
    'rand_number': 0.67486,
    'rand_signed_int': -8,
    'rand_datetime': '2000-09-29T04:43:09',
    'text_array': [
    'ceaf41d92e9b42d4929b967fd41d596f',
    '15335ad7737945459e34193252e3b858',
],
    'words': 'ladybug panda',
    'nested': {
    'id': 114,
    'rand_digit': 7,
    'array': [
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
],
    'word': 'whale',
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
    'giraffe',
    'chicken',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'giraffe',
    'maybe_null': None,
},
},
    {
    'id': 15,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 115,
    'id_str': [
],
    'text_data': 'cbab6124798c4d63a541ee2cf8286873',
    'rand_digit': 7,
    'rand_number': 0.15614,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-29T12:25:42.899401',
    'text_array': [
    'cfda7242e41346d389f092a20bd3d8ea',
    '2cdffd16edc24c29a28f6ea96c054928',
],
    'words': 'giraffe squid',
    'nested': {
    'id': 115,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'leopard',
    'number': 3,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'chicken',
    'snail',
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
    'mixed_type': 6,
    'maybe': 'lobster',
    'maybe_null': 'mouse',
},
},
    {
    'id': 16,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 116,
    'id_str': [
    '30',
    '21',
    '04',
],
    'text_data': '47ebb67265134bf2afe9343f66186654',
    'rand_digit': 7,
    'rand_number': 0.10702,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-01 09:52:19.657099',
    'text_array': [
    '5a583a8aef0345e98168b8b3d413ae8a',
    '5fb5ce33057d40be8d6af577585dca71',
],
    'words': 'lion snake',
    'nested': {
    'id': 116,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 6,
},
],
},
    'nested_array': [
    [
    2,
],
    [
    9,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'mosquito',
    'chicken',
],
    'city': {
    'name': 'Leeds',
    'geo': {
    'lat': 53.800755,
    'lon': -1.549077,
},
},
    'rand_tuple': [
    22,
],
    'rand_bool': False,
    'mixed_type': 'sloth',
    'maybe_null': 'rabbit',
},
},
    {
    'id': 17,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 117,
    'id_str': [
    '28',
    '27',
    '05',
    '07',
    '15',
],
    'text_data': '0d07951629874ef0a8a797f3376a1676',
    'rand_digit': 4,
    'rand_number': 0.97551,
    'rand_signed_int': 9,
    'rand_datetime': '2000-12-26',
    'text_array': [
    '1c376f1809544821a94ebbdab5584086',
    '556655975c314b04858f91da3c913ba6',
],
    'words': 'rhino fish',
    'nested': {
    'id': 117,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'mouse',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'panda',
    'number': 1,
},
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
    'word': 'crab',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -10,
],
],
    'two_words': [
    'deer',
    'fox',
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
    'mixed_type': False,
    'maybe_null': None,
},
},
    {
    'id': 18,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 118,
    'id_str': [
    '07',
    '01',
    '30',
    '25',
],
    'text_data': '2048f585ca774f6fa05d6462a15eb01e',
    'rand_digit': 6,
    'rand_number': 0.39649,
    'rand_signed_int': 10,
    'rand_datetime': '2000-05-15 11:03',
    'text_array': [
    '20dffda1175f4c0986a62c361696bddf',
    'dd0e04aaa5434136a3faff29202fea28',
],
    'words': 'wolf hyena',
    'nested': {
    'id': 118,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'wolf',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'snail',
    'rabbit',
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
    'mixed_type': 0.10423,
    'maybe': 'ant',
    'maybe_null': 'ant',
},
},
    {
    'id': 19,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 119,
    'id_str': [
    '12',
    '21',
    '03',
],
    'text_data': 'e5ffbd364fbb48e8a457dc6e74d782aa',
    'rand_digit': 9,
    'rand_number': 0.9236,
    'rand_signed_int': -6,
    'rand_datetime': '2000-07-15 11:17',
    'text_array': [
    'fc10d8ea84bd49b38b068c0107605d41',
    '56292285d32949d0b608d3d22919d6a1',
],
    'words': 'elephant grasshopper',
    'nested': {
    'id': 119,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 5,
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
    'word': 'mouse',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -8,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'bird',
    'spider',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.97247,
    'maybe': 'hippo',
},
},
    {
    'id': 20,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 120,
    'id_str': [
    '15',
    '14',
    '25',
],
    'text_data': 'e6be1832e06e41cebeafb606c053afd3',
    'rand_digit': 4,
    'rand_number': 0.86278,
    'rand_signed_int': 9,
    'rand_datetime': '2000-04-11 14:41:22.715518',
    'text_array': [
    '7db782e3581042e1b69771b4022af485',
    '59df7f59127549c28f1cec314541cd19',
],
    'words': 'snail wolf',
    'nested': {
    'id': 120,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lion',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=2, normalized=True),
    'two_words': [
    'whale',
    'snake',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'dragonfly',
},
},
    {
    'id': 21,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 121,
    'id_str': [
    '05',
    '20',
    '11',
    '21',
    '14',
],
    'text_data': '2e59f78fb0f746369f4ef9920d251c6c',
    'rand_digit': 7,
    'rand_number': 0.50225,
    'rand_signed_int': -4,
    'rand_datetime': '2000-03-05T13:25:29',
    'text_array': [
    'f29b58daceaa47eba56d0aabcc66316e',
    '01d56bf1a0df41ccbe82a57cdb33a385',
],
    'words': 'fish goat',
    'nested': {
    'id': 121,
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
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'mosquito',
    'cow',
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
    'mixed_type': 8,
    'maybe': 'goat',
    'maybe_null': None,
},
},
    {
    'id': 22,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 122,
    'id_str': [
    '11',
    '05',
    '16',
],
    'text_data': '95d6c1b65ad6480c8868ed0c378fcf80',
    'rand_digit': 5,
    'rand_number': 0.53959,
    'rand_signed_int': -7,
    'rand_datetime': '2000-12-23 05:22:19',
    'text_array': [
    '0ce53b5999e94ef99d7977325af92d47',
    '7a18c58343764ae3957211fd55549c82',
],
    'words': 'pig ape',
    'nested': {
    'id': 122,
    'rand_digit': 4,
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
    'word': 'turtle',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 10,
},
],
},
    'nested_array': [
    [
    5,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bird',
    'ape',
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
    'maybe_null': 'lobster',
},
},
    {
    'id': 23,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 123,
    'id_str': [
],
    'text_data': '7ef7eb6bdfde4804be5cbcdf4b2cd4ce',
    'rand_digit': 5,
    'rand_number': 0.22407,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-27T11:46:10',
    'text_array': [
    'ec526c1dc70747bb94e44cd5762007e1',
    'f7ee77e8ce1247c5842157a47f72d6a2',
],
    'words': 'dolphin snail',
    'nested': {
    'id': 123,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'cheetah',
    'scorpion',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'panda',
    'maybe_null': 'cat',
},
},
    {
    'id': 24,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 124,
    'id_str': [
    '09',
    '04',
    '09',
    '04',
],
    'text_data': 'f8db138fce444cf99c8cdc320c0e12c3',
    'rand_digit': 4,
    'rand_number': 0.72537,
    'rand_signed_int': 3,
    'rand_datetime': '2000-07-20 18:36:59.169651-0300',
    'text_array': [
    'd2a0f2e61462460b80857abeaff2d6b0',
    'd885ab5a60ce4ed2b478b215354e6440',
],
    'words': 'hyena fox',
    'nested': {
    'id': 124,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'jaguar',
    'frog',
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
    'mixed_type': 6,
},
},
    {
    'id': 25,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 125,
    'id_str': [
    '23',
    '25',
    '27',
    '14',
    '28',
],
    'text_data': 'e8e07cf4b19d4a63969b34042f6f6b08',
    'rand_digit': 5,
    'rand_number': 0.26457,
    'rand_signed_int': -5,
    'rand_datetime': '2000-07-27T20:56:26.201392+07:00',
    'text_array': [
    '660f6c18ab314304b559c4c01f0a695b',
    'd0181b8d628a45528f402f0f118e8aeb',
],
    'words': 'tiger dog',
    'nested': {
    'id': 125,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 1,
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
],
    'word': 'dragonfly',
    'number': 8,
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
    'hippo',
    'gorilla',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': [
    72,
],
    'rand_bool': True,
    'mixed_type': 'turtle',
    'maybe': 'hyena',
    'maybe_null': 'gorilla',
},
},
    {
    'id': 26,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 126,
    'id_str': [
    '15',
    '28',
],
    'text_data': 'e9ea0407251942fc8de12d4310851c16',
    'rand_digit': 8,
    'rand_number': 0.7187,
    'rand_signed_int': -6,
    'rand_datetime': '2000-07-02T08:38:15.156270',
    'text_array': [
    'dcacbb0cc9ec4809beaa7fc392ca1bf4',
    '09f6fa4149394c72acf4a0bb34b53319',
],
    'words': 'cat koala',
    'nested': {
    'id': 126,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'chicken',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'spider',
    'cat',
],
    'city': {
    'name': 'Zurich',
    'geo': {
    'lat': 47.376887,
    'lon': 8.541694,
},
},
    'rand_tuple': [
    8,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'lion',
    'maybe_null': None,
},
},
    {
    'id': 27,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 127,
    'id_str': [
    '14',
    '17',
    '25',
    '15',
],
    'text_data': '48518c9ba184420dbe243e084207bebf',
    'rand_digit': 0,
    'rand_number': 0.7098,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-21T03:32:27',
    'text_array': [
    '9d6dd1f39399493aac47ed85658a3085',
    'dbc886d9d23c45beaee672104fe8dedf',
],
    'words': 'butterfly frog',
    'nested': {
    'id': 127,
    'rand_digit': 7,
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
    'word': 'rabbit',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'squid',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dog',
    'tiger',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
},
},
    {
    'id': 28,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 128,
    'id_str': [
    '21',
],
    'text_data': '47fbca527a8a4f62a3e219cf6fee7774',
    'rand_digit': 8,
    'rand_number': 0.22278,
    'rand_signed_int': 3,
    'rand_datetime': '2000-06-16 15:09:03.058915',
    'text_array': [
    '2d593edc3d6540dd888fc147cf1b0942',
    'c8ea2965fd774dfb97b6d5c118b4fb69',
],
    'words': 'grasshopper crab',
    'nested': {
    'id': 128,
    'rand_digit': 4,
    'array': [
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
    'word': 'ant',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
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
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -5,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bird',
    'cat',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'dolphin',
    'maybe_null': 'hippo',
},
},
    {
    'id': 29,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 129,
    'id_str': [
],
    'text_data': '5c4179f671524f7e9e2c8adbd8d55f85',
    'rand_digit': 9,
    'rand_number': 0.49133,
    'rand_signed_int': 9,
    'rand_datetime': '2001-01-23T06:25:55.045708',
    'text_array': [
    'f0ac50bc7c5f499f9be57878880ca538',
    '4f24451420b446e9aa699705d0a66a14',
],
    'words': 'spider ladybug',
    'nested': {
    'id': 129,
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
    'number': 8,
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
],
    'word': 'spider',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'goat',
    'tiger',
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
    'mixed_type': False,
    'maybe_null': 'whale',
},
},
    {
    'id': 30,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 130,
    'id_str': [
],
    'text_data': '14e5b5baf6e14816aab5195756d655c8',
    'rand_digit': 7,
    'rand_number': 0.07147,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-15 10:52:51',
    'text_array': [
    'ed1342c83fc4407cba8725d085988c1b',
    '44d777de8bef42939519a1c58c0e2ccc',
],
    'words': 'camel bird',
    'nested': {
    'id': 130,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'leopard',
    'bear',
],
    'city': {
    'name': 'Zurich',
    'geo': {
    'lat': 47.376887,
    'lon': 8.541694,
},
},
    'rand_tuple': [
    55,
],
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'bear',
},
},
    {
    'id': 31,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 131,
    'id_str': [
    '10',
    '01',
    '24',
    '27',
    '04',
],
    'text_data': '50ad5b360dab4810ad0d9e22a7b881e2',
    'rand_digit': 0,
    'rand_number': 0.73688,
    'rand_signed_int': -6,
    'rand_datetime': '2000-10-14T10:50:32.843978+01:00',
    'text_array': [
    '57a132c6ae9141c3b8d90eb1e5769857',
    'ff4c8d9bef444b3b94ec345b3c224eea',
],
    'words': 'lobster mouse',
    'nested': {
    'id': 131,
    'rand_digit': 6,
    'array': [
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
    'word': 'shark',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 8,
},
],
},
    'nested_array': [
    [
    -10,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'camel',
    'hyena',
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
    'maybe': 'mosquito',
    'maybe_null': 'deer',
},
},
    {
    'id': 32,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 132,
    'id_str': [
    '02',
    '14',
    '22',
    '06',
],
    'text_data': '1b5005ff56f04a1da9198917b6c6cab6',
    'rand_digit': 6,
    'rand_number': 0.75348,
    'rand_signed_int': -1,
    'rand_datetime': '2000-08-21T07:04:53+0100',
    'text_array': [
    '5203096c681844eaabfa3b4c76e9a6a4',
    'ddc7820bcc2f4c59838262f87403a4a5',
],
    'words': 'giraffe dolphin',
    'nested': {
    'id': 132,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'sloth',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'monkey',
    'cheetah',
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
    'mixed_type': 0.49683,
    'maybe_null': 'zebra',
},
},
    {
    'id': 33,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_7,80__',
},
    'payload': {
    'id': 133,
    'id_str': [
    '10',
    '03',
    '24',
    '07',
],
    'text_data': '2384399ae1c14287b74840ab2a0c738c',
    'rand_digit': 0,
    'rand_number': 0.11706,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-03T02:04:07-1200',
    'text_array': [
    'bb84d319f7b147809bf066968e260520',
    '0929d9ba8331432bb8430138265499b3',
],
    'words': 'panda fox',
    'nested': {
    'id': 133,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mosquito',
    'mouse',
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
    'mixed_type': 'mouse',
    'maybe_null': 'hippo',
},
},
    {
    'id': 34,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 134,
    'id_str': [
    '11',
    '13',
    '22',
    '21',
],
    'text_data': '507d3cf10d1c477c89f0d71518098ad7',
    'rand_digit': 4,
    'rand_number': 0.57404,
    'rand_signed_int': -1,
    'rand_datetime': '2001-01-12 03:42',
    'text_array': [
    '004f742653044a3496a5e81276f3614f',
    'ba825cc325e540d886fc249b4fe020bf',
],
    'words': 'fox gorilla',
    'nested': {
    'id': 134,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 3,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'koala',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bear',
    'horse',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': [
    52,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'cat',
    'maybe_null': None,
},
},
    {
    'id': 35,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 135,
    'id_str': [
    '15',
    '27',
    '04',
    '17',
    '07',
],
    'text_data': 'b00d953ef2404523a74bb0489ab6aa18',
    'rand_digit': 3,
    'rand_number': 0.43798,
    'rand_signed_int': 6,
    'rand_datetime': '2000-01-08T10:59:56-1000',
    'text_array': [
    '3cbc06ed6b8f47c2a5cc0781111ee2bd',
    'd45ca55d2a8a4e979ac5226b626dbd49',
],
    'words': 'cheetah squid',
    'nested': {
    'id': 135,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'dog',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'mouse',
    'gorilla',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'lobster',
},
},
    {
    'id': 36,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 136,
    'id_str': [
    '23',
    '17',
],
    'text_data': '052791d01ee24964886e49599f6a1c3b',
    'rand_digit': 6,
    'rand_number': 0.22757,
    'rand_signed_int': -3,
    'rand_datetime': '2000-12-09T14:30:53.357181',
    'text_array': [
    '565ee941fd0441fca138d0d5afc0d2d9',
    '92aa5a35102a4d309133178e2ee440b2',
],
    'words': 'dolphin hyena',
    'nested': {
    'id': 136,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 6,
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
    {
    'nested_empty': None,
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
    'word': 'giraffe',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'giraffe',
    'kangaroo',
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
    'mixed_type': 6,
    'maybe_null': 'frog',
},
},
    {
    'id': 37,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 137,
    'id_str': [
],
    'text_data': '10a0c3c230c94bba8c9707d081f81984',
    'rand_digit': 3,
    'rand_number': 0.96718,
    'rand_signed_int': 9,
    'rand_datetime': '2001-01-20 20:07:59-0300',
    'text_array': [
    '5bae12fa7eab41b6975ae73b5c4b7780',
    '3d155930b32f4f6ebe38b16f0df38159',
],
    'words': 'sloth lizard',
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
    'word': 'bee',
    'number': 5,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fox',
    'number': 10,
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
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'duck',
    'turtle',
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
    'mixed_type': 5,
    'maybe': 'octopus',
},
},
    {
    'id': 38,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_10,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 138,
    'id_str': [
    '08',
    '13',
    '23',
],
    'text_data': '99236713a7f44b69a4cfa898a77c5e1f',
    'rand_digit': 7,
    'rand_number': 0.26387,
    'rand_signed_int': -7,
    'rand_datetime': '2001-01-12T15:16:58-1000',
    'text_array': [
    '35961539e9a8415ea8017f7a1a305218',
    '3d61f81cf46d4908bbff9de3d9f7d394',
],
    'words': 'tiger ladybug',
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
    'word': 'bee',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
    -4,
],
],
    'two_words': [
    'dog',
    'hyena',
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
    'mixed_type': 0,
},
},
    {
    'id': 39,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_6,100__',
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 139,
    'id_str': [
    '29',
],
    'text_data': '6f4216c75b6546919ffe4910e83a83e4',
    'rand_digit': 3,
    'rand_number': 0.26145,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-19',
    'text_array': [
    'f076fa840be347e8bf41e27dde344444',
    'b4735318417b4d0a8da575a33ff3ddb3',
],
    'words': 'zebra sheep',
    'nested': {
    'id': 139,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -2,
],
],
    'two_words': [
    'jaguar',
    'pig',
],
    'city': {
    'name': 'Dublin',
    'geo': {
    'lat': 53.349805,
    'lon': -6.26031,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.18201,
    'maybe_null': 'rabbit',
},
},
    {
    'id': 40,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 140,
    'id_str': [
    '20',
    '29',
    '26',
    '08',
],
    'text_data': 'dff80fafc70348169d58e76fd8559dc5',
    'rand_digit': 1,
    'rand_number': 0.30692,
    'rand_signed_int': 10,
    'rand_datetime': '2000-02-13 23:26:36',
    'text_array': [
    '32048daa5c8648aa8c8da83d1351b06e',
    'd42f5c3a9a8041e7899c8d2826b59631',
],
    'words': 'bee zebra',
    'nested': {
    'id': 140,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
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
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'leopard',
    'ladybug',
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
    'maybe': 'dog',
},
},
    {
    'id': 41,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 141,
    'id_str': [
    '13',
    '25',
],
    'text_data': '8e47419fbd054ceda4fc8522e5de8e9d',
    'rand_digit': 9,
    'rand_number': 0.13677,
    'rand_signed_int': -5,
    'rand_datetime': '2000-06-06',
    'text_array': [
    'a553a5824068425a88921580b72f2fda',
    'f697df6ffc604fa8955cfe1e1d526e3d',
],
    'words': 'monkey ladybug',
    'nested': {
    'id': 141,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'octopus',
    'lion',
],
    'city': {
    'name': 'Lima',
    'geo': {
    'lat': -12.046374,
    'lon': -77.042793,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 7,
    'maybe': 'gorilla',
    'maybe_null': None,
},
},
    {
    'id': 42,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 142,
    'id_str': [
    '13',
    '10',
],
    'text_data': '33aca4264cd643a7aa2bd49c9a312efe',
    'rand_digit': 9,
    'rand_number': 0.71972,
    'rand_signed_int': -3,
    'rand_datetime': '2000-11-14',
    'text_array': [
    'c532a46b3b68480bbc373f8cf9e3204d',
    'f3bd8bb1292b43a7a77d038d704bcb17',
],
    'words': 'cat cheetah',
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
    'word': 'spider',
    'number': 7,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'snail',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 3,
},
],
},
    'nested_array': [
    [
    2,
],
],
    'two_words': [
    'duck',
    'giraffe',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'cheetah',
    'maybe_null': 'snake',
},
},
    {
    'id': 43,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 143,
    'id_str': [
],
    'text_data': '5ba27bc9eb67445db101ddfd26b2117e',
    'rand_digit': 4,
    'rand_number': 0.09232,
    'rand_signed_int': -5,
    'rand_datetime': '2000-09-26 00:48:34',
    'text_array': [
    'e716257dbe534e19af080141e7c60e01',
    '57e6d5945ad748eca84a60388eb2d079',
],
    'words': 'bird rabbit',
    'nested': {
    'id': 143,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'squid',
    'duck',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'cheetah',
    'maybe_null': 'snail',
},
},
    {
    'id': 44,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 144,
    'id_str': [
    '03',
    '08',
    '14',
    '14',
],
    'text_data': '3bd59c20375340da9d3068da6bbc23f2',
    'rand_digit': 8,
    'rand_number': 0.93427,
    'rand_signed_int': 1,
    'rand_datetime': '2000-07-20T22:23:31+0300',
    'text_array': [
    '6decf4b96a704f7589015c97d268069f',
    '2d49db7266ce4852a780adfb4b46c56b',
],
    'words': 'frog bear',
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
    'word': 'squid',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'leopard',
    'duck',
],
    'city': {
    'name': 'Cardiff',
    'geo': {
    'lat': 51.481581,
    'lon': -3.17909,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'gorilla',
},
},
    {
    'id': 45,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_7,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 145,
    'id_str': [
    '22',
    '16',
    '17',
],
    'text_data': '05a6d8911de345a1a11542000503334a',
    'rand_digit': 9,
    'rand_number': 0.02279,
    'rand_signed_int': 6,
    'rand_datetime': '2001-01-11 13:17',
    'text_array': [
    '82154916db7a48cfb4489e2b57f779e8',
    '5d41c92ea7f54ffcb88eb44f2f00ce9b',
],
    'words': 'octopus scorpion',
    'nested': {
    'id': 145,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -3,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'elephant',
    'ant',
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
},
},
    {
    'id': 46,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 146,
    'id_str': [
],
    'text_data': '1b93556388fc4164a6f019058b17b880',
    'rand_digit': 6,
    'rand_number': 0.84117,
    'rand_signed_int': 2,
    'rand_datetime': '2000-09-17T15:12:02',
    'text_array': [
    '0ffdc965617e4cdc94e44ac8620bffcc',
    '91051dd7b191417399128a2b58c42220',
],
    'words': 'frog horse',
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
    'word': 'hippo',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'wolf',
    'mosquito',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'mosquito',
},
},
    {
    'id': 47,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_8,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 147,
    'id_str': [
    '21',
    '27',
    '04',
    '03',
],
    'text_data': 'b711122c974e4bb596d5a74284ccec7b',
    'rand_digit': 1,
    'rand_number': 0.39075,
    'rand_signed_int': 5,
    'rand_datetime': '2000-11-13 02:56',
    'text_array': [
    '1085ef0a23dd4266910f214048539aae',
    '49d13555f4694d62b37efbf6ecda7e7f',
],
    'words': 'camel rhino',
    'nested': {
    'id': 147,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 6,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'ape',
    'wolf',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': [
    95,
],
    'rand_bool': False,
    'mixed_type': 0.65972,
    'maybe': 'squid',
    'maybe_null': 'cheetah',
},
},
    {
    'id': 48,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 148,
    'id_str': [
],
    'text_data': '03c805edb24c4130bfd0066e7f4458c8',
    'rand_digit': 4,
    'rand_number': 0.50396,
    'rand_signed_int': 2,
    'rand_datetime': '2000-02-22T13:28:33',
    'text_array': [
    'd2716fb315d34cfd89dd8fdaf65f5170',
    '8b161e0eec1f42ceaef16e8bba3176dc',
],
    'words': 'jaguar deer',
    'nested': {
    'id': 148,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
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
    'number': 10,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'elephant',
    'goat',
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
    'mixed_type': None,
    'maybe': 'bee',
    'maybe_null': 'fox',
},
},
    {
    'id': 49,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_3,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_10,80__',
},
    'payload': {
    'id': 149,
    'id_str': [
    '26',
],
    'text_data': '292788da9f1c453b9fba7f9140067088',
    'rand_digit': 7,
    'rand_number': 0.00671,
    'rand_signed_int': 7,
    'rand_datetime': '2000-06-03 03:41:58',
    'text_array': [
    '5d0e95a1356f49008f3e113239548c75',
    '3077f34a187c4df492197a4b0f3b466b',
],
    'words': 'lobster frog',
    'nested': {
    'id': 149,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'lobster',
    'sloth',
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
    'mixed_type': 'bee',
    'maybe': 'camel',
    'maybe_null': 'bird',
},
},
    {
    'id': 50,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 150,
    'id_str': [
    '20',
    '08',
    '21',
],
    'text_data': '16cb8cc9cbcf4bf4ae90a1156dfa2392',
    'rand_digit': 2,
    'rand_number': 0.75472,
    'rand_signed_int': 8,
    'rand_datetime': '2000-08-01',
    'text_array': [
    '569422ec08254ab8be0d265cf3c7802c',
    'bdeb72001b854773bac444bcc7916c1b',
],
    'words': 'whale panda',
    'nested': {
    'id': 150,
    'rand_digit': 9,
    'array': [
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
],
    'word': 'duck',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    [
    2,
],
],
    'two_words': [
    'snail',
    'octopus',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': [
    35,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'crab',
    'maybe_null': 'lobster',
},
},
    {
    'id': 51,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_6,80__',
},
    'payload': {
    'id': 151,
    'id_str': [
    '25',
    '02',
],
    'text_data': '3a077376124a4e4eb6c13fa8aa69e44c',
    'rand_digit': 2,
    'rand_number': 0.64098,
    'rand_signed_int': -9,
    'rand_datetime': '2000-04-19T10:11:34.250559+1100',
    'text_array': [
    '0484722df3214263a44ebd6407c25355',
    'dec00092f357499c95982f7e54b7d685',
],
    'words': 'dog fish',
    'nested': {
    'id': 151,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'ape',
    'number': 2,
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
    'word': 'wolf',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'fox',
    'jaguar',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'lizard',
    'maybe_null': 'ape',
},
},
    {
    'id': 52,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_2,80__',
},
    'payload': {
    'id': 152,
    'id_str': [
    '23',
    '30',
],
    'text_data': '097ac66a1bfa4a749b3b3ef4ec2f7039',
    'rand_digit': 5,
    'rand_number': 0.62055,
    'rand_signed_int': -5,
    'rand_datetime': '2000-06-01 15:11:36+0600',
    'text_array': [
    'a8400f458ca741c29c834cc851b1d203',
    '848172529c034081aabaff697eb10119',
],
    'words': 'spider hippo',
    'nested': {
    'id': 152,
    'rand_digit': 9,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'giraffe',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'lion',
    'mosquito',
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
    'mixed_type': False,
    'maybe_null': None,
},
},
    {
    'id': 53,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_9,50__',
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 153,
    'id_str': [
    '15',
    '13',
    '29',
    '14',
],
    'text_data': 'd5f549daed4f473d99330dace0696f5d',
    'rand_digit': 9,
    'rand_number': 0.13767,
    'rand_signed_int': 1,
    'rand_datetime': '2000-06-25',
    'text_array': [
    '8a847983ec93483098c2e833738f2da5',
    'ff1221d31a1f4355b3a73b9685a4b9be',
],
    'words': 'chicken pig',
    'nested': {
    'id': 153,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lion',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 8,
},
],
},
    'nested_array': [
    [
    -5,
],
],
    'two_words': [
    'turtle',
    'hyena',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 54,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_4,80__',
},
    'payload': {
    'id': 154,
    'id_str': [
    '08',
    '21',
    '30',
    '01',
],
    'text_data': 'b72abe9c904e4567b2ec2e2b7f33b821',
    'rand_digit': 7,
    'rand_number': 0.23234,
    'rand_signed_int': 4,
    'rand_datetime': '2000-05-17T23:12:41+0200',
    'text_array': [
    'e488a188dfa24e49a8723425586499fd',
    'ca34047bc5094093ab62a31f9786e5eb',
],
    'words': 'turtle elephant',
    'nested': {
    'id': 154,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'horse',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
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
],
},
    'nested_array': [
    [
    -2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'frog',
    'giraffe',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': [
    98,
],
    'rand_bool': True,
    'mixed_type': 4,
    'maybe': 'pig',
    'maybe_null': 'sloth',
},
},
    {
    'id': 55,
    'vector': {
    'multi-text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'multi-image': '__FLOAT_MULTI_DIM_4,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 155,
    'id_str': [
    '26',
    '15',
    '12',
],
    'text_data': '0c9762df45644ff1b1d02bec4d434f55',
    'rand_digit': 5,
    'rand_number': 0.54315,
    'rand_signed_int': 3,
    'rand_datetime': '2000-03-03 11:45:41.332934',
    'text_array': [
    'e396ae6606654ef1a9971ab21fa215f6',
    '774d536497794922a9421f39baf6861c',
],
    'words': 'giraffe kangaroo',
    'nested': {
    'id': 155,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'scorpion',
    'snail',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': [
    81,
],
    'rand_bool': True,
    'mixed_type': 7,
    'maybe': 'leopard',
},
},
    {
    'id': 56,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 156,
    'id_str': [
    '17',
    '16',
],
    'text_data': '8ef9522316d74eebb4da92cec866accb',
    'rand_digit': 3,
    'rand_number': 0.60485,
    'rand_signed_int': -10,
    'rand_datetime': '2000-09-23 15:56:36.739737-1100',
    'text_array': [
    '6965340ed2e149f5a67f03bf23873ea6',
    '6cc8d49de1b84347816138cfcc42e273',
],
    'words': 'cheetah whale',
    'nested': {
    'id': 156,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'snake',
    'duck',
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
    'mixed_type': False,
    'maybe_null': None,
},
},
    {
    'id': 57,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 157,
    'id_str': [
    '24',
    '05',
    '17',
    '25',
    '04',
],
    'text_data': '2c84251acda24112a42158e13955b4c0',
    'rand_digit': 3,
    'rand_number': 0.77371,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-26T16:03:03.561128',
    'text_array': [
    'd04a916a732c4dacaff5675c18c691d6',
    '7bfabda22de34fe1bee1f54b28badb65',
],
    'words': 'fox cat',
    'nested': {
    'id': 157,
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -6,
],
],
    'two_words': [
    'lizard',
    'dolphin',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'whale',
},
},
    {
    'id': 58,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_5,50__',
    'multi-image': '__FLOAT_MULTI_DIM_9,100__',
    'multi-code': '__FLOAT_MULTI_DIM_9,80__',
},
    'payload': {
    'id': 158,
    'id_str': [
    '10',
    '04',
    '24',
],
    'text_data': 'a38367beee4f46b59ece7b109dea185d',
    'rand_digit': 2,
    'rand_number': 0.15161,
    'rand_signed_int': 3,
    'rand_datetime': '2000-07-28',
    'text_array': [
    'd8353f435b1c4e488d642428b82ae521',
    '646c43c475144e2e81ca436f22a924b6',
],
    'words': 'butterfly rhino',
    'nested': {
    'id': 158,
    'rand_digit': 1,
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
    'word': 'chicken',
    'number': 9,
},
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
],
    'word': 'wolf',
    'number': 10,
},
],
},
    'nested_array': [
    [
    0,
],
],
    'two_words': [
    'bee',
    'lobster',
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
    'mixed_type': None,
    'maybe_null': None,
},
},
    {
    'id': 59,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_4,50__',
    'multi-image': '__FLOAT_MULTI_DIM_7,100__',
    'multi-code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 159,
    'id_str': [
    '02',
    '25',
    '13',
],
    'text_data': 'b7f3c73d3e194aa6938f9fdbe65b90d4',
    'rand_digit': 9,
    'rand_number': 0.15231,
    'rand_signed_int': -9,
    'rand_datetime': '2000-03-24T09:33:13',
    'text_array': [
    '006c4247c0c447c1a5e7c6d5e4a2b6a4',
    '81b5d6609c4945418eb7b4472c7710d8',
],
    'words': 'lizard bird',
    'nested': {
    'id': 159,
    'rand_digit': 0,
    'array': [
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
    'word': 'pig',
    'number': 1,
},
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
    'word': 'lobster',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'monkey',
    'chicken',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 60,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_6,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 160,
    'id_str': [
    '24',
    '13',
    '18',
],
    'text_data': '8cc480f57ad94cfd86c2a939319a1d2b',
    'rand_digit': 1,
    'rand_number': 0.30311,
    'rand_signed_int': 0,
    'rand_datetime': '2000-11-06T19:55:57.876312',
    'text_array': [
    '2051ce7b37ae4063a8d944a7adec3f69',
    '8f6cdae9b0824e32868b7d66fc2deb53',
],
    'words': 'scorpion deer',
    'nested': {
    'id': 160,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'lobster',
    'fish',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': [
    51,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'hippo',
    'maybe_null': 'butterfly',
},
},
    {
    'id': 61,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_10,50__',
    'multi-image': '__FLOAT_MULTI_DIM_5,100__',
    'multi-code': '__FLOAT_MULTI_DIM_8,80__',
},
    'payload': {
    'id': 161,
    'id_str': [
],
    'text_data': '085f776d1360455a9ff67d5417878fcc',
    'rand_digit': 2,
    'rand_number': 0.46973,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-02 17:06:59+0600',
    'text_array': [
    '01ea7ac6b65c4ed08813ca4aed46c80c',
    '43db9ac7d5784aa58128c74dbcad3fc4',
],
    'words': 'elephant camel',
    'nested': {
    'id': 161,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
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
],
    'word': 'cat',
    'number': 6,
},
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
    'ape',
    'deer',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
},
    {
    'id': 62,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_8,50__',
    'multi-image': '__FLOAT_MULTI_DIM_2,100__',
    'multi-code': '__FLOAT_MULTI_DIM_3,80__',
},
    'payload': {
    'id': 162,
    'id_str': [
    '14',
    '05',
],
    'text_data': 'a2f57fb50788427c9c8df52bebba4572',
    'rand_digit': 8,
    'rand_number': 0.80558,
    'rand_signed_int': 10,
    'rand_datetime': '2000-12-09 15:27:53.099330-1000',
    'text_array': [
    '6fb2b9df745a4f96a650abcd09bb22e8',
    'aa23ab83b8f04d0183e8b98dff4fea60',
],
    'words': 'grasshopper scorpion',
    'nested': {
    'id': 162,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ant',
    'number': 6,
},
    {
    'nested_empty': None,
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
    'word': 'pig',
    'number': 7,
},
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
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'octopus',
    'monkey',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
},
    {
    'id': 63,
    'vector': {
    'multi-text': '__FLOAT_MULTI_DIM_2,50__',
    'multi-image': '__FLOAT_MULTI_DIM_3,100__',
    'multi-code': '__FLOAT_MULTI_DIM_5,80__',
},
    'payload': {
    'id': 163,
    'id_str': [
    '29',
],
    'text_data': 'ca1b1f71331146ef9cc126602bc8a224',
    'rand_digit': 4,
    'rand_number': 0.08304,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-25 08:44:53-1000',
    'text_array': [
    '44ca3b602b76438db3124e68e2a7484e',
    '8f4ade7c45cd42cd97eb59bfb89ce49f',
],
    'words': 'pig kangaroo',
    'nested': {
    'id': 163,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 8,
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
],
    'two_words': [
    'turtle',
    'duck',
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
    'mixed_type': 'lizard',
    'maybe': 'rhino',
    'maybe_null': 'bear',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_multivector_updates.test_upload_points')
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
    test = TestMultivectorUpdatestestUploadPoints()
    test.run_tests()
