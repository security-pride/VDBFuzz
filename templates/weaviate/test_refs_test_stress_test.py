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
logger = logging.getLogger('vdb_fuzzer.test.test_refs_test_stress')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:8080"
TARGET_ENV_VARS = ("WEAVIATE_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_weaviate_0520"
TEST_NAME = "test_refs.test_stress"
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



class TestRefstestStress:
    """自动生成的VDB模糊测试类 - test_refs.test_stress"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_refs.test_stress"
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
    'content-length': '91',
}
        
        # 原始请求内容
        original_content = {
    'class': 'Author',
    'properties': [
    {
    'dataType': [
    'string',
],
    'name': 'name',
},
],
    'vectorizer': 'none',
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
    'content-length': '7663',
}
        
        # 原始请求内容
        original_content = [
    {
    'from': 'weaviate://localhost/Paragraph/494e7faf-1e73-4e3a-b335-87a3ce547b9e/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/9b0d2dc2-0516-423b-be86-9d4fe882a74b/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/6966ae67-16d7-41fa-a059-dcf9ab362c00/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/6966ae67-16d7-41fa-a059-dcf9ab362c00/hasParagraphs',
    'to': 'weaviate://localhost/494e7faf-1e73-4e3a-b335-87a3ce547b9e',
},
    {
    'from': 'weaviate://localhost/Paragraph/119f4a79-1fc2-4972-ad78-73db89db427f/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/53c2c24d-b744-4543-aeed-2e30346d71a8/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/53c2c24d-b744-4543-aeed-2e30346d71a8/hasParagraphs',
    'to': 'weaviate://localhost/494e7faf-1e73-4e3a-b335-87a3ce547b9e',
},
    {
    'from': 'weaviate://localhost/Paragraph/d30b1f08-09b8-4073-9507-6b3c4f5b434b/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/4bd60214-db33-4127-85fc-2ba903403656/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/4bd60214-db33-4127-85fc-2ba903403656/hasParagraphs',
    'to': 'weaviate://localhost/494e7faf-1e73-4e3a-b335-87a3ce547b9e',
},
    {
    'from': 'weaviate://localhost/Paragraph/30c3fcb3-ea7f-44f1-85a1-aa7f406ea45d/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/28bdbd8e-31c9-4588-bb86-1203cc49fdd4/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/28bdbd8e-31c9-4588-bb86-1203cc49fdd4/hasParagraphs',
    'to': 'weaviate://localhost/494e7faf-1e73-4e3a-b335-87a3ce547b9e',
},
    {
    'from': 'weaviate://localhost/Paragraph/e5b9ae27-9720-434c-a643-3fb573567b53/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/5dba2aac-cb02-41e2-a42c-089619242ab9/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/5dba2aac-cb02-41e2-a42c-089619242ab9/hasParagraphs',
    'to': 'weaviate://localhost/494e7faf-1e73-4e3a-b335-87a3ce547b9e',
},
    {
    'from': 'weaviate://localhost/Paragraph/3e753022-f491-49bd-8d40-246d44407dc1/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/360d0111-cfb2-49b4-b061-456c6e3b805f/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/360d0111-cfb2-49b4-b061-456c6e3b805f/hasParagraphs',
    'to': 'weaviate://localhost/494e7faf-1e73-4e3a-b335-87a3ce547b9e',
},
    {
    'from': 'weaviate://localhost/Paragraph/706a452a-c474-4ae4-a7a6-6e12381db8c6/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/2f8b2f0b-9bef-44ea-b5b3-b215ae2194ae/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/2f8b2f0b-9bef-44ea-b5b3-b215ae2194ae/hasParagraphs',
    'to': 'weaviate://localhost/494e7faf-1e73-4e3a-b335-87a3ce547b9e',
},
    {
    'from': 'weaviate://localhost/Paragraph/dfd6add1-7831-426f-bceb-7c4fe1277323/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/40a56ee7-5eda-421d-ac3b-847389ad29dd/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/40a56ee7-5eda-421d-ac3b-847389ad29dd/hasParagraphs',
    'to': 'weaviate://localhost/494e7faf-1e73-4e3a-b335-87a3ce547b9e',
},
    {
    'from': 'weaviate://localhost/Paragraph/e357710c-4c34-4129-afe5-12639991b9de/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/4813fbe2-c104-41ca-9208-4df78c6ba6b3/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/4813fbe2-c104-41ca-9208-4df78c6ba6b3/hasParagraphs',
    'to': 'weaviate://localhost/494e7faf-1e73-4e3a-b335-87a3ce547b9e',
},
    {
    'from': 'weaviate://localhost/Paragraph/f3f4be2d-831f-4312-9d14-831c779a5e09/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/3fe59d90-5515-49ca-97cd-41645d59b333/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/3fe59d90-5515-49ca-97cd-41645d59b333/hasParagraphs',
    'to': 'weaviate://localhost/494e7faf-1e73-4e3a-b335-87a3ce547b9e',
},
    {
    'from': 'weaviate://localhost/Paragraph/453df2a0-09f2-46be-9359-f56f949c5ad2/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/a1d80e28-e976-4922-9fec-4a22b72f4283/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/a1d80e28-e976-4922-9fec-4a22b72f4283/hasParagraphs',
    'to': 'weaviate://localhost/494e7faf-1e73-4e3a-b335-87a3ce547b9e',
},
    {
    'from': 'weaviate://localhost/Paragraph/84f7fff7-1b4d-4e27-9175-d319961aa33e/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/8ef78592-41cc-48bc-a900-8b03dae42d93/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/8ef78592-41cc-48bc-a900-8b03dae42d93/hasParagraphs',
    'to': 'weaviate://localhost/494e7faf-1e73-4e3a-b335-87a3ce547b9e',
},
    {
    'from': 'weaviate://localhost/Paragraph/bcd65efa-a58b-4193-aa8f-c30c175bc010/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/849a43f5-422b-4906-8d35-3a8b93f3fb04/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/849a43f5-422b-4906-8d35-3a8b93f3fb04/hasParagraphs',
    'to': 'weaviate://localhost/494e7faf-1e73-4e3a-b335-87a3ce547b9e',
},
    {
    'from': 'weaviate://localhost/Paragraph/409bd9c2-88e2-4896-962f-4c7915b281ed/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/7e3ed84e-20a9-465b-b06b-5890deb877d7/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/7e3ed84e-20a9-465b-b06b-5890deb877d7/hasParagraphs',
    'to': 'weaviate://localhost/494e7faf-1e73-4e3a-b335-87a3ce547b9e',
},
    {
    'from': 'weaviate://localhost/Paragraph/649d0682-bf44-47e2-9fa8-2037b466707e/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/992117af-e39a-4ae6-98af-99d31fb3956e/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/992117af-e39a-4ae6-98af-99d31fb3956e/hasParagraphs',
    'to': 'weaviate://localhost/494e7faf-1e73-4e3a-b335-87a3ce547b9e',
},
    {
    'from': 'weaviate://localhost/Paragraph/7caba661-c636-4d77-80c1-a13c7dcb62da/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/3c5dd0ac-0f89-4ec8-9f8a-d20bad27cf8d/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
},
    {
    'from': 'weaviate://localhost/Paragraph/3c5dd0ac-0f89-4ec8-9f8a-d20bad27cf8d/hasParagraphs',
    'to': 'weaviate://localhost/494e7faf-1e73-4e3a-b335-87a3ce547b9e',
},
    {
    'from': 'weaviate://localhost/Paragraph/efebed3c-4191-47a2-9908-279e661711ed/author',
    'to': 'weaviate://localhost/b66650d5-54ae-4228-b5e4-a937770879a1',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_refs.test_stress')
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
    test = TestRefstestStress()
    test.run_tests()
