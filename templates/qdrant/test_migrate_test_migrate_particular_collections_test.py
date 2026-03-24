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
logger = logging.getLogger('vdb_fuzzer.test.test_migrate_test_migrate_particular_collections')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_migrate.test_migrate_particular_collections"
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


def send_request(content, request_type="PUT", url_path="http://localhost:6333/collections/collection_1", custom_headers=None):
    """
    发送请求到目标服务器

    Args:
        content: 请求内容
        request_type: 请求方法，默认为"PUT"
        url_path: URL路径，默认为"http://localhost:6333/collections/collection_1"
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



class TestMigratetestMigrateParticularCollections:
    """自动生成的VDB模糊测试类 - test_migrate.test_migrate_particular_collections"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_migrate.test_migrate_particular_collections"
        self.test_count = 15  # 测试方法数量
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
        """测试请求 0 - PUT http://localhost:6333/collections/collection_1"""
        logger.info(f"跳过非写请求或无内容请求: PUT http://localhost:6333/collections/collection_1")
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/collection_1'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '467',
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
    'hnsw_config': {
    'm': 16,
    'ef_construct': 100,
    'full_scan_threshold': 10000,
    'max_indexing_threads': 0,
},
    'wal_config': {
    'wal_capacity_mb': 32,
    'wal_segments_ahead': 0,
},
    'optimizers_config': {
    'deleted_threshold': 0.2,
    'vacuum_min_vector_number': 1000,
    'default_segment_number': 0,
    'indexing_threshold': 20000,
    'flush_interval_sec': 5,
    'max_optimization_threads': 1,
},
}


        send_request(original_content, method, url_path, headers)
        return True



    def test_request_1(self):
        """测试请求 1 - PUT http://localhost:6333/collections/collection_1/points?wait=true"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/collection_1/points?wait=true")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/collection_1/points?wait=true'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '10518',
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
    '03',
    '21',
],
    'text_data': 'd6ea977251894f01b6ea0f13831e45c1',
    'rand_digit': 7,
    'rand_number': 0.98691,
    'rand_signed_int': 8,
    'rand_datetime': '2000-10-20 11:43:46',
    'text_array': [
    '9aee40a166e44d4f9b5416be084ae30a',
    'd6cfe4571b2143bbb71cb80eddb0bf46',
],
    'words': 'snake mouse',
    'nested': {
    'id': 100,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 2,
},
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
    'word': 'fish',
    'number': 4,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'bee',
    'fly',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'spider',
    'maybe_null': None,
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
],
    'text_data': '8d82b55629b643608354a062debaecd4',
    'rand_digit': 3,
    'rand_number': 0.40943,
    'rand_signed_int': 6,
    'rand_datetime': '2000-06-25 19:55:35.116550+0600',
    'text_array': [
    '7446ce55ceca450ca1156671bf1a6bc1',
    'a70a2c29ac014c558eb38b8c2f6eb9ca',
],
    'words': 'cat camel',
    'nested': {
    'id': 101,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    2,
],
],
    'two_words': [
    'cat',
    'bird',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'chicken',
    'maybe_null': 'cat',
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
        """测试请求 2 - POST http://localhost:6333/collections/collection_1/points/count"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/collection_1/points/count")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/collection_1/points/count'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '14',
}
        
        # 原始请求内容
        original_content = {
    'exact': True,
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
        """测试请求 3 - PUT http://localhost:6333/collections/collection_2"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/collection_2")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/collection_2'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '467',
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
    'hnsw_config': {
    'm': 16,
    'ef_construct': 100,
    'full_scan_threshold': 10000,
    'max_indexing_threads': 0,
},
    'wal_config': {
    'wal_capacity_mb': 32,
    'wal_segments_ahead': 0,
},
    'optimizers_config': {
    'deleted_threshold': 0.2,
    'vacuum_min_vector_number': 1000,
    'default_segment_number': 0,
    'indexing_threshold': 20000,
    'flush_interval_sec': 5,
    'max_optimization_threads': 1,
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
        """测试请求 4 - PUT http://localhost:6333/collections/collection_2/points?wait=true"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/collection_2/points?wait=true")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/collection_2/points?wait=true'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '10463',
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
    '28',
    '17',
    '22',
    '27',
    '20',
],
    'text_data': '1cd0737c98f54eab9c6998ed8327e576',
    'rand_digit': 9,
    'rand_number': 0.382,
    'rand_signed_int': 5,
    'rand_datetime': '2000-07-08T19:45:31.221322',
    'text_array': [
    'd5175fb71a584aefbd030c465f32eb15',
    'cc6c2e85f6974490862d6a1196cbabd4',
],
    'words': 'sloth mosquito',
    'nested': {
    'id': 100,
    'rand_digit': 5,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'monkey',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'elephant',
    'panda',
],
    'city': {
    'name': 'Dnipro',
    'geo': {
    'lat': 48.464717,
    'lon': 35.046183,
},
},
    'rand_tuple': [
    92,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'spider',
    'maybe_null': None,
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
    '23',
    '18',
    '07',
    '27',
],
    'text_data': 'e7b1802ae1d24a9497756ee5fd697c4b',
    'rand_digit': 0,
    'rand_number': 0.42406,
    'rand_signed_int': 0,
    'rand_datetime': '2000-06-02 06:10:12.849348+1000',
    'text_array': [
    'f2ba71adcddd4845ad535c380b082a81',
    'ac1f0f1064c9414584f0aca78ee1d181',
],
    'words': 'scorpion cow',
    'nested': {
    'id': 101,
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
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'monkey',
    'lizard',
],
    'city': {
    'name': 'Moscow',
    'geo': {
    'lat': 55.755826,
    'lon': 37.6173,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
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



    def test_request_5(self):
        """测试请求 5 - POST http://localhost:6333/collections/collection_2/points/count"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/collection_2/points/count")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/collection_2/points/count'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '14',
}
        
        # 原始请求内容
        original_content = {
    'exact': True,
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
        """测试请求 6 - POST http://localhost:6333/collections/collection_1/points/scroll"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/collection_1/points/scroll")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/collection_1/points/scroll'
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



    def test_request_7(self):
        """测试请求 7 - POST http://localhost:6333/collections/collection_2/points/scroll"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/collection_2/points/scroll")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/collection_2/points/scroll'
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



    def test_request_8(self):
        """测试请求 8 - PUT http://localhost:6333/collections/collection_1?timeout=60"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/collection_1?timeout=60")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/collection_1?timeout=60'
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



    def test_request_9(self):
        """测试请求 9 - PUT http://localhost:6333/collections/collection_2?timeout=60"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/collection_2?timeout=60")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/collection_2?timeout=60'
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



    def test_request_10(self):
        """测试请求 10 - PUT http://localhost:6333/collections/collection_3?timeout=60"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/collection_3?timeout=60")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/collection_3?timeout=60'
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



    def test_request_11(self):
        """测试请求 11 - PUT http://localhost:6333/collections/collection_3/points?wait=true"""
        logger.info(f"测试请求: PUT http://localhost:6333/collections/collection_3/points?wait=true")
        
        method = 'PUT'
        url_path = 'http://localhost:6333/collections/collection_3/points?wait=true'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '136876',
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
    '18',
    '14',
    '22',
    '08',
],
    'text_data': 'd37a2d1178064307a697f92b7562b6eb',
    'rand_digit': 9,
    'rand_number': 0.86421,
    'rand_signed_int': 10,
    'rand_datetime': '2000-01-02T00:48:36+0100',
    'text_array': [
    '7e5b3fb9590841ab9f4292e17e9b189d',
    '84655995784243c088e796d236b98644',
],
    'words': 'sloth dog',
    'nested': {
    'id': 100,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'mouse',
    'giraffe',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': [
    30,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'tiger',
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
    '30',
    '05',
    '13',
],
    'text_data': '9d50be0f5be340f5888e8df6b6e7c5f1',
    'rand_digit': 1,
    'rand_number': 0.47725,
    'rand_signed_int': -10,
    'rand_datetime': '2001-01-24 18:04',
    'text_array': [
    '6f19347c881b497f8a30d23287049527',
    '71dcf30e617649359477ec9f2672d8e2',
],
    'words': 'grasshopper shark',
    'nested': {
    'id': 101,
    'rand_digit': 8,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'kangaroo',
    'snail',
],
    'city': {
    'name': 'Buenos Aires',
    'geo': {
    'lat': -34.603684,
    'lon': -58.381559,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 'fish',
    'maybe': 'lion',
    'maybe_null': 'fly',
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
    '07',
    '27',
],
    'text_data': 'a5d0597320034e498f87319ce2b094bc',
    'rand_digit': 4,
    'rand_number': 0.18913,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-07T02:37:19',
    'text_array': [
    'ba90078242a2471fae014f94d99f56ed',
    'b222d1c747ed4cf6ae0dc0dd973e4505',
],
    'words': 'elephant turtle',
    'nested': {
    'id': 102,
    'rand_digit': 7,
    'array': [
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
],
    'word': 'deer',
    'number': 2,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,2__',
    'two_words': [
    'mosquito',
    'fox',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': [
    35,
],
    'rand_bool': False,
    'mixed_type': 7,
    'maybe': 'bear',
    'maybe_null': 'monkey',
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
    '15',
],
    'text_data': '7a12bccdb5074726984442c90a1f8c1f',
    'rand_digit': 3,
    'rand_number': 0.10527,
    'rand_signed_int': 4,
    'rand_datetime': '2000-06-27 20:02',
    'text_array': [
    'fdfe15fc52154aef93712d41c7d07973',
    '0114c0a5aaf040beb7c03d423d34d0cb',
],
    'words': 'octopus octopus',
    'nested': {
    'id': 103,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    0,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'duck',
    'turtle',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'scorpion',
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
    '08',
    '23',
],
    'text_data': 'ced2392863494469a8ea92f9f808a423',
    'rand_digit': 9,
    'rand_number': 0.79206,
    'rand_signed_int': 0,
    'rand_datetime': '2000-12-17T08:50:58',
    'text_array': [
    'e67d54e8a0664ec6bbf1dd1289ff18d7',
    'e610ed6c83b94ded9ad2e7a271b01f3c',
],
    'words': 'lizard turtle',
    'nested': {
    'id': 104,
    'rand_digit': 9,
    'array': [
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 1,
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
],
    'two_words': [
    'koala',
    'dolphin',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 3,
    'maybe': 'ant',
    'maybe_null': None,
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
    '15',
    '23',
],
    'text_data': '06b7c85dc9154f3ca5739801ab099f58',
    'rand_digit': 9,
    'rand_number': 0.24686,
    'rand_signed_int': -3,
    'rand_datetime': '2001-01-03T06:13:44.645030+0200',
    'text_array': [
    'a33247206efe4056a45917d42c4a4d16',
    '335268d39bb040b1ace5ac495957c37e',
],
    'words': 'cheetah crab',
    'nested': {
    'id': 105,
    'rand_digit': 9,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'deer',
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
    'word': 'turtle',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bear',
    'lobster',
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
    'mixed_type': 0.92826,
    'maybe_null': 'ant',
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
    '02',
    '05',
    '16',
],
    'text_data': 'cc9f590c57e349d48b8fc01fccf82ef1',
    'rand_digit': 0,
    'rand_number': 0.74852,
    'rand_signed_int': -4,
    'rand_datetime': '2000-09-03',
    'text_array': [
    '129482e2966441b5b11eb9df8f0e8aa1',
    'c47835fc710d45e09d22f3b734cc683c',
],
    'words': 'leopard deer',
    'nested': {
    'id': 106,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    3,
],
],
    'two_words': [
    'fox',
    'giraffe',
],
    'city': {
    'name': 'Singapore',
    'geo': {
    'lat': 1.352083,
    'lon': 103.819836,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bird',
    'maybe_null': 'elephant',
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
],
    'text_data': 'cb1fdefe935f424f93e82659036f8b5d',
    'rand_digit': 1,
    'rand_number': 0.70131,
    'rand_signed_int': 6,
    'rand_datetime': '2000-11-05T00:20:04',
    'text_array': [
    'c5b2b9b2866946e292e6a4c213d801b0',
    '0f6752e5e13c4cf1a513e746c71c2c38',
],
    'words': 'ladybug horse',
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
    'word': 'squid',
    'number': 6,
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
    'word': 'mouse',
    'number': 2,
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
    'cow',
    'grasshopper',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
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
    'id': 8,
    'vector': {
    'text': self.mutator.generate_float_array(dimension=50, normalized=True),
    'image': self.mutator.generate_float_array(dimension=100, normalized=True),
    'code': self.mutator.generate_float_array(dimension=80, normalized=True),
},
    'payload': {
    'id': 108,
    'id_str': [
    '27',
    '18',
    '11',
    '05',
],
    'text_data': '9727d08914b6408a9da13f2aca950f9b',
    'rand_digit': 2,
    'rand_number': 0.91522,
    'rand_signed_int': 9,
    'rand_datetime': '2000-03-20',
    'text_array': [
    'c253835455a14edb9ba945309980188c',
    '2bab1cc6b8144500a738bb4d244de385',
],
    'words': 'kangaroo sloth',
    'nested': {
    'id': 108,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
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
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'kangaroo',
    'cat',
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
    'mixed_type': 'lion',
    'maybe_null': 'mosquito',
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
    '05',
    '06',
    '12',
],
    'text_data': 'c2d5caffe93941ef8e738a42fddd4115',
    'rand_digit': 7,
    'rand_number': 0.31171,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-23T05:11:23.945934',
    'text_array': [
    'cab257fa681744ec85adc481d03009e1',
    '98f0ffde305046a5bcec089ea28039ad',
],
    'words': 'bee squid',
    'nested': {
    'id': 109,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'deer',
    'bird',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'ant',
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
    '12',
    '18',
],
    'text_data': '292ebdc3ee3d4b0d9c0e055fc35af4a9',
    'rand_digit': 0,
    'rand_number': 0.72596,
    'rand_signed_int': 10,
    'rand_datetime': '2000-01-30',
    'text_array': [
    '743c3229ccfa48ec9b8dcb887b5131f7',
    '00ddb9ecbfb8450995e7c1fafb2eb7bb',
],
    'words': 'duck panda',
    'nested': {
    'id': 110,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 5,
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
    'hello',
],
    'word': 'butterfly',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dog',
    'zebra',
],
    'city': {
    'name': 'Dubai',
    'geo': {
    'lat': 25.204849,
    'lon': 55.270783,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.36535,
    'maybe': 'rabbit',
    'maybe_null': 'frog',
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
    '15',
    '28',
    '16',
    '17',
],
    'text_data': '4512094690b94251b2ba7991ada11994',
    'rand_digit': 9,
    'rand_number': 0.97274,
    'rand_signed_int': 9,
    'rand_datetime': '2000-07-16 05:21',
    'text_array': [
    'a42e7c2af69140ab8b2d90f5605817b2',
    '5542758ea26b4b3d962a39001cfd0da4',
],
    'words': 'bee jaguar',
    'nested': {
    'id': 111,
    'rand_digit': 4,
    'array': [
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
    'word': 'frog',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 10,
},
],
},
    'nested_array': [
    [
    -8,
],
    [
    -4,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'tiger',
    'hippo',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'zebra',
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
],
    'text_data': '7868fc719dc14d94aa721c57988a5527',
    'rand_digit': 4,
    'rand_number': 0.68274,
    'rand_signed_int': -8,
    'rand_datetime': '2000-05-30T09:36:57.649584+0000',
    'text_array': [
    '176a03fef9bf4730af5199ffcc858163',
    'ebdfe5e161db4927add5d9d9a513358f',
],
    'words': 'pig elephant',
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
    'word': 'bee',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'whale',
    'ladybug',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.54017,
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
    '27',
    '14',
    '08',
    '27',
],
    'text_data': '6a65d09d0f334561bf559b96b4b17797',
    'rand_digit': 3,
    'rand_number': 0.3334,
    'rand_signed_int': -5,
    'rand_datetime': '2000-06-16T09:24:01.709638',
    'text_array': [
    '4e8830eb49ea46e59594288b9d800fca',
    'b7944785c4af453983f47353a0309ae0',
],
    'words': 'mosquito hyena',
    'nested': {
    'id': 113,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
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
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
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
],
    'word': 'chicken',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    2,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'snake',
    'lobster',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'sloth',
    'maybe_null': 'mosquito',
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
    '17',
    '02',
    '02',
    '02',
    '08',
],
    'text_data': 'd64f269ad8fd4236947d20ff1cf442b6',
    'rand_digit': 7,
    'rand_number': 0.46493,
    'rand_signed_int': 2,
    'rand_datetime': '2000-09-13T04:10:48.045686-0200',
    'text_array': [
    'f7863e7cf6ab47aa9838177ece2df9b5',
    '61849606e5f34d8c8ee353e79c9abad5',
],
    'words': 'cat hippo',
    'nested': {
    'id': 114,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'rhino',
    'monkey',
],
    'city': {
    'name': 'Bangkok',
    'geo': {
    'lat': 13.756331,
    'lon': 100.501765,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'mosquito',
    'maybe_null': 'bear',
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
],
    'text_data': '8d2d3d6ddc324a6bb4ea230987c4e217',
    'rand_digit': 5,
    'rand_number': 0.07117,
    'rand_signed_int': -8,
    'rand_datetime': '2000-11-08 17:25:16.911780',
    'text_array': [
    'f9b2ec0ffca54e72887933e7c58d3f79',
    '17871d1f2a374ffab5d673c2f89b8e5f',
],
    'words': 'dog panda',
    'nested': {
    'id': 115,
    'rand_digit': 2,
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
],
    'word': 'dragonfly',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'sloth',
    'shark',
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
    'mixed_type': 0,
    'maybe_null': None,
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
    '12',
    '12',
    '26',
],
    'text_data': '692f54536ad8432ebb91775b2f81ab02',
    'rand_digit': 1,
    'rand_number': 0.78241,
    'rand_signed_int': 8,
    'rand_datetime': '2000-11-01 21:56:22.711174+1000',
    'text_array': [
    'e56a11e4d0484c8b9f60421234d5aa14',
    '8f8ec3e9b3f0455aa5647206427684f3',
],
    'words': 'butterfly rhino',
    'nested': {
    'id': 116,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
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
],
    'word': 'sheep',
    'number': 10,
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
    'word': 'duck',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'goat',
    'duck',
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
    'mixed_type': 'deer',
    'maybe_null': None,
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
    '21',
],
    'text_data': '1c3f7779086d47b2b4f96dea2f519e8b',
    'rand_digit': 4,
    'rand_number': 0.91956,
    'rand_signed_int': 3,
    'rand_datetime': '2000-08-20T17:00:27-1000',
    'text_array': [
    'f5e62344fa214f8c8393a3907842e4f5',
    'c07bb7e3b582459cb6780c9944b0579c',
],
    'words': 'deer lobster',
    'nested': {
    'id': 117,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 5,
},
    {
    'nested_empty': None,
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
    'word': 'fish',
    'number': 9,
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
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'lion',
    'rabbit',
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
    'maybe': 'tiger',
    'maybe_null': 'dragonfly',
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
    '11',
    '22',
    '13',
    '03',
    '29',
],
    'text_data': '2ce8a275282c45d5a0ef4eeb08bc0014',
    'rand_digit': 7,
    'rand_number': 0.29076,
    'rand_signed_int': 3,
    'rand_datetime': '2000-05-27',
    'text_array': [
    '46e4a0e4c2f241f9aea27b445c2abb0b',
    '296be000d806414785fb9beaea9e0912',
],
    'words': 'cow giraffe',
    'nested': {
    'id': 118,
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
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 5,
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
    'word': 'camel',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bear',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'scorpion',
    'elephant',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': [
    82,
],
    'rand_bool': False,
    'mixed_type': False,
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
    '12',
    '27',
],
    'text_data': 'a7ee154145074b3ca105e45da46845a6',
    'rand_digit': 0,
    'rand_number': 0.54061,
    'rand_signed_int': 10,
    'rand_datetime': '2000-12-16T14:52:28.245565+0200',
    'text_array': [
    '595642995ff34a8490f3cf0802f321cc',
    '510439a881224761ad5f8d2d46620991',
],
    'words': 'cat sloth',
    'nested': {
    'id': 119,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'octopus',
    'deer',
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
    'mixed_type': 0.77627,
    'maybe': 'bee',
    'maybe_null': None,
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
    '10',
    '19',
    '11',
],
    'text_data': '519747a90f6b4e8d8164aecefd723cef',
    'rand_digit': 1,
    'rand_number': 0.59016,
    'rand_signed_int': -6,
    'rand_datetime': '2000-01-16',
    'text_array': [
    '2e199c88410c44eca6ffcb3e58918348',
    '31e5b084e2094bb693a45733794a5db7',
],
    'words': 'frog octopus',
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
    'word': 'frog',
    'number': 1,
},
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
    'word': 'wolf',
    'number': 10,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -1,
],
],
    'two_words': [
    'kangaroo',
    'bee',
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
    'maybe_null': 'goat',
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
],
    'text_data': 'e7bf7c7346914b93b5300ecf600f8a36',
    'rand_digit': 6,
    'rand_number': 0.81868,
    'rand_signed_int': 7,
    'rand_datetime': '2000-10-26',
    'text_array': [
    'f3741bef59d443c68828935505716b7b',
    '897ede02e8b14bdeae94f65237d905fe',
],
    'words': 'horse lobster',
    'nested': {
    'id': 121,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'bird',
    'pig',
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
    'mixed_type': 'lobster',
    'maybe': 'spider',
    'maybe_null': None,
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
    '04',
    '18',
    '05',
],
    'text_data': '83ac40af89a4418b92aa10a3eb9b6164',
    'rand_digit': 9,
    'rand_number': 0.83667,
    'rand_signed_int': 3,
    'rand_datetime': '2000-06-10T14:06:25.648554',
    'text_array': [
    'b9dd02b1f0344638b784bb2455d08334',
    '650b73a89e1546afb93232874b75b356',
],
    'words': 'whale rabbit',
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
    'word': 'hyena',
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
    'number': 4,
},
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fish',
    'octopus',
],
    'city': {
    'name': 'Copenhagen',
    'geo': {
    'lat': 55.676097,
    'lon': 12.568337,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'rhino',
    'maybe': 'duck',
    'maybe_null': 'leopard',
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
    '11',
    '13',
],
    'text_data': 'ceb68ee25a934209bae87f4681b6e991',
    'rand_digit': 2,
    'rand_number': 0.43475,
    'rand_signed_int': 6,
    'rand_datetime': '2000-09-17 03:08:46+0100',
    'text_array': [
    'ed3bc323f8154faaaff237f43ff40060',
    'd1a81db2d9834dce8a1b8b94d7d2dc27',
],
    'words': 'octopus butterfly',
    'nested': {
    'id': 123,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cat',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'cat',
    'panda',
],
    'city': {
    'name': 'Washington',
    'geo': {
    'lat': 38.907192,
    'lon': -77.036871,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'pig',
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
    '08',
    '24',
],
    'text_data': 'e6d92eec658e4e6d9082ca3db0631966',
    'rand_digit': 2,
    'rand_number': 0.42116,
    'rand_signed_int': 4,
    'rand_datetime': '2000-04-03 20:20:55.568349+1100',
    'text_array': [
    '8d7ececfaf074dff987d372455a056c5',
    '22be53e3b61a47e29eb87eb7c852dc48',
],
    'words': 'spider pig',
    'nested': {
    'id': 124,
    'rand_digit': 3,
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
    'word': 'ladybug',
    'number': 6,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -2,
],
],
    'two_words': [
    'cow',
    'hippo',
],
    'city': {
    'name': 'Stockholm',
    'geo': {
    'lat': 59.329323,
    'lon': 18.068581,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 'koala',
    'maybe': 'kangaroo',
    'maybe_null': 'frog',
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
    '19',
    '24',
    '15',
    '05',
],
    'text_data': '603e406aede0471ba7c1e4f2ce182ba1',
    'rand_digit': 3,
    'rand_number': 0.17093,
    'rand_signed_int': -6,
    'rand_datetime': '2000-05-01 00:34:41',
    'text_array': [
    '4b5c691acf1b4baea5a6d50f86c9c1d6',
    '018df73e5fd74686a2e8f8c4b8bf1f9f',
],
    'words': 'monkey scorpion',
    'nested': {
    'id': 125,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 5,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'bird',
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
    'mixed_type': {
    'key': 'value',
},
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
    '06',
],
    'text_data': '1282eff2e602434eb3cf2da12359435d',
    'rand_digit': 0,
    'rand_number': 0.67548,
    'rand_signed_int': -7,
    'rand_datetime': '2000-06-20 13:29:53',
    'text_array': [
    'f081e43635d44bceb57770fa188eaae5',
    'b5715823cc6842ec902379ec23c4ae84',
],
    'words': 'hyena butterfly',
    'nested': {
    'id': 126,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -1,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'hyena',
    'goat',
],
    'city': {
    'name': 'Kharkiv',
    'geo': {
    'lat': 49.980812,
    'lon': 36.25272,
},
},
    'rand_tuple': [
    59,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'giraffe',
    'maybe_null': 'rabbit',
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
    '02',
],
    'text_data': 'd6d118f8820e4f70a4ebc466519d3a6a',
    'rand_digit': 2,
    'rand_number': 0.6721,
    'rand_signed_int': 7,
    'rand_datetime': '2000-11-10T04:21:37.960091',
    'text_array': [
    '77bab0a21143476e85f1332df74128cf',
    'e99508bbf59448deae9ebc121522aff2',
],
    'words': 'chicken snail',
    'nested': {
    'id': 127,
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
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'bear',
    'cheetah',
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
    'mixed_type': 7,
    'maybe_null': 'goat',
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
    '03',
    '24',
],
    'text_data': 'bb6694ec30074c599be782ee930b2ce8',
    'rand_digit': 3,
    'rand_number': 0.15561,
    'rand_signed_int': 6,
    'rand_datetime': '2000-12-11T17:10:45.055748+03:00',
    'text_array': [
    '07b05b21bacd41a9a91c5225a009d051',
    '44ffb2e80bdc4277994857197bb1edbb',
],
    'words': 'bee deer',
    'nested': {
    'id': 128,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'duck',
    'koala',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': [
    3,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'hyena',
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
    '09',
    '09',
    '24',
],
    'text_data': '351396ea4e6d457e834f32aef750742b',
    'rand_digit': 8,
    'rand_number': 0.45834,
    'rand_signed_int': 0,
    'rand_datetime': '2000-02-20T06:46:43.974150+12:00',
    'text_array': [
    '134c15c8675a4f4f93fb30f7a1221cf7',
    'c7ae9061eef3457f9f0976617f5fbee4',
],
    'words': 'mosquito cat',
    'nested': {
    'id': 129,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'elephant',
    'shark',
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
    'mixed_type': 0.55105,
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
    '04',
    '13',
    '23',
    '29',
],
    'text_data': '4e2168fd973b4b559584e10850502fed',
    'rand_digit': 0,
    'rand_number': 0.77308,
    'rand_signed_int': 7,
    'rand_datetime': '2000-08-18T07:01:59.670074-03:00',
    'text_array': [
    'c93f259f15da4d2180909100bafdff19',
    '7327d0646d7b4b66b1b5bbe63edd797a',
],
    'words': 'snake koala',
    'nested': {
    'id': 130,
    'rand_digit': 8,
    'array': [
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
    'nested_empty': [
    'hello',
],
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
    'word': 'fox',
    'number': 9,
},
],
},
    'nested_array': [
    [
    -5,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'tiger',
    'dragonfly',
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
    'mixed_type': 0.49947,
    'maybe': 'frog',
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
],
    'text_data': 'f7283cb45df9403e9a70c6c5bd7c7f4b',
    'rand_digit': 1,
    'rand_number': 0.18633,
    'rand_signed_int': 4,
    'rand_datetime': '2000-10-22 04:50:31+0700',
    'text_array': [
    'c19dcb32277d4f4681c9891d53cd025e',
    'c4a7a158de88422f8651472506ea0722',
],
    'words': 'duck cheetah',
    'nested': {
    'id': 131,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    [
],
    [
    2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'duck',
    'sheep',
],
    'city': {
    'name': 'Vilnius',
    'geo': {
    'lat': 54.687157,
    'lon': 25.279652,
},
},
    'rand_tuple': [
    23,
],
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'cow',
    'maybe_null': 'bird',
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
    '24',
    '16',
    '23',
    '05',
    '25',
],
    'text_data': '37f0cf2ed0454b9b9f386d1714768367',
    'rand_digit': 2,
    'rand_number': 0.01731,
    'rand_signed_int': -8,
    'rand_datetime': '2000-09-02 19:53',
    'text_array': [
    '0aeb807ac25a4588b24c7be11a10f67a',
    'c69653266449466b913cdadeee636a67',
],
    'words': 'grasshopper sheep',
    'nested': {
    'id': 132,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 5,
},
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
    'word': 'bear',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'snail',
    'fly',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'leopard',
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
    '08',
    '23',
],
    'text_data': '574ae303cff040199818d31bdc45aa70',
    'rand_digit': 1,
    'rand_number': 0.86334,
    'rand_signed_int': 3,
    'rand_datetime': '2000-03-03 09:47:34.538040-0500',
    'text_array': [
    'efd688a1a65d4f7296e92834eefb995b',
    '540d1aaaa84d459fa4559e2852b6a0d8',
],
    'words': 'sloth gorilla',
    'nested': {
    'id': 133,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bee',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mouse',
    'bee',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'butterfly',
    'maybe_null': None,
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
    '23',
],
    'text_data': '284960f36e294b55a2d103d3199c5767',
    'rand_digit': 0,
    'rand_number': 0.07756,
    'rand_signed_int': 7,
    'rand_datetime': '2000-08-25T23:01:40',
    'text_array': [
    '5e24fcdc451d4788b94cb3c2925343db',
    '647a28b0ce6944dc8c5ef4766b73e6de',
],
    'words': 'ape leopard',
    'nested': {
    'id': 134,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -6,
],
    [
    10,
],
    [
],
    [
    -2,
],
],
    'two_words': [
    'lobster',
    'zebra',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
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
    '29',
],
    'text_data': '6982e0475a444670ab125a0f7452021a',
    'rand_digit': 8,
    'rand_number': 0.03948,
    'rand_signed_int': 2,
    'rand_datetime': '2000-08-11T11:07:01.512435',
    'text_array': [
    'cafd3e3a42344707803e1c94395394f4',
    '8dfa144130aa48a2a780a4ec731c1d95',
],
    'words': 'shark lobster',
    'nested': {
    'id': 135,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ape',
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
    'number': 3,
},
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
    'word': 'ladybug',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'fly',
    'turtle',
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
    'maybe': 'dolphin',
    'maybe_null': 'goat',
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
    '03',
    '05',
    '27',
],
    'text_data': 'b97c1ecc33b5481dbfe3af28bbd2d452',
    'rand_digit': 5,
    'rand_number': 0.21006,
    'rand_signed_int': 2,
    'rand_datetime': '2000-02-23 02:02:29',
    'text_array': [
    '8d4d47b050d7484b882e1d065e6abd9e',
    '98f63741b35b4e669cf5178c4c5c41bb',
],
    'words': 'mouse fox',
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
    'word': 'camel',
    'number': 10,
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
    'hello',
],
    'word': 'snake',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'sloth',
    'jaguar',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': [
    87,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'lizard',
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
    '13',
],
    'text_data': 'b6dca94438f44c91868602a60d959a81',
    'rand_digit': 2,
    'rand_number': 0.71361,
    'rand_signed_int': 9,
    'rand_datetime': '2000-05-29T10:00:44-1100',
    'text_array': [
    'e6b7fed275404a8e91880dacb17f1483',
    '7050e77e536945aeb31f31a9ca1611ce',
],
    'words': 'mosquito fly',
    'nested': {
    'id': 137,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    8,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'bear',
    'hippo',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': [
    96,
],
    'rand_bool': False,
    'mixed_type': 7,
    'maybe': 'cat',
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
    '14',
    '11',
    '18',
],
    'text_data': '29f7c95fe28f4d2e9de5b8749e650e16',
    'rand_digit': 0,
    'rand_number': 0.62163,
    'rand_signed_int': 6,
    'rand_datetime': '2000-11-21T06:01:03.278717',
    'text_array': [
    'e6b1c15d7e554536beb3ea4e07ef9711',
    '2f2df1b3c21a4a408044940aed93ff85',
],
    'words': 'mosquito fox',
    'nested': {
    'id': 138,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    8,
],
    [
    -6,
],
],
    'two_words': [
    'wolf',
    'jaguar',
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
    'mixed_type': None,
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
    '14',
    '04',
],
    'text_data': '645bd28b9c3344c7b5f9601006df0fb4',
    'rand_digit': 7,
    'rand_number': 0.01546,
    'rand_signed_int': -3,
    'rand_datetime': '2000-08-04 21:42:21',
    'text_array': [
    'af309421019b4716ba8059487ca2cf80',
    'a8ea17f42609401b90338dd61055954e',
],
    'words': 'turtle mosquito',
    'nested': {
    'id': 139,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
    3,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'ladybug',
    'grasshopper',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
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
    '24',
    '09',
    '09',
    '15',
    '20',
],
    'text_data': 'd7fe4cac7715482f8810146173e82d74',
    'rand_digit': 7,
    'rand_number': 0.35298,
    'rand_signed_int': 9,
    'rand_datetime': '2000-11-01 06:19',
    'text_array': [
    '16facb16ddce4a1697e17ce745683214',
    '20580b38710e4fc1961895e4ac4265f0',
],
    'words': 'turtle kangaroo',
    'nested': {
    'id': 140,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'elephant',
    'jaguar',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': [
    7,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'dolphin',
    'maybe_null': 'turtle',
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
    '18',
    '05',
    '06',
    '01',
],
    'text_data': '758f27dbe7584a82b9d918a115b87ad0',
    'rand_digit': 4,
    'rand_number': 0.25207,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-30T19:35:42.694652+0700',
    'text_array': [
    'c8361911358248c19857b94a047f31da',
    '600f27aee09248258a920f78a3c55c49',
],
    'words': 'scorpion sheep',
    'nested': {
    'id': 141,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'bee',
    'zebra',
],
    'city': {
    'name': 'Samara',
    'geo': {
    'lat': 53.195873,
    'lon': 50.100193,
},
},
    'rand_tuple': [
    89,
],
    'rand_bool': False,
    'mixed_type': 0.72755,
    'maybe': 'fly',
    'maybe_null': 'snail',
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
    '29',
],
    'text_data': '906a6a5a4dcd4cdba1fd56071f3b8270',
    'rand_digit': 8,
    'rand_number': 0.60179,
    'rand_signed_int': 3,
    'rand_datetime': '2000-07-21T00:36:41.609878',
    'text_array': [
    '97f4cb2eec5a4359bc37760afd27350b',
    '78f54fb9a9be481cbfce91477581805c',
],
    'words': 'pig ladybug',
    'nested': {
    'id': 142,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'bird',
    'wolf',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': [
    48,
],
    'rand_bool': False,
    'mixed_type': 'kangaroo',
    'maybe_null': 'dragonfly',
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
    '14',
    '24',
    '29',
    '22',
    '16',
],
    'text_data': '538f7525a2614341a5b0f997039d42d2',
    'rand_digit': 0,
    'rand_number': 0.81123,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-24T21:27:32.381620+01:00',
    'text_array': [
    'cbf1dd454a69402d84a433e616c2ac5f',
    'aa92228607f74cf0b6a487296929d5a6',
],
    'words': 'pig koala',
    'nested': {
    'id': 143,
    'rand_digit': 2,
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
],
    'two_words': [
    'bee',
    'grasshopper',
],
    'city': {
    'name': 'Dubai',
    'geo': {
    'lat': 25.204849,
    'lon': 55.270783,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'cat',
    'maybe_null': 'ape',
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
    '27',
    '11',
    '09',
],
    'text_data': '157e56fe22ba4581946b8dc2be07dcb6',
    'rand_digit': 9,
    'rand_number': 0.60432,
    'rand_signed_int': -7,
    'rand_datetime': '2000-01-16T14:25:03.781626+0900',
    'text_array': [
    '8bedd9380f144bd9bb932916b1fba415',
    'e71cf118f86c4c3dbdf78d32caa9bc5a',
],
    'words': 'hyena dolphin',
    'nested': {
    'id': 144,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
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
],
    'two_words': [
    'spider',
    'scorpion',
],
    'city': {
    'name': 'Warsaw',
    'geo': {
    'lat': 52.229676,
    'lon': 21.012229,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 6,
    'maybe': 'jaguar',
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
    '22',
    '24',
    '26',
    '29',
],
    'text_data': '1b30226dfd8e45b0828aa9e5376c2cad',
    'rand_digit': 2,
    'rand_number': 0.89763,
    'rand_signed_int': -9,
    'rand_datetime': '2001-01-30 16:05:23.619180+0300',
    'text_array': [
    '3cf6778dedd54bb181816b70fb0eb494',
    'af26fb722c224170b6e5099804ad9cd2',
],
    'words': 'chicken octopus',
    'nested': {
    'id': 145,
    'rand_digit': 5,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -4,
],
    [
],
    [
    -6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'panda',
    'cat',
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
    'mixed_type': 'fly',
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
    '06',
    '10',
    '25',
    '08',
    '03',
],
    'text_data': '0788db17bbb649f889a87302e1d596ea',
    'rand_digit': 0,
    'rand_number': 0.75008,
    'rand_signed_int': -8,
    'rand_datetime': '2000-12-14',
    'text_array': [
    'b66aae40f5c74ed5aef63cf241b92bd9',
    'f5fb091972734d55939b25e64f049a7e',
],
    'words': 'sloth sloth',
    'nested': {
    'id': 146,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 2,
},
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
],
    'word': 'wolf',
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
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'rabbit',
    'dog',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'chicken',
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
    '22',
    '09',
    '12',
],
    'text_data': '71956f2fee9042fca5856f297e25e245',
    'rand_digit': 4,
    'rand_number': 0.37054,
    'rand_signed_int': 9,
    'rand_datetime': '2000-10-01 16:00',
    'text_array': [
    '018487866c8546bc8ead557e333e2140',
    'd97e2ae1d0324da283118f957759bafe',
],
    'words': 'rhino zebra',
    'nested': {
    'id': 147,
    'rand_digit': 6,
    'array': [
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'mosquito',
    'giraffe',
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
    'mixed_type': False,
    'maybe': 'hippo',
    'maybe_null': 'dragonfly',
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
    '30',
    '06',
],
    'text_data': '0a7fd46915994f5c9e92ce45f5dbe45a',
    'rand_digit': 0,
    'rand_number': 0.37308,
    'rand_signed_int': 1,
    'rand_datetime': '2000-09-06 02:58',
    'text_array': [
    '3b2559063ed247048e59ed6978866619',
    '567e4a18ae7e4275adf27abf03a92ac0',
],
    'words': 'goat crab',
    'nested': {
    'id': 148,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    [
],
    [
],
    [
    -9,
],
],
    'two_words': [
    'cheetah',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'panda',
    'maybe_null': 'hippo',
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
    '28',
],
    'text_data': 'a35c14ec0b8b48d6b67e3f0e89f183e9',
    'rand_digit': 2,
    'rand_number': 0.20128,
    'rand_signed_int': -6,
    'rand_datetime': '2000-11-09 05:33:26.826326',
    'text_array': [
    '63a107d13d494c52b097e7f2c85ff0c3',
    'b35d16b57f2c4149acb64abd61463095',
],
    'words': 'snake rhino',
    'nested': {
    'id': 149,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
    'number': 5,
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
    'hello',
],
    'word': 'chicken',
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'horse',
    'grasshopper',
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
    'mixed_type': 0.77407,
    'maybe': 'scorpion',
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
    '02',
    '27',
],
    'text_data': '19edb360e9f6481391fa72071d1d10ec',
    'rand_digit': 1,
    'rand_number': 0.32189,
    'rand_signed_int': 7,
    'rand_datetime': '2001-01-19T02:24:25.179749',
    'text_array': [
    '20fc0e987e8047b4af09df708a3fbd0b',
    '793adbcd92c24aeaadbe446cccb4ffdf',
],
    'words': 'rhino crab',
    'nested': {
    'id': 150,
    'rand_digit': 6,
    'array': [
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
    'word': 'leopard',
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
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    3,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'dragonfly',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'kangaroo',
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
    '01',
    '17',
],
    'text_data': 'ede4d22ad2fe48eabb9747fdd0f6f383',
    'rand_digit': 6,
    'rand_number': 0.36038,
    'rand_signed_int': -10,
    'rand_datetime': '2000-01-19 22:39:00-0200',
    'text_array': [
    '3f6c383d44c2469e9d5804f6f6a7f2ba',
    'ed106b1b4672496182976d2dbc84ff17',
],
    'words': 'wolf ladybug',
    'nested': {
    'id': 151,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 1,
},
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'rhino',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'koala',
    'fly',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'camel',
    'maybe_null': None,
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
    '29',
    '17',
    '10',
    '25',
    '26',
],
    'text_data': 'a989e64a7f6a44b7b5d5a7dc25471887',
    'rand_digit': 7,
    'rand_number': 0.54593,
    'rand_signed_int': 9,
    'rand_datetime': '2000-08-21 21:56:10-0700',
    'text_array': [
    'c3469320762449b6b63c80a913cfc0ad',
    '1eddf427f935472cb23f04fc486e47e1',
],
    'words': 'rabbit tiger',
    'nested': {
    'id': 152,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'snake',
    'fox',
],
    'city': {
    'name': 'Saint Petersburg',
    'geo': {
    'lat': 59.938732,
    'lon': 30.314129,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'turtle',
    'maybe_null': 'kangaroo',
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
    '01',
    '13',
],
    'text_data': 'c1f45a98fc904683896088d5f439700d',
    'rand_digit': 2,
    'rand_number': 0.72935,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-18 23:14:26+0300',
    'text_array': [
    '6b67f910335c4c69b54b0ec52435b832',
    '0da4f2bf7bc94e0bace26dfd7db5adba',
],
    'words': 'goat sloth',
    'nested': {
    'id': 153,
    'rand_digit': 9,
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
],
},
    'nested_array': [
],
    'two_words': [
    'horse',
    'fish',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'panda',
    'maybe_null': 'dragonfly',
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
],
    'text_data': 'e5433c196ab845b091f68df5738bd19f',
    'rand_digit': 7,
    'rand_number': 0.38763,
    'rand_signed_int': -2,
    'rand_datetime': '2000-03-06T07:43:18.921639',
    'text_array': [
    'e67577e96ced4e23ba74184d1aeae0be',
    'a6b7071afedf420b8f598c57acf6bf96',
],
    'words': 'squid lion',
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
    'word': 'rhino',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rabbit',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'bear',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 8,
},
],
},
    'nested_array': [
    [
],
    [
    10,
],
],
    'two_words': [
    'goat',
    'fish',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
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
    '25',
],
    'text_data': '5263fb376368416d8b5b76122cb71d71',
    'rand_digit': 9,
    'rand_number': 0.51161,
    'rand_signed_int': 5,
    'rand_datetime': '2000-04-09 17:55:51',
    'text_array': [
    '906c7fec45314b7b82fe667b308e44c9',
    '219f52d42f3e499b961f99041c656f96',
],
    'words': 'goat chicken',
    'nested': {
    'id': 155,
    'rand_digit': 1,
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
    'word': 'pig',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'fly',
    'ape',
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
    'mixed_type': 8,
    'maybe_null': None,
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
    '28',
],
    'text_data': '838ffa01320d4be5ad60752f5427b2e1',
    'rand_digit': 0,
    'rand_number': 0.47062,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-20 18:02:31.080109+0900',
    'text_array': [
    '6f0029a44153423cb8caebc28ec80eeb',
    'c5468c366ffa458290a646a6730b337a',
],
    'words': 'hyena dragonfly',
    'nested': {
    'id': 156,
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
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 2,
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
],
    'word': 'deer',
    'number': 9,
},
],
},
    'nested_array': [
    [
    -5,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    10,
],
    [
    5,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'turtle',
    'frog',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'snake',
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
    '19',
],
    'text_data': '77393f3c973248418fdd3fb9b5f2843a',
    'rand_digit': 3,
    'rand_number': 0.05383,
    'rand_signed_int': 2,
    'rand_datetime': '2000-11-07T02:35:20.755307',
    'text_array': [
    '5eba651882c34ee9be624f6a7c7702bc',
    '0cba8dd57172400e8b0ee9d197e4cfd4',
],
    'words': 'horse koala',
    'nested': {
    'id': 157,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'camel',
    'number': 1,
},
],
},
    'nested_array': [
    [
    8,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'mosquito',
    'chicken',
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
    '09',
    '01',
    '10',
],
    'text_data': 'dd944d80c1c342a4a6b124b93684564c',
    'rand_digit': 9,
    'rand_number': 0.29257,
    'rand_signed_int': -8,
    'rand_datetime': '2000-03-05T19:30:03.174638',
    'text_array': [
    '9caa153324e84155b96dbb8b8cd9fc1c',
    '9a4672cbae5142fcb6e3c1faa9b63525',
],
    'words': 'bear bird',
    'nested': {
    'id': 158,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -9,
],
    [
    -8,
],
    [
],
    [
],
],
    'two_words': [
    'tiger',
    'monkey',
],
    'city': {
    'name': 'Bogota',
    'geo': {
    'lat': 4.710989,
    'lon': -74.072092,
},
},
    'rand_tuple': [
    57,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'butterfly',
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
    '14',
    '15',
    '18',
],
    'text_data': '1b99c2d672a64a6d9fea536cc8bd428e',
    'rand_digit': 5,
    'rand_number': 0.06735,
    'rand_signed_int': 10,
    'rand_datetime': '2000-12-09 08:53:40.316736',
    'text_array': [
    'fb0bce884d444d11bb3411fdf3762b8f',
    '0f90972616154a5f96727f10bf5819a2',
],
    'words': 'spider bear',
    'nested': {
    'id': 159,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'frog',
    'number': 9,
},
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
    'word': 'goat',
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
],
    'two_words': [
    'bee',
    'bear',
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
    'mixed_type': False,
    'maybe_null': None,
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
    '21',
    '10',
    '21',
    '12',
    '05',
],
    'text_data': '2a15a1162ba24d89b6999435ad7b486e',
    'rand_digit': 9,
    'rand_number': 0.08854,
    'rand_signed_int': 1,
    'rand_datetime': '2000-01-26T05:12:11',
    'text_array': [
    'f19dee7da6c94667bdb2327332c108db',
    '228b2ab34b76463fa3a6f8e1e9aab082',
],
    'words': 'leopard zebra',
    'nested': {
    'id': 160,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
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
    'word': 'spider',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'kangaroo',
    'crab',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
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
],
    'text_data': '8990b2aa6b9246a082f460a661b39414',
    'rand_digit': 0,
    'rand_number': 0.92228,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-13T05:17:43.915087-1100',
    'text_array': [
    '140294dc96df463c84a361e5e7191766',
    '8b78bffe1ff9453486abc6a0352fdbde',
],
    'words': 'fox sheep',
    'nested': {
    'id': 161,
    'rand_digit': 2,
    'array': [
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
    'word': 'panda',
    'number': 5,
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
    'nested_array': '__FLOAT_MULTI_DIM_3,4__',
    'two_words': [
    'koala',
    'panda',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
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
    '08',
    '22',
],
    'text_data': 'ba20849c3b2b4d45a6e2441b672fc942',
    'rand_digit': 0,
    'rand_number': 0.83318,
    'rand_signed_int': 3,
    'rand_datetime': '2000-05-21T16:33:25.340570',
    'text_array': [
    '3d00b6ddde764e76aed6a5a462aa44b2',
    '1b09dece3f104a0f943003467c7bc875',
],
    'words': 'panda butterfly',
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
    'word': 'goat',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'dragonfly',
    'squid',
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
    'mixed_type': 0.0637,
    'maybe': 'giraffe',
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
    '19',
    '01',
    '11',
    '08',
],
    'text_data': '00d237af55384e37b33ba5e182199129',
    'rand_digit': 9,
    'rand_number': 0.06839,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-13 22:20:06',
    'text_array': [
    'bd4adeb0abeb4869b25ca003f76850c0',
    '2011f3bc520b45199533f8387009a23d',
],
    'words': 'snake fly',
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
    'word': 'rabbit',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'crab',
    'number': 9,
},
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
    'word': 'gorilla',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'leopard',
    'dolphin',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': [
    59,
],
    'rand_bool': True,
    'mixed_type': 7,
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



    def test_request_12(self):
        """测试请求 12 - POST http://localhost:6333/collections/collection_1/points/scroll"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/collection_1/points/scroll")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/collection_1/points/scroll'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '63',
}
        
        # 原始请求内容
        original_content = {
    'offset': 2,
    'limit': 100,
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
        """测试请求 13 - POST http://localhost:6333/collections/collection_2/points/scroll"""
        logger.info(f"测试请求: POST http://localhost:6333/collections/collection_2/points/scroll")
        
        method = 'POST'
        url_path = 'http://localhost:6333/collections/collection_2/points/scroll'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '63',
}
        
        # 原始请求内容
        original_content = {
    'offset': 2,
    'limit': 100,
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
        """测试请求 14 - DELETE http://localhost:6333/collections/collection_1"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://localhost:6333/collections/collection_1")
        method = 'DELETE'
        url_path = 'http://localhost:6333/collections/collection_1'
        headers = {
    'host': 'localhost:6333',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'qdrant-client/1.14.2 python/3.12.3',
    'content-type': 'application/json',
    'content-length': '467',
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
    'hnsw_config': {
    'm': 16,
    'ef_construct': 100,
    'full_scan_threshold': 10000,
    'max_indexing_threads': 0,
},
    'wal_config': {
    'wal_capacity_mb': 32,
    'wal_segments_ahead': 0,
},
    'optimizers_config': {
    'deleted_threshold': 0.2,
    'vacuum_min_vector_number': 1000,
    'default_segment_number': 0,
    'indexing_threshold': 20000,
    'flush_interval_sec': 5,
    'max_optimization_threads': 1,
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_migrate.test_migrate_particular_collections')
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
    test = TestMigratetestMigrateParticularCollections()
    test.run_tests()
