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
logger = logging.getLogger('vdb_fuzzer.test.test_batch_v4_test_add_ref_batch_with_tenant')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:8080"
TARGET_ENV_VARS = ("WEAVIATE_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_weaviate_0520"
TEST_NAME = "test_batch_v4.test_add_ref_batch_with_tenant"
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



class TestBatchV4TestAddRefBatchWithTenant:
    """自动生成的VDB模糊测试类 - test_batch_v4.test_add_ref_batch_with_tenant"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_batch_v4.test_add_ref_batch_with_tenant"
        self.test_count = 3  # 测试方法数量
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
    'content-length': '272',
}
        
        # 原始请求内容
        original_content = {
    'multiTenancyConfig': {
    'enabled': True,
},
    'vectorizer': 'none',
    'vectorIndexType': 'hnsw',
    'class': 'Test_add_ref_batch_with_tenant',
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
    {
    'name': 'test',
    'dataType': [
    'Test_add_ref_batch_with_tenant',
],
},
],
}


        send_request(original_content, method, url_path, headers)
        return True



    def test_request_1(self):
        """测试请求 1 - POST http://localhost:8080/v1/schema/Test_add_ref_batch_with_tenant/tenants"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_add_ref_batch_with_tenant/tenants")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_add_ref_batch_with_tenant/tenants'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '211',
}
        
        # 原始请求内容
        original_content = [
    {
    'name': 'tenant0',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant1',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant2',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant3',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant4',
    'activityStatus': 'HOT',
},
]
        
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
        """测试请求 2 - POST http://localhost:8080/v1/batch/references"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/batch/references")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/batch/references'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '11001',
}
        
        # 原始请求内容
        original_content = [
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/5833f8fa-4c14-4c6c-b8e1-3a2fb6e6cfac/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/5833f8fa-4c14-4c6c-b8e1-3a2fb6e6cfac',
    'tenant': 'tenant0',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/10fa0f57-fdfb-4d85-a367-dd1ce682515c/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/10fa0f57-fdfb-4d85-a367-dd1ce682515c',
    'tenant': 'tenant1',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/9c7227d1-109f-45b5-9948-7d7c0b41897c/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/9c7227d1-109f-45b5-9948-7d7c0b41897c',
    'tenant': 'tenant2',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/bef6bdbf-7fdb-4a83-ac48-e7b3162aed72/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/bef6bdbf-7fdb-4a83-ac48-e7b3162aed72',
    'tenant': 'tenant3',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/a3d2e494-4359-4410-85ce-15b3135e524c/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/a3d2e494-4359-4410-85ce-15b3135e524c',
    'tenant': 'tenant4',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/d90c7ee3-ab84-4cc7-bc3b-049b910d73c3/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/d90c7ee3-ab84-4cc7-bc3b-049b910d73c3',
    'tenant': 'tenant0',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/25f59365-9591-4f57-a61c-16aff38145fa/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/25f59365-9591-4f57-a61c-16aff38145fa',
    'tenant': 'tenant1',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/d3b47c37-84dd-43ab-b89e-af2e10077dbe/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/d3b47c37-84dd-43ab-b89e-af2e10077dbe',
    'tenant': 'tenant2',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/5d14877c-4413-4b6d-b25f-0f9156669cd6/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/5d14877c-4413-4b6d-b25f-0f9156669cd6',
    'tenant': 'tenant3',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/daae74eb-2c88-4f3e-95c9-d05594d2faca/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/daae74eb-2c88-4f3e-95c9-d05594d2faca',
    'tenant': 'tenant4',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/8c05b9d4-3db3-4867-86a7-9d268ef0de30/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/8c05b9d4-3db3-4867-86a7-9d268ef0de30',
    'tenant': 'tenant0',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/7ac27a88-ba69-463a-ae4a-ecffcf833017/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/7ac27a88-ba69-463a-ae4a-ecffcf833017',
    'tenant': 'tenant1',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/b3aa16d8-e796-4716-a5b6-5b89142242a3/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/b3aa16d8-e796-4716-a5b6-5b89142242a3',
    'tenant': 'tenant2',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/b1681714-c678-439c-a509-da130bea82f1/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/b1681714-c678-439c-a509-da130bea82f1',
    'tenant': 'tenant3',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/284be031-a7f3-42bc-9d82-200ae6a4f444/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/284be031-a7f3-42bc-9d82-200ae6a4f444',
    'tenant': 'tenant4',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/02dc699a-def1-4645-9382-5ae5a35b7422/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/02dc699a-def1-4645-9382-5ae5a35b7422',
    'tenant': 'tenant0',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/5c81ff10-8fda-4c2d-b8a8-0d922739151b/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/5c81ff10-8fda-4c2d-b8a8-0d922739151b',
    'tenant': 'tenant1',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/e3e4f2a6-63bd-413c-9572-8cd3f3e1da25/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/e3e4f2a6-63bd-413c-9572-8cd3f3e1da25',
    'tenant': 'tenant2',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/d074e4d4-c387-4203-91a0-3115d14a7015/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/d074e4d4-c387-4203-91a0-3115d14a7015',
    'tenant': 'tenant3',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/f5dadc4e-4378-48a0-8b7a-a42de749fd76/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/f5dadc4e-4378-48a0-8b7a-a42de749fd76',
    'tenant': 'tenant4',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/e9b147dd-aa74-4d5c-9b98-2f4aae7801e1/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/e9b147dd-aa74-4d5c-9b98-2f4aae7801e1',
    'tenant': 'tenant0',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/0b7bbd7a-f192-4d1e-b4dd-675c58225ce1/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/0b7bbd7a-f192-4d1e-b4dd-675c58225ce1',
    'tenant': 'tenant1',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/ae009e2c-ebd7-4c17-b4e3-4afab6e97fb7/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/ae009e2c-ebd7-4c17-b4e3-4afab6e97fb7',
    'tenant': 'tenant2',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/3aed8695-3b06-4649-8832-0c40d5d82bfe/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/3aed8695-3b06-4649-8832-0c40d5d82bfe',
    'tenant': 'tenant3',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/92e0fec3-82a8-42cb-ab2a-32a79a8c8c69/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/92e0fec3-82a8-42cb-ab2a-32a79a8c8c69',
    'tenant': 'tenant4',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/6f362ea4-a87c-43d9-9703-c4ffa5badaf5/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/6f362ea4-a87c-43d9-9703-c4ffa5badaf5',
    'tenant': 'tenant0',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/86ac4a7e-9be4-4ea2-9404-e576d9c2b8e9/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/86ac4a7e-9be4-4ea2-9404-e576d9c2b8e9',
    'tenant': 'tenant1',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/41bfd5b8-5f8d-4be0-9978-80a3df7056cf/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/41bfd5b8-5f8d-4be0-9978-80a3df7056cf',
    'tenant': 'tenant2',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/46b8ded9-c774-47da-b514-1e73bd47e61d/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/46b8ded9-c774-47da-b514-1e73bd47e61d',
    'tenant': 'tenant3',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/6ce21be3-42b4-4ee6-81af-84ef89a84743/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/6ce21be3-42b4-4ee6-81af-84ef89a84743',
    'tenant': 'tenant4',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/20134d2d-1bc1-4a73-b914-3e6c9e4ea877/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/20134d2d-1bc1-4a73-b914-3e6c9e4ea877',
    'tenant': 'tenant0',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/16f97bb3-3411-4b2b-bc46-7f44dc39c874/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/16f97bb3-3411-4b2b-bc46-7f44dc39c874',
    'tenant': 'tenant1',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/268b18a7-baff-4deb-ab4a-3b7ab7998788/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/268b18a7-baff-4deb-ab4a-3b7ab7998788',
    'tenant': 'tenant2',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/3efeae2e-96e1-4627-97c8-fa7d77cd3988/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/3efeae2e-96e1-4627-97c8-fa7d77cd3988',
    'tenant': 'tenant3',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/ac7c3699-dee3-4215-9091-35fc1bfdd818/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/ac7c3699-dee3-4215-9091-35fc1bfdd818',
    'tenant': 'tenant4',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/aa225518-7a37-4be1-aa0b-86175f574abc/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/aa225518-7a37-4be1-aa0b-86175f574abc',
    'tenant': 'tenant0',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/387fcaf0-7e30-4417-9cca-4c421c0f1838/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/387fcaf0-7e30-4417-9cca-4c421c0f1838',
    'tenant': 'tenant1',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/e62069c6-5e34-43e8-a9fa-5c480010ad51/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/e62069c6-5e34-43e8-a9fa-5c480010ad51',
    'tenant': 'tenant2',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/7ba455b5-4316-45c2-8d60-5656097a692d/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/7ba455b5-4316-45c2-8d60-5656097a692d',
    'tenant': 'tenant3',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/0b3fba20-fad1-4871-bf07-adc9d555b334/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/0b3fba20-fad1-4871-bf07-adc9d555b334',
    'tenant': 'tenant4',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/9e928dcd-5587-48f7-910a-fba218fb6b37/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/9e928dcd-5587-48f7-910a-fba218fb6b37',
    'tenant': 'tenant0',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/1e86d847-6555-4af5-a305-153a377dfa71/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/1e86d847-6555-4af5-a305-153a377dfa71',
    'tenant': 'tenant1',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/0613f1aa-c9f2-41bc-8446-66fde0a623a1/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/0613f1aa-c9f2-41bc-8446-66fde0a623a1',
    'tenant': 'tenant2',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/7e8068cc-f9a1-4f12-95ff-ecbe0b5bf70b/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/7e8068cc-f9a1-4f12-95ff-ecbe0b5bf70b',
    'tenant': 'tenant3',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/88744e62-f62d-4905-87b7-e10e020354c6/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/88744e62-f62d-4905-87b7-e10e020354c6',
    'tenant': 'tenant4',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/f9ec58ed-15e2-4507-82cf-22f1a298e11b/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/f9ec58ed-15e2-4507-82cf-22f1a298e11b',
    'tenant': 'tenant0',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/4a848957-945e-4685-bd76-0acd12443b40/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/4a848957-945e-4685-bd76-0acd12443b40',
    'tenant': 'tenant1',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/4cbeb222-862d-4bb7-8c17-05a7f3e7ec02/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/4cbeb222-862d-4bb7-8c17-05a7f3e7ec02',
    'tenant': 'tenant2',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/a8401586-9fb3-440a-92d5-fe28e6b6205f/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/a8401586-9fb3-440a-92d5-fe28e6b6205f',
    'tenant': 'tenant3',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_with_tenant/eba83c18-1ab7-49ab-b4de-7de563b7213a/test',
    'to': 'weaviate://localhost/Test_add_ref_batch_with_tenant/eba83c18-1ab7-49ab-b4de-7de563b7213a',
    'tenant': 'tenant4',
},
]
        
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_batch_v4.test_add_ref_batch_with_tenant')
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
    test = TestBatchV4TestAddRefBatchWithTenant()
    test.run_tests()
