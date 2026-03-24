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
logger = logging.getLogger('vdb_fuzzer.test.test_tenants_test_tenants_create_and_update_1001_tenants')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:8080"
TARGET_ENV_VARS = ("WEAVIATE_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_weaviate_0520"
TEST_NAME = "test_tenants.test_tenants_create_and_update_1001_tenants"
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



class TestTenantstestTenantsCreateAndUpdate1001Tenants:
    """自动生成的VDB模糊测试类 - test_tenants.test_tenants_create_and_update_1001_tenants"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_tenants.test_tenants_create_and_update_1001_tenants"
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
    'content-length': '155',
}
        
        # 原始请求内容
        original_content = {
    'multiTenancyConfig': {
    'enabled': True,
},
    'vectorizer': 'none',
    'vectorIndexType': 'hnsw',
    'class': 'Test_tenantspy_test_tenants_create_and_update_1001_tenants_1',
}


        send_request(original_content, method, url_path, headers)
        return True



    def test_request_1(self):
        """测试请求 1 - POST http://localhost:8080/v1/schema/Test_tenantspy_test_tenants_create_and_update_1001_tenants_1/tenants"""
        logger.info(f"测试请求: POST http://localhost:8080/v1/schema/Test_tenantspy_test_tenants_create_and_update_1001_tenants_1/tenants")
        
        method = 'POST'
        url_path = 'http://localhost:8080/v1/schema/Test_tenantspy_test_tenants_create_and_update_1001_tenants_1/tenants'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '43936',
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
    {
    'name': 'tenant5',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant6',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant7',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant8',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant9',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant10',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant11',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant12',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant13',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant14',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant15',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant16',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant17',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant18',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant19',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant20',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant21',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant22',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant23',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant24',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant25',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant26',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant27',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant28',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant29',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant30',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant31',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant32',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant33',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant34',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant35',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant36',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant37',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant38',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant39',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant40',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant41',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant42',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant43',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant44',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant45',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant46',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant47',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant48',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant49',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant50',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant51',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant52',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant53',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant54',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant55',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant56',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant57',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant58',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant59',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant60',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant61',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant62',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant63',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant64',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant65',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant66',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant67',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant68',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant69',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant70',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant71',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant72',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant73',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant74',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant75',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant76',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant77',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant78',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant79',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant80',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant81',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant82',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant83',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant84',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant85',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant86',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant87',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant88',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant89',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant90',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant91',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant92',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant93',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant94',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant95',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant96',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant97',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant98',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant99',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant100',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant101',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant102',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant103',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant104',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant105',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant106',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant107',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant108',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant109',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant110',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant111',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant112',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant113',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant114',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant115',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant116',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant117',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant118',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant119',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant120',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant121',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant122',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant123',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant124',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant125',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant126',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant127',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant128',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant129',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant130',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant131',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant132',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant133',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant134',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant135',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant136',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant137',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant138',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant139',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant140',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant141',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant142',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant143',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant144',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant145',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant146',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant147',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant148',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant149',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant150',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant151',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant152',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant153',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant154',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant155',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant156',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant157',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant158',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant159',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant160',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant161',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant162',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant163',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant164',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant165',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant166',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant167',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant168',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant169',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant170',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant171',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant172',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant173',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant174',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant175',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant176',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant177',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant178',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant179',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant180',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant181',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant182',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant183',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant184',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant185',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant186',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant187',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant188',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant189',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant190',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant191',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant192',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant193',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant194',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant195',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant196',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant197',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant198',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant199',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant200',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant201',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant202',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant203',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant204',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant205',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant206',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant207',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant208',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant209',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant210',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant211',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant212',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant213',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant214',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant215',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant216',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant217',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant218',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant219',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant220',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant221',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant222',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant223',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant224',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant225',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant226',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant227',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant228',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant229',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant230',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant231',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant232',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant233',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant234',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant235',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant236',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant237',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant238',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant239',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant240',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant241',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant242',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant243',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant244',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant245',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant246',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant247',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant248',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant249',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant250',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant251',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant252',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant253',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant254',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant255',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant256',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant257',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant258',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant259',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant260',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant261',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant262',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant263',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant264',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant265',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant266',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant267',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant268',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant269',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant270',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant271',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant272',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant273',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant274',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant275',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant276',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant277',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant278',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant279',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant280',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant281',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant282',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant283',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant284',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant285',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant286',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant287',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant288',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant289',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant290',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant291',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant292',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant293',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant294',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant295',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant296',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant297',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant298',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant299',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant300',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant301',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant302',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant303',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant304',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant305',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant306',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant307',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant308',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant309',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant310',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant311',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant312',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant313',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant314',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant315',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant316',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant317',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant318',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant319',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant320',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant321',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant322',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant323',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant324',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant325',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant326',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant327',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant328',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant329',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant330',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant331',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant332',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant333',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant334',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant335',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant336',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant337',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant338',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant339',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant340',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant341',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant342',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant343',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant344',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant345',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant346',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant347',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant348',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant349',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant350',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant351',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant352',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant353',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant354',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant355',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant356',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant357',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant358',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant359',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant360',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant361',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant362',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant363',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant364',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant365',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant366',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant367',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant368',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant369',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant370',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant371',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant372',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant373',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant374',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant375',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant376',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant377',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant378',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant379',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant380',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant381',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant382',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant383',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant384',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant385',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant386',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant387',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant388',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant389',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant390',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant391',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant392',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant393',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant394',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant395',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant396',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant397',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant398',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant399',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant400',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant401',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant402',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant403',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant404',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant405',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant406',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant407',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant408',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant409',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant410',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant411',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant412',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant413',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant414',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant415',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant416',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant417',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant418',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant419',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant420',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant421',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant422',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant423',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant424',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant425',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant426',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant427',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant428',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant429',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant430',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant431',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant432',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant433',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant434',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant435',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant436',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant437',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant438',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant439',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant440',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant441',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant442',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant443',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant444',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant445',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant446',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant447',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant448',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant449',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant450',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant451',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant452',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant453',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant454',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant455',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant456',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant457',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant458',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant459',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant460',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant461',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant462',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant463',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant464',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant465',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant466',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant467',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant468',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant469',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant470',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant471',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant472',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant473',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant474',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant475',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant476',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant477',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant478',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant479',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant480',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant481',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant482',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant483',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant484',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant485',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant486',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant487',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant488',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant489',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant490',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant491',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant492',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant493',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant494',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant495',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant496',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant497',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant498',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant499',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant500',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant501',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant502',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant503',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant504',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant505',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant506',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant507',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant508',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant509',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant510',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant511',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant512',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant513',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant514',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant515',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant516',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant517',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant518',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant519',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant520',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant521',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant522',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant523',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant524',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant525',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant526',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant527',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant528',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant529',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant530',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant531',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant532',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant533',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant534',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant535',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant536',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant537',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant538',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant539',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant540',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant541',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant542',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant543',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant544',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant545',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant546',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant547',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant548',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant549',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant550',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant551',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant552',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant553',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant554',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant555',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant556',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant557',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant558',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant559',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant560',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant561',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant562',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant563',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant564',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant565',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant566',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant567',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant568',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant569',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant570',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant571',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant572',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant573',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant574',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant575',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant576',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant577',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant578',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant579',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant580',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant581',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant582',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant583',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant584',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant585',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant586',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant587',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant588',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant589',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant590',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant591',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant592',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant593',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant594',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant595',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant596',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant597',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant598',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant599',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant600',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant601',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant602',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant603',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant604',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant605',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant606',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant607',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant608',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant609',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant610',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant611',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant612',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant613',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant614',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant615',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant616',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant617',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant618',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant619',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant620',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant621',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant622',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant623',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant624',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant625',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant626',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant627',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant628',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant629',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant630',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant631',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant632',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant633',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant634',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant635',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant636',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant637',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant638',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant639',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant640',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant641',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant642',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant643',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant644',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant645',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant646',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant647',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant648',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant649',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant650',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant651',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant652',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant653',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant654',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant655',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant656',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant657',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant658',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant659',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant660',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant661',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant662',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant663',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant664',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant665',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant666',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant667',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant668',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant669',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant670',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant671',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant672',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant673',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant674',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant675',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant676',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant677',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant678',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant679',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant680',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant681',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant682',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant683',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant684',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant685',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant686',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant687',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant688',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant689',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant690',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant691',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant692',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant693',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant694',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant695',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant696',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant697',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant698',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant699',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant700',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant701',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant702',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant703',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant704',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant705',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant706',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant707',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant708',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant709',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant710',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant711',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant712',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant713',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant714',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant715',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant716',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant717',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant718',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant719',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant720',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant721',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant722',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant723',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant724',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant725',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant726',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant727',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant728',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant729',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant730',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant731',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant732',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant733',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant734',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant735',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant736',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant737',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant738',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant739',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant740',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant741',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant742',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant743',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant744',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant745',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant746',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant747',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant748',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant749',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant750',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant751',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant752',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant753',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant754',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant755',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant756',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant757',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant758',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant759',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant760',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant761',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant762',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant763',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant764',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant765',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant766',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant767',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant768',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant769',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant770',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant771',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant772',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant773',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant774',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant775',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant776',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant777',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant778',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant779',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant780',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant781',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant782',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant783',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant784',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant785',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant786',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant787',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant788',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant789',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant790',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant791',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant792',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant793',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant794',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant795',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant796',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant797',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant798',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant799',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant800',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant801',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant802',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant803',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant804',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant805',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant806',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant807',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant808',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant809',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant810',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant811',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant812',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant813',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant814',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant815',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant816',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant817',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant818',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant819',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant820',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant821',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant822',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant823',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant824',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant825',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant826',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant827',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant828',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant829',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant830',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant831',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant832',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant833',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant834',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant835',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant836',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant837',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant838',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant839',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant840',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant841',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant842',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant843',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant844',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant845',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant846',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant847',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant848',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant849',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant850',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant851',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant852',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant853',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant854',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant855',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant856',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant857',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant858',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant859',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant860',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant861',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant862',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant863',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant864',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant865',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant866',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant867',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant868',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant869',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant870',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant871',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant872',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant873',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant874',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant875',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant876',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant877',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant878',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant879',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant880',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant881',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant882',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant883',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant884',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant885',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant886',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant887',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant888',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant889',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant890',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant891',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant892',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant893',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant894',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant895',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant896',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant897',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant898',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant899',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant900',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant901',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant902',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant903',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant904',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant905',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant906',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant907',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant908',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant909',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant910',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant911',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant912',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant913',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant914',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant915',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant916',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant917',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant918',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant919',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant920',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant921',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant922',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant923',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant924',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant925',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant926',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant927',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant928',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant929',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant930',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant931',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant932',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant933',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant934',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant935',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant936',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant937',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant938',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant939',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant940',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant941',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant942',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant943',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant944',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant945',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant946',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant947',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant948',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant949',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant950',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant951',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant952',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant953',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant954',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant955',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant956',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant957',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant958',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant959',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant960',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant961',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant962',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant963',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant964',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant965',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant966',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant967',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant968',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant969',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant970',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant971',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant972',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant973',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant974',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant975',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant976',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant977',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant978',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant979',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant980',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant981',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant982',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant983',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant984',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant985',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant986',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant987',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant988',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant989',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant990',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant991',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant992',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant993',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant994',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant995',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant996',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant997',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant998',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant999',
    'activityStatus': 'HOT',
},
    {
    'name': 'tenant1000',
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
        """测试请求 2 - PUT http://localhost:8080/v1/schema/Test_tenantspy_test_tenants_create_and_update_1001_tenants_1/tenants"""
        logger.info(f"测试请求: PUT http://localhost:8080/v1/schema/Test_tenantspy_test_tenants_create_and_update_1001_tenants_1/tenants")
        
        method = 'PUT'
        url_path = 'http://localhost:8080/v1/schema/Test_tenantspy_test_tenants_create_and_update_1001_tenants_1/tenants'
        headers = {
    'host': 'localhost:8080',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate',
    'connection': 'keep-alive',
    'user-agent': 'python-httpx/0.28.1',
    'content-type': 'application/json',
    'content-length': '4391',
}
        
        # 原始请求内容
        original_content = [
    {
    'name': 'tenant0',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant1',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant2',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant3',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant4',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant5',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant6',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant7',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant8',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant9',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant10',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant11',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant12',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant13',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant14',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant15',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant16',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant17',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant18',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant19',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant20',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant21',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant22',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant23',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant24',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant25',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant26',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant27',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant28',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant29',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant30',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant31',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant32',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant33',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant34',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant35',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant36',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant37',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant38',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant39',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant40',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant41',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant42',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant43',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant44',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant45',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant46',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant47',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant48',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant49',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant50',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant51',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant52',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant53',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant54',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant55',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant56',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant57',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant58',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant59',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant60',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant61',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant62',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant63',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant64',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant65',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant66',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant67',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant68',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant69',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant70',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant71',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant72',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant73',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant74',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant75',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant76',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant77',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant78',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant79',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant80',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant81',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant82',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant83',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant84',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant85',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant86',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant87',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant88',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant89',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant90',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant91',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant92',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant93',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant94',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant95',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant96',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant97',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant98',
    'activityStatus': 'COLD',
},
    {
    'name': 'tenant99',
    'activityStatus': 'COLD',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_tenants.test_tenants_create_and_update_1001_tenants')
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
    test = TestTenantstestTenantsCreateAndUpdate1001Tenants()
    test.run_tests()
