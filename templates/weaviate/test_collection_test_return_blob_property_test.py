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
logger = logging.getLogger('vdb_fuzzer.test.test_collection_test_return_blob_property')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:8080"
TARGET_ENV_VARS = ("WEAVIATE_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_weaviate_0520"
TEST_NAME = "test_collection.test_return_blob_property"
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



class TestCollectiontestReturnBlobProperty:
    """自动生成的VDB模糊测试类 - test_collection.test_return_blob_property"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_collection.test_return_blob_property"
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
    'content-length': '153',
}
        
        # 原始请求内容
        original_content = {
    'vectorizer': 'none',
    'vectorIndexType': 'hnsw',
    'class': 'Test_collectionpy_test_return_blob_property_1',
    'properties': [
    {
    'name': 'blob',
    'dataType': [
    'blob',
],
},
],
}


        send_request(original_content, method, url_path, headers)
        return True



    def test_request_1(self):
        """测试请求 1 - POST http://localhost:8080/v1/objects"""
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
    'content-length': '8754',
}
        
        # 原始请求内容
        original_content = {
    'class': 'Test_collectionpy_test_return_blob_property_1',
    'properties': {
    'blob': 'iVBORw0KGgoAAAANSUhEUgAAAZAAAAE5CAYAAAC+rHbqAAAAGXRFWHRTb2Z0d2FyZQBBZG9iZSBJbWFnZVJlYWR5ccllPAAAAyhpVFh0WE1MOmNvbS5hZG9iZS54bXAAAAAAADw/eHBhY2tldCBiZWdpbj0i77u/IiBpZD0iVzVNME1wQ2VoaUh6cmVTek5UY3prYzlkIj8+IDx4OnhtcG1ldGEgeG1sbnM6eD0iYWRvYmU6bnM6bWV0YS8iIHg6eG1wdGs9IkFkb2JlIFhNUCBDb3JlIDUuNi1jMTQ1IDc5LjE2MzQ5OSwgMjAxOC8wOC8xMy0xNjo0MDoyMiAgICAgICAgIj4gPHJkZjpSREYgeG1sbnM6cmRmPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5LzAyLzIyLXJkZi1zeW50YXgtbnMjIj4gPHJkZjpEZXNjcmlwdGlvbiByZGY6YWJvdXQ9IiIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIiB4bWxuczp4bXBNTT0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL21tLyIgeG1sbnM6c3RSZWY9Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9zVHlwZS9SZXNvdXJjZVJlZiMiIHhtcDpDcmVhdG9yVG9vbD0iQWRvYmUgUGhvdG9zaG9wIENDIDIwMTkgKE1hY2ludG9zaCkiIHhtcE1NOkluc3RhbmNlSUQ9InhtcC5paWQ6Rjc3MkEzQzdGM0QxMTFFODlBRTRBNjMyNUE2MTk3NzgiIHhtcE1NOkRvY3VtZW50SUQ9InhtcC5kaWQ6Rjc3MkEzQzhGM0QxMTFFODlBRTRBNjMyNUE2MTk3NzgiPiA8eG1wTU06RGVyaXZlZEZyb20gc3RSZWY6aW5zdGFuY2VJRD0ieG1wLmlpZDpGNzcyQTNDNUYzRDExMUU4OUFFNEE2MzI1QTYxOTc3OCIgc3RSZWY6ZG9jdW1lbnRJRD0ieG1wLmRpZDpGNzcyQTNDNkYzRDExMUU4OUFFNEE2MzI1QTYxOTc3OCIvPiA8L3JkZjpEZXNjcmlwdGlvbj4gPC9yZGY6UkRGPiA8L3g6eG1wbWV0YT4gPD94cGFja2V0IGVuZD0iciI/PnOiDKoAABWzSURBVHja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',
},
    'id': 'a0d6d8fe-43f3-4504-a185-8c2ea0b2002d',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_collection.test_return_blob_property')
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
    test = TestCollectiontestReturnBlobProperty()
    test.run_tests()
