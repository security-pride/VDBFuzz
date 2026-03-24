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

# 导入变异模块
try:
    from vdbfuzz.mutator import Mutator
except ImportError:
    try:
        # 尝试相对导入
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from vdbfuzz.mutator import Mutator
    except ImportError:
        # 尝试从当前目录的父目录导入
        vdbfuzz_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'vdbfuzz')
        if os.path.exists(vdbfuzz_path):
            sys.path.append(os.path.dirname(vdbfuzz_path))
            from vdbfuzz.mutator import Mutator
        else:
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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestSearchVector_test_search_vector_with_sparse_float_vector_datatype[coo-user_id-128-3000-True-False-True-10]_1752747798_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestSearchVector_test_search_vector_with_sparse_float_vector_datatype[coo-user_id-128-3000-True-False-True-10]_1752747798.json"
VDB_TYPE = "milvus"


def send_request(content, request_type="POST", url_path="http://172.17.0.5:23210/v2/vectordb/collections/create", custom_headers=None):
    """
    发送请求到目标服务器

    Args:
        content: 请求内容
        request_type: 请求方法，默认为"POST"
        url_path: URL路径，默认为"http://172.17.0.5:23210/v2/vectordb/collections/create"
        custom_headers: 自定义请求头，如果提供则会合并到默认headers
        
    Returns:
        requests.Response: 响应对象
    """
    if not TARGET_URL:
        raise ValueError("目标URL未设置，请使用 -t 参数指定目标服务器URL")
    
    # 检查url_path是否已经是完整URL
    if url_path.startswith(('http://', 'https://')):
        from urllib.parse import urlsplit

        parsed = urlsplit(url_path)
        path = parsed.path or '/'
        if parsed.query:
            path = f"{path}?{parsed.query}"
        url = TARGET_URL.rstrip('/') + path
    else:
        url = TARGET_URL.rstrip('/') + url_path
    
    # 基础请求头
    headers = {
        'Content-Type': 'application/json',
    }

    # 合并自定义请求头
    if custom_headers:
        headers.update(custom_headers)

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
        return response.status_code in [200, 404, 503]
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



class AllmilvusLogtestsearchvectorTestSearchVectorWithSparseFloatVectorDatatypeCooUserId1283000TrueFalseTrue101752747798Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestSearchVector_test_search_vector_with_sparse_float_vector_datatype[coo-user_id-128-3000-True-False-True-10]_1752747798.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestSearchVector_test_search_vector_with_sparse_float_vector_datatype[coo-user_id-128-3000-True-False-True-10]_1752747798.json"
        self.test_count = 5  # 测试方法数量
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
        """测试请求 0 - POST http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: POST http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '0a4e6770-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_23_11_285545jXYpvQFT',
    'schema': {
    'autoId': True,
    'enableDynamicField': True,
    'fields': [
    {
    'fieldName': 'book_id',
    'dataType': 'Int64',
    'isPrimary': True,
    'elementTypeParams': {
},
},
    {
    'fieldName': 'user_id',
    'dataType': 'Int64',
    'isPartitionKey': False,
    'elementTypeParams': {
},
},
    {
    'fieldName': 'word_count',
    'dataType': 'Int64',
    'elementTypeParams': {
},
},
    {
    'fieldName': 'book_describe',
    'dataType': 'VarChar',
    'elementTypeParams': {
    'max_length': '256',
},
},
    {
    'fieldName': 'sparse_float_vector',
    'dataType': 'SparseFloatVector',
},
],
},
    'indexParams': [
    {
    'fieldName': 'sparse_float_vector',
    'indexName': 'sparse_float_vector',
    'metricType': 'IP',
    'params': {
    'index_type': 'SPARSE_INVERTED_INDEX',
    'drop_ratio_build': '0.2',
},
},
],
    'params': {
    'consistencyLevel': 'Strong',
},
}


        send_request(original_content, method, url_path, headers)
        return True



    def test_request_1(self):
        """测试请求 1 - POST http://172.17.0.5:23210/v2/vectordb/collections/describe"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/collections/describe")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/describe'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '0a4e6770-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_23_11_285545jXYpvQFT',
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
        """测试请求 2 - POST http://172.17.0.5:23210/v2/vectordb/entities/insert"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/insert")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/insert'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '0a4e6770-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_23_11_285545jXYpvQFT',
    'data': [
    {
    'user_id': 0,
    'word_count': 0,
    'book_describe': 'book_0',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 1,
    'book_describe': 'book_1',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 2,
    'book_describe': 'book_2',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 3,
    'book_describe': 'book_3',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 4,
    'book_describe': 'book_4',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 5,
    'book_describe': 'book_5',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 6,
    'book_describe': 'book_6',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 7,
    'book_describe': 'book_7',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 8,
    'book_describe': 'book_8',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 9,
    'book_describe': 'book_9',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 10,
    'book_describe': 'book_10',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 11,
    'book_describe': 'book_11',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 12,
    'book_describe': 'book_12',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 13,
    'book_describe': 'book_13',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 14,
    'book_describe': 'book_14',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 15,
    'book_describe': 'book_15',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 16,
    'book_describe': 'book_16',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 17,
    'book_describe': 'book_17',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 18,
    'book_describe': 'book_18',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 19,
    'book_describe': 'book_19',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 20,
    'book_describe': 'book_20',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 21,
    'book_describe': 'book_21',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 22,
    'book_describe': 'book_22',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 23,
    'book_describe': 'book_23',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 24,
    'book_describe': 'book_24',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 25,
    'book_describe': 'book_25',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 26,
    'book_describe': 'book_26',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 27,
    'book_describe': 'book_27',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 28,
    'book_describe': 'book_28',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 29,
    'book_describe': 'book_29',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 30,
    'book_describe': 'book_30',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 31,
    'book_describe': 'book_31',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 32,
    'book_describe': 'book_32',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 33,
    'book_describe': 'book_33',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 34,
    'book_describe': 'book_34',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 35,
    'book_describe': 'book_35',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 36,
    'book_describe': 'book_36',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 37,
    'book_describe': 'book_37',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 38,
    'book_describe': 'book_38',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 39,
    'book_describe': 'book_39',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 40,
    'book_describe': 'book_40',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 41,
    'book_describe': 'book_41',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 42,
    'book_describe': 'book_42',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 43,
    'book_describe': 'book_43',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 44,
    'book_describe': 'book_44',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 45,
    'book_describe': 'book_45',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 46,
    'book_describe': 'book_46',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 47,
    'book_describe': 'book_47',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 48,
    'book_describe': 'book_48',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 49,
    'book_describe': 'book_49',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 50,
    'book_describe': 'book_50',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 51,
    'book_describe': 'book_51',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 52,
    'book_describe': 'book_52',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 53,
    'book_describe': 'book_53',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 54,
    'book_describe': 'book_54',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 55,
    'book_describe': 'book_55',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 56,
    'book_describe': 'book_56',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 57,
    'book_describe': 'book_57',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 58,
    'book_describe': 'book_58',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 59,
    'book_describe': 'book_59',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 60,
    'book_describe': 'book_60',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 61,
    'book_describe': 'book_61',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 62,
    'book_describe': 'book_62',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 63,
    'book_describe': 'book_63',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 64,
    'book_describe': 'book_64',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 65,
    'book_describe': 'book_65',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 66,
    'book_describe': 'book_66',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 67,
    'book_describe': 'book_67',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 68,
    'book_describe': 'book_68',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 69,
    'book_describe': 'book_69',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 70,
    'book_describe': 'book_70',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 71,
    'book_describe': 'book_71',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 72,
    'book_describe': 'book_72',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 73,
    'book_describe': 'book_73',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 74,
    'book_describe': 'book_74',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 75,
    'book_describe': 'book_75',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 76,
    'book_describe': 'book_76',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 77,
    'book_describe': 'book_77',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 78,
    'book_describe': 'book_78',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 79,
    'book_describe': 'book_79',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 80,
    'book_describe': 'book_80',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 81,
    'book_describe': 'book_81',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 82,
    'book_describe': 'book_82',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 83,
    'book_describe': 'book_83',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 84,
    'book_describe': 'book_84',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 85,
    'book_describe': 'book_85',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 86,
    'book_describe': 'book_86',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 87,
    'book_describe': 'book_87',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 88,
    'book_describe': 'book_88',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 89,
    'book_describe': 'book_89',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 90,
    'book_describe': 'book_90',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 91,
    'book_describe': 'book_91',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 92,
    'book_describe': 'book_92',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 93,
    'book_describe': 'book_93',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 94,
    'book_describe': 'book_94',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 95,
    'book_describe': 'book_95',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 96,
    'book_describe': 'book_96',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 97,
    'book_describe': 'book_97',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 98,
    'book_describe': 'book_98',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 99,
    'book_describe': 'book_99',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 100,
    'book_describe': 'book_100',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 101,
    'book_describe': 'book_101',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 102,
    'book_describe': 'book_102',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 103,
    'book_describe': 'book_103',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 104,
    'book_describe': 'book_104',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 105,
    'book_describe': 'book_105',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 106,
    'book_describe': 'book_106',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 107,
    'book_describe': 'book_107',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 108,
    'book_describe': 'book_108',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 109,
    'book_describe': 'book_109',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 110,
    'book_describe': 'book_110',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 111,
    'book_describe': 'book_111',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 112,
    'book_describe': 'book_112',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 113,
    'book_describe': 'book_113',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 114,
    'book_describe': 'book_114',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 115,
    'book_describe': 'book_115',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 116,
    'book_describe': 'book_116',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 117,
    'book_describe': 'book_117',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 118,
    'book_describe': 'book_118',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 119,
    'book_describe': 'book_119',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 120,
    'book_describe': 'book_120',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 121,
    'book_describe': 'book_121',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 122,
    'book_describe': 'book_122',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 123,
    'book_describe': 'book_123',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 124,
    'book_describe': 'book_124',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 125,
    'book_describe': 'book_125',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 126,
    'book_describe': 'book_126',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 127,
    'book_describe': 'book_127',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 128,
    'book_describe': 'book_128',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 129,
    'book_describe': 'book_129',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 130,
    'book_describe': 'book_130',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 131,
    'book_describe': 'book_131',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 132,
    'book_describe': 'book_132',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 133,
    'book_describe': 'book_133',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 134,
    'book_describe': 'book_134',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 135,
    'book_describe': 'book_135',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 136,
    'book_describe': 'book_136',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 137,
    'book_describe': 'book_137',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 138,
    'book_describe': 'book_138',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 139,
    'book_describe': 'book_139',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 140,
    'book_describe': 'book_140',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 141,
    'book_describe': 'book_141',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 142,
    'book_describe': 'book_142',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 143,
    'book_describe': 'book_143',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 144,
    'book_describe': 'book_144',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 145,
    'book_describe': 'book_145',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 146,
    'book_describe': 'book_146',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 147,
    'book_describe': 'book_147',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 148,
    'book_describe': 'book_148',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 149,
    'book_describe': 'book_149',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 150,
    'book_describe': 'book_150',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 151,
    'book_describe': 'book_151',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 152,
    'book_describe': 'book_152',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 153,
    'book_describe': 'book_153',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 154,
    'book_describe': 'book_154',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 155,
    'book_describe': 'book_155',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 156,
    'book_describe': 'book_156',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 157,
    'book_describe': 'book_157',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 158,
    'book_describe': 'book_158',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 159,
    'book_describe': 'book_159',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 160,
    'book_describe': 'book_160',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 161,
    'book_describe': 'book_161',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 162,
    'book_describe': 'book_162',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 163,
    'book_describe': 'book_163',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 164,
    'book_describe': 'book_164',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 165,
    'book_describe': 'book_165',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 166,
    'book_describe': 'book_166',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 167,
    'book_describe': 'book_167',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 168,
    'book_describe': 'book_168',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 169,
    'book_describe': 'book_169',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 170,
    'book_describe': 'book_170',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 171,
    'book_describe': 'book_171',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 172,
    'book_describe': 'book_172',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 173,
    'book_describe': 'book_173',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 174,
    'book_describe': 'book_174',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 175,
    'book_describe': 'book_175',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 176,
    'book_describe': 'book_176',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 177,
    'book_describe': 'book_177',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 178,
    'book_describe': 'book_178',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 179,
    'book_describe': 'book_179',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 180,
    'book_describe': 'book_180',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 181,
    'book_describe': 'book_181',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 182,
    'book_describe': 'book_182',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 183,
    'book_describe': 'book_183',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 184,
    'book_describe': 'book_184',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 185,
    'book_describe': 'book_185',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 186,
    'book_describe': 'book_186',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 187,
    'book_describe': 'book_187',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 188,
    'book_describe': 'book_188',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 189,
    'book_describe': 'book_189',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 190,
    'book_describe': 'book_190',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 191,
    'book_describe': 'book_191',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 192,
    'book_describe': 'book_192',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 193,
    'book_describe': 'book_193',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 194,
    'book_describe': 'book_194',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 195,
    'book_describe': 'book_195',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 196,
    'book_describe': 'book_196',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 197,
    'book_describe': 'book_197',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 198,
    'book_describe': 'book_198',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 199,
    'book_describe': 'book_199',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 200,
    'book_describe': 'book_200',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 201,
    'book_describe': 'book_201',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 202,
    'book_describe': 'book_202',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 203,
    'book_describe': 'book_203',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 204,
    'book_describe': 'book_204',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 205,
    'book_describe': 'book_205',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 206,
    'book_describe': 'book_206',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 207,
    'book_describe': 'book_207',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 208,
    'book_describe': 'book_208',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 209,
    'book_describe': 'book_209',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 210,
    'book_describe': 'book_210',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 211,
    'book_describe': 'book_211',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 212,
    'book_describe': 'book_212',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 213,
    'book_describe': 'book_213',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 214,
    'book_describe': 'book_214',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 215,
    'book_describe': 'book_215',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 216,
    'book_describe': 'book_216',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 217,
    'book_describe': 'book_217',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 218,
    'book_describe': 'book_218',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 219,
    'book_describe': 'book_219',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 220,
    'book_describe': 'book_220',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 221,
    'book_describe': 'book_221',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 222,
    'book_describe': 'book_222',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 223,
    'book_describe': 'book_223',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 224,
    'book_describe': 'book_224',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 225,
    'book_describe': 'book_225',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 226,
    'book_describe': 'book_226',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 227,
    'book_describe': 'book_227',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 228,
    'book_describe': 'book_228',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 229,
    'book_describe': 'book_229',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 230,
    'book_describe': 'book_230',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 231,
    'book_describe': 'book_231',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 232,
    'book_describe': 'book_232',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 233,
    'book_describe': 'book_233',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 234,
    'book_describe': 'book_234',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 235,
    'book_describe': 'book_235',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 236,
    'book_describe': 'book_236',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 237,
    'book_describe': 'book_237',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 238,
    'book_describe': 'book_238',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 239,
    'book_describe': 'book_239',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 240,
    'book_describe': 'book_240',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 241,
    'book_describe': 'book_241',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 242,
    'book_describe': 'book_242',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 243,
    'book_describe': 'book_243',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 244,
    'book_describe': 'book_244',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 245,
    'book_describe': 'book_245',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 246,
    'book_describe': 'book_246',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 247,
    'book_describe': 'book_247',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 248,
    'book_describe': 'book_248',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 249,
    'book_describe': 'book_249',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 250,
    'book_describe': 'book_250',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 251,
    'book_describe': 'book_251',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 252,
    'book_describe': 'book_252',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 253,
    'book_describe': 'book_253',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 254,
    'book_describe': 'book_254',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 255,
    'book_describe': 'book_255',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 256,
    'book_describe': 'book_256',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 257,
    'book_describe': 'book_257',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 258,
    'book_describe': 'book_258',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 259,
    'book_describe': 'book_259',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 260,
    'book_describe': 'book_260',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 261,
    'book_describe': 'book_261',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 262,
    'book_describe': 'book_262',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 263,
    'book_describe': 'book_263',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 264,
    'book_describe': 'book_264',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 265,
    'book_describe': 'book_265',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 266,
    'book_describe': 'book_266',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 267,
    'book_describe': 'book_267',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 268,
    'book_describe': 'book_268',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 269,
    'book_describe': 'book_269',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 270,
    'book_describe': 'book_270',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 271,
    'book_describe': 'book_271',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 272,
    'book_describe': 'book_272',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 273,
    'book_describe': 'book_273',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 274,
    'book_describe': 'book_274',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 275,
    'book_describe': 'book_275',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 276,
    'book_describe': 'book_276',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 277,
    'book_describe': 'book_277',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 278,
    'book_describe': 'book_278',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 279,
    'book_describe': 'book_279',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 280,
    'book_describe': 'book_280',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 281,
    'book_describe': 'book_281',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 282,
    'book_describe': 'book_282',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 283,
    'book_describe': 'book_283',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 284,
    'book_describe': 'book_284',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 285,
    'book_describe': 'book_285',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 286,
    'book_describe': 'book_286',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 287,
    'book_describe': 'book_287',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 288,
    'book_describe': 'book_288',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 289,
    'book_describe': 'book_289',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 290,
    'book_describe': 'book_290',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 291,
    'book_describe': 'book_291',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 292,
    'book_describe': 'book_292',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 293,
    'book_describe': 'book_293',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 294,
    'book_describe': 'book_294',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 295,
    'book_describe': 'book_295',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 296,
    'book_describe': 'book_296',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 297,
    'book_describe': 'book_297',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 298,
    'book_describe': 'book_298',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 299,
    'book_describe': 'book_299',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 300,
    'book_describe': 'book_300',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 301,
    'book_describe': 'book_301',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 302,
    'book_describe': 'book_302',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 303,
    'book_describe': 'book_303',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 304,
    'book_describe': 'book_304',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 305,
    'book_describe': 'book_305',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 306,
    'book_describe': 'book_306',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 307,
    'book_describe': 'book_307',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 308,
    'book_describe': 'book_308',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 309,
    'book_describe': 'book_309',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 310,
    'book_describe': 'book_310',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 311,
    'book_describe': 'book_311',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 312,
    'book_describe': 'book_312',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 313,
    'book_describe': 'book_313',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 314,
    'book_describe': 'book_314',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 315,
    'book_describe': 'book_315',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 316,
    'book_describe': 'book_316',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 317,
    'book_describe': 'book_317',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 318,
    'book_describe': 'book_318',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 319,
    'book_describe': 'book_319',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 320,
    'book_describe': 'book_320',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 321,
    'book_describe': 'book_321',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 322,
    'book_describe': 'book_322',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 323,
    'book_describe': 'book_323',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 324,
    'book_describe': 'book_324',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 325,
    'book_describe': 'book_325',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 326,
    'book_describe': 'book_326',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 327,
    'book_describe': 'book_327',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 328,
    'book_describe': 'book_328',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 329,
    'book_describe': 'book_329',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 330,
    'book_describe': 'book_330',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 331,
    'book_describe': 'book_331',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 332,
    'book_describe': 'book_332',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 333,
    'book_describe': 'book_333',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 334,
    'book_describe': 'book_334',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 335,
    'book_describe': 'book_335',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 336,
    'book_describe': 'book_336',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 337,
    'book_describe': 'book_337',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 338,
    'book_describe': 'book_338',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 339,
    'book_describe': 'book_339',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 340,
    'book_describe': 'book_340',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 341,
    'book_describe': 'book_341',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 342,
    'book_describe': 'book_342',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 343,
    'book_describe': 'book_343',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 344,
    'book_describe': 'book_344',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 345,
    'book_describe': 'book_345',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 346,
    'book_describe': 'book_346',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 347,
    'book_describe': 'book_347',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 348,
    'book_describe': 'book_348',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 349,
    'book_describe': 'book_349',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 350,
    'book_describe': 'book_350',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 351,
    'book_describe': 'book_351',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 352,
    'book_describe': 'book_352',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 353,
    'book_describe': 'book_353',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 354,
    'book_describe': 'book_354',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 355,
    'book_describe': 'book_355',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 356,
    'book_describe': 'book_356',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 357,
    'book_describe': 'book_357',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 358,
    'book_describe': 'book_358',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 359,
    'book_describe': 'book_359',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 360,
    'book_describe': 'book_360',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 361,
    'book_describe': 'book_361',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 362,
    'book_describe': 'book_362',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 363,
    'book_describe': 'book_363',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 364,
    'book_describe': 'book_364',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 365,
    'book_describe': 'book_365',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 366,
    'book_describe': 'book_366',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 367,
    'book_describe': 'book_367',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 368,
    'book_describe': 'book_368',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 369,
    'book_describe': 'book_369',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 370,
    'book_describe': 'book_370',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 371,
    'book_describe': 'book_371',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 372,
    'book_describe': 'book_372',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 373,
    'book_describe': 'book_373',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 374,
    'book_describe': 'book_374',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 375,
    'book_describe': 'book_375',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 376,
    'book_describe': 'book_376',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 377,
    'book_describe': 'book_377',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 378,
    'book_describe': 'book_378',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 379,
    'book_describe': 'book_379',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 380,
    'book_describe': 'book_380',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 381,
    'book_describe': 'book_381',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 382,
    'book_describe': 'book_382',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 383,
    'book_describe': 'book_383',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 384,
    'book_describe': 'book_384',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 385,
    'book_describe': 'book_385',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 386,
    'book_describe': 'book_386',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 387,
    'book_describe': 'book_387',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 388,
    'book_describe': 'book_388',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 389,
    'book_describe': 'book_389',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 390,
    'book_describe': 'book_390',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 391,
    'book_describe': 'book_391',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 392,
    'book_describe': 'book_392',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 393,
    'book_describe': 'book_393',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 394,
    'book_describe': 'book_394',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 395,
    'book_describe': 'book_395',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 396,
    'book_describe': 'book_396',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 397,
    'book_describe': 'book_397',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 398,
    'book_describe': 'book_398',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 399,
    'book_describe': 'book_399',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 400,
    'book_describe': 'book_400',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 401,
    'book_describe': 'book_401',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 402,
    'book_describe': 'book_402',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 403,
    'book_describe': 'book_403',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 404,
    'book_describe': 'book_404',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 405,
    'book_describe': 'book_405',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 406,
    'book_describe': 'book_406',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 407,
    'book_describe': 'book_407',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 408,
    'book_describe': 'book_408',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 409,
    'book_describe': 'book_409',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 410,
    'book_describe': 'book_410',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 411,
    'book_describe': 'book_411',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 412,
    'book_describe': 'book_412',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 413,
    'book_describe': 'book_413',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 414,
    'book_describe': 'book_414',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 415,
    'book_describe': 'book_415',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 416,
    'book_describe': 'book_416',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 417,
    'book_describe': 'book_417',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 418,
    'book_describe': 'book_418',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 419,
    'book_describe': 'book_419',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 420,
    'book_describe': 'book_420',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 421,
    'book_describe': 'book_421',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 422,
    'book_describe': 'book_422',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 423,
    'book_describe': 'book_423',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 424,
    'book_describe': 'book_424',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 425,
    'book_describe': 'book_425',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 426,
    'book_describe': 'book_426',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 427,
    'book_describe': 'book_427',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 428,
    'book_describe': 'book_428',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 429,
    'book_describe': 'book_429',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 430,
    'book_describe': 'book_430',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 431,
    'book_describe': 'book_431',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 432,
    'book_describe': 'book_432',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 433,
    'book_describe': 'book_433',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 434,
    'book_describe': 'book_434',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 435,
    'book_describe': 'book_435',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 436,
    'book_describe': 'book_436',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 437,
    'book_describe': 'book_437',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 438,
    'book_describe': 'book_438',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 439,
    'book_describe': 'book_439',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 440,
    'book_describe': 'book_440',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 441,
    'book_describe': 'book_441',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 442,
    'book_describe': 'book_442',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 443,
    'book_describe': 'book_443',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 444,
    'book_describe': 'book_444',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 445,
    'book_describe': 'book_445',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 446,
    'book_describe': 'book_446',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 447,
    'book_describe': 'book_447',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 448,
    'book_describe': 'book_448',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 449,
    'book_describe': 'book_449',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 450,
    'book_describe': 'book_450',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 451,
    'book_describe': 'book_451',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 452,
    'book_describe': 'book_452',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 453,
    'book_describe': 'book_453',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 454,
    'book_describe': 'book_454',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 455,
    'book_describe': 'book_455',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 456,
    'book_describe': 'book_456',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 457,
    'book_describe': 'book_457',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 458,
    'book_describe': 'book_458',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 459,
    'book_describe': 'book_459',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 460,
    'book_describe': 'book_460',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 461,
    'book_describe': 'book_461',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 462,
    'book_describe': 'book_462',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 463,
    'book_describe': 'book_463',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 464,
    'book_describe': 'book_464',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 465,
    'book_describe': 'book_465',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 466,
    'book_describe': 'book_466',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 467,
    'book_describe': 'book_467',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 468,
    'book_describe': 'book_468',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 469,
    'book_describe': 'book_469',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 470,
    'book_describe': 'book_470',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 471,
    'book_describe': 'book_471',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 472,
    'book_describe': 'book_472',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 473,
    'book_describe': 'book_473',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 474,
    'book_describe': 'book_474',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 475,
    'book_describe': 'book_475',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 476,
    'book_describe': 'book_476',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 477,
    'book_describe': 'book_477',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 478,
    'book_describe': 'book_478',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 479,
    'book_describe': 'book_479',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 480,
    'book_describe': 'book_480',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 481,
    'book_describe': 'book_481',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 482,
    'book_describe': 'book_482',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 483,
    'book_describe': 'book_483',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 484,
    'book_describe': 'book_484',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 485,
    'book_describe': 'book_485',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 486,
    'book_describe': 'book_486',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 487,
    'book_describe': 'book_487',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 488,
    'book_describe': 'book_488',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 489,
    'book_describe': 'book_489',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 490,
    'book_describe': 'book_490',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 491,
    'book_describe': 'book_491',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 492,
    'book_describe': 'book_492',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 493,
    'book_describe': 'book_493',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 494,
    'book_describe': 'book_494',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 495,
    'book_describe': 'book_495',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 496,
    'book_describe': 'book_496',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 497,
    'book_describe': 'book_497',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 498,
    'book_describe': 'book_498',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 499,
    'book_describe': 'book_499',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 500,
    'book_describe': 'book_500',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 501,
    'book_describe': 'book_501',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 502,
    'book_describe': 'book_502',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 503,
    'book_describe': 'book_503',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 504,
    'book_describe': 'book_504',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 505,
    'book_describe': 'book_505',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 506,
    'book_describe': 'book_506',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 507,
    'book_describe': 'book_507',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 508,
    'book_describe': 'book_508',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 509,
    'book_describe': 'book_509',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 510,
    'book_describe': 'book_510',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 511,
    'book_describe': 'book_511',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 512,
    'book_describe': 'book_512',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 513,
    'book_describe': 'book_513',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 514,
    'book_describe': 'book_514',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 515,
    'book_describe': 'book_515',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 516,
    'book_describe': 'book_516',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 517,
    'book_describe': 'book_517',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 518,
    'book_describe': 'book_518',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 519,
    'book_describe': 'book_519',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 520,
    'book_describe': 'book_520',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 521,
    'book_describe': 'book_521',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 522,
    'book_describe': 'book_522',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 523,
    'book_describe': 'book_523',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 524,
    'book_describe': 'book_524',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 525,
    'book_describe': 'book_525',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 526,
    'book_describe': 'book_526',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 527,
    'book_describe': 'book_527',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 528,
    'book_describe': 'book_528',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 529,
    'book_describe': 'book_529',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 530,
    'book_describe': 'book_530',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 531,
    'book_describe': 'book_531',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 532,
    'book_describe': 'book_532',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 533,
    'book_describe': 'book_533',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 534,
    'book_describe': 'book_534',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 535,
    'book_describe': 'book_535',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 536,
    'book_describe': 'book_536',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 537,
    'book_describe': 'book_537',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 538,
    'book_describe': 'book_538',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 539,
    'book_describe': 'book_539',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 540,
    'book_describe': 'book_540',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 541,
    'book_describe': 'book_541',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 542,
    'book_describe': 'book_542',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 543,
    'book_describe': 'book_543',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 544,
    'book_describe': 'book_544',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 545,
    'book_describe': 'book_545',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 546,
    'book_describe': 'book_546',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 547,
    'book_describe': 'book_547',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 548,
    'book_describe': 'book_548',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 549,
    'book_describe': 'book_549',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 550,
    'book_describe': 'book_550',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 551,
    'book_describe': 'book_551',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 552,
    'book_describe': 'book_552',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 553,
    'book_describe': 'book_553',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 554,
    'book_describe': 'book_554',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 555,
    'book_describe': 'book_555',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 556,
    'book_describe': 'book_556',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 557,
    'book_describe': 'book_557',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 558,
    'book_describe': 'book_558',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 559,
    'book_describe': 'book_559',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 560,
    'book_describe': 'book_560',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 561,
    'book_describe': 'book_561',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 562,
    'book_describe': 'book_562',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 563,
    'book_describe': 'book_563',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 564,
    'book_describe': 'book_564',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 565,
    'book_describe': 'book_565',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 566,
    'book_describe': 'book_566',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 567,
    'book_describe': 'book_567',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 568,
    'book_describe': 'book_568',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 569,
    'book_describe': 'book_569',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 570,
    'book_describe': 'book_570',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 571,
    'book_describe': 'book_571',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 572,
    'book_describe': 'book_572',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 573,
    'book_describe': 'book_573',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 574,
    'book_describe': 'book_574',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 575,
    'book_describe': 'book_575',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 576,
    'book_describe': 'book_576',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 577,
    'book_describe': 'book_577',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 578,
    'book_describe': 'book_578',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 579,
    'book_describe': 'book_579',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 580,
    'book_describe': 'book_580',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 581,
    'book_describe': 'book_581',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 582,
    'book_describe': 'book_582',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 583,
    'book_describe': 'book_583',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 584,
    'book_describe': 'book_584',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 585,
    'book_describe': 'book_585',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 586,
    'book_describe': 'book_586',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 587,
    'book_describe': 'book_587',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 588,
    'book_describe': 'book_588',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 589,
    'book_describe': 'book_589',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 590,
    'book_describe': 'book_590',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 591,
    'book_describe': 'book_591',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 592,
    'book_describe': 'book_592',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 593,
    'book_describe': 'book_593',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 594,
    'book_describe': 'book_594',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 595,
    'book_describe': 'book_595',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 596,
    'book_describe': 'book_596',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 597,
    'book_describe': 'book_597',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 598,
    'book_describe': 'book_598',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 599,
    'book_describe': 'book_599',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 600,
    'book_describe': 'book_600',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 601,
    'book_describe': 'book_601',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 602,
    'book_describe': 'book_602',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 603,
    'book_describe': 'book_603',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 604,
    'book_describe': 'book_604',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 605,
    'book_describe': 'book_605',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 606,
    'book_describe': 'book_606',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 607,
    'book_describe': 'book_607',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 608,
    'book_describe': 'book_608',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 609,
    'book_describe': 'book_609',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 610,
    'book_describe': 'book_610',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 611,
    'book_describe': 'book_611',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 612,
    'book_describe': 'book_612',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 613,
    'book_describe': 'book_613',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 614,
    'book_describe': 'book_614',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 615,
    'book_describe': 'book_615',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 616,
    'book_describe': 'book_616',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 617,
    'book_describe': 'book_617',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 618,
    'book_describe': 'book_618',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 619,
    'book_describe': 'book_619',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 620,
    'book_describe': 'book_620',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 621,
    'book_describe': 'book_621',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 622,
    'book_describe': 'book_622',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 623,
    'book_describe': 'book_623',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 624,
    'book_describe': 'book_624',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 625,
    'book_describe': 'book_625',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 626,
    'book_describe': 'book_626',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 627,
    'book_describe': 'book_627',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 628,
    'book_describe': 'book_628',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 629,
    'book_describe': 'book_629',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 630,
    'book_describe': 'book_630',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 631,
    'book_describe': 'book_631',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 632,
    'book_describe': 'book_632',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 633,
    'book_describe': 'book_633',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 634,
    'book_describe': 'book_634',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 635,
    'book_describe': 'book_635',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 636,
    'book_describe': 'book_636',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 637,
    'book_describe': 'book_637',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 638,
    'book_describe': 'book_638',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 639,
    'book_describe': 'book_639',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 640,
    'book_describe': 'book_640',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 641,
    'book_describe': 'book_641',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 642,
    'book_describe': 'book_642',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 643,
    'book_describe': 'book_643',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 644,
    'book_describe': 'book_644',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 645,
    'book_describe': 'book_645',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 646,
    'book_describe': 'book_646',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 647,
    'book_describe': 'book_647',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 648,
    'book_describe': 'book_648',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 649,
    'book_describe': 'book_649',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 650,
    'book_describe': 'book_650',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 651,
    'book_describe': 'book_651',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 652,
    'book_describe': 'book_652',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 653,
    'book_describe': 'book_653',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 654,
    'book_describe': 'book_654',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 655,
    'book_describe': 'book_655',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 656,
    'book_describe': 'book_656',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 657,
    'book_describe': 'book_657',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 658,
    'book_describe': 'book_658',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 659,
    'book_describe': 'book_659',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 660,
    'book_describe': 'book_660',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 661,
    'book_describe': 'book_661',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 662,
    'book_describe': 'book_662',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 663,
    'book_describe': 'book_663',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 664,
    'book_describe': 'book_664',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 665,
    'book_describe': 'book_665',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 666,
    'book_describe': 'book_666',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 667,
    'book_describe': 'book_667',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 668,
    'book_describe': 'book_668',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 669,
    'book_describe': 'book_669',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 670,
    'book_describe': 'book_670',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 671,
    'book_describe': 'book_671',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 672,
    'book_describe': 'book_672',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 673,
    'book_describe': 'book_673',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 674,
    'book_describe': 'book_674',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 675,
    'book_describe': 'book_675',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 676,
    'book_describe': 'book_676',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 677,
    'book_describe': 'book_677',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 678,
    'book_describe': 'book_678',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 679,
    'book_describe': 'book_679',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 680,
    'book_describe': 'book_680',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 681,
    'book_describe': 'book_681',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 682,
    'book_describe': 'book_682',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 683,
    'book_describe': 'book_683',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 684,
    'book_describe': 'book_684',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 685,
    'book_describe': 'book_685',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 686,
    'book_describe': 'book_686',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 687,
    'book_describe': 'book_687',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 688,
    'book_describe': 'book_688',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 689,
    'book_describe': 'book_689',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 690,
    'book_describe': 'book_690',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 691,
    'book_describe': 'book_691',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 692,
    'book_describe': 'book_692',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 693,
    'book_describe': 'book_693',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 694,
    'book_describe': 'book_694',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 695,
    'book_describe': 'book_695',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 696,
    'book_describe': 'book_696',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 697,
    'book_describe': 'book_697',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 698,
    'book_describe': 'book_698',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 699,
    'book_describe': 'book_699',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 700,
    'book_describe': 'book_700',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 701,
    'book_describe': 'book_701',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 702,
    'book_describe': 'book_702',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 703,
    'book_describe': 'book_703',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 704,
    'book_describe': 'book_704',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 705,
    'book_describe': 'book_705',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 706,
    'book_describe': 'book_706',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 707,
    'book_describe': 'book_707',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 708,
    'book_describe': 'book_708',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 709,
    'book_describe': 'book_709',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 710,
    'book_describe': 'book_710',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 711,
    'book_describe': 'book_711',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 712,
    'book_describe': 'book_712',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 713,
    'book_describe': 'book_713',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 714,
    'book_describe': 'book_714',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 715,
    'book_describe': 'book_715',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 716,
    'book_describe': 'book_716',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 717,
    'book_describe': 'book_717',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 718,
    'book_describe': 'book_718',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 719,
    'book_describe': 'book_719',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 720,
    'book_describe': 'book_720',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 721,
    'book_describe': 'book_721',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 722,
    'book_describe': 'book_722',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 723,
    'book_describe': 'book_723',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 724,
    'book_describe': 'book_724',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 725,
    'book_describe': 'book_725',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 726,
    'book_describe': 'book_726',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 727,
    'book_describe': 'book_727',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 728,
    'book_describe': 'book_728',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 729,
    'book_describe': 'book_729',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 730,
    'book_describe': 'book_730',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 731,
    'book_describe': 'book_731',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 732,
    'book_describe': 'book_732',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 733,
    'book_describe': 'book_733',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 734,
    'book_describe': 'book_734',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 735,
    'book_describe': 'book_735',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 736,
    'book_describe': 'book_736',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 737,
    'book_describe': 'book_737',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 738,
    'book_describe': 'book_738',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 739,
    'book_describe': 'book_739',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 740,
    'book_describe': 'book_740',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 741,
    'book_describe': 'book_741',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 742,
    'book_describe': 'book_742',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 743,
    'book_describe': 'book_743',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 744,
    'book_describe': 'book_744',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 745,
    'book_describe': 'book_745',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 746,
    'book_describe': 'book_746',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 747,
    'book_describe': 'book_747',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 748,
    'book_describe': 'book_748',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 749,
    'book_describe': 'book_749',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 750,
    'book_describe': 'book_750',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 751,
    'book_describe': 'book_751',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 752,
    'book_describe': 'book_752',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 753,
    'book_describe': 'book_753',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 754,
    'book_describe': 'book_754',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 755,
    'book_describe': 'book_755',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 756,
    'book_describe': 'book_756',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 757,
    'book_describe': 'book_757',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 758,
    'book_describe': 'book_758',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 759,
    'book_describe': 'book_759',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 760,
    'book_describe': 'book_760',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 761,
    'book_describe': 'book_761',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 762,
    'book_describe': 'book_762',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 763,
    'book_describe': 'book_763',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 764,
    'book_describe': 'book_764',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 765,
    'book_describe': 'book_765',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 766,
    'book_describe': 'book_766',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 767,
    'book_describe': 'book_767',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 768,
    'book_describe': 'book_768',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 769,
    'book_describe': 'book_769',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 770,
    'book_describe': 'book_770',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 771,
    'book_describe': 'book_771',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 772,
    'book_describe': 'book_772',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 773,
    'book_describe': 'book_773',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 774,
    'book_describe': 'book_774',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 775,
    'book_describe': 'book_775',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 776,
    'book_describe': 'book_776',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 777,
    'book_describe': 'book_777',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 778,
    'book_describe': 'book_778',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 779,
    'book_describe': 'book_779',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 780,
    'book_describe': 'book_780',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 781,
    'book_describe': 'book_781',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 782,
    'book_describe': 'book_782',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 783,
    'book_describe': 'book_783',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 784,
    'book_describe': 'book_784',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 785,
    'book_describe': 'book_785',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 786,
    'book_describe': 'book_786',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 787,
    'book_describe': 'book_787',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 788,
    'book_describe': 'book_788',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 789,
    'book_describe': 'book_789',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 790,
    'book_describe': 'book_790',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 791,
    'book_describe': 'book_791',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 792,
    'book_describe': 'book_792',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 793,
    'book_describe': 'book_793',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 794,
    'book_describe': 'book_794',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 795,
    'book_describe': 'book_795',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 796,
    'book_describe': 'book_796',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 797,
    'book_describe': 'book_797',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 798,
    'book_describe': 'book_798',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 799,
    'book_describe': 'book_799',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 800,
    'book_describe': 'book_800',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 801,
    'book_describe': 'book_801',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 802,
    'book_describe': 'book_802',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 803,
    'book_describe': 'book_803',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 804,
    'book_describe': 'book_804',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 805,
    'book_describe': 'book_805',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 806,
    'book_describe': 'book_806',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 807,
    'book_describe': 'book_807',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 808,
    'book_describe': 'book_808',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 809,
    'book_describe': 'book_809',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 810,
    'book_describe': 'book_810',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 811,
    'book_describe': 'book_811',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 812,
    'book_describe': 'book_812',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 813,
    'book_describe': 'book_813',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 814,
    'book_describe': 'book_814',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 815,
    'book_describe': 'book_815',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 816,
    'book_describe': 'book_816',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 817,
    'book_describe': 'book_817',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 818,
    'book_describe': 'book_818',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 819,
    'book_describe': 'book_819',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 820,
    'book_describe': 'book_820',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 821,
    'book_describe': 'book_821',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 822,
    'book_describe': 'book_822',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 823,
    'book_describe': 'book_823',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 824,
    'book_describe': 'book_824',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 825,
    'book_describe': 'book_825',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 826,
    'book_describe': 'book_826',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 827,
    'book_describe': 'book_827',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 828,
    'book_describe': 'book_828',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 829,
    'book_describe': 'book_829',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 830,
    'book_describe': 'book_830',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 831,
    'book_describe': 'book_831',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 832,
    'book_describe': 'book_832',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 833,
    'book_describe': 'book_833',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 834,
    'book_describe': 'book_834',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 835,
    'book_describe': 'book_835',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 836,
    'book_describe': 'book_836',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 837,
    'book_describe': 'book_837',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 838,
    'book_describe': 'book_838',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 839,
    'book_describe': 'book_839',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 840,
    'book_describe': 'book_840',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 841,
    'book_describe': 'book_841',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 842,
    'book_describe': 'book_842',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 843,
    'book_describe': 'book_843',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 844,
    'book_describe': 'book_844',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 845,
    'book_describe': 'book_845',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 846,
    'book_describe': 'book_846',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 847,
    'book_describe': 'book_847',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 848,
    'book_describe': 'book_848',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 849,
    'book_describe': 'book_849',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 850,
    'book_describe': 'book_850',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 851,
    'book_describe': 'book_851',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 852,
    'book_describe': 'book_852',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 853,
    'book_describe': 'book_853',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 854,
    'book_describe': 'book_854',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 855,
    'book_describe': 'book_855',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 856,
    'book_describe': 'book_856',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 857,
    'book_describe': 'book_857',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 858,
    'book_describe': 'book_858',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 859,
    'book_describe': 'book_859',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 860,
    'book_describe': 'book_860',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 861,
    'book_describe': 'book_861',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 862,
    'book_describe': 'book_862',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 863,
    'book_describe': 'book_863',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 864,
    'book_describe': 'book_864',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 865,
    'book_describe': 'book_865',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 866,
    'book_describe': 'book_866',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 867,
    'book_describe': 'book_867',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 868,
    'book_describe': 'book_868',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 869,
    'book_describe': 'book_869',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 870,
    'book_describe': 'book_870',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 871,
    'book_describe': 'book_871',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 872,
    'book_describe': 'book_872',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 873,
    'book_describe': 'book_873',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 874,
    'book_describe': 'book_874',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 875,
    'book_describe': 'book_875',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 876,
    'book_describe': 'book_876',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 877,
    'book_describe': 'book_877',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 878,
    'book_describe': 'book_878',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 879,
    'book_describe': 'book_879',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 880,
    'book_describe': 'book_880',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 881,
    'book_describe': 'book_881',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 882,
    'book_describe': 'book_882',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 883,
    'book_describe': 'book_883',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 884,
    'book_describe': 'book_884',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 885,
    'book_describe': 'book_885',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 886,
    'book_describe': 'book_886',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 887,
    'book_describe': 'book_887',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 888,
    'book_describe': 'book_888',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 889,
    'book_describe': 'book_889',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 890,
    'book_describe': 'book_890',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 891,
    'book_describe': 'book_891',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 892,
    'book_describe': 'book_892',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 893,
    'book_describe': 'book_893',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 894,
    'book_describe': 'book_894',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 895,
    'book_describe': 'book_895',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 896,
    'book_describe': 'book_896',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 897,
    'book_describe': 'book_897',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 898,
    'book_describe': 'book_898',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 899,
    'book_describe': 'book_899',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 900,
    'book_describe': 'book_900',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 901,
    'book_describe': 'book_901',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 902,
    'book_describe': 'book_902',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 903,
    'book_describe': 'book_903',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 904,
    'book_describe': 'book_904',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 905,
    'book_describe': 'book_905',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 906,
    'book_describe': 'book_906',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 907,
    'book_describe': 'book_907',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 908,
    'book_describe': 'book_908',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 909,
    'book_describe': 'book_909',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 910,
    'book_describe': 'book_910',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 911,
    'book_describe': 'book_911',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 912,
    'book_describe': 'book_912',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 913,
    'book_describe': 'book_913',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 914,
    'book_describe': 'book_914',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 915,
    'book_describe': 'book_915',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 916,
    'book_describe': 'book_916',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 917,
    'book_describe': 'book_917',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 918,
    'book_describe': 'book_918',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 919,
    'book_describe': 'book_919',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 920,
    'book_describe': 'book_920',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 921,
    'book_describe': 'book_921',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 922,
    'book_describe': 'book_922',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 923,
    'book_describe': 'book_923',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 924,
    'book_describe': 'book_924',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 925,
    'book_describe': 'book_925',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 926,
    'book_describe': 'book_926',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 927,
    'book_describe': 'book_927',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 928,
    'book_describe': 'book_928',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 929,
    'book_describe': 'book_929',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 930,
    'book_describe': 'book_930',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 931,
    'book_describe': 'book_931',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 932,
    'book_describe': 'book_932',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 933,
    'book_describe': 'book_933',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 934,
    'book_describe': 'book_934',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 935,
    'book_describe': 'book_935',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 936,
    'book_describe': 'book_936',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 937,
    'book_describe': 'book_937',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 938,
    'book_describe': 'book_938',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 939,
    'book_describe': 'book_939',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 940,
    'book_describe': 'book_940',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 941,
    'book_describe': 'book_941',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 942,
    'book_describe': 'book_942',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 943,
    'book_describe': 'book_943',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 944,
    'book_describe': 'book_944',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 945,
    'book_describe': 'book_945',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 946,
    'book_describe': 'book_946',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 947,
    'book_describe': 'book_947',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 948,
    'book_describe': 'book_948',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 949,
    'book_describe': 'book_949',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 950,
    'book_describe': 'book_950',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 951,
    'book_describe': 'book_951',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 952,
    'book_describe': 'book_952',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 953,
    'book_describe': 'book_953',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 954,
    'book_describe': 'book_954',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 955,
    'book_describe': 'book_955',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 956,
    'book_describe': 'book_956',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 957,
    'book_describe': 'book_957',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 958,
    'book_describe': 'book_958',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 959,
    'book_describe': 'book_959',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 960,
    'book_describe': 'book_960',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 961,
    'book_describe': 'book_961',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 962,
    'book_describe': 'book_962',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 963,
    'book_describe': 'book_963',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 964,
    'book_describe': 'book_964',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 965,
    'book_describe': 'book_965',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 966,
    'book_describe': 'book_966',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 967,
    'book_describe': 'book_967',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 968,
    'book_describe': 'book_968',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 969,
    'book_describe': 'book_969',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 970,
    'book_describe': 'book_970',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 971,
    'book_describe': 'book_971',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 972,
    'book_describe': 'book_972',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 973,
    'book_describe': 'book_973',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 974,
    'book_describe': 'book_974',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 975,
    'book_describe': 'book_975',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 976,
    'book_describe': 'book_976',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 977,
    'book_describe': 'book_977',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 978,
    'book_describe': 'book_978',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 979,
    'book_describe': 'book_979',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 980,
    'book_describe': 'book_980',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 981,
    'book_describe': 'book_981',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 982,
    'book_describe': 'book_982',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 983,
    'book_describe': 'book_983',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 984,
    'book_describe': 'book_984',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 985,
    'book_describe': 'book_985',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 986,
    'book_describe': 'book_986',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 987,
    'book_describe': 'book_987',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 988,
    'book_describe': 'book_988',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 989,
    'book_describe': 'book_989',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 990,
    'book_describe': 'book_990',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 991,
    'book_describe': 'book_991',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 992,
    'book_describe': 'book_992',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 993,
    'book_describe': 'book_993',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 994,
    'book_describe': 'book_994',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 995,
    'book_describe': 'book_995',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 996,
    'book_describe': 'book_996',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 997,
    'book_describe': 'book_997',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 998,
    'book_describe': 'book_998',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 999,
    'book_describe': 'book_999',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 1000,
    'book_describe': 'book_1000',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 1001,
    'book_describe': 'book_1001',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 1002,
    'book_describe': 'book_1002',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 1003,
    'book_describe': 'book_1003',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 1004,
    'book_describe': 'book_1004',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 1005,
    'book_describe': 'book_1005',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 1006,
    'book_describe': 'book_1006',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 1007,
    'book_describe': 'book_1007',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 1008,
    'book_describe': 'book_1008',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 1009,
    'book_describe': 'book_1009',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 1010,
    'book_describe': 'book_1010',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 1011,
    'book_describe': 'book_1011',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 1012,
    'book_describe': 'book_1012',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 1013,
    'book_describe': 'book_1013',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 1014,
    'book_describe': 'book_1014',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 1015,
    'book_describe': 'book_1015',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 1016,
    'book_describe': 'book_1016',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 1017,
    'book_describe': 'book_1017',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 1018,
    'book_describe': 'book_1018',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 1019,
    'book_describe': 'book_1019',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 1020,
    'book_describe': 'book_1020',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 1021,
    'book_describe': 'book_1021',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 1022,
    'book_describe': 'book_1022',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 1023,
    'book_describe': 'book_1023',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 1024,
    'book_describe': 'book_1024',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 1025,
    'book_describe': 'book_1025',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 1026,
    'book_describe': 'book_1026',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 1027,
    'book_describe': 'book_1027',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 1028,
    'book_describe': 'book_1028',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 1029,
    'book_describe': 'book_1029',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 1030,
    'book_describe': 'book_1030',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 1031,
    'book_describe': 'book_1031',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 1032,
    'book_describe': 'book_1032',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 1033,
    'book_describe': 'book_1033',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 1034,
    'book_describe': 'book_1034',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 1035,
    'book_describe': 'book_1035',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 1036,
    'book_describe': 'book_1036',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 1037,
    'book_describe': 'book_1037',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 1038,
    'book_describe': 'book_1038',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 1039,
    'book_describe': 'book_1039',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 1040,
    'book_describe': 'book_1040',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 1041,
    'book_describe': 'book_1041',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 1042,
    'book_describe': 'book_1042',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 1043,
    'book_describe': 'book_1043',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 1044,
    'book_describe': 'book_1044',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 1045,
    'book_describe': 'book_1045',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 1046,
    'book_describe': 'book_1046',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 1047,
    'book_describe': 'book_1047',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 1048,
    'book_describe': 'book_1048',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 1049,
    'book_describe': 'book_1049',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 1050,
    'book_describe': 'book_1050',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 1051,
    'book_describe': 'book_1051',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 1052,
    'book_describe': 'book_1052',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 1053,
    'book_describe': 'book_1053',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 1054,
    'book_describe': 'book_1054',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 1055,
    'book_describe': 'book_1055',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 1056,
    'book_describe': 'book_1056',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 1057,
    'book_describe': 'book_1057',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 1058,
    'book_describe': 'book_1058',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 1059,
    'book_describe': 'book_1059',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 1060,
    'book_describe': 'book_1060',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 1061,
    'book_describe': 'book_1061',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 1062,
    'book_describe': 'book_1062',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 1063,
    'book_describe': 'book_1063',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 1064,
    'book_describe': 'book_1064',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 1065,
    'book_describe': 'book_1065',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 1066,
    'book_describe': 'book_1066',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 1067,
    'book_describe': 'book_1067',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 1068,
    'book_describe': 'book_1068',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 1069,
    'book_describe': 'book_1069',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 1070,
    'book_describe': 'book_1070',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 1071,
    'book_describe': 'book_1071',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 1072,
    'book_describe': 'book_1072',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 1073,
    'book_describe': 'book_1073',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 1074,
    'book_describe': 'book_1074',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 1075,
    'book_describe': 'book_1075',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 1076,
    'book_describe': 'book_1076',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 1077,
    'book_describe': 'book_1077',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 1078,
    'book_describe': 'book_1078',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 1079,
    'book_describe': 'book_1079',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 1080,
    'book_describe': 'book_1080',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 1081,
    'book_describe': 'book_1081',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 1082,
    'book_describe': 'book_1082',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 1083,
    'book_describe': 'book_1083',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 1084,
    'book_describe': 'book_1084',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 1085,
    'book_describe': 'book_1085',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 1086,
    'book_describe': 'book_1086',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 1087,
    'book_describe': 'book_1087',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 1088,
    'book_describe': 'book_1088',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 1089,
    'book_describe': 'book_1089',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 1090,
    'book_describe': 'book_1090',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 1091,
    'book_describe': 'book_1091',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 1092,
    'book_describe': 'book_1092',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 1093,
    'book_describe': 'book_1093',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 1094,
    'book_describe': 'book_1094',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 1095,
    'book_describe': 'book_1095',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 1096,
    'book_describe': 'book_1096',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 1097,
    'book_describe': 'book_1097',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 1098,
    'book_describe': 'book_1098',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 1099,
    'book_describe': 'book_1099',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 1100,
    'book_describe': 'book_1100',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 1101,
    'book_describe': 'book_1101',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 1102,
    'book_describe': 'book_1102',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 1103,
    'book_describe': 'book_1103',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 1104,
    'book_describe': 'book_1104',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 1105,
    'book_describe': 'book_1105',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 1106,
    'book_describe': 'book_1106',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 1107,
    'book_describe': 'book_1107',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 1108,
    'book_describe': 'book_1108',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 1109,
    'book_describe': 'book_1109',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 1110,
    'book_describe': 'book_1110',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 1111,
    'book_describe': 'book_1111',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 1112,
    'book_describe': 'book_1112',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 1113,
    'book_describe': 'book_1113',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 1114,
    'book_describe': 'book_1114',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 1115,
    'book_describe': 'book_1115',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 1116,
    'book_describe': 'book_1116',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 1117,
    'book_describe': 'book_1117',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 1118,
    'book_describe': 'book_1118',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 1119,
    'book_describe': 'book_1119',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 1120,
    'book_describe': 'book_1120',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 1121,
    'book_describe': 'book_1121',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 1122,
    'book_describe': 'book_1122',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 1123,
    'book_describe': 'book_1123',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 1124,
    'book_describe': 'book_1124',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 1125,
    'book_describe': 'book_1125',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 1126,
    'book_describe': 'book_1126',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 1127,
    'book_describe': 'book_1127',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 1128,
    'book_describe': 'book_1128',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 1129,
    'book_describe': 'book_1129',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 1130,
    'book_describe': 'book_1130',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 1131,
    'book_describe': 'book_1131',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 1132,
    'book_describe': 'book_1132',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 1133,
    'book_describe': 'book_1133',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 1134,
    'book_describe': 'book_1134',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 1135,
    'book_describe': 'book_1135',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 1136,
    'book_describe': 'book_1136',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 1137,
    'book_describe': 'book_1137',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 1138,
    'book_describe': 'book_1138',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 1139,
    'book_describe': 'book_1139',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 1140,
    'book_describe': 'book_1140',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 1141,
    'book_describe': 'book_1141',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 1142,
    'book_describe': 'book_1142',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 1143,
    'book_describe': 'book_1143',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 1144,
    'book_describe': 'book_1144',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 1145,
    'book_describe': 'book_1145',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 1146,
    'book_describe': 'book_1146',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 1147,
    'book_describe': 'book_1147',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 1148,
    'book_describe': 'book_1148',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 1149,
    'book_describe': 'book_1149',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 1150,
    'book_describe': 'book_1150',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 1151,
    'book_describe': 'book_1151',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 1152,
    'book_describe': 'book_1152',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 1153,
    'book_describe': 'book_1153',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 1154,
    'book_describe': 'book_1154',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 1155,
    'book_describe': 'book_1155',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 1156,
    'book_describe': 'book_1156',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 1157,
    'book_describe': 'book_1157',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 1158,
    'book_describe': 'book_1158',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 1159,
    'book_describe': 'book_1159',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 1160,
    'book_describe': 'book_1160',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 1161,
    'book_describe': 'book_1161',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 1162,
    'book_describe': 'book_1162',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 1163,
    'book_describe': 'book_1163',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 1164,
    'book_describe': 'book_1164',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 1165,
    'book_describe': 'book_1165',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 1166,
    'book_describe': 'book_1166',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 1167,
    'book_describe': 'book_1167',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 1168,
    'book_describe': 'book_1168',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 1169,
    'book_describe': 'book_1169',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 1170,
    'book_describe': 'book_1170',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 1171,
    'book_describe': 'book_1171',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 1172,
    'book_describe': 'book_1172',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 1173,
    'book_describe': 'book_1173',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 1174,
    'book_describe': 'book_1174',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 1175,
    'book_describe': 'book_1175',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 1176,
    'book_describe': 'book_1176',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 1177,
    'book_describe': 'book_1177',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 1178,
    'book_describe': 'book_1178',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 1179,
    'book_describe': 'book_1179',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 1180,
    'book_describe': 'book_1180',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 1181,
    'book_describe': 'book_1181',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 1182,
    'book_describe': 'book_1182',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 1183,
    'book_describe': 'book_1183',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 1184,
    'book_describe': 'book_1184',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 1185,
    'book_describe': 'book_1185',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 1186,
    'book_describe': 'book_1186',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 1187,
    'book_describe': 'book_1187',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 1188,
    'book_describe': 'book_1188',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 1189,
    'book_describe': 'book_1189',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 1190,
    'book_describe': 'book_1190',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 1191,
    'book_describe': 'book_1191',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 1192,
    'book_describe': 'book_1192',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 1193,
    'book_describe': 'book_1193',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 1194,
    'book_describe': 'book_1194',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 1195,
    'book_describe': 'book_1195',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 1196,
    'book_describe': 'book_1196',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 1197,
    'book_describe': 'book_1197',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 1198,
    'book_describe': 'book_1198',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 1199,
    'book_describe': 'book_1199',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 1200,
    'book_describe': 'book_1200',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 1201,
    'book_describe': 'book_1201',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 1202,
    'book_describe': 'book_1202',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 1203,
    'book_describe': 'book_1203',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 1204,
    'book_describe': 'book_1204',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 1205,
    'book_describe': 'book_1205',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 1206,
    'book_describe': 'book_1206',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 1207,
    'book_describe': 'book_1207',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 1208,
    'book_describe': 'book_1208',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 1209,
    'book_describe': 'book_1209',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 1210,
    'book_describe': 'book_1210',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 1211,
    'book_describe': 'book_1211',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 1212,
    'book_describe': 'book_1212',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 1213,
    'book_describe': 'book_1213',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 1214,
    'book_describe': 'book_1214',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 1215,
    'book_describe': 'book_1215',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 1216,
    'book_describe': 'book_1216',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 1217,
    'book_describe': 'book_1217',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 1218,
    'book_describe': 'book_1218',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 1219,
    'book_describe': 'book_1219',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 1220,
    'book_describe': 'book_1220',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 1221,
    'book_describe': 'book_1221',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 1222,
    'book_describe': 'book_1222',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 1223,
    'book_describe': 'book_1223',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 1224,
    'book_describe': 'book_1224',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 1225,
    'book_describe': 'book_1225',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 1226,
    'book_describe': 'book_1226',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 1227,
    'book_describe': 'book_1227',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 1228,
    'book_describe': 'book_1228',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 1229,
    'book_describe': 'book_1229',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 1230,
    'book_describe': 'book_1230',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 1231,
    'book_describe': 'book_1231',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 1232,
    'book_describe': 'book_1232',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 1233,
    'book_describe': 'book_1233',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 1234,
    'book_describe': 'book_1234',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 1235,
    'book_describe': 'book_1235',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 1236,
    'book_describe': 'book_1236',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 1237,
    'book_describe': 'book_1237',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 1238,
    'book_describe': 'book_1238',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 1239,
    'book_describe': 'book_1239',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 1240,
    'book_describe': 'book_1240',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 1241,
    'book_describe': 'book_1241',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 1242,
    'book_describe': 'book_1242',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 1243,
    'book_describe': 'book_1243',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 1244,
    'book_describe': 'book_1244',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 1245,
    'book_describe': 'book_1245',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 1246,
    'book_describe': 'book_1246',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 1247,
    'book_describe': 'book_1247',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 1248,
    'book_describe': 'book_1248',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 1249,
    'book_describe': 'book_1249',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 1250,
    'book_describe': 'book_1250',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 1251,
    'book_describe': 'book_1251',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 1252,
    'book_describe': 'book_1252',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 1253,
    'book_describe': 'book_1253',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 1254,
    'book_describe': 'book_1254',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 1255,
    'book_describe': 'book_1255',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 1256,
    'book_describe': 'book_1256',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 1257,
    'book_describe': 'book_1257',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 1258,
    'book_describe': 'book_1258',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 1259,
    'book_describe': 'book_1259',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 1260,
    'book_describe': 'book_1260',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 1261,
    'book_describe': 'book_1261',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 1262,
    'book_describe': 'book_1262',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 1263,
    'book_describe': 'book_1263',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 1264,
    'book_describe': 'book_1264',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 1265,
    'book_describe': 'book_1265',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 1266,
    'book_describe': 'book_1266',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 1267,
    'book_describe': 'book_1267',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 1268,
    'book_describe': 'book_1268',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 1269,
    'book_describe': 'book_1269',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 1270,
    'book_describe': 'book_1270',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 1271,
    'book_describe': 'book_1271',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 1272,
    'book_describe': 'book_1272',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 1273,
    'book_describe': 'book_1273',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 1274,
    'book_describe': 'book_1274',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 1275,
    'book_describe': 'book_1275',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 1276,
    'book_describe': 'book_1276',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 1277,
    'book_describe': 'book_1277',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 1278,
    'book_describe': 'book_1278',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 1279,
    'book_describe': 'book_1279',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 1280,
    'book_describe': 'book_1280',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 1281,
    'book_describe': 'book_1281',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 1282,
    'book_describe': 'book_1282',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 1283,
    'book_describe': 'book_1283',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 1284,
    'book_describe': 'book_1284',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 1285,
    'book_describe': 'book_1285',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 1286,
    'book_describe': 'book_1286',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 1287,
    'book_describe': 'book_1287',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 1288,
    'book_describe': 'book_1288',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 1289,
    'book_describe': 'book_1289',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 1290,
    'book_describe': 'book_1290',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 1291,
    'book_describe': 'book_1291',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 1292,
    'book_describe': 'book_1292',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 1293,
    'book_describe': 'book_1293',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 1294,
    'book_describe': 'book_1294',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 1295,
    'book_describe': 'book_1295',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 1296,
    'book_describe': 'book_1296',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 1297,
    'book_describe': 'book_1297',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 1298,
    'book_describe': 'book_1298',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 1299,
    'book_describe': 'book_1299',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 1300,
    'book_describe': 'book_1300',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 1301,
    'book_describe': 'book_1301',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 1302,
    'book_describe': 'book_1302',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 1303,
    'book_describe': 'book_1303',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 1304,
    'book_describe': 'book_1304',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 1305,
    'book_describe': 'book_1305',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 1306,
    'book_describe': 'book_1306',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 1307,
    'book_describe': 'book_1307',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 1308,
    'book_describe': 'book_1308',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 1309,
    'book_describe': 'book_1309',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 1310,
    'book_describe': 'book_1310',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 1311,
    'book_describe': 'book_1311',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 1312,
    'book_describe': 'book_1312',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 1313,
    'book_describe': 'book_1313',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 1314,
    'book_describe': 'book_1314',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 1315,
    'book_describe': 'book_1315',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 1316,
    'book_describe': 'book_1316',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 1317,
    'book_describe': 'book_1317',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 1318,
    'book_describe': 'book_1318',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 1319,
    'book_describe': 'book_1319',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 1320,
    'book_describe': 'book_1320',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 1321,
    'book_describe': 'book_1321',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 1322,
    'book_describe': 'book_1322',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 1323,
    'book_describe': 'book_1323',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 1324,
    'book_describe': 'book_1324',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 1325,
    'book_describe': 'book_1325',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 1326,
    'book_describe': 'book_1326',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 1327,
    'book_describe': 'book_1327',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 1328,
    'book_describe': 'book_1328',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 1329,
    'book_describe': 'book_1329',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 1330,
    'book_describe': 'book_1330',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 1331,
    'book_describe': 'book_1331',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 1332,
    'book_describe': 'book_1332',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 1333,
    'book_describe': 'book_1333',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 1334,
    'book_describe': 'book_1334',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 1335,
    'book_describe': 'book_1335',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 1336,
    'book_describe': 'book_1336',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 1337,
    'book_describe': 'book_1337',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 1338,
    'book_describe': 'book_1338',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 1339,
    'book_describe': 'book_1339',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 1340,
    'book_describe': 'book_1340',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 1341,
    'book_describe': 'book_1341',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 1342,
    'book_describe': 'book_1342',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 1343,
    'book_describe': 'book_1343',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 1344,
    'book_describe': 'book_1344',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 1345,
    'book_describe': 'book_1345',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 1346,
    'book_describe': 'book_1346',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 1347,
    'book_describe': 'book_1347',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 1348,
    'book_describe': 'book_1348',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 1349,
    'book_describe': 'book_1349',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 1350,
    'book_describe': 'book_1350',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 1351,
    'book_describe': 'book_1351',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 1352,
    'book_describe': 'book_1352',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 1353,
    'book_describe': 'book_1353',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 1354,
    'book_describe': 'book_1354',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 1355,
    'book_describe': 'book_1355',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 1356,
    'book_describe': 'book_1356',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 1357,
    'book_describe': 'book_1357',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 1358,
    'book_describe': 'book_1358',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 1359,
    'book_describe': 'book_1359',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 1360,
    'book_describe': 'book_1360',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 1361,
    'book_describe': 'book_1361',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 1362,
    'book_describe': 'book_1362',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 1363,
    'book_describe': 'book_1363',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 1364,
    'book_describe': 'book_1364',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 1365,
    'book_describe': 'book_1365',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 1366,
    'book_describe': 'book_1366',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 1367,
    'book_describe': 'book_1367',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 1368,
    'book_describe': 'book_1368',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 1369,
    'book_describe': 'book_1369',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 1370,
    'book_describe': 'book_1370',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 1371,
    'book_describe': 'book_1371',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 1372,
    'book_describe': 'book_1372',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 1373,
    'book_describe': 'book_1373',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 1374,
    'book_describe': 'book_1374',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 1375,
    'book_describe': 'book_1375',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 1376,
    'book_describe': 'book_1376',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 1377,
    'book_describe': 'book_1377',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 1378,
    'book_describe': 'book_1378',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 1379,
    'book_describe': 'book_1379',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 1380,
    'book_describe': 'book_1380',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 1381,
    'book_describe': 'book_1381',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 1382,
    'book_describe': 'book_1382',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 1383,
    'book_describe': 'book_1383',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 1384,
    'book_describe': 'book_1384',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 1385,
    'book_describe': 'book_1385',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 1386,
    'book_describe': 'book_1386',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 1387,
    'book_describe': 'book_1387',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 1388,
    'book_describe': 'book_1388',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 1389,
    'book_describe': 'book_1389',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 1390,
    'book_describe': 'book_1390',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 1391,
    'book_describe': 'book_1391',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 1392,
    'book_describe': 'book_1392',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 1393,
    'book_describe': 'book_1393',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 1394,
    'book_describe': 'book_1394',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 1395,
    'book_describe': 'book_1395',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 1396,
    'book_describe': 'book_1396',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 1397,
    'book_describe': 'book_1397',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 1398,
    'book_describe': 'book_1398',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 1399,
    'book_describe': 'book_1399',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 1400,
    'book_describe': 'book_1400',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 1401,
    'book_describe': 'book_1401',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 1402,
    'book_describe': 'book_1402',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 1403,
    'book_describe': 'book_1403',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 1404,
    'book_describe': 'book_1404',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 1405,
    'book_describe': 'book_1405',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 1406,
    'book_describe': 'book_1406',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 1407,
    'book_describe': 'book_1407',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 1408,
    'book_describe': 'book_1408',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 1409,
    'book_describe': 'book_1409',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 1410,
    'book_describe': 'book_1410',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 1411,
    'book_describe': 'book_1411',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 1412,
    'book_describe': 'book_1412',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 1413,
    'book_describe': 'book_1413',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 1414,
    'book_describe': 'book_1414',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 1415,
    'book_describe': 'book_1415',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 1416,
    'book_describe': 'book_1416',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 1417,
    'book_describe': 'book_1417',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 1418,
    'book_describe': 'book_1418',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 1419,
    'book_describe': 'book_1419',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 1420,
    'book_describe': 'book_1420',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 1421,
    'book_describe': 'book_1421',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 1422,
    'book_describe': 'book_1422',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 1423,
    'book_describe': 'book_1423',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 1424,
    'book_describe': 'book_1424',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 1425,
    'book_describe': 'book_1425',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 1426,
    'book_describe': 'book_1426',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 1427,
    'book_describe': 'book_1427',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 1428,
    'book_describe': 'book_1428',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 1429,
    'book_describe': 'book_1429',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 1430,
    'book_describe': 'book_1430',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 1431,
    'book_describe': 'book_1431',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 1432,
    'book_describe': 'book_1432',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 1433,
    'book_describe': 'book_1433',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 1434,
    'book_describe': 'book_1434',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 1435,
    'book_describe': 'book_1435',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 1436,
    'book_describe': 'book_1436',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 1437,
    'book_describe': 'book_1437',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 1438,
    'book_describe': 'book_1438',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 1439,
    'book_describe': 'book_1439',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 1440,
    'book_describe': 'book_1440',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 1441,
    'book_describe': 'book_1441',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 1442,
    'book_describe': 'book_1442',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 1443,
    'book_describe': 'book_1443',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 1444,
    'book_describe': 'book_1444',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 1445,
    'book_describe': 'book_1445',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 1446,
    'book_describe': 'book_1446',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 1447,
    'book_describe': 'book_1447',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 1448,
    'book_describe': 'book_1448',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 1449,
    'book_describe': 'book_1449',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 1450,
    'book_describe': 'book_1450',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 1451,
    'book_describe': 'book_1451',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 1452,
    'book_describe': 'book_1452',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 1453,
    'book_describe': 'book_1453',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 1454,
    'book_describe': 'book_1454',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 1455,
    'book_describe': 'book_1455',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 1456,
    'book_describe': 'book_1456',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 1457,
    'book_describe': 'book_1457',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 1458,
    'book_describe': 'book_1458',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 1459,
    'book_describe': 'book_1459',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 1460,
    'book_describe': 'book_1460',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 1461,
    'book_describe': 'book_1461',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 1462,
    'book_describe': 'book_1462',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 1463,
    'book_describe': 'book_1463',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 1464,
    'book_describe': 'book_1464',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 1465,
    'book_describe': 'book_1465',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 1466,
    'book_describe': 'book_1466',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 1467,
    'book_describe': 'book_1467',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 1468,
    'book_describe': 'book_1468',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 1469,
    'book_describe': 'book_1469',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 1470,
    'book_describe': 'book_1470',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 1471,
    'book_describe': 'book_1471',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 1472,
    'book_describe': 'book_1472',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 1473,
    'book_describe': 'book_1473',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 1474,
    'book_describe': 'book_1474',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 1475,
    'book_describe': 'book_1475',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 1476,
    'book_describe': 'book_1476',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 1477,
    'book_describe': 'book_1477',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 1478,
    'book_describe': 'book_1478',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 1479,
    'book_describe': 'book_1479',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 1480,
    'book_describe': 'book_1480',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 1481,
    'book_describe': 'book_1481',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 1482,
    'book_describe': 'book_1482',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 1483,
    'book_describe': 'book_1483',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 1484,
    'book_describe': 'book_1484',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 1485,
    'book_describe': 'book_1485',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 1486,
    'book_describe': 'book_1486',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 1487,
    'book_describe': 'book_1487',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 1488,
    'book_describe': 'book_1488',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 1489,
    'book_describe': 'book_1489',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 1490,
    'book_describe': 'book_1490',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 1491,
    'book_describe': 'book_1491',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 1492,
    'book_describe': 'book_1492',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 1493,
    'book_describe': 'book_1493',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 1494,
    'book_describe': 'book_1494',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 1495,
    'book_describe': 'book_1495',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 1496,
    'book_describe': 'book_1496',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 1497,
    'book_describe': 'book_1497',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 1498,
    'book_describe': 'book_1498',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 1499,
    'book_describe': 'book_1499',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 1500,
    'book_describe': 'book_1500',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 1501,
    'book_describe': 'book_1501',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 1502,
    'book_describe': 'book_1502',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 1503,
    'book_describe': 'book_1503',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 1504,
    'book_describe': 'book_1504',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 1505,
    'book_describe': 'book_1505',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 1506,
    'book_describe': 'book_1506',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 1507,
    'book_describe': 'book_1507',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 1508,
    'book_describe': 'book_1508',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 1509,
    'book_describe': 'book_1509',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 1510,
    'book_describe': 'book_1510',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 1511,
    'book_describe': 'book_1511',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 1512,
    'book_describe': 'book_1512',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 1513,
    'book_describe': 'book_1513',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 1514,
    'book_describe': 'book_1514',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 1515,
    'book_describe': 'book_1515',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 1516,
    'book_describe': 'book_1516',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 1517,
    'book_describe': 'book_1517',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 1518,
    'book_describe': 'book_1518',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 1519,
    'book_describe': 'book_1519',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 1520,
    'book_describe': 'book_1520',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 1521,
    'book_describe': 'book_1521',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 1522,
    'book_describe': 'book_1522',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 1523,
    'book_describe': 'book_1523',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 1524,
    'book_describe': 'book_1524',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 1525,
    'book_describe': 'book_1525',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 1526,
    'book_describe': 'book_1526',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 1527,
    'book_describe': 'book_1527',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 1528,
    'book_describe': 'book_1528',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 1529,
    'book_describe': 'book_1529',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 1530,
    'book_describe': 'book_1530',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 1531,
    'book_describe': 'book_1531',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 1532,
    'book_describe': 'book_1532',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 1533,
    'book_describe': 'book_1533',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 1534,
    'book_describe': 'book_1534',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 1535,
    'book_describe': 'book_1535',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 1536,
    'book_describe': 'book_1536',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 1537,
    'book_describe': 'book_1537',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 1538,
    'book_describe': 'book_1538',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 1539,
    'book_describe': 'book_1539',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 1540,
    'book_describe': 'book_1540',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 1541,
    'book_describe': 'book_1541',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 1542,
    'book_describe': 'book_1542',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 1543,
    'book_describe': 'book_1543',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 1544,
    'book_describe': 'book_1544',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 1545,
    'book_describe': 'book_1545',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 1546,
    'book_describe': 'book_1546',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 1547,
    'book_describe': 'book_1547',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 1548,
    'book_describe': 'book_1548',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 1549,
    'book_describe': 'book_1549',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 1550,
    'book_describe': 'book_1550',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 1551,
    'book_describe': 'book_1551',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 1552,
    'book_describe': 'book_1552',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 1553,
    'book_describe': 'book_1553',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 1554,
    'book_describe': 'book_1554',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 1555,
    'book_describe': 'book_1555',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 1556,
    'book_describe': 'book_1556',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 1557,
    'book_describe': 'book_1557',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 1558,
    'book_describe': 'book_1558',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 1559,
    'book_describe': 'book_1559',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 1560,
    'book_describe': 'book_1560',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 1561,
    'book_describe': 'book_1561',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 1562,
    'book_describe': 'book_1562',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 1563,
    'book_describe': 'book_1563',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 1564,
    'book_describe': 'book_1564',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 1565,
    'book_describe': 'book_1565',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 1566,
    'book_describe': 'book_1566',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 1567,
    'book_describe': 'book_1567',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 1568,
    'book_describe': 'book_1568',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 1569,
    'book_describe': 'book_1569',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 1570,
    'book_describe': 'book_1570',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 1571,
    'book_describe': 'book_1571',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 1572,
    'book_describe': 'book_1572',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 1573,
    'book_describe': 'book_1573',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 1574,
    'book_describe': 'book_1574',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 1575,
    'book_describe': 'book_1575',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 1576,
    'book_describe': 'book_1576',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 1577,
    'book_describe': 'book_1577',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 1578,
    'book_describe': 'book_1578',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 1579,
    'book_describe': 'book_1579',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 1580,
    'book_describe': 'book_1580',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 1581,
    'book_describe': 'book_1581',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 1582,
    'book_describe': 'book_1582',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 1583,
    'book_describe': 'book_1583',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 1584,
    'book_describe': 'book_1584',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 1585,
    'book_describe': 'book_1585',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 1586,
    'book_describe': 'book_1586',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 1587,
    'book_describe': 'book_1587',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 1588,
    'book_describe': 'book_1588',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 1589,
    'book_describe': 'book_1589',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 1590,
    'book_describe': 'book_1590',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 1591,
    'book_describe': 'book_1591',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 1592,
    'book_describe': 'book_1592',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 1593,
    'book_describe': 'book_1593',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 1594,
    'book_describe': 'book_1594',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 1595,
    'book_describe': 'book_1595',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 1596,
    'book_describe': 'book_1596',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 1597,
    'book_describe': 'book_1597',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 1598,
    'book_describe': 'book_1598',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 1599,
    'book_describe': 'book_1599',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 1600,
    'book_describe': 'book_1600',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 1601,
    'book_describe': 'book_1601',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 1602,
    'book_describe': 'book_1602',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 1603,
    'book_describe': 'book_1603',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 1604,
    'book_describe': 'book_1604',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 1605,
    'book_describe': 'book_1605',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 1606,
    'book_describe': 'book_1606',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 1607,
    'book_describe': 'book_1607',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 1608,
    'book_describe': 'book_1608',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 1609,
    'book_describe': 'book_1609',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 1610,
    'book_describe': 'book_1610',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 1611,
    'book_describe': 'book_1611',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 1612,
    'book_describe': 'book_1612',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 1613,
    'book_describe': 'book_1613',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 1614,
    'book_describe': 'book_1614',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 1615,
    'book_describe': 'book_1615',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 1616,
    'book_describe': 'book_1616',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 1617,
    'book_describe': 'book_1617',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 1618,
    'book_describe': 'book_1618',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 1619,
    'book_describe': 'book_1619',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 1620,
    'book_describe': 'book_1620',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 1621,
    'book_describe': 'book_1621',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 1622,
    'book_describe': 'book_1622',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 1623,
    'book_describe': 'book_1623',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 1624,
    'book_describe': 'book_1624',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 1625,
    'book_describe': 'book_1625',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 1626,
    'book_describe': 'book_1626',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 1627,
    'book_describe': 'book_1627',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 1628,
    'book_describe': 'book_1628',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 1629,
    'book_describe': 'book_1629',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 1630,
    'book_describe': 'book_1630',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 1631,
    'book_describe': 'book_1631',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 1632,
    'book_describe': 'book_1632',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 1633,
    'book_describe': 'book_1633',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 1634,
    'book_describe': 'book_1634',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 1635,
    'book_describe': 'book_1635',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 1636,
    'book_describe': 'book_1636',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 1637,
    'book_describe': 'book_1637',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 1638,
    'book_describe': 'book_1638',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 1639,
    'book_describe': 'book_1639',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 1640,
    'book_describe': 'book_1640',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 1641,
    'book_describe': 'book_1641',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 1642,
    'book_describe': 'book_1642',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 1643,
    'book_describe': 'book_1643',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 1644,
    'book_describe': 'book_1644',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 1645,
    'book_describe': 'book_1645',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 1646,
    'book_describe': 'book_1646',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 1647,
    'book_describe': 'book_1647',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 1648,
    'book_describe': 'book_1648',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 1649,
    'book_describe': 'book_1649',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 1650,
    'book_describe': 'book_1650',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 1651,
    'book_describe': 'book_1651',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 1652,
    'book_describe': 'book_1652',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 1653,
    'book_describe': 'book_1653',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 1654,
    'book_describe': 'book_1654',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 1655,
    'book_describe': 'book_1655',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 1656,
    'book_describe': 'book_1656',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 1657,
    'book_describe': 'book_1657',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 1658,
    'book_describe': 'book_1658',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 1659,
    'book_describe': 'book_1659',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 1660,
    'book_describe': 'book_1660',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 1661,
    'book_describe': 'book_1661',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 1662,
    'book_describe': 'book_1662',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 1663,
    'book_describe': 'book_1663',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 1664,
    'book_describe': 'book_1664',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 1665,
    'book_describe': 'book_1665',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 1666,
    'book_describe': 'book_1666',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 1667,
    'book_describe': 'book_1667',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 1668,
    'book_describe': 'book_1668',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 1669,
    'book_describe': 'book_1669',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 1670,
    'book_describe': 'book_1670',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 1671,
    'book_describe': 'book_1671',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 1672,
    'book_describe': 'book_1672',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 1673,
    'book_describe': 'book_1673',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 1674,
    'book_describe': 'book_1674',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 1675,
    'book_describe': 'book_1675',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 1676,
    'book_describe': 'book_1676',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 1677,
    'book_describe': 'book_1677',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 1678,
    'book_describe': 'book_1678',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 1679,
    'book_describe': 'book_1679',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 1680,
    'book_describe': 'book_1680',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 1681,
    'book_describe': 'book_1681',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 1682,
    'book_describe': 'book_1682',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 1683,
    'book_describe': 'book_1683',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 1684,
    'book_describe': 'book_1684',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 1685,
    'book_describe': 'book_1685',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 1686,
    'book_describe': 'book_1686',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 1687,
    'book_describe': 'book_1687',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 1688,
    'book_describe': 'book_1688',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 1689,
    'book_describe': 'book_1689',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 1690,
    'book_describe': 'book_1690',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 1691,
    'book_describe': 'book_1691',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 1692,
    'book_describe': 'book_1692',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 1693,
    'book_describe': 'book_1693',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 1694,
    'book_describe': 'book_1694',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 1695,
    'book_describe': 'book_1695',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 1696,
    'book_describe': 'book_1696',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 1697,
    'book_describe': 'book_1697',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 1698,
    'book_describe': 'book_1698',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 1699,
    'book_describe': 'book_1699',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 1700,
    'book_describe': 'book_1700',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 1701,
    'book_describe': 'book_1701',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 1702,
    'book_describe': 'book_1702',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 1703,
    'book_describe': 'book_1703',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 1704,
    'book_describe': 'book_1704',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 1705,
    'book_describe': 'book_1705',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 1706,
    'book_describe': 'book_1706',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 1707,
    'book_describe': 'book_1707',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 1708,
    'book_describe': 'book_1708',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 1709,
    'book_describe': 'book_1709',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 1710,
    'book_describe': 'book_1710',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 1711,
    'book_describe': 'book_1711',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 1712,
    'book_describe': 'book_1712',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 1713,
    'book_describe': 'book_1713',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 1714,
    'book_describe': 'book_1714',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 1715,
    'book_describe': 'book_1715',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 1716,
    'book_describe': 'book_1716',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 1717,
    'book_describe': 'book_1717',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 1718,
    'book_describe': 'book_1718',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 1719,
    'book_describe': 'book_1719',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 1720,
    'book_describe': 'book_1720',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 1721,
    'book_describe': 'book_1721',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 1722,
    'book_describe': 'book_1722',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 1723,
    'book_describe': 'book_1723',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 1724,
    'book_describe': 'book_1724',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 1725,
    'book_describe': 'book_1725',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 1726,
    'book_describe': 'book_1726',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 1727,
    'book_describe': 'book_1727',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 1728,
    'book_describe': 'book_1728',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 1729,
    'book_describe': 'book_1729',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 1730,
    'book_describe': 'book_1730',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 1731,
    'book_describe': 'book_1731',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 1732,
    'book_describe': 'book_1732',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 1733,
    'book_describe': 'book_1733',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 1734,
    'book_describe': 'book_1734',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 1735,
    'book_describe': 'book_1735',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 1736,
    'book_describe': 'book_1736',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 1737,
    'book_describe': 'book_1737',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 1738,
    'book_describe': 'book_1738',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 1739,
    'book_describe': 'book_1739',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 1740,
    'book_describe': 'book_1740',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 1741,
    'book_describe': 'book_1741',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 1742,
    'book_describe': 'book_1742',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 1743,
    'book_describe': 'book_1743',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 1744,
    'book_describe': 'book_1744',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 1745,
    'book_describe': 'book_1745',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 1746,
    'book_describe': 'book_1746',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 1747,
    'book_describe': 'book_1747',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 1748,
    'book_describe': 'book_1748',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 1749,
    'book_describe': 'book_1749',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 1750,
    'book_describe': 'book_1750',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 1751,
    'book_describe': 'book_1751',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 1752,
    'book_describe': 'book_1752',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 1753,
    'book_describe': 'book_1753',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 1754,
    'book_describe': 'book_1754',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 1755,
    'book_describe': 'book_1755',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 1756,
    'book_describe': 'book_1756',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 1757,
    'book_describe': 'book_1757',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 1758,
    'book_describe': 'book_1758',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 1759,
    'book_describe': 'book_1759',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 1760,
    'book_describe': 'book_1760',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 1761,
    'book_describe': 'book_1761',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 1762,
    'book_describe': 'book_1762',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 1763,
    'book_describe': 'book_1763',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 1764,
    'book_describe': 'book_1764',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 1765,
    'book_describe': 'book_1765',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 1766,
    'book_describe': 'book_1766',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 1767,
    'book_describe': 'book_1767',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 1768,
    'book_describe': 'book_1768',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 1769,
    'book_describe': 'book_1769',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 1770,
    'book_describe': 'book_1770',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 1771,
    'book_describe': 'book_1771',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 1772,
    'book_describe': 'book_1772',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 1773,
    'book_describe': 'book_1773',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 1774,
    'book_describe': 'book_1774',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 1775,
    'book_describe': 'book_1775',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 1776,
    'book_describe': 'book_1776',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 1777,
    'book_describe': 'book_1777',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 1778,
    'book_describe': 'book_1778',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 1779,
    'book_describe': 'book_1779',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 1780,
    'book_describe': 'book_1780',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 1781,
    'book_describe': 'book_1781',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 1782,
    'book_describe': 'book_1782',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 1783,
    'book_describe': 'book_1783',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 1784,
    'book_describe': 'book_1784',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 1785,
    'book_describe': 'book_1785',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 1786,
    'book_describe': 'book_1786',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 1787,
    'book_describe': 'book_1787',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 1788,
    'book_describe': 'book_1788',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 1789,
    'book_describe': 'book_1789',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 1790,
    'book_describe': 'book_1790',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 1791,
    'book_describe': 'book_1791',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 1792,
    'book_describe': 'book_1792',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 1793,
    'book_describe': 'book_1793',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 1794,
    'book_describe': 'book_1794',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 1795,
    'book_describe': 'book_1795',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 1796,
    'book_describe': 'book_1796',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 1797,
    'book_describe': 'book_1797',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 1798,
    'book_describe': 'book_1798',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 1799,
    'book_describe': 'book_1799',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 1800,
    'book_describe': 'book_1800',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 1801,
    'book_describe': 'book_1801',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 1802,
    'book_describe': 'book_1802',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 1803,
    'book_describe': 'book_1803',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 1804,
    'book_describe': 'book_1804',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 1805,
    'book_describe': 'book_1805',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 1806,
    'book_describe': 'book_1806',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 1807,
    'book_describe': 'book_1807',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 1808,
    'book_describe': 'book_1808',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 1809,
    'book_describe': 'book_1809',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 1810,
    'book_describe': 'book_1810',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 1811,
    'book_describe': 'book_1811',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 1812,
    'book_describe': 'book_1812',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 1813,
    'book_describe': 'book_1813',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 1814,
    'book_describe': 'book_1814',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 1815,
    'book_describe': 'book_1815',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 1816,
    'book_describe': 'book_1816',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 1817,
    'book_describe': 'book_1817',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 1818,
    'book_describe': 'book_1818',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 1819,
    'book_describe': 'book_1819',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 1820,
    'book_describe': 'book_1820',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 1821,
    'book_describe': 'book_1821',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 1822,
    'book_describe': 'book_1822',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 1823,
    'book_describe': 'book_1823',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 1824,
    'book_describe': 'book_1824',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 1825,
    'book_describe': 'book_1825',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 1826,
    'book_describe': 'book_1826',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 1827,
    'book_describe': 'book_1827',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 1828,
    'book_describe': 'book_1828',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 1829,
    'book_describe': 'book_1829',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 1830,
    'book_describe': 'book_1830',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 1831,
    'book_describe': 'book_1831',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 1832,
    'book_describe': 'book_1832',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 1833,
    'book_describe': 'book_1833',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 1834,
    'book_describe': 'book_1834',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 1835,
    'book_describe': 'book_1835',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 1836,
    'book_describe': 'book_1836',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 1837,
    'book_describe': 'book_1837',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 1838,
    'book_describe': 'book_1838',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 1839,
    'book_describe': 'book_1839',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 1840,
    'book_describe': 'book_1840',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 1841,
    'book_describe': 'book_1841',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 1842,
    'book_describe': 'book_1842',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 1843,
    'book_describe': 'book_1843',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 1844,
    'book_describe': 'book_1844',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 1845,
    'book_describe': 'book_1845',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 1846,
    'book_describe': 'book_1846',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 1847,
    'book_describe': 'book_1847',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 1848,
    'book_describe': 'book_1848',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 1849,
    'book_describe': 'book_1849',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 1850,
    'book_describe': 'book_1850',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 1851,
    'book_describe': 'book_1851',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 1852,
    'book_describe': 'book_1852',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 1853,
    'book_describe': 'book_1853',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 1854,
    'book_describe': 'book_1854',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 1855,
    'book_describe': 'book_1855',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 1856,
    'book_describe': 'book_1856',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 1857,
    'book_describe': 'book_1857',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 1858,
    'book_describe': 'book_1858',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 1859,
    'book_describe': 'book_1859',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 1860,
    'book_describe': 'book_1860',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 1861,
    'book_describe': 'book_1861',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 1862,
    'book_describe': 'book_1862',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 1863,
    'book_describe': 'book_1863',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 1864,
    'book_describe': 'book_1864',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 1865,
    'book_describe': 'book_1865',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 1866,
    'book_describe': 'book_1866',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 1867,
    'book_describe': 'book_1867',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 1868,
    'book_describe': 'book_1868',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 1869,
    'book_describe': 'book_1869',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 1870,
    'book_describe': 'book_1870',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 1871,
    'book_describe': 'book_1871',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 1872,
    'book_describe': 'book_1872',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 1873,
    'book_describe': 'book_1873',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 1874,
    'book_describe': 'book_1874',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 1875,
    'book_describe': 'book_1875',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 1876,
    'book_describe': 'book_1876',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 1877,
    'book_describe': 'book_1877',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 1878,
    'book_describe': 'book_1878',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 1879,
    'book_describe': 'book_1879',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 1880,
    'book_describe': 'book_1880',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 1881,
    'book_describe': 'book_1881',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 1882,
    'book_describe': 'book_1882',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 1883,
    'book_describe': 'book_1883',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 1884,
    'book_describe': 'book_1884',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 1885,
    'book_describe': 'book_1885',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 1886,
    'book_describe': 'book_1886',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 1887,
    'book_describe': 'book_1887',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 1888,
    'book_describe': 'book_1888',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 1889,
    'book_describe': 'book_1889',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 1890,
    'book_describe': 'book_1890',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 1891,
    'book_describe': 'book_1891',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 1892,
    'book_describe': 'book_1892',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 1893,
    'book_describe': 'book_1893',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 1894,
    'book_describe': 'book_1894',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 1895,
    'book_describe': 'book_1895',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 1896,
    'book_describe': 'book_1896',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 1897,
    'book_describe': 'book_1897',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 1898,
    'book_describe': 'book_1898',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 1899,
    'book_describe': 'book_1899',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 1900,
    'book_describe': 'book_1900',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 1901,
    'book_describe': 'book_1901',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 1902,
    'book_describe': 'book_1902',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 1903,
    'book_describe': 'book_1903',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 1904,
    'book_describe': 'book_1904',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 1905,
    'book_describe': 'book_1905',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 1906,
    'book_describe': 'book_1906',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 1907,
    'book_describe': 'book_1907',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 1908,
    'book_describe': 'book_1908',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 1909,
    'book_describe': 'book_1909',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 1910,
    'book_describe': 'book_1910',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 1911,
    'book_describe': 'book_1911',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 1912,
    'book_describe': 'book_1912',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 1913,
    'book_describe': 'book_1913',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 1914,
    'book_describe': 'book_1914',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 1915,
    'book_describe': 'book_1915',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 1916,
    'book_describe': 'book_1916',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 1917,
    'book_describe': 'book_1917',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 1918,
    'book_describe': 'book_1918',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 1919,
    'book_describe': 'book_1919',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 1920,
    'book_describe': 'book_1920',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 1921,
    'book_describe': 'book_1921',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 1922,
    'book_describe': 'book_1922',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 1923,
    'book_describe': 'book_1923',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 1924,
    'book_describe': 'book_1924',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 1925,
    'book_describe': 'book_1925',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 1926,
    'book_describe': 'book_1926',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 1927,
    'book_describe': 'book_1927',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 1928,
    'book_describe': 'book_1928',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 1929,
    'book_describe': 'book_1929',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 1930,
    'book_describe': 'book_1930',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 1931,
    'book_describe': 'book_1931',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 1932,
    'book_describe': 'book_1932',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 1933,
    'book_describe': 'book_1933',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 1934,
    'book_describe': 'book_1934',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 1935,
    'book_describe': 'book_1935',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 1936,
    'book_describe': 'book_1936',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 1937,
    'book_describe': 'book_1937',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 1938,
    'book_describe': 'book_1938',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 1939,
    'book_describe': 'book_1939',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 1940,
    'book_describe': 'book_1940',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 1941,
    'book_describe': 'book_1941',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 1942,
    'book_describe': 'book_1942',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 1943,
    'book_describe': 'book_1943',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 1944,
    'book_describe': 'book_1944',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 1945,
    'book_describe': 'book_1945',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 1946,
    'book_describe': 'book_1946',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 1947,
    'book_describe': 'book_1947',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 1948,
    'book_describe': 'book_1948',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 1949,
    'book_describe': 'book_1949',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 1950,
    'book_describe': 'book_1950',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 1951,
    'book_describe': 'book_1951',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 1952,
    'book_describe': 'book_1952',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 1953,
    'book_describe': 'book_1953',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 1954,
    'book_describe': 'book_1954',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 1955,
    'book_describe': 'book_1955',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 1956,
    'book_describe': 'book_1956',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 1957,
    'book_describe': 'book_1957',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 1958,
    'book_describe': 'book_1958',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 1959,
    'book_describe': 'book_1959',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 1960,
    'book_describe': 'book_1960',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 1961,
    'book_describe': 'book_1961',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 1962,
    'book_describe': 'book_1962',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 1963,
    'book_describe': 'book_1963',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 1964,
    'book_describe': 'book_1964',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 1965,
    'book_describe': 'book_1965',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 1966,
    'book_describe': 'book_1966',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 1967,
    'book_describe': 'book_1967',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 1968,
    'book_describe': 'book_1968',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 1969,
    'book_describe': 'book_1969',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 1970,
    'book_describe': 'book_1970',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 1971,
    'book_describe': 'book_1971',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 1972,
    'book_describe': 'book_1972',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 1973,
    'book_describe': 'book_1973',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 1974,
    'book_describe': 'book_1974',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 1975,
    'book_describe': 'book_1975',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 1976,
    'book_describe': 'book_1976',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 1977,
    'book_describe': 'book_1977',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 1978,
    'book_describe': 'book_1978',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 1979,
    'book_describe': 'book_1979',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 1980,
    'book_describe': 'book_1980',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 1981,
    'book_describe': 'book_1981',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 1982,
    'book_describe': 'book_1982',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 1983,
    'book_describe': 'book_1983',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 1984,
    'book_describe': 'book_1984',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 1985,
    'book_describe': 'book_1985',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 1986,
    'book_describe': 'book_1986',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 1987,
    'book_describe': 'book_1987',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 1988,
    'book_describe': 'book_1988',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 1989,
    'book_describe': 'book_1989',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 1990,
    'book_describe': 'book_1990',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 1991,
    'book_describe': 'book_1991',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 1992,
    'book_describe': 'book_1992',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 1993,
    'book_describe': 'book_1993',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 1994,
    'book_describe': 'book_1994',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 1995,
    'book_describe': 'book_1995',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 1996,
    'book_describe': 'book_1996',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 1997,
    'book_describe': 'book_1997',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 1998,
    'book_describe': 'book_1998',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 1999,
    'book_describe': 'book_1999',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 2000,
    'book_describe': 'book_2000',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 2001,
    'book_describe': 'book_2001',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 2002,
    'book_describe': 'book_2002',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 2003,
    'book_describe': 'book_2003',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 2004,
    'book_describe': 'book_2004',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 2005,
    'book_describe': 'book_2005',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 2006,
    'book_describe': 'book_2006',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 2007,
    'book_describe': 'book_2007',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 2008,
    'book_describe': 'book_2008',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 2009,
    'book_describe': 'book_2009',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 2010,
    'book_describe': 'book_2010',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 2011,
    'book_describe': 'book_2011',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 2012,
    'book_describe': 'book_2012',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 2013,
    'book_describe': 'book_2013',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 2014,
    'book_describe': 'book_2014',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 2015,
    'book_describe': 'book_2015',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 2016,
    'book_describe': 'book_2016',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 2017,
    'book_describe': 'book_2017',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 2018,
    'book_describe': 'book_2018',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 2019,
    'book_describe': 'book_2019',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 2020,
    'book_describe': 'book_2020',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 2021,
    'book_describe': 'book_2021',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 2022,
    'book_describe': 'book_2022',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 2023,
    'book_describe': 'book_2023',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 2024,
    'book_describe': 'book_2024',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 2025,
    'book_describe': 'book_2025',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 2026,
    'book_describe': 'book_2026',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 2027,
    'book_describe': 'book_2027',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 2028,
    'book_describe': 'book_2028',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 2029,
    'book_describe': 'book_2029',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 2030,
    'book_describe': 'book_2030',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 2031,
    'book_describe': 'book_2031',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 2032,
    'book_describe': 'book_2032',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 2033,
    'book_describe': 'book_2033',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 2034,
    'book_describe': 'book_2034',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 2035,
    'book_describe': 'book_2035',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 2036,
    'book_describe': 'book_2036',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 2037,
    'book_describe': 'book_2037',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 2038,
    'book_describe': 'book_2038',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 2039,
    'book_describe': 'book_2039',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 2040,
    'book_describe': 'book_2040',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 2041,
    'book_describe': 'book_2041',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 2042,
    'book_describe': 'book_2042',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 2043,
    'book_describe': 'book_2043',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 2044,
    'book_describe': 'book_2044',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 2045,
    'book_describe': 'book_2045',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 2046,
    'book_describe': 'book_2046',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 2047,
    'book_describe': 'book_2047',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 2048,
    'book_describe': 'book_2048',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 2049,
    'book_describe': 'book_2049',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 2050,
    'book_describe': 'book_2050',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 2051,
    'book_describe': 'book_2051',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 2052,
    'book_describe': 'book_2052',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 2053,
    'book_describe': 'book_2053',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 2054,
    'book_describe': 'book_2054',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 2055,
    'book_describe': 'book_2055',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 2056,
    'book_describe': 'book_2056',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 2057,
    'book_describe': 'book_2057',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 2058,
    'book_describe': 'book_2058',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 2059,
    'book_describe': 'book_2059',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 2060,
    'book_describe': 'book_2060',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 2061,
    'book_describe': 'book_2061',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 2062,
    'book_describe': 'book_2062',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 2063,
    'book_describe': 'book_2063',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 2064,
    'book_describe': 'book_2064',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 2065,
    'book_describe': 'book_2065',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 2066,
    'book_describe': 'book_2066',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 2067,
    'book_describe': 'book_2067',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 2068,
    'book_describe': 'book_2068',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 2069,
    'book_describe': 'book_2069',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 2070,
    'book_describe': 'book_2070',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 2071,
    'book_describe': 'book_2071',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 2072,
    'book_describe': 'book_2072',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 2073,
    'book_describe': 'book_2073',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 2074,
    'book_describe': 'book_2074',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 2075,
    'book_describe': 'book_2075',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 2076,
    'book_describe': 'book_2076',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 2077,
    'book_describe': 'book_2077',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 2078,
    'book_describe': 'book_2078',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 2079,
    'book_describe': 'book_2079',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 2080,
    'book_describe': 'book_2080',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 2081,
    'book_describe': 'book_2081',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 2082,
    'book_describe': 'book_2082',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 2083,
    'book_describe': 'book_2083',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 2084,
    'book_describe': 'book_2084',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 2085,
    'book_describe': 'book_2085',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 2086,
    'book_describe': 'book_2086',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 2087,
    'book_describe': 'book_2087',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 2088,
    'book_describe': 'book_2088',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 2089,
    'book_describe': 'book_2089',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 2090,
    'book_describe': 'book_2090',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 2091,
    'book_describe': 'book_2091',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 2092,
    'book_describe': 'book_2092',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 2093,
    'book_describe': 'book_2093',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 2094,
    'book_describe': 'book_2094',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 2095,
    'book_describe': 'book_2095',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 2096,
    'book_describe': 'book_2096',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 2097,
    'book_describe': 'book_2097',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 2098,
    'book_describe': 'book_2098',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 2099,
    'book_describe': 'book_2099',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 2100,
    'book_describe': 'book_2100',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 2101,
    'book_describe': 'book_2101',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 2102,
    'book_describe': 'book_2102',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 2103,
    'book_describe': 'book_2103',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 2104,
    'book_describe': 'book_2104',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 2105,
    'book_describe': 'book_2105',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 2106,
    'book_describe': 'book_2106',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 2107,
    'book_describe': 'book_2107',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 2108,
    'book_describe': 'book_2108',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 2109,
    'book_describe': 'book_2109',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 2110,
    'book_describe': 'book_2110',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 2111,
    'book_describe': 'book_2111',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 2112,
    'book_describe': 'book_2112',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 2113,
    'book_describe': 'book_2113',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 2114,
    'book_describe': 'book_2114',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 2115,
    'book_describe': 'book_2115',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 2116,
    'book_describe': 'book_2116',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 2117,
    'book_describe': 'book_2117',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 2118,
    'book_describe': 'book_2118',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 2119,
    'book_describe': 'book_2119',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 2120,
    'book_describe': 'book_2120',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 2121,
    'book_describe': 'book_2121',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 2122,
    'book_describe': 'book_2122',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 2123,
    'book_describe': 'book_2123',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 2124,
    'book_describe': 'book_2124',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 2125,
    'book_describe': 'book_2125',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 2126,
    'book_describe': 'book_2126',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 2127,
    'book_describe': 'book_2127',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 2128,
    'book_describe': 'book_2128',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 2129,
    'book_describe': 'book_2129',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 2130,
    'book_describe': 'book_2130',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 2131,
    'book_describe': 'book_2131',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 2132,
    'book_describe': 'book_2132',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 2133,
    'book_describe': 'book_2133',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 2134,
    'book_describe': 'book_2134',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 2135,
    'book_describe': 'book_2135',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 2136,
    'book_describe': 'book_2136',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 2137,
    'book_describe': 'book_2137',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 2138,
    'book_describe': 'book_2138',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 2139,
    'book_describe': 'book_2139',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 2140,
    'book_describe': 'book_2140',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 2141,
    'book_describe': 'book_2141',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 2142,
    'book_describe': 'book_2142',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 2143,
    'book_describe': 'book_2143',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 2144,
    'book_describe': 'book_2144',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 2145,
    'book_describe': 'book_2145',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 2146,
    'book_describe': 'book_2146',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 2147,
    'book_describe': 'book_2147',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 2148,
    'book_describe': 'book_2148',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 2149,
    'book_describe': 'book_2149',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 2150,
    'book_describe': 'book_2150',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 2151,
    'book_describe': 'book_2151',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 2152,
    'book_describe': 'book_2152',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 2153,
    'book_describe': 'book_2153',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 2154,
    'book_describe': 'book_2154',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 2155,
    'book_describe': 'book_2155',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 2156,
    'book_describe': 'book_2156',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 2157,
    'book_describe': 'book_2157',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 2158,
    'book_describe': 'book_2158',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 2159,
    'book_describe': 'book_2159',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 2160,
    'book_describe': 'book_2160',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 2161,
    'book_describe': 'book_2161',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 2162,
    'book_describe': 'book_2162',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 2163,
    'book_describe': 'book_2163',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 2164,
    'book_describe': 'book_2164',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 2165,
    'book_describe': 'book_2165',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 2166,
    'book_describe': 'book_2166',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 2167,
    'book_describe': 'book_2167',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 2168,
    'book_describe': 'book_2168',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 2169,
    'book_describe': 'book_2169',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 2170,
    'book_describe': 'book_2170',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 2171,
    'book_describe': 'book_2171',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 2172,
    'book_describe': 'book_2172',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 2173,
    'book_describe': 'book_2173',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 2174,
    'book_describe': 'book_2174',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 2175,
    'book_describe': 'book_2175',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 2176,
    'book_describe': 'book_2176',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 2177,
    'book_describe': 'book_2177',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 2178,
    'book_describe': 'book_2178',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 2179,
    'book_describe': 'book_2179',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 2180,
    'book_describe': 'book_2180',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 2181,
    'book_describe': 'book_2181',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 2182,
    'book_describe': 'book_2182',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 2183,
    'book_describe': 'book_2183',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 2184,
    'book_describe': 'book_2184',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 2185,
    'book_describe': 'book_2185',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 2186,
    'book_describe': 'book_2186',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 2187,
    'book_describe': 'book_2187',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 2188,
    'book_describe': 'book_2188',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 2189,
    'book_describe': 'book_2189',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 2190,
    'book_describe': 'book_2190',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 2191,
    'book_describe': 'book_2191',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 2192,
    'book_describe': 'book_2192',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 2193,
    'book_describe': 'book_2193',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 2194,
    'book_describe': 'book_2194',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 2195,
    'book_describe': 'book_2195',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 2196,
    'book_describe': 'book_2196',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 2197,
    'book_describe': 'book_2197',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 2198,
    'book_describe': 'book_2198',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 2199,
    'book_describe': 'book_2199',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 2200,
    'book_describe': 'book_2200',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 2201,
    'book_describe': 'book_2201',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 2202,
    'book_describe': 'book_2202',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 2203,
    'book_describe': 'book_2203',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 2204,
    'book_describe': 'book_2204',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 2205,
    'book_describe': 'book_2205',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 2206,
    'book_describe': 'book_2206',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 2207,
    'book_describe': 'book_2207',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 2208,
    'book_describe': 'book_2208',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 2209,
    'book_describe': 'book_2209',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 2210,
    'book_describe': 'book_2210',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 2211,
    'book_describe': 'book_2211',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 2212,
    'book_describe': 'book_2212',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 2213,
    'book_describe': 'book_2213',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 2214,
    'book_describe': 'book_2214',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 2215,
    'book_describe': 'book_2215',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 2216,
    'book_describe': 'book_2216',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 2217,
    'book_describe': 'book_2217',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 2218,
    'book_describe': 'book_2218',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 2219,
    'book_describe': 'book_2219',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 2220,
    'book_describe': 'book_2220',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 2221,
    'book_describe': 'book_2221',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 2222,
    'book_describe': 'book_2222',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 2223,
    'book_describe': 'book_2223',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 2224,
    'book_describe': 'book_2224',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 2225,
    'book_describe': 'book_2225',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 2226,
    'book_describe': 'book_2226',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 2227,
    'book_describe': 'book_2227',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 2228,
    'book_describe': 'book_2228',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 2229,
    'book_describe': 'book_2229',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 2230,
    'book_describe': 'book_2230',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 2231,
    'book_describe': 'book_2231',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 2232,
    'book_describe': 'book_2232',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 2233,
    'book_describe': 'book_2233',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 2234,
    'book_describe': 'book_2234',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 2235,
    'book_describe': 'book_2235',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 2236,
    'book_describe': 'book_2236',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 2237,
    'book_describe': 'book_2237',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 2238,
    'book_describe': 'book_2238',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 2239,
    'book_describe': 'book_2239',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 2240,
    'book_describe': 'book_2240',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 2241,
    'book_describe': 'book_2241',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 2242,
    'book_describe': 'book_2242',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 2243,
    'book_describe': 'book_2243',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 2244,
    'book_describe': 'book_2244',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 2245,
    'book_describe': 'book_2245',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 2246,
    'book_describe': 'book_2246',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 2247,
    'book_describe': 'book_2247',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 2248,
    'book_describe': 'book_2248',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 2249,
    'book_describe': 'book_2249',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 2250,
    'book_describe': 'book_2250',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 2251,
    'book_describe': 'book_2251',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 2252,
    'book_describe': 'book_2252',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 2253,
    'book_describe': 'book_2253',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 2254,
    'book_describe': 'book_2254',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 2255,
    'book_describe': 'book_2255',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 2256,
    'book_describe': 'book_2256',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 2257,
    'book_describe': 'book_2257',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 2258,
    'book_describe': 'book_2258',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 2259,
    'book_describe': 'book_2259',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 2260,
    'book_describe': 'book_2260',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 2261,
    'book_describe': 'book_2261',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 2262,
    'book_describe': 'book_2262',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 2263,
    'book_describe': 'book_2263',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 2264,
    'book_describe': 'book_2264',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 2265,
    'book_describe': 'book_2265',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 2266,
    'book_describe': 'book_2266',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 2267,
    'book_describe': 'book_2267',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 2268,
    'book_describe': 'book_2268',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 2269,
    'book_describe': 'book_2269',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 2270,
    'book_describe': 'book_2270',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 2271,
    'book_describe': 'book_2271',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 2272,
    'book_describe': 'book_2272',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 2273,
    'book_describe': 'book_2273',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 2274,
    'book_describe': 'book_2274',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 2275,
    'book_describe': 'book_2275',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 2276,
    'book_describe': 'book_2276',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 2277,
    'book_describe': 'book_2277',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 2278,
    'book_describe': 'book_2278',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 2279,
    'book_describe': 'book_2279',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 2280,
    'book_describe': 'book_2280',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 2281,
    'book_describe': 'book_2281',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 2282,
    'book_describe': 'book_2282',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 2283,
    'book_describe': 'book_2283',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 2284,
    'book_describe': 'book_2284',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 2285,
    'book_describe': 'book_2285',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 2286,
    'book_describe': 'book_2286',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 2287,
    'book_describe': 'book_2287',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 2288,
    'book_describe': 'book_2288',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 2289,
    'book_describe': 'book_2289',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 2290,
    'book_describe': 'book_2290',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 2291,
    'book_describe': 'book_2291',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 2292,
    'book_describe': 'book_2292',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 2293,
    'book_describe': 'book_2293',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 2294,
    'book_describe': 'book_2294',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 2295,
    'book_describe': 'book_2295',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 2296,
    'book_describe': 'book_2296',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 2297,
    'book_describe': 'book_2297',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 2298,
    'book_describe': 'book_2298',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 2299,
    'book_describe': 'book_2299',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 2300,
    'book_describe': 'book_2300',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 2301,
    'book_describe': 'book_2301',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 2302,
    'book_describe': 'book_2302',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 2303,
    'book_describe': 'book_2303',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 2304,
    'book_describe': 'book_2304',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 2305,
    'book_describe': 'book_2305',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 2306,
    'book_describe': 'book_2306',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 2307,
    'book_describe': 'book_2307',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 2308,
    'book_describe': 'book_2308',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 2309,
    'book_describe': 'book_2309',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 2310,
    'book_describe': 'book_2310',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 2311,
    'book_describe': 'book_2311',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 2312,
    'book_describe': 'book_2312',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 2313,
    'book_describe': 'book_2313',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 2314,
    'book_describe': 'book_2314',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 2315,
    'book_describe': 'book_2315',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 2316,
    'book_describe': 'book_2316',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 2317,
    'book_describe': 'book_2317',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 2318,
    'book_describe': 'book_2318',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 2319,
    'book_describe': 'book_2319',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 2320,
    'book_describe': 'book_2320',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 2321,
    'book_describe': 'book_2321',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 2322,
    'book_describe': 'book_2322',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 2323,
    'book_describe': 'book_2323',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 2324,
    'book_describe': 'book_2324',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 2325,
    'book_describe': 'book_2325',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 2326,
    'book_describe': 'book_2326',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 2327,
    'book_describe': 'book_2327',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 2328,
    'book_describe': 'book_2328',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 2329,
    'book_describe': 'book_2329',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 2330,
    'book_describe': 'book_2330',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 2331,
    'book_describe': 'book_2331',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 2332,
    'book_describe': 'book_2332',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 2333,
    'book_describe': 'book_2333',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 2334,
    'book_describe': 'book_2334',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 2335,
    'book_describe': 'book_2335',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 2336,
    'book_describe': 'book_2336',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 2337,
    'book_describe': 'book_2337',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 2338,
    'book_describe': 'book_2338',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 2339,
    'book_describe': 'book_2339',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 2340,
    'book_describe': 'book_2340',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 2341,
    'book_describe': 'book_2341',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 2342,
    'book_describe': 'book_2342',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 2343,
    'book_describe': 'book_2343',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 2344,
    'book_describe': 'book_2344',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 2345,
    'book_describe': 'book_2345',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 2346,
    'book_describe': 'book_2346',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 2347,
    'book_describe': 'book_2347',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 2348,
    'book_describe': 'book_2348',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 2349,
    'book_describe': 'book_2349',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 2350,
    'book_describe': 'book_2350',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 2351,
    'book_describe': 'book_2351',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 2352,
    'book_describe': 'book_2352',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 2353,
    'book_describe': 'book_2353',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 2354,
    'book_describe': 'book_2354',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 2355,
    'book_describe': 'book_2355',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 2356,
    'book_describe': 'book_2356',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 2357,
    'book_describe': 'book_2357',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 2358,
    'book_describe': 'book_2358',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 2359,
    'book_describe': 'book_2359',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 2360,
    'book_describe': 'book_2360',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 2361,
    'book_describe': 'book_2361',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 2362,
    'book_describe': 'book_2362',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 2363,
    'book_describe': 'book_2363',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 2364,
    'book_describe': 'book_2364',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 2365,
    'book_describe': 'book_2365',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 2366,
    'book_describe': 'book_2366',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 2367,
    'book_describe': 'book_2367',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 2368,
    'book_describe': 'book_2368',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 2369,
    'book_describe': 'book_2369',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 2370,
    'book_describe': 'book_2370',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 2371,
    'book_describe': 'book_2371',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 2372,
    'book_describe': 'book_2372',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 2373,
    'book_describe': 'book_2373',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 2374,
    'book_describe': 'book_2374',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 2375,
    'book_describe': 'book_2375',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 2376,
    'book_describe': 'book_2376',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 2377,
    'book_describe': 'book_2377',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 2378,
    'book_describe': 'book_2378',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 2379,
    'book_describe': 'book_2379',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 2380,
    'book_describe': 'book_2380',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 2381,
    'book_describe': 'book_2381',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 2382,
    'book_describe': 'book_2382',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 2383,
    'book_describe': 'book_2383',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 2384,
    'book_describe': 'book_2384',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 2385,
    'book_describe': 'book_2385',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 2386,
    'book_describe': 'book_2386',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 2387,
    'book_describe': 'book_2387',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 2388,
    'book_describe': 'book_2388',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 2389,
    'book_describe': 'book_2389',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 2390,
    'book_describe': 'book_2390',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 2391,
    'book_describe': 'book_2391',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 2392,
    'book_describe': 'book_2392',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 2393,
    'book_describe': 'book_2393',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 2394,
    'book_describe': 'book_2394',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 2395,
    'book_describe': 'book_2395',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 2396,
    'book_describe': 'book_2396',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 2397,
    'book_describe': 'book_2397',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 2398,
    'book_describe': 'book_2398',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 2399,
    'book_describe': 'book_2399',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 2400,
    'book_describe': 'book_2400',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 2401,
    'book_describe': 'book_2401',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 2402,
    'book_describe': 'book_2402',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 2403,
    'book_describe': 'book_2403',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 2404,
    'book_describe': 'book_2404',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 2405,
    'book_describe': 'book_2405',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 2406,
    'book_describe': 'book_2406',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 2407,
    'book_describe': 'book_2407',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 2408,
    'book_describe': 'book_2408',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 2409,
    'book_describe': 'book_2409',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 2410,
    'book_describe': 'book_2410',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 2411,
    'book_describe': 'book_2411',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 2412,
    'book_describe': 'book_2412',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 2413,
    'book_describe': 'book_2413',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 2414,
    'book_describe': 'book_2414',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 2415,
    'book_describe': 'book_2415',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 2416,
    'book_describe': 'book_2416',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 2417,
    'book_describe': 'book_2417',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 2418,
    'book_describe': 'book_2418',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 2419,
    'book_describe': 'book_2419',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 2420,
    'book_describe': 'book_2420',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 2421,
    'book_describe': 'book_2421',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 2422,
    'book_describe': 'book_2422',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 2423,
    'book_describe': 'book_2423',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 2424,
    'book_describe': 'book_2424',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 2425,
    'book_describe': 'book_2425',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 2426,
    'book_describe': 'book_2426',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 2427,
    'book_describe': 'book_2427',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 2428,
    'book_describe': 'book_2428',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 2429,
    'book_describe': 'book_2429',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 2430,
    'book_describe': 'book_2430',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 2431,
    'book_describe': 'book_2431',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 2432,
    'book_describe': 'book_2432',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 2433,
    'book_describe': 'book_2433',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 2434,
    'book_describe': 'book_2434',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 2435,
    'book_describe': 'book_2435',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 2436,
    'book_describe': 'book_2436',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 2437,
    'book_describe': 'book_2437',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 2438,
    'book_describe': 'book_2438',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 2439,
    'book_describe': 'book_2439',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 2440,
    'book_describe': 'book_2440',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 2441,
    'book_describe': 'book_2441',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 2442,
    'book_describe': 'book_2442',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 2443,
    'book_describe': 'book_2443',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 2444,
    'book_describe': 'book_2444',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 2445,
    'book_describe': 'book_2445',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 2446,
    'book_describe': 'book_2446',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 2447,
    'book_describe': 'book_2447',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 2448,
    'book_describe': 'book_2448',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 2449,
    'book_describe': 'book_2449',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 2450,
    'book_describe': 'book_2450',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 2451,
    'book_describe': 'book_2451',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 2452,
    'book_describe': 'book_2452',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 2453,
    'book_describe': 'book_2453',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 2454,
    'book_describe': 'book_2454',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 2455,
    'book_describe': 'book_2455',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 2456,
    'book_describe': 'book_2456',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 2457,
    'book_describe': 'book_2457',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 2458,
    'book_describe': 'book_2458',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 2459,
    'book_describe': 'book_2459',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 2460,
    'book_describe': 'book_2460',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 2461,
    'book_describe': 'book_2461',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 2462,
    'book_describe': 'book_2462',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 2463,
    'book_describe': 'book_2463',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 2464,
    'book_describe': 'book_2464',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 2465,
    'book_describe': 'book_2465',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 2466,
    'book_describe': 'book_2466',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 2467,
    'book_describe': 'book_2467',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 2468,
    'book_describe': 'book_2468',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 2469,
    'book_describe': 'book_2469',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 2470,
    'book_describe': 'book_2470',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 2471,
    'book_describe': 'book_2471',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 2472,
    'book_describe': 'book_2472',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 2473,
    'book_describe': 'book_2473',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 2474,
    'book_describe': 'book_2474',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 2475,
    'book_describe': 'book_2475',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 2476,
    'book_describe': 'book_2476',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 2477,
    'book_describe': 'book_2477',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 2478,
    'book_describe': 'book_2478',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 2479,
    'book_describe': 'book_2479',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 2480,
    'book_describe': 'book_2480',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 2481,
    'book_describe': 'book_2481',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 2482,
    'book_describe': 'book_2482',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 2483,
    'book_describe': 'book_2483',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 2484,
    'book_describe': 'book_2484',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 2485,
    'book_describe': 'book_2485',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 2486,
    'book_describe': 'book_2486',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 2487,
    'book_describe': 'book_2487',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 2488,
    'book_describe': 'book_2488',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 2489,
    'book_describe': 'book_2489',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 2490,
    'book_describe': 'book_2490',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 2491,
    'book_describe': 'book_2491',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 2492,
    'book_describe': 'book_2492',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 2493,
    'book_describe': 'book_2493',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 2494,
    'book_describe': 'book_2494',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 2495,
    'book_describe': 'book_2495',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 2496,
    'book_describe': 'book_2496',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 2497,
    'book_describe': 'book_2497',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 2498,
    'book_describe': 'book_2498',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 2499,
    'book_describe': 'book_2499',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 2500,
    'book_describe': 'book_2500',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 2501,
    'book_describe': 'book_2501',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 2502,
    'book_describe': 'book_2502',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 2503,
    'book_describe': 'book_2503',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 2504,
    'book_describe': 'book_2504',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 2505,
    'book_describe': 'book_2505',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 2506,
    'book_describe': 'book_2506',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 2507,
    'book_describe': 'book_2507',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 2508,
    'book_describe': 'book_2508',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 2509,
    'book_describe': 'book_2509',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 2510,
    'book_describe': 'book_2510',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 2511,
    'book_describe': 'book_2511',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 2512,
    'book_describe': 'book_2512',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 2513,
    'book_describe': 'book_2513',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 2514,
    'book_describe': 'book_2514',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 2515,
    'book_describe': 'book_2515',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 2516,
    'book_describe': 'book_2516',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 2517,
    'book_describe': 'book_2517',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 2518,
    'book_describe': 'book_2518',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 2519,
    'book_describe': 'book_2519',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 2520,
    'book_describe': 'book_2520',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 2521,
    'book_describe': 'book_2521',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 2522,
    'book_describe': 'book_2522',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 2523,
    'book_describe': 'book_2523',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 2524,
    'book_describe': 'book_2524',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 2525,
    'book_describe': 'book_2525',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 2526,
    'book_describe': 'book_2526',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 2527,
    'book_describe': 'book_2527',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 2528,
    'book_describe': 'book_2528',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 2529,
    'book_describe': 'book_2529',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 2530,
    'book_describe': 'book_2530',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 2531,
    'book_describe': 'book_2531',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 2532,
    'book_describe': 'book_2532',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 2533,
    'book_describe': 'book_2533',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 2534,
    'book_describe': 'book_2534',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 2535,
    'book_describe': 'book_2535',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 2536,
    'book_describe': 'book_2536',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 2537,
    'book_describe': 'book_2537',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 2538,
    'book_describe': 'book_2538',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 2539,
    'book_describe': 'book_2539',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 2540,
    'book_describe': 'book_2540',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 2541,
    'book_describe': 'book_2541',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 2542,
    'book_describe': 'book_2542',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 2543,
    'book_describe': 'book_2543',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 2544,
    'book_describe': 'book_2544',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 2545,
    'book_describe': 'book_2545',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 2546,
    'book_describe': 'book_2546',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 2547,
    'book_describe': 'book_2547',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 2548,
    'book_describe': 'book_2548',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 2549,
    'book_describe': 'book_2549',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 2550,
    'book_describe': 'book_2550',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 2551,
    'book_describe': 'book_2551',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 2552,
    'book_describe': 'book_2552',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 2553,
    'book_describe': 'book_2553',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 2554,
    'book_describe': 'book_2554',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 2555,
    'book_describe': 'book_2555',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 2556,
    'book_describe': 'book_2556',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 2557,
    'book_describe': 'book_2557',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 2558,
    'book_describe': 'book_2558',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 2559,
    'book_describe': 'book_2559',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 2560,
    'book_describe': 'book_2560',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 2561,
    'book_describe': 'book_2561',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 2562,
    'book_describe': 'book_2562',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 2563,
    'book_describe': 'book_2563',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 2564,
    'book_describe': 'book_2564',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 2565,
    'book_describe': 'book_2565',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 2566,
    'book_describe': 'book_2566',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 2567,
    'book_describe': 'book_2567',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 2568,
    'book_describe': 'book_2568',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 2569,
    'book_describe': 'book_2569',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 2570,
    'book_describe': 'book_2570',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 2571,
    'book_describe': 'book_2571',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 2572,
    'book_describe': 'book_2572',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 2573,
    'book_describe': 'book_2573',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 2574,
    'book_describe': 'book_2574',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 2575,
    'book_describe': 'book_2575',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 2576,
    'book_describe': 'book_2576',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 2577,
    'book_describe': 'book_2577',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 2578,
    'book_describe': 'book_2578',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 2579,
    'book_describe': 'book_2579',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 2580,
    'book_describe': 'book_2580',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 2581,
    'book_describe': 'book_2581',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 2582,
    'book_describe': 'book_2582',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 2583,
    'book_describe': 'book_2583',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 2584,
    'book_describe': 'book_2584',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 2585,
    'book_describe': 'book_2585',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 2586,
    'book_describe': 'book_2586',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 2587,
    'book_describe': 'book_2587',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 2588,
    'book_describe': 'book_2588',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 2589,
    'book_describe': 'book_2589',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 2590,
    'book_describe': 'book_2590',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 2591,
    'book_describe': 'book_2591',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 2592,
    'book_describe': 'book_2592',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 2593,
    'book_describe': 'book_2593',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 2594,
    'book_describe': 'book_2594',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 2595,
    'book_describe': 'book_2595',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 2596,
    'book_describe': 'book_2596',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 2597,
    'book_describe': 'book_2597',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 2598,
    'book_describe': 'book_2598',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 2599,
    'book_describe': 'book_2599',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 2600,
    'book_describe': 'book_2600',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 2601,
    'book_describe': 'book_2601',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 2602,
    'book_describe': 'book_2602',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 2603,
    'book_describe': 'book_2603',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 2604,
    'book_describe': 'book_2604',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 2605,
    'book_describe': 'book_2605',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 2606,
    'book_describe': 'book_2606',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 2607,
    'book_describe': 'book_2607',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 2608,
    'book_describe': 'book_2608',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 2609,
    'book_describe': 'book_2609',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 2610,
    'book_describe': 'book_2610',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 2611,
    'book_describe': 'book_2611',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 2612,
    'book_describe': 'book_2612',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 2613,
    'book_describe': 'book_2613',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 2614,
    'book_describe': 'book_2614',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 2615,
    'book_describe': 'book_2615',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 2616,
    'book_describe': 'book_2616',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 2617,
    'book_describe': 'book_2617',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 2618,
    'book_describe': 'book_2618',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 2619,
    'book_describe': 'book_2619',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 2620,
    'book_describe': 'book_2620',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 2621,
    'book_describe': 'book_2621',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 2622,
    'book_describe': 'book_2622',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 2623,
    'book_describe': 'book_2623',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 2624,
    'book_describe': 'book_2624',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 2625,
    'book_describe': 'book_2625',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 2626,
    'book_describe': 'book_2626',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 2627,
    'book_describe': 'book_2627',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 2628,
    'book_describe': 'book_2628',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 2629,
    'book_describe': 'book_2629',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 2630,
    'book_describe': 'book_2630',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 2631,
    'book_describe': 'book_2631',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 2632,
    'book_describe': 'book_2632',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 2633,
    'book_describe': 'book_2633',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 2634,
    'book_describe': 'book_2634',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 2635,
    'book_describe': 'book_2635',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 2636,
    'book_describe': 'book_2636',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 2637,
    'book_describe': 'book_2637',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 2638,
    'book_describe': 'book_2638',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 2639,
    'book_describe': 'book_2639',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 2640,
    'book_describe': 'book_2640',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 2641,
    'book_describe': 'book_2641',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 2642,
    'book_describe': 'book_2642',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 2643,
    'book_describe': 'book_2643',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 2644,
    'book_describe': 'book_2644',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 2645,
    'book_describe': 'book_2645',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 2646,
    'book_describe': 'book_2646',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 2647,
    'book_describe': 'book_2647',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 2648,
    'book_describe': 'book_2648',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 2649,
    'book_describe': 'book_2649',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 2650,
    'book_describe': 'book_2650',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 2651,
    'book_describe': 'book_2651',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 2652,
    'book_describe': 'book_2652',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 2653,
    'book_describe': 'book_2653',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 2654,
    'book_describe': 'book_2654',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 2655,
    'book_describe': 'book_2655',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 2656,
    'book_describe': 'book_2656',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 2657,
    'book_describe': 'book_2657',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 2658,
    'book_describe': 'book_2658',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 2659,
    'book_describe': 'book_2659',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 2660,
    'book_describe': 'book_2660',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 2661,
    'book_describe': 'book_2661',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 2662,
    'book_describe': 'book_2662',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 2663,
    'book_describe': 'book_2663',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 2664,
    'book_describe': 'book_2664',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 2665,
    'book_describe': 'book_2665',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 2666,
    'book_describe': 'book_2666',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 2667,
    'book_describe': 'book_2667',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 2668,
    'book_describe': 'book_2668',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 2669,
    'book_describe': 'book_2669',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 2670,
    'book_describe': 'book_2670',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 2671,
    'book_describe': 'book_2671',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 2672,
    'book_describe': 'book_2672',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 2673,
    'book_describe': 'book_2673',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 2674,
    'book_describe': 'book_2674',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 2675,
    'book_describe': 'book_2675',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 2676,
    'book_describe': 'book_2676',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 2677,
    'book_describe': 'book_2677',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 2678,
    'book_describe': 'book_2678',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 2679,
    'book_describe': 'book_2679',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 2680,
    'book_describe': 'book_2680',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 2681,
    'book_describe': 'book_2681',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 2682,
    'book_describe': 'book_2682',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 2683,
    'book_describe': 'book_2683',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 2684,
    'book_describe': 'book_2684',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 2685,
    'book_describe': 'book_2685',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 2686,
    'book_describe': 'book_2686',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 2687,
    'book_describe': 'book_2687',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 2688,
    'book_describe': 'book_2688',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 2689,
    'book_describe': 'book_2689',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 2690,
    'book_describe': 'book_2690',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 2691,
    'book_describe': 'book_2691',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 2692,
    'book_describe': 'book_2692',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 2693,
    'book_describe': 'book_2693',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 2694,
    'book_describe': 'book_2694',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 2695,
    'book_describe': 'book_2695',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 2696,
    'book_describe': 'book_2696',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 2697,
    'book_describe': 'book_2697',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 2698,
    'book_describe': 'book_2698',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 2699,
    'book_describe': 'book_2699',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 2700,
    'book_describe': 'book_2700',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 2701,
    'book_describe': 'book_2701',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 2702,
    'book_describe': 'book_2702',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 2703,
    'book_describe': 'book_2703',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 2704,
    'book_describe': 'book_2704',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 2705,
    'book_describe': 'book_2705',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 2706,
    'book_describe': 'book_2706',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 2707,
    'book_describe': 'book_2707',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 2708,
    'book_describe': 'book_2708',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 2709,
    'book_describe': 'book_2709',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 2710,
    'book_describe': 'book_2710',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 2711,
    'book_describe': 'book_2711',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 2712,
    'book_describe': 'book_2712',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 2713,
    'book_describe': 'book_2713',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 2714,
    'book_describe': 'book_2714',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 2715,
    'book_describe': 'book_2715',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 2716,
    'book_describe': 'book_2716',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 2717,
    'book_describe': 'book_2717',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 2718,
    'book_describe': 'book_2718',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 2719,
    'book_describe': 'book_2719',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 2720,
    'book_describe': 'book_2720',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 2721,
    'book_describe': 'book_2721',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 2722,
    'book_describe': 'book_2722',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 2723,
    'book_describe': 'book_2723',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 2724,
    'book_describe': 'book_2724',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 2725,
    'book_describe': 'book_2725',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 2726,
    'book_describe': 'book_2726',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 2727,
    'book_describe': 'book_2727',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 2728,
    'book_describe': 'book_2728',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 2729,
    'book_describe': 'book_2729',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 2730,
    'book_describe': 'book_2730',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 2731,
    'book_describe': 'book_2731',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 2732,
    'book_describe': 'book_2732',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 2733,
    'book_describe': 'book_2733',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 2734,
    'book_describe': 'book_2734',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 2735,
    'book_describe': 'book_2735',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 2736,
    'book_describe': 'book_2736',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 2737,
    'book_describe': 'book_2737',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 2738,
    'book_describe': 'book_2738',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 2739,
    'book_describe': 'book_2739',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 2740,
    'book_describe': 'book_2740',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 2741,
    'book_describe': 'book_2741',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 2742,
    'book_describe': 'book_2742',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 2743,
    'book_describe': 'book_2743',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 2744,
    'book_describe': 'book_2744',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 2745,
    'book_describe': 'book_2745',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 2746,
    'book_describe': 'book_2746',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 2747,
    'book_describe': 'book_2747',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 2748,
    'book_describe': 'book_2748',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 2749,
    'book_describe': 'book_2749',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 2750,
    'book_describe': 'book_2750',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 2751,
    'book_describe': 'book_2751',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 2752,
    'book_describe': 'book_2752',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 2753,
    'book_describe': 'book_2753',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 2754,
    'book_describe': 'book_2754',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 2755,
    'book_describe': 'book_2755',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 2756,
    'book_describe': 'book_2756',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 2757,
    'book_describe': 'book_2757',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 2758,
    'book_describe': 'book_2758',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 2759,
    'book_describe': 'book_2759',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 2760,
    'book_describe': 'book_2760',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 2761,
    'book_describe': 'book_2761',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 2762,
    'book_describe': 'book_2762',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 2763,
    'book_describe': 'book_2763',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 2764,
    'book_describe': 'book_2764',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 2765,
    'book_describe': 'book_2765',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 2766,
    'book_describe': 'book_2766',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 2767,
    'book_describe': 'book_2767',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 2768,
    'book_describe': 'book_2768',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 2769,
    'book_describe': 'book_2769',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 2770,
    'book_describe': 'book_2770',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 2771,
    'book_describe': 'book_2771',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 2772,
    'book_describe': 'book_2772',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 2773,
    'book_describe': 'book_2773',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 2774,
    'book_describe': 'book_2774',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 2775,
    'book_describe': 'book_2775',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 2776,
    'book_describe': 'book_2776',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 2777,
    'book_describe': 'book_2777',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 2778,
    'book_describe': 'book_2778',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 2779,
    'book_describe': 'book_2779',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 2780,
    'book_describe': 'book_2780',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 2781,
    'book_describe': 'book_2781',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 2782,
    'book_describe': 'book_2782',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 2783,
    'book_describe': 'book_2783',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 2784,
    'book_describe': 'book_2784',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 2785,
    'book_describe': 'book_2785',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 2786,
    'book_describe': 'book_2786',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 2787,
    'book_describe': 'book_2787',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 2788,
    'book_describe': 'book_2788',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 2789,
    'book_describe': 'book_2789',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 2790,
    'book_describe': 'book_2790',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 2791,
    'book_describe': 'book_2791',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 2792,
    'book_describe': 'book_2792',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 2793,
    'book_describe': 'book_2793',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 2794,
    'book_describe': 'book_2794',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 2795,
    'book_describe': 'book_2795',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 2796,
    'book_describe': 'book_2796',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 2797,
    'book_describe': 'book_2797',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 2798,
    'book_describe': 'book_2798',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 2799,
    'book_describe': 'book_2799',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 2800,
    'book_describe': 'book_2800',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 2801,
    'book_describe': 'book_2801',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 2802,
    'book_describe': 'book_2802',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 2803,
    'book_describe': 'book_2803',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 2804,
    'book_describe': 'book_2804',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 2805,
    'book_describe': 'book_2805',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 2806,
    'book_describe': 'book_2806',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 2807,
    'book_describe': 'book_2807',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 2808,
    'book_describe': 'book_2808',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 2809,
    'book_describe': 'book_2809',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 2810,
    'book_describe': 'book_2810',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 2811,
    'book_describe': 'book_2811',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 2812,
    'book_describe': 'book_2812',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 2813,
    'book_describe': 'book_2813',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 2814,
    'book_describe': 'book_2814',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 2815,
    'book_describe': 'book_2815',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 2816,
    'book_describe': 'book_2816',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 2817,
    'book_describe': 'book_2817',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 2818,
    'book_describe': 'book_2818',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 2819,
    'book_describe': 'book_2819',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 2820,
    'book_describe': 'book_2820',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 2821,
    'book_describe': 'book_2821',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 2822,
    'book_describe': 'book_2822',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 2823,
    'book_describe': 'book_2823',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 2824,
    'book_describe': 'book_2824',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 2825,
    'book_describe': 'book_2825',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 2826,
    'book_describe': 'book_2826',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 2827,
    'book_describe': 'book_2827',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 2828,
    'book_describe': 'book_2828',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 2829,
    'book_describe': 'book_2829',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 2830,
    'book_describe': 'book_2830',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 2831,
    'book_describe': 'book_2831',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 2832,
    'book_describe': 'book_2832',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 2833,
    'book_describe': 'book_2833',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 2834,
    'book_describe': 'book_2834',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 2835,
    'book_describe': 'book_2835',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 2836,
    'book_describe': 'book_2836',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 2837,
    'book_describe': 'book_2837',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 2838,
    'book_describe': 'book_2838',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 2839,
    'book_describe': 'book_2839',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 2840,
    'book_describe': 'book_2840',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 2841,
    'book_describe': 'book_2841',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 2842,
    'book_describe': 'book_2842',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 2843,
    'book_describe': 'book_2843',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 2844,
    'book_describe': 'book_2844',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 2845,
    'book_describe': 'book_2845',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 2846,
    'book_describe': 'book_2846',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 2847,
    'book_describe': 'book_2847',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 2848,
    'book_describe': 'book_2848',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 2849,
    'book_describe': 'book_2849',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 2850,
    'book_describe': 'book_2850',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 2851,
    'book_describe': 'book_2851',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 2852,
    'book_describe': 'book_2852',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 2853,
    'book_describe': 'book_2853',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 2854,
    'book_describe': 'book_2854',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 2855,
    'book_describe': 'book_2855',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 2856,
    'book_describe': 'book_2856',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 2857,
    'book_describe': 'book_2857',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 2858,
    'book_describe': 'book_2858',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 2859,
    'book_describe': 'book_2859',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 2860,
    'book_describe': 'book_2860',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 2861,
    'book_describe': 'book_2861',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 2862,
    'book_describe': 'book_2862',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 2863,
    'book_describe': 'book_2863',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 2864,
    'book_describe': 'book_2864',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 2865,
    'book_describe': 'book_2865',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 2866,
    'book_describe': 'book_2866',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 2867,
    'book_describe': 'book_2867',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 2868,
    'book_describe': 'book_2868',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 2869,
    'book_describe': 'book_2869',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 2870,
    'book_describe': 'book_2870',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 2871,
    'book_describe': 'book_2871',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 2872,
    'book_describe': 'book_2872',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 2873,
    'book_describe': 'book_2873',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 2874,
    'book_describe': 'book_2874',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 2875,
    'book_describe': 'book_2875',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 2876,
    'book_describe': 'book_2876',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 2877,
    'book_describe': 'book_2877',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 2878,
    'book_describe': 'book_2878',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 2879,
    'book_describe': 'book_2879',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 2880,
    'book_describe': 'book_2880',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 2881,
    'book_describe': 'book_2881',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 2882,
    'book_describe': 'book_2882',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 2883,
    'book_describe': 'book_2883',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 2884,
    'book_describe': 'book_2884',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 2885,
    'book_describe': 'book_2885',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 2886,
    'book_describe': 'book_2886',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 2887,
    'book_describe': 'book_2887',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 2888,
    'book_describe': 'book_2888',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 2889,
    'book_describe': 'book_2889',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 2890,
    'book_describe': 'book_2890',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 2891,
    'book_describe': 'book_2891',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 2892,
    'book_describe': 'book_2892',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 2893,
    'book_describe': 'book_2893',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 2894,
    'book_describe': 'book_2894',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 2895,
    'book_describe': 'book_2895',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 2896,
    'book_describe': 'book_2896',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 2897,
    'book_describe': 'book_2897',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 2898,
    'book_describe': 'book_2898',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 2899,
    'book_describe': 'book_2899',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 0,
    'word_count': 2900,
    'book_describe': 'book_2900',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 1,
    'word_count': 2901,
    'book_describe': 'book_2901',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 2,
    'word_count': 2902,
    'book_describe': 'book_2902',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 3,
    'word_count': 2903,
    'book_describe': 'book_2903',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 4,
    'word_count': 2904,
    'book_describe': 'book_2904',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 5,
    'word_count': 2905,
    'book_describe': 'book_2905',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 6,
    'word_count': 2906,
    'book_describe': 'book_2906',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 7,
    'word_count': 2907,
    'book_describe': 'book_2907',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 8,
    'word_count': 2908,
    'book_describe': 'book_2908',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 9,
    'word_count': 2909,
    'book_describe': 'book_2909',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 10,
    'word_count': 2910,
    'book_describe': 'book_2910',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 11,
    'word_count': 2911,
    'book_describe': 'book_2911',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 12,
    'word_count': 2912,
    'book_describe': 'book_2912',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 13,
    'word_count': 2913,
    'book_describe': 'book_2913',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 14,
    'word_count': 2914,
    'book_describe': 'book_2914',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 15,
    'word_count': 2915,
    'book_describe': 'book_2915',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 16,
    'word_count': 2916,
    'book_describe': 'book_2916',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 17,
    'word_count': 2917,
    'book_describe': 'book_2917',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 18,
    'word_count': 2918,
    'book_describe': 'book_2918',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 19,
    'word_count': 2919,
    'book_describe': 'book_2919',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 20,
    'word_count': 2920,
    'book_describe': 'book_2920',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 21,
    'word_count': 2921,
    'book_describe': 'book_2921',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 22,
    'word_count': 2922,
    'book_describe': 'book_2922',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 23,
    'word_count': 2923,
    'book_describe': 'book_2923',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 24,
    'word_count': 2924,
    'book_describe': 'book_2924',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 25,
    'word_count': 2925,
    'book_describe': 'book_2925',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 26,
    'word_count': 2926,
    'book_describe': 'book_2926',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 27,
    'word_count': 2927,
    'book_describe': 'book_2927',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 28,
    'word_count': 2928,
    'book_describe': 'book_2928',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 29,
    'word_count': 2929,
    'book_describe': 'book_2929',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 30,
    'word_count': 2930,
    'book_describe': 'book_2930',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 31,
    'word_count': 2931,
    'book_describe': 'book_2931',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 32,
    'word_count': 2932,
    'book_describe': 'book_2932',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 33,
    'word_count': 2933,
    'book_describe': 'book_2933',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 34,
    'word_count': 2934,
    'book_describe': 'book_2934',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 35,
    'word_count': 2935,
    'book_describe': 'book_2935',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 36,
    'word_count': 2936,
    'book_describe': 'book_2936',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 37,
    'word_count': 2937,
    'book_describe': 'book_2937',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 38,
    'word_count': 2938,
    'book_describe': 'book_2938',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 39,
    'word_count': 2939,
    'book_describe': 'book_2939',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 40,
    'word_count': 2940,
    'book_describe': 'book_2940',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 41,
    'word_count': 2941,
    'book_describe': 'book_2941',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 42,
    'word_count': 2942,
    'book_describe': 'book_2942',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 43,
    'word_count': 2943,
    'book_describe': 'book_2943',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 44,
    'word_count': 2944,
    'book_describe': 'book_2944',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=23, normalized=True),
    'values': self.mutator.generate_float_array(dimension=23, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 45,
    'word_count': 2945,
    'book_describe': 'book_2945',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 46,
    'word_count': 2946,
    'book_describe': 'book_2946',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 47,
    'word_count': 2947,
    'book_describe': 'book_2947',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 48,
    'word_count': 2948,
    'book_describe': 'book_2948',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 49,
    'word_count': 2949,
    'book_describe': 'book_2949',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 50,
    'word_count': 2950,
    'book_describe': 'book_2950',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 51,
    'word_count': 2951,
    'book_describe': 'book_2951',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 52,
    'word_count': 2952,
    'book_describe': 'book_2952',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 53,
    'word_count': 2953,
    'book_describe': 'book_2953',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 54,
    'word_count': 2954,
    'book_describe': 'book_2954',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 55,
    'word_count': 2955,
    'book_describe': 'book_2955',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 56,
    'word_count': 2956,
    'book_describe': 'book_2956',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 57,
    'word_count': 2957,
    'book_describe': 'book_2957',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 58,
    'word_count': 2958,
    'book_describe': 'book_2958',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 59,
    'word_count': 2959,
    'book_describe': 'book_2959',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 60,
    'word_count': 2960,
    'book_describe': 'book_2960',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 61,
    'word_count': 2961,
    'book_describe': 'book_2961',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 62,
    'word_count': 2962,
    'book_describe': 'book_2962',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 63,
    'word_count': 2963,
    'book_describe': 'book_2963',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 64,
    'word_count': 2964,
    'book_describe': 'book_2964',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 65,
    'word_count': 2965,
    'book_describe': 'book_2965',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 66,
    'word_count': 2966,
    'book_describe': 'book_2966',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 67,
    'word_count': 2967,
    'book_describe': 'book_2967',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 68,
    'word_count': 2968,
    'book_describe': 'book_2968',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 69,
    'word_count': 2969,
    'book_describe': 'book_2969',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 70,
    'word_count': 2970,
    'book_describe': 'book_2970',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 71,
    'word_count': 2971,
    'book_describe': 'book_2971',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 72,
    'word_count': 2972,
    'book_describe': 'book_2972',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 73,
    'word_count': 2973,
    'book_describe': 'book_2973',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 74,
    'word_count': 2974,
    'book_describe': 'book_2974',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 75,
    'word_count': 2975,
    'book_describe': 'book_2975',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 76,
    'word_count': 2976,
    'book_describe': 'book_2976',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 77,
    'word_count': 2977,
    'book_describe': 'book_2977',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 78,
    'word_count': 2978,
    'book_describe': 'book_2978',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 79,
    'word_count': 2979,
    'book_describe': 'book_2979',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 80,
    'word_count': 2980,
    'book_describe': 'book_2980',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 81,
    'word_count': 2981,
    'book_describe': 'book_2981',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 82,
    'word_count': 2982,
    'book_describe': 'book_2982',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 83,
    'word_count': 2983,
    'book_describe': 'book_2983',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=26, normalized=True),
    'values': self.mutator.generate_float_array(dimension=26, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 84,
    'word_count': 2984,
    'book_describe': 'book_2984',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 85,
    'word_count': 2985,
    'book_describe': 'book_2985',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 86,
    'word_count': 2986,
    'book_describe': 'book_2986',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 87,
    'word_count': 2987,
    'book_describe': 'book_2987',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 88,
    'word_count': 2988,
    'book_describe': 'book_2988',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 89,
    'word_count': 2989,
    'book_describe': 'book_2989',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=29, normalized=True),
    'values': self.mutator.generate_float_array(dimension=29, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 90,
    'word_count': 2990,
    'book_describe': 'book_2990',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 91,
    'word_count': 2991,
    'book_describe': 'book_2991',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 92,
    'word_count': 2992,
    'book_describe': 'book_2992',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=25, normalized=True),
    'values': self.mutator.generate_float_array(dimension=25, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 93,
    'word_count': 2993,
    'book_describe': 'book_2993',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=24, normalized=True),
    'values': self.mutator.generate_float_array(dimension=24, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 94,
    'word_count': 2994,
    'book_describe': 'book_2994',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=30, normalized=True),
    'values': self.mutator.generate_float_array(dimension=30, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 95,
    'word_count': 2995,
    'book_describe': 'book_2995',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=27, normalized=True),
    'values': self.mutator.generate_float_array(dimension=27, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 96,
    'word_count': 2996,
    'book_describe': 'book_2996',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=22, normalized=True),
    'values': self.mutator.generate_float_array(dimension=22, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 97,
    'word_count': 2997,
    'book_describe': 'book_2997',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=21, normalized=True),
    'values': self.mutator.generate_float_array(dimension=21, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 98,
    'word_count': 2998,
    'book_describe': 'book_2998',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=20, normalized=True),
    'values': self.mutator.generate_float_array(dimension=20, normalized=True),
},
    'dynamic_field_0': 0,
},
    {
    'user_id': 99,
    'word_count': 2999,
    'book_describe': 'book_2999',
    'sparse_float_vector': {
    'indices': self.mutator.generate_float_array(dimension=28, normalized=True),
    'values': self.mutator.generate_float_array(dimension=28, normalized=True),
},
    'dynamic_field_0': 0,
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



    def test_request_3(self):
        """测试请求 3 - POST http://172.17.0.5:23210/v2/vectordb/entities/search"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v2/vectordb/entities/search")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/entities/search'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'Accept-Type-Allow-Int64': 'true',
    'RequestId': '0a4e6770-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_23_11_285545jXYpvQFT',
    'data': [
    {
    '10': 0.8790278600018762,
    '86': 0.6533252286615916,
    '48': 0.6250686145324448,
    '50': 0.10325589577938243,
    '103': 0.8027339440187597,
    '3': 0.13967271221766508,
    '82': 0.3058408386777205,
    '24': 0.6683511268158375,
    '46': 0.8817933186352964,
    '124': 0.3377098817215606,
    '12': 0.07521306183945264,
    '66': 0.5403206001524686,
    '13': 0.8399774465042485,
    '70': 0.31495951549880885,
    '87': 0.22121524307424523,
    '92': 0.024930147748774112,
    '32': 0.2718813250005767,
    '102': 0.126195144878278,
    '116': 0.9662311654581012,
    '104': 0.20588774930596743,
    '60': 0.6874079454831519,
    '107': 0.7776012185383856,
    '56': 0.774993236869897,
    '77': 0.5342643594231254,
},
],
    'filter': 'word_count > 100',
    'outputFields': [
    '*',
],
    'searchParams': {
    'metricType': 'IP',
    'params': {
    'drop_ratio_search': '0.2',
},
},
    'limit': 500,
    'groupingField': 'user_id',
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
        """测试请求 4 - DELETE http://172.17.0.5:23210/v2/vectordb/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v2/vectordb/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v2/vectordb/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer None',
    'RequestId': '0a4e6770-62f8-11f0-85c3-0242ac11000b',
    'Request-Timeout': '120',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_18_23_11_285545jXYpvQFT',
    'schema': {
    'autoId': True,
    'enableDynamicField': True,
    'fields': [
    {
    'fieldName': 'book_id',
    'dataType': 'Int64',
    'isPrimary': True,
    'elementTypeParams': {
},
},
    {
    'fieldName': 'user_id',
    'dataType': 'Int64',
    'isPartitionKey': False,
    'elementTypeParams': {
},
},
    {
    'fieldName': 'word_count',
    'dataType': 'Int64',
    'elementTypeParams': {
},
},
    {
    'fieldName': 'book_describe',
    'dataType': 'VarChar',
    'elementTypeParams': {
    'max_length': '256',
},
},
    {
    'fieldName': 'sparse_float_vector',
    'dataType': 'SparseFloatVector',
},
],
},
    'indexParams': [
    {
    'fieldName': 'sparse_float_vector',
    'indexName': 'sparse_float_vector',
    'metricType': 'IP',
    'params': {
    'index_type': 'SPARSE_INVERTED_INDEX',
    'drop_ratio_build': '0.2',
},
},
],
    'params': {
    'consistencyLevel': 'Strong',
},
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestSearchVector_test_search_vector_with_sparse_float_vector_datatype[coo-user_id-128-3000-True-False-True-10]_1752747798.json')
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
        TARGET_URL = args.target
    if args.output_dir:
        OUTPUT_DIR = args.output_dir
    
    # 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 实例化测试类并运行测试
    test = AllmilvusLogtestsearchvectorTestSearchVectorWithSparseFloatVectorDatatypeCooUserId1283000TrueFalseTrue101752747798Json()
    test.run_tests()
