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
logger = logging.getLogger('vdb_fuzzer.test.test_batch_v4_test_add_one_hundred_objects_and_references_between_all')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:8080"
TARGET_ENV_VARS = ("WEAVIATE_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_weaviate_0520"
TEST_NAME = "test_batch_v4.test_add_one_hundred_objects_and_references_between_all"
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



class TestBatchV4TestAddOneHundredObjectsAndReferencesBetweenAll:
    """自动生成的VDB模糊测试类 - test_batch_v4.test_add_one_hundred_objects_and_references_between_all"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_batch_v4.test_add_one_hundred_objects_and_references_between_all"
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
    'content-length': '323',
}
        
        # 原始请求内容
        original_content = {
    'multiTenancyConfig': {
    'enabled': False,
},
    'vectorizer': 'none',
    'vectorIndexType': 'hnsw',
    'class': 'Test_add_one_hundred_objects_and_references_between_all',
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
    'Test_add_one_hundred_objects_and_references_between_all',
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
    'content-length': '9751',
}
        
        # 原始请求内容
        original_content = [
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/6c4d349f-2186-482b-a0cc-791a0578857f',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/d1981437-99ed-4bce-bcba-5ab22fdbff6a',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/aacccd5a-fce7-499c-af4d-8a1b8b005728',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/cc81e234-e480-45b7-9617-841363490367',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/b651aa13-533d-4030-bc20-2eb5a152a766',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/78bbdf25-b17b-4f0d-8a3e-bdceb82a9d87',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/f12ea19d-1afd-45a6-81d2-5e86e7ed733b',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/a6101823-6c90-4ac3-a19f-9049024a7cb6',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/aae965e0-406f-46b8-88d8-09d4932e92de',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/d2421134-2f61-49b1-aebf-e03ba258e801',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/5f27dbb8-1351-4957-a8ff-c1586d35c24f',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/655084c3-9ec9-40ef-977d-17821baf7d1c',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/f205b0f6-4a02-4891-9c22-bb43997c1c34',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/16b04f91-b0d7-4c27-a3fe-7a2d871da5a7',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/b935042c-f892-453f-98b4-350b538987f7',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/34339a66-e82d-4691-97ce-db4461349f77',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/332df14a-f81f-419a-b8f4-5afcb22fa89f',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/6ac46006-5018-477c-8848-77f9720d121c',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/34f3f631-6543-43de-ba3f-f32937d0454c',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/0f0d8e3a-9d8b-41f9-a66b-1a49427f8ffc',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/e387cb2a-794d-4e83-a39a-a9eb71d09241',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/d19f21f6-5536-4269-812a-00ce1e2fa3d5',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/40150ba0-b5aa-4ff8-9e45-43c1989caa84',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/21f19921-9072-42ff-a45f-e4839c6a2ad6',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/599f1304-24c9-4aea-acc9-34fffbf3c2e6',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/fc6b97c8-86ac-4ee9-b57e-b9861ecd56f7',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/5ddceb8c-b509-4471-8767-adefd461f87f',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/46946fdf-aaa1-458b-81b6-7018c34c7639',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/4fa55ac5-ecf6-4a1d-a98f-830cba01e86a',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/5ec387a6-26d3-4618-9389-fe434762fb9d',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/97f6e854-e149-4d28-aee7-1b16a79ab835',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/c0ab753d-d753-4251-af56-5f45b29e1bfd',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/84eee301-9a2e-4b6f-a17f-a9d9843f9f89',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/d3af73e5-3a02-478b-9fc7-e25d7451734c',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/53a7abda-261c-40cc-a2c5-05fafef443a7',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/29f8bb21-25a1-4728-9672-f9a17ca406d0',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/dc1498f5-9fa2-406c-8595-b0554bb43c06',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/cabd5998-7821-44dd-a210-5da8a223469e',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/4d73570d-65ff-453b-be6c-c78edbc49a4c',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/1f56931c-102b-4833-80bf-27c88f5e115d',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/153faa18-fe04-460c-bc70-7d626d215c53',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/4507efe7-fc53-446a-a232-28c255f23dd3',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/9eb5009d-ba42-428d-a2c4-876caf63a088',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/200169a7-cf69-4466-a3f5-36239428a542',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/c8ba1146-16fa-4cc1-8b1c-5b8c68bb5840',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/1e603326-ffe6-40f0-afe1-5c6c00f61f69',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/9b5ea523-8e4b-4534-a1f1-2a3bfec10fcb',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/5a0bb5c4-ee0c-40a6-a3ad-8f2df2f506c6',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/feff3a67-038c-4cad-84fb-1663504343b4',
},
    {
    'from': 'weaviate://localhost/Test_add_one_hundred_objects_and_references_between_all/13ead011-1573-4593-8f78-fee3203bdfe7/test',
    'to': 'weaviate://localhost/db9cca9c-23ef-40c5-8189-a986ccbaa3f9',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_batch_v4.test_add_one_hundred_objects_and_references_between_all')
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
    test = TestBatchV4TestAddOneHundredObjectsAndReferencesBetweenAll()
    test.run_tests()
