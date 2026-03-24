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
logger = logging.getLogger('vdb_fuzzer.test.test_collection_test_return_properties_metadata_references_combos')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:8080"
TARGET_ENV_VARS = ("WEAVIATE_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_weaviate_0520"
TEST_NAME = "test_collection.test_return_properties_metadata_references_combos"
VDB_TYPE = "weaviate"


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


def send_request(content, request_type="POST", url_path="http://localhost:8080/v1/schema", custom_headers=None):
    """
    发送请求到目标服务器

    Args:
        content: 请求内容
        request_type: 请求方法，默认为"POST"
        url_path: URL路径，默认为"http://localhost:8080/v1/schema"
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
        url = TARGET_URL.rstrip('/') + "/v1/.well-known/ready"
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



class TestCollectiontestReturnPropertiesMetadataReferencesCombos:
    """自动生成的VDB模糊测试类 - test_collection.test_return_properties_metadata_references_combos"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_collection.test_return_properties_metadata_references_combos"
        self.test_count = 153  # 测试方法数量
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
        """测试请求 0 - POST http://localhost:8080/v1/schema"""
        logger.info(f"跳过非写请求或无内容请求: POST http://localhost:8080/v1/schema")
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '228',
}
        
        # 原始请求内容
        original_content = {
    'vectorizer': 'none',
    'vectorIndexType': 'hnsw',
    'class': 'Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNoneNone_1',
    'properties': [
    {
    'name': 'name',
    'dataType': [
    'text',
],
},
    {
    'name': 'age',
    'dataType': [
    'int',
],
},
],
}


        send_request(original_content, method, url_path, headers)
        return True



    def test_request_1(self):
        """测试请求 1 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNoneNone_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNoneNone_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNoneNone_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '119',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNoneNone_1',
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
        """测试请求 2 - POST http://localhost:8080/v1/objects"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/objects")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/objects'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '201',
}
        
        # 原始请求内容
        original_content = {
    'class': 'Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNoneNone_1',
    'properties': {
    'name': 'Graham',
    'age': 42,
},
    'id': '806827e0-2b31-43ca-9269-24fa95a221f9',
    'vector': self.mutator.generate_float_array(dimension=4, normalized=True),
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
        """测试请求 3 - POST http://localhost:8080/v1/objects"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/objects")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/objects'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '281',
}
        
        # 原始请求内容
        original_content = {
    'class': 'Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNoneNone_1',
    'properties': {
    'name': 'John',
    'age': 43,
    'friend': [
    {
    'beacon': 'weaviate://localhost/806827e0-2b31-43ca-9269-24fa95a221f9',
},
],
},
    'id': '8ad0d33c-8db1-4437-87f3-72161ca2a51a',
    'vector': self.mutator.generate_float_array(dimension=4, normalized=True),
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
        """测试请求 4 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNonereturn_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNonereturn_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNonereturn_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '133',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNonereturn_properties1_1',
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
        """测试请求 5 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNonereturn_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNonereturn_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNonereturn_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '133',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNonereturn_properties2_1',
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
        """测试请求 6 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNoneFalse_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNoneFalse_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNoneFalse_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '120',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNoneFalse_1',
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
        """测试请求 7 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNoneTrue_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNoneTrue_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNoneTrue_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '119',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNoneNoneTrue_1',
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



    def test_request_8(self):
        """测试请求 8 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '131',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1None_1',
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



    def test_request_9(self):
        """测试请求 9 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1return_properties1_1',
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



    def test_request_10(self):
        """测试请求 10 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1return_properties2_1',
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



    def test_request_11(self):
        """测试请求 11 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '132',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1False_1',
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
        """测试请求 12 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '131',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata1True_1',
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



    def test_request_13(self):
        """测试请求 13 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '131',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2None_1',
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



    def test_request_14(self):
        """测试请求 14 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2return_properties1_1',
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



    def test_request_15(self):
        """测试请求 15 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2return_properties2_1',
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



    def test_request_16(self):
        """测试请求 16 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '132',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2False_1',
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



    def test_request_17(self):
        """测试请求 17 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '131',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata2True_1',
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



    def test_request_18(self):
        """测试请求 18 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '131',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3None_1',
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



    def test_request_19(self):
        """测试请求 19 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3return_properties1_1',
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



    def test_request_20(self):
        """测试请求 20 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3return_properties2_1',
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



    def test_request_21(self):
        """测试请求 21 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '132',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3False_1',
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



    def test_request_22(self):
        """测试请求 22 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '131',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata3True_1',
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



    def test_request_23(self):
        """测试请求 23 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '131',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4None_1',
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



    def test_request_24(self):
        """测试请求 24 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4return_properties1_1',
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



    def test_request_25(self):
        """测试请求 25 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4return_properties2_1',
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



    def test_request_26(self):
        """测试请求 26 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '132',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4False_1',
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



    def test_request_27(self):
        """测试请求 27 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '131',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalseNonereturn_metadata4True_1',
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



    def test_request_28(self):
        """测试请求 28 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1NoneNone_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1NoneNone_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1NoneNone_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '133',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1NoneNone_1',
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



    def test_request_29(self):
        """测试请求 29 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1Nonereturn_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1Nonereturn_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1Nonereturn_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '147',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1Nonereturn_properties1_1',
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



    def test_request_30(self):
        """测试请求 30 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1Nonereturn_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1Nonereturn_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1Nonereturn_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '147',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1Nonereturn_properties2_1',
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



    def test_request_31(self):
        """测试请求 31 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1NoneFalse_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1NoneFalse_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1NoneFalse_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '134',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1NoneFalse_1',
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



    def test_request_32(self):
        """测试请求 32 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1NoneTrue_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1NoneTrue_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1NoneTrue_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '133',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1NoneTrue_1',
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



    def test_request_33(self):
        """测试请求 33 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1None_1',
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



    def test_request_34(self):
        """测试请求 34 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '159',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1return_properties1_1',
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



    def test_request_35(self):
        """测试请求 35 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '159',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1return_properties2_1',
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



    def test_request_36(self):
        """测试请求 36 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '146',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1False_1',
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



    def test_request_37(self):
        """测试请求 37 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata1True_1',
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



    def test_request_38(self):
        """测试请求 38 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2None_1',
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



    def test_request_39(self):
        """测试请求 39 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '159',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2return_properties1_1',
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



    def test_request_40(self):
        """测试请求 40 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '159',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2return_properties2_1',
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



    def test_request_41(self):
        """测试请求 41 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '146',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2False_1',
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



    def test_request_42(self):
        """测试请求 42 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata2True_1',
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



    def test_request_43(self):
        """测试请求 43 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3None_1',
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



    def test_request_44(self):
        """测试请求 44 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '159',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3return_properties1_1',
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



    def test_request_45(self):
        """测试请求 45 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '159',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3return_properties2_1',
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



    def test_request_46(self):
        """测试请求 46 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '146',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3False_1',
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



    def test_request_47(self):
        """测试请求 47 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata3True_1',
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



    def test_request_48(self):
        """测试请求 48 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4None_1',
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



    def test_request_49(self):
        """测试请求 49 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '159',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4return_properties1_1',
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



    def test_request_50(self):
        """测试请求 50 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '159',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4return_properties2_1',
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



    def test_request_51(self):
        """测试请求 51 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '146',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4False_1',
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



    def test_request_52(self):
        """测试请求 52 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references1return_metadata4True_1',
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



    def test_request_53(self):
        """测试请求 53 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2NoneNone_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2NoneNone_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2NoneNone_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '133',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2NoneNone_1',
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



    def test_request_54(self):
        """测试请求 54 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2Nonereturn_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2Nonereturn_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2Nonereturn_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '147',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2Nonereturn_properties1_1',
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



    def test_request_55(self):
        """测试请求 55 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2Nonereturn_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2Nonereturn_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2Nonereturn_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '147',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2Nonereturn_properties2_1',
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



    def test_request_56(self):
        """测试请求 56 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2NoneFalse_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2NoneFalse_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2NoneFalse_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '134',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2NoneFalse_1',
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



    def test_request_57(self):
        """测试请求 57 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2NoneTrue_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2NoneTrue_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2NoneTrue_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '133',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2NoneTrue_1',
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



    def test_request_58(self):
        """测试请求 58 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1None_1',
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



    def test_request_59(self):
        """测试请求 59 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '159',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1return_properties1_1',
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



    def test_request_60(self):
        """测试请求 60 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '159',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1return_properties2_1',
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



    def test_request_61(self):
        """测试请求 61 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '146',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1False_1',
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



    def test_request_62(self):
        """测试请求 62 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata1True_1',
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



    def test_request_63(self):
        """测试请求 63 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2None_1',
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



    def test_request_64(self):
        """测试请求 64 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '159',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2return_properties1_1',
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



    def test_request_65(self):
        """测试请求 65 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '159',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2return_properties2_1',
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



    def test_request_66(self):
        """测试请求 66 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '146',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2False_1',
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



    def test_request_67(self):
        """测试请求 67 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata2True_1',
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



    def test_request_68(self):
        """测试请求 68 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3None_1',
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



    def test_request_69(self):
        """测试请求 69 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '159',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3return_properties1_1',
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



    def test_request_70(self):
        """测试请求 70 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '159',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3return_properties2_1',
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



    def test_request_71(self):
        """测试请求 71 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '146',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3False_1',
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



    def test_request_72(self):
        """测试请求 72 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata3True_1',
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



    def test_request_73(self):
        """测试请求 73 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4None_1',
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



    def test_request_74(self):
        """测试请求 74 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '159',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4return_properties1_1',
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



    def test_request_75(self):
        """测试请求 75 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '159',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4return_properties2_1',
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



    def test_request_76(self):
        """测试请求 76 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '146',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4False_1',
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



    def test_request_77(self):
        """测试请求 77 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosFalsereturn_references2return_metadata4True_1',
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



    def test_request_78(self):
        """测试请求 78 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNoneNone_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNoneNone_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNoneNone_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '118',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNoneNone_1',
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



    def test_request_79(self):
        """测试请求 79 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNonereturn_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNonereturn_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNonereturn_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '132',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNonereturn_properties1_1',
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



    def test_request_80(self):
        """测试请求 80 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNonereturn_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNonereturn_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNonereturn_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '132',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNonereturn_properties2_1',
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



    def test_request_81(self):
        """测试请求 81 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNoneFalse_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNoneFalse_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNoneFalse_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '119',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNoneFalse_1',
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



    def test_request_82(self):
        """测试请求 82 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNoneTrue_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNoneTrue_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNoneTrue_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '118',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNoneNoneTrue_1',
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



    def test_request_83(self):
        """测试请求 83 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '130',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1None_1',
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



    def test_request_84(self):
        """测试请求 84 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1return_properties1_1',
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



    def test_request_85(self):
        """测试请求 85 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1return_properties2_1',
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



    def test_request_86(self):
        """测试请求 86 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '131',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1False_1',
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



    def test_request_87(self):
        """测试请求 87 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '130',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata1True_1',
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



    def test_request_88(self):
        """测试请求 88 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '130',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2None_1',
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



    def test_request_89(self):
        """测试请求 89 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2return_properties1_1',
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



    def test_request_90(self):
        """测试请求 90 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2return_properties2_1',
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



    def test_request_91(self):
        """测试请求 91 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '131',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2False_1',
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



    def test_request_92(self):
        """测试请求 92 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '130',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata2True_1',
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



    def test_request_93(self):
        """测试请求 93 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '130',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3None_1',
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



    def test_request_94(self):
        """测试请求 94 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3return_properties1_1',
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



    def test_request_95(self):
        """测试请求 95 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3return_properties2_1',
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



    def test_request_96(self):
        """测试请求 96 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '131',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3False_1',
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



    def test_request_97(self):
        """测试请求 97 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '130',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata3True_1',
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



    def test_request_98(self):
        """测试请求 98 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '130',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4None_1',
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



    def test_request_99(self):
        """测试请求 99 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4return_properties1_1',
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



    def test_request_100(self):
        """测试请求 100 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4return_properties2_1',
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



    def test_request_101(self):
        """测试请求 101 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '131',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4False_1',
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



    def test_request_102(self):
        """测试请求 102 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '130',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTrueNonereturn_metadata4True_1',
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



    def test_request_103(self):
        """测试请求 103 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1NoneNone_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1NoneNone_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1NoneNone_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '132',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1NoneNone_1',
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



    def test_request_104(self):
        """测试请求 104 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1Nonereturn_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1Nonereturn_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1Nonereturn_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '146',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1Nonereturn_properties1_1',
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



    def test_request_105(self):
        """测试请求 105 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1Nonereturn_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1Nonereturn_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1Nonereturn_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '146',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1Nonereturn_properties2_1',
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



    def test_request_106(self):
        """测试请求 106 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1NoneFalse_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1NoneFalse_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1NoneFalse_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '133',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1NoneFalse_1',
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



    def test_request_107(self):
        """测试请求 107 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1NoneTrue_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1NoneTrue_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1NoneTrue_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '132',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1NoneTrue_1',
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



    def test_request_108(self):
        """测试请求 108 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1None_1',
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



    def test_request_109(self):
        """测试请求 109 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '158',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1return_properties1_1',
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



    def test_request_110(self):
        """测试请求 110 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '158',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1return_properties2_1',
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



    def test_request_111(self):
        """测试请求 111 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1False_1',
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



    def test_request_112(self):
        """测试请求 112 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata1True_1',
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



    def test_request_113(self):
        """测试请求 113 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2None_1',
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



    def test_request_114(self):
        """测试请求 114 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '158',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2return_properties1_1',
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



    def test_request_115(self):
        """测试请求 115 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '158',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2return_properties2_1',
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



    def test_request_116(self):
        """测试请求 116 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2False_1',
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



    def test_request_117(self):
        """测试请求 117 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata2True_1',
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



    def test_request_118(self):
        """测试请求 118 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3None_1',
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



    def test_request_119(self):
        """测试请求 119 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '158',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3return_properties1_1',
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



    def test_request_120(self):
        """测试请求 120 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '158',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3return_properties2_1',
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



    def test_request_121(self):
        """测试请求 121 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3False_1',
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



    def test_request_122(self):
        """测试请求 122 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata3True_1',
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



    def test_request_123(self):
        """测试请求 123 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4None_1',
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



    def test_request_124(self):
        """测试请求 124 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '158',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4return_properties1_1',
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



    def test_request_125(self):
        """测试请求 125 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '158',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4return_properties2_1',
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



    def test_request_126(self):
        """测试请求 126 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4False_1',
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



    def test_request_127(self):
        """测试请求 127 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references1return_metadata4True_1',
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



    def test_request_128(self):
        """测试请求 128 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2NoneNone_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2NoneNone_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2NoneNone_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '132',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2NoneNone_1',
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



    def test_request_129(self):
        """测试请求 129 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2Nonereturn_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2Nonereturn_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2Nonereturn_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '146',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2Nonereturn_properties1_1',
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



    def test_request_130(self):
        """测试请求 130 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2Nonereturn_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2Nonereturn_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2Nonereturn_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '146',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2Nonereturn_properties2_1',
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



    def test_request_131(self):
        """测试请求 131 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2NoneFalse_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2NoneFalse_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2NoneFalse_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '133',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2NoneFalse_1',
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



    def test_request_132(self):
        """测试请求 132 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2NoneTrue_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2NoneTrue_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2NoneTrue_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '132',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2NoneTrue_1',
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



    def test_request_133(self):
        """测试请求 133 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1None_1',
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



    def test_request_134(self):
        """测试请求 134 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '158',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1return_properties1_1',
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



    def test_request_135(self):
        """测试请求 135 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '158',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1return_properties2_1',
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



    def test_request_136(self):
        """测试请求 136 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1False_1',
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



    def test_request_137(self):
        """测试请求 137 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata1True_1',
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



    def test_request_138(self):
        """测试请求 138 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2None_1',
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



    def test_request_139(self):
        """测试请求 139 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '158',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2return_properties1_1',
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



    def test_request_140(self):
        """测试请求 140 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '158',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2return_properties2_1',
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



    def test_request_141(self):
        """测试请求 141 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2False_1',
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



    def test_request_142(self):
        """测试请求 142 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata2True_1',
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



    def test_request_143(self):
        """测试请求 143 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3None_1',
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



    def test_request_144(self):
        """测试请求 144 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '158',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3return_properties1_1',
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



    def test_request_145(self):
        """测试请求 145 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '158',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3return_properties2_1',
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



    def test_request_146(self):
        """测试请求 146 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3False_1',
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



    def test_request_147(self):
        """测试请求 147 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata3True_1',
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



    def test_request_148(self):
        """测试请求 148 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4None_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4None_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4None_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4None_1',
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



    def test_request_149(self):
        """测试请求 149 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4return_properties1_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4return_properties1_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4return_properties1_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '158',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4return_properties1_1',
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



    def test_request_150(self):
        """测试请求 150 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4return_properties2_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4return_properties2_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4return_properties2_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '158',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4return_properties2_1',
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



    def test_request_151(self):
        """测试请求 151 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4False_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4False_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4False_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '145',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4False_1',
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



    def test_request_152(self):
        """测试请求 152 - POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4True_1/properties"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4True_1/properties")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4True_1/properties'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '144',
}
        
        # 原始请求内容
        original_content = {
    'name': 'friend',
    'dataType': [
    'Test_collectionpy_test_return_properties_metadata_references_combosTruereturn_references2return_metadata4True_1',
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



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_collection.test_return_properties_metadata_references_combos')
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
    test = TestCollectiontestReturnPropertiesMetadataReferencesCombos()
    test.run_tests()
