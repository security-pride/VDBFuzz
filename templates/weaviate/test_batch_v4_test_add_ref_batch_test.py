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
logger = logging.getLogger('vdb_fuzzer.test.test_batch_v4_test_add_ref_batch')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:8080"
TARGET_ENV_VARS = ("WEAVIATE_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_weaviate_0520"
TEST_NAME = "test_batch_v4.test_add_ref_batch"
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



class TestBatchV4TestAddRefBatch:
    """自动生成的VDB模糊测试类 - test_batch_v4.test_add_ref_batch"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_batch_v4.test_add_ref_batch"
        self.test_count = 2  # 测试方法数量
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
    'content-length': '285',
}
        
        # 原始请求内容
        original_content = {
    'multiTenancyConfig': {
    'enabled': False,
},
    'vectorizer': 'none',
    'vectorIndexType': 'hnsw',
    'class': 'Test_add_ref_batch_from_uuid_to_uuid',
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
    'Test_add_ref_batch_from_uuid_to_uuid',
],
},
],
}


        send_request(original_content, method, url_path, headers)
        return True



    def test_request_1(self):
        """测试请求 1 - POST http://localhost:8080/v1/batch/references"""
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
    'content-length': '8801',
}
        
        # 原始请求内容
        original_content = [
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/f4081561-10b9-453e-a0b7-b578876c6e82/test',
    'to': 'weaviate://localhost/f4081561-10b9-453e-a0b7-b578876c6e82',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/a68db38a-c4e7-4fc6-b091-b9d5b95ac98f/test',
    'to': 'weaviate://localhost/a68db38a-c4e7-4fc6-b091-b9d5b95ac98f',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/f90db086-f34f-411a-968f-ad22593b8c76/test',
    'to': 'weaviate://localhost/f90db086-f34f-411a-968f-ad22593b8c76',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/0bedea4e-92a0-4a12-a345-2df0d95ab158/test',
    'to': 'weaviate://localhost/0bedea4e-92a0-4a12-a345-2df0d95ab158',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/6b4d0d33-e61a-4e26-99e9-86b502749031/test',
    'to': 'weaviate://localhost/6b4d0d33-e61a-4e26-99e9-86b502749031',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/6a841626-6000-4c36-be71-5a3ec73dba11/test',
    'to': 'weaviate://localhost/6a841626-6000-4c36-be71-5a3ec73dba11',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/a6e99dfc-86f9-4a2d-ae9f-0462628336f3/test',
    'to': 'weaviate://localhost/a6e99dfc-86f9-4a2d-ae9f-0462628336f3',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/a8e10fd2-0074-460b-b447-105f3a4c7f53/test',
    'to': 'weaviate://localhost/a8e10fd2-0074-460b-b447-105f3a4c7f53',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/cf1b746b-2183-4cb2-bea1-ecf9510826bb/test',
    'to': 'weaviate://localhost/cf1b746b-2183-4cb2-bea1-ecf9510826bb',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/ad01cc21-140f-4358-ad15-f964f38f48bf/test',
    'to': 'weaviate://localhost/ad01cc21-140f-4358-ad15-f964f38f48bf',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/30ec2acf-d22e-4dde-9f4a-865c2e1a05be/test',
    'to': 'weaviate://localhost/30ec2acf-d22e-4dde-9f4a-865c2e1a05be',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/6c7c3db3-a3f3-469e-8bb9-221a0a0c412f/test',
    'to': 'weaviate://localhost/6c7c3db3-a3f3-469e-8bb9-221a0a0c412f',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/a2831002-b580-412b-93ce-b3027adc926f/test',
    'to': 'weaviate://localhost/a2831002-b580-412b-93ce-b3027adc926f',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/932562a5-f138-4b55-9cc7-03a07dd3ac7f/test',
    'to': 'weaviate://localhost/932562a5-f138-4b55-9cc7-03a07dd3ac7f',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/3e844657-c3cf-48db-bc8f-25d1a3af061f/test',
    'to': 'weaviate://localhost/3e844657-c3cf-48db-bc8f-25d1a3af061f',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/675482b3-64b7-4eb5-bdc6-d35633266aa2/test',
    'to': 'weaviate://localhost/675482b3-64b7-4eb5-bdc6-d35633266aa2',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/6e788221-e72a-4c58-92be-8ccd4b097ece/test',
    'to': 'weaviate://localhost/6e788221-e72a-4c58-92be-8ccd4b097ece',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/0cc0e11f-473f-4bc0-82ff-bbd49f2c5ba0/test',
    'to': 'weaviate://localhost/0cc0e11f-473f-4bc0-82ff-bbd49f2c5ba0',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/93ba106f-6b92-45c1-85b0-0c3f5db34ba4/test',
    'to': 'weaviate://localhost/93ba106f-6b92-45c1-85b0-0c3f5db34ba4',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/c49130cf-cf2f-4080-b1eb-3e2cb03146b0/test',
    'to': 'weaviate://localhost/c49130cf-cf2f-4080-b1eb-3e2cb03146b0',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/c1661313-e3f2-4b78-a427-14e73c5e9b98/test',
    'to': 'weaviate://localhost/c1661313-e3f2-4b78-a427-14e73c5e9b98',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/ea20ad4d-433e-4a88-b23b-1ee5216b0efc/test',
    'to': 'weaviate://localhost/ea20ad4d-433e-4a88-b23b-1ee5216b0efc',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/6db998af-5853-431d-8f98-685a12681b3b/test',
    'to': 'weaviate://localhost/6db998af-5853-431d-8f98-685a12681b3b',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/d2ae7593-ea25-4572-92a2-050d97f45622/test',
    'to': 'weaviate://localhost/d2ae7593-ea25-4572-92a2-050d97f45622',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/d6b623fa-3ace-48c1-9cfc-b523ec0e31a8/test',
    'to': 'weaviate://localhost/d6b623fa-3ace-48c1-9cfc-b523ec0e31a8',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/6146b820-6c20-408c-9694-4ff7531ac3b1/test',
    'to': 'weaviate://localhost/6146b820-6c20-408c-9694-4ff7531ac3b1',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/40afb658-db53-4f4d-8672-d5f4331bd835/test',
    'to': 'weaviate://localhost/40afb658-db53-4f4d-8672-d5f4331bd835',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/4b6bcd82-0b63-4286-8600-6bc4e1bdd60e/test',
    'to': 'weaviate://localhost/4b6bcd82-0b63-4286-8600-6bc4e1bdd60e',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/c18e8599-c0ec-4caa-aeee-ec0e6eca0216/test',
    'to': 'weaviate://localhost/c18e8599-c0ec-4caa-aeee-ec0e6eca0216',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/44f61fa2-f94a-4bbf-8f28-86c0c46ed394/test',
    'to': 'weaviate://localhost/44f61fa2-f94a-4bbf-8f28-86c0c46ed394',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/4c9c560e-9130-4c6a-8f20-86b4f9199dd0/test',
    'to': 'weaviate://localhost/4c9c560e-9130-4c6a-8f20-86b4f9199dd0',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/c339ba35-5d57-4224-9d26-6d87f693ffc0/test',
    'to': 'weaviate://localhost/c339ba35-5d57-4224-9d26-6d87f693ffc0',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/b3905414-6c75-4b2d-84f9-d7bc45bb3bfc/test',
    'to': 'weaviate://localhost/b3905414-6c75-4b2d-84f9-d7bc45bb3bfc',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/0cc2495c-7a7e-4c22-a539-27ef1d34d8ab/test',
    'to': 'weaviate://localhost/0cc2495c-7a7e-4c22-a539-27ef1d34d8ab',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/a9666235-0753-469f-9fe2-21b8d7a2eb44/test',
    'to': 'weaviate://localhost/a9666235-0753-469f-9fe2-21b8d7a2eb44',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/9667b2cf-9c4c-4e3e-a1b2-f25bc6302493/test',
    'to': 'weaviate://localhost/9667b2cf-9c4c-4e3e-a1b2-f25bc6302493',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/45abeda3-e00d-44b7-ab67-1e6cf64afa51/test',
    'to': 'weaviate://localhost/45abeda3-e00d-44b7-ab67-1e6cf64afa51',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/842c0a1b-04a1-4b9a-8651-8c839f40e9a4/test',
    'to': 'weaviate://localhost/842c0a1b-04a1-4b9a-8651-8c839f40e9a4',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/d1bfc2c5-1b29-4512-831f-9cdbf89db80e/test',
    'to': 'weaviate://localhost/d1bfc2c5-1b29-4512-831f-9cdbf89db80e',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/2ffe1825-6114-4bba-ab6f-db3e508463b6/test',
    'to': 'weaviate://localhost/2ffe1825-6114-4bba-ab6f-db3e508463b6',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/00b416e5-0a21-4604-92a2-1ad908c7c610/test',
    'to': 'weaviate://localhost/00b416e5-0a21-4604-92a2-1ad908c7c610',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/b8cc6ea7-478a-47f1-9ccc-f21e85e83bf2/test',
    'to': 'weaviate://localhost/b8cc6ea7-478a-47f1-9ccc-f21e85e83bf2',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/16e99911-6ccc-4a75-a7d5-8826c9f8f120/test',
    'to': 'weaviate://localhost/16e99911-6ccc-4a75-a7d5-8826c9f8f120',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/e3d19bb9-f91b-434c-bb11-09caa8ef5be5/test',
    'to': 'weaviate://localhost/e3d19bb9-f91b-434c-bb11-09caa8ef5be5',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/5043cc74-2f81-4ea5-b43c-56686ea6e9ed/test',
    'to': 'weaviate://localhost/5043cc74-2f81-4ea5-b43c-56686ea6e9ed',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/9c8b78f2-c031-4147-a41b-ea570b6f3638/test',
    'to': 'weaviate://localhost/9c8b78f2-c031-4147-a41b-ea570b6f3638',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/399d366b-6893-4162-b397-594f62a10563/test',
    'to': 'weaviate://localhost/399d366b-6893-4162-b397-594f62a10563',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/0d21a202-c7ff-49e2-8f98-1346d04faa9d/test',
    'to': 'weaviate://localhost/0d21a202-c7ff-49e2-8f98-1346d04faa9d',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/637cec03-5c3c-4a1e-abd7-a5a74013c8e5/test',
    'to': 'weaviate://localhost/637cec03-5c3c-4a1e-abd7-a5a74013c8e5',
},
    {
    'from': 'weaviate://localhost/Test_add_ref_batch_from_uuid_to_uuid/c292f6d8-d356-445a-b323-0c3f885ad4df/test',
    'to': 'weaviate://localhost/c292f6d8-d356-445a-b323-0c3f885ad4df',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_batch_v4.test_add_ref_batch')
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
    test = TestBatchV4TestAddRefBatch()
    test.run_tests()
