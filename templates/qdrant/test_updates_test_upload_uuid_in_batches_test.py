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
logger = logging.getLogger('vdb_fuzzer.test.test_updates_test_upload_uuid_in_batches')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
DEFAULT_TARGET_URL = "http://localhost:6333"
TARGET_ENV_VARS = ("QDRANT_TARGET_URL", "VDBFUZZ_TARGET_URL")
TARGET_URL = next(
    (os.environ.get(name, "").strip() for name in TARGET_ENV_VARS if os.environ.get(name, "").strip()),
    DEFAULT_TARGET_URL,
)
OUTPUT_DIR = "template_qdrant_0520"
TEST_NAME = "test_updates.test_upload_uuid_in_batches"
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



class TestUpdatestestUploadUuidInBatches:
    """自动生成的VDB模糊测试类 - test_updates.test_upload_uuid_in_batches"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "test_updates.test_upload_uuid_in_batches"
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
    'content-length': '215909',
}
        
        # 原始请求内容
        original_content = {
    'batch': {
    'ids': [
    '4b3390e8-814c-4db9-8f87-a3e6e4febf11',
    'aaad3685-263d-4a17-bf6a-cb33ddb73441',
    'a1a3ac79-c651-4106-9f46-224672f90b55',
    '2dd9c098-a632-4209-a839-cc019e2473d2',
    'c6b2809d-d6f8-4234-8846-580157fca10c',
    'b9393291-1aa9-4ec2-9b3b-e2c1eae65a23',
    '2a2d9568-2eee-435e-bc18-8d80386beeaa',
    'b9e0c608-d53e-4e5a-a34c-1743c878d530',
    'feabe24f-a7bf-4165-a036-493e012bb6aa',
    '993d6d01-1991-483b-9c89-5a54383ecd1d',
    'e9b92800-f8dc-4ed3-8052-50ce572e243f',
    '851d33b2-1074-46df-8c06-66fccd814285',
    'dc0a3476-1209-4ee1-b6c8-fb1e5cf4bded',
    '1e7dcc2e-c7b5-4bbb-b04c-9c9deabe564f',
    '801a0e09-db7c-4957-9068-97ed6dbfaee4',
    '2c742b07-8def-44e0-b5a3-cb526f8d2951',
    'e1f38e39-e671-425c-9c94-e8c5f9f01a54',
    '41f01b08-48d0-439a-9e8f-9bf6a42ea7e0',
    '1b12037f-e3b0-43db-87d0-85b2738e765e',
    '2e4c8d1d-4622-4d7f-866c-cb00ea090290',
    'dab5cfa7-2296-401c-a19c-51850df1a3c8',
    '8add6c11-06b2-4f36-9e0d-34884e9ff5e2',
    '18e8ca11-9e49-43df-a19d-b654275168b7',
    '7a0c5510-ec1e-4d6c-8358-1af554454f53',
    '47115fff-1596-444c-98b6-3d4926277347',
    '13a64329-b7b6-4aa5-990d-fc589c930cbc',
    '4b09c2f3-c22e-457e-8235-dded915a2a41',
    'dceaad55-b9dd-4be9-96f9-b302be1fd7bd',
    '1d5b6bdb-3d42-4d63-99e8-2a44e3543892',
    'b3df7f92-e68e-4d48-b9c0-95f9e2d4ba62',
    '733f9a40-e579-46b9-abcc-09878ad34ecf',
    '86926159-412a-46b7-bea2-127b50f108b2',
    '048feccb-cced-4833-93c1-27a2f690d353',
    'f0dbd4eb-1234-4443-8b72-659af9dfc715',
    '33442c70-82c0-4217-b1c3-e4588d1ba4da',
    'd9c836dc-8e28-4149-b50d-5e6890cfe7ae',
    '0e5941a1-4a42-4585-b53f-1effb1b2f047',
    '4d1aee21-88c7-4dce-acf3-a6cabadde8af',
    'd30531ff-27ad-435d-9c76-7e59e03e1985',
    '57f04e15-8c41-4bb8-85b2-9ba9912328d9',
    '0f85c029-eff5-405d-b018-4bda933615ba',
    '4e3e84ad-f1c4-4a02-804c-695d3f24354f',
    '446de4e1-1dfd-4be4-a316-d13a44e3c830',
    'a0303502-7ed8-4657-9448-ffa225bc047c',
    '3503e36b-ef24-4136-9de5-71bb3eadc6a8',
    '4387b979-4f0a-4fa8-a387-eed57ec6a4a0',
    'f95f4480-9fdb-4476-a969-97cae11a9e8f',
    '83bbe850-a9de-4310-8cbf-d1d5bafa0f26',
    '957e7ac9-a112-4564-89a5-80f3fbca74a3',
    '1c183cd4-bdba-4b0f-a878-53693b3aa846',
    '024d913e-a3e4-4a5c-b5c9-40d57ee5f9ad',
    '060a121b-589b-43b4-bffb-213390d35fa4',
    'a5f8a24b-b29f-4ec0-a535-90efca1a0675',
    'a17b3cd9-9c40-4ebc-8d7a-b6ad425c39b7',
    'd3ef50a0-02bf-450d-88ff-26c38cc8e4f3',
    '42b67612-9952-4f4a-a4b1-2252f808e4a6',
    '7b776ae0-6b59-4041-b04f-131591e4b010',
    '24082eaf-1dda-44dd-90a5-2d1852389209',
    'a7c1b322-934c-4927-a6d8-7e3c03ee5afb',
    '4eeb06ae-c097-4f25-823b-6af93bb51d76',
    '1839368d-5315-43a1-8ba2-dcd34027d7e2',
    'ca563bdd-3af6-4dc0-992b-f07eab6dac74',
    '84fc44bf-fae3-4bca-a7e0-fc6184b28131',
    'f15b359c-54ba-42bf-9394-5966ad967f1f',
    'ee7f89a3-f103-456e-8733-65e726677358',
    '88cf418d-94fc-4f09-bd9d-4d1c526f878a',
    '137e7bf7-a3e1-4dd5-aa09-50c13375de86',
    '29f1b518-12fd-4e76-9483-cf6c47c9e29c',
    'f79bc41f-c364-4b19-a7f3-311b82544a6c',
    'e4463284-c73c-4533-8c27-ff2635963a37',
    '0ee51c2a-2ccb-4770-812e-0a24df4fc4b0',
    '85038cad-6962-4c0b-93d6-48de8986dd55',
    '5347a270-191b-403f-a146-cab358057baa',
    'a4891477-6f72-463e-8f0d-92ef82a2d636',
    '35d81bd6-4457-4dcd-aed3-ccaf497c74f6',
    'e6368e41-4115-47a3-8701-aad34936f0cc',
    'd279037d-88e1-41a3-9dd9-5edc5220aba3',
    '3cb944ec-8ca5-4be2-a306-e4ff875034db',
    '4c7c6ee6-92c4-4757-808a-4b1483fe031b',
    '7399048b-0cfe-44bd-bd91-528794d03eed',
    'cf1af71c-d2f4-43b8-ae17-a5b99922d7b5',
    '0d4557ca-a266-4458-a07f-bd9cf3d29f8a',
    '3fc8d027-3d92-4022-9cda-25fc47c444db',
    '0926a940-82f2-411e-91da-4f2811e6ac40',
    'cd793424-1a05-4744-a87e-147bd9fcd730',
    'ae5a416a-99ff-4cd9-a26d-8d9df28d130f',
    'd596b2f8-9efc-4003-81ad-53e8b0f7cff4',
    '29954bf6-0e41-451a-8949-606f96849a75',
    'cdec6b06-8834-42eb-b6ca-802e73a10d0a',
    '1dac708d-1b64-4516-90e7-fd3b76868a19',
    'eac60af3-d6cb-49fe-a29d-5ca34a8aa6ed',
    'b0b3b4b6-e41e-4d85-96f4-44e484305707',
    'cb5cbaa4-d889-4708-a2bd-ba1970e85b46',
    '09b51f9f-94b0-49d0-9b93-a9bfe7c11bc0',
    '05e271b3-1b83-4419-a8b1-2beddc7fd61c',
    '487338f7-b793-4d88-8385-6307fa25614a',
    '9fa0a52d-1a3f-49c5-9363-62341dc23a62',
    '12bcd1df-b398-4934-b324-7876b38f8322',
    'dc27efff-bf2b-4864-912c-1ca99c6b29c2',
    'af4adc2e-02b1-4efd-8cc9-448020617387',
],
    'vectors': {
    'text': '__FLOAT_MULTI_DIM_100,50__',
    'image': '__FLOAT_MULTI_DIM_100,100__',
    'code': '__FLOAT_MULTI_DIM_100,80__',
},
    'payloads': [
    {
    'id': 100,
    'id_str': [
    '20',
    '11',
],
    'text_data': 'ea558dbb08eb43dfb47665ee3244eb6c',
    'rand_digit': 5,
    'rand_number': 0.10425,
    'rand_signed_int': 3,
    'rand_datetime': '2000-10-26T19:08:11.581620',
    'text_array': [
    '8c7c38e76c284c2dbd2ff5e3ab622d22',
    '9093b81fbf254fd4a69dffa54619c5cf',
],
    'words': 'koala crab',
    'nested': {
    'id': 100,
    'rand_digit': 1,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'cheetah',
    'sheep',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'rhino',
    'maybe_null': None,
},
    {
    'id': 101,
    'id_str': [
    '09',
    '15',
],
    'text_data': '75bfe3e210c0494b988d00f234425883',
    'rand_digit': 5,
    'rand_number': 0.34121,
    'rand_signed_int': -4,
    'rand_datetime': '2000-10-13T14:56:17',
    'text_array': [
    'b409ce6b4c5f494d85faebe66969fc5b',
    '27f9b2f02ca541a2b17ea3c18cdb65f4',
],
    'words': 'sheep butterfly',
    'nested': {
    'id': 101,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'horse',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bird',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 4,
},
],
},
    'nested_array': [
    [
    -8,
],
],
    'two_words': [
    'chicken',
    'chicken',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': None,
},
    {
    'id': 102,
    'id_str': [
    '18',
],
    'text_data': '70fa8537f4ab475faf4d9d1fa80c3025',
    'rand_digit': 8,
    'rand_number': 0.05815,
    'rand_signed_int': 9,
    'rand_datetime': '2000-12-24T01:50:11.398975+0900',
    'text_array': [
    'b7e62468434844089d05ff6ff66022a7',
    '9233ef3a01e24929a09c00751695f63b',
],
    'words': 'sheep giraffe',
    'nested': {
    'id': 102,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'giraffe',
    'giraffe',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 5,
    'maybe': 'dog',
    'maybe_null': 'leopard',
},
    {
    'id': 103,
    'id_str': [
    '17',
    '13',
    '27',
    '14',
    '15',
],
    'text_data': '6f17d04fef264038a593c52937f1d33c',
    'rand_digit': 9,
    'rand_number': 0.74536,
    'rand_signed_int': 9,
    'rand_datetime': '2000-10-30T01:27:47-0300',
    'text_array': [
    '8b069ac709dd48b998c4d044e9e33965',
    '9cdb048d7dac4071ba294351328e87cf',
],
    'words': 'lizard giraffe',
    'nested': {
    'id': 103,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'horse',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bee',
    'monkey',
],
    'city': {
    'name': 'Budapest',
    'geo': {
    'lat': 47.497912,
    'lon': 19.040235,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 7,
    'maybe': 'dolphin',
},
    {
    'id': 104,
    'id_str': [
],
    'text_data': '6085315eca91474cbfbe67e136d918ea',
    'rand_digit': 2,
    'rand_number': 0.78944,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-02T16:25:05.467532-0200',
    'text_array': [
    '8e497eee288248dd8b0e652642160da7',
    '7a24158765ab4b7c8daf069d70efb511',
],
    'words': 'duck monkey',
    'nested': {
    'id': 104,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fly',
    'bird',
],
    'city': {
    'name': 'Kharkiv',
    'geo': {
    'lat': 49.980812,
    'lon': 36.25272,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
    {
    'id': 105,
    'id_str': [
    '21',
],
    'text_data': '117db0afc81b4fb39117e42198842798',
    'rand_digit': 6,
    'rand_number': 0.24247,
    'rand_signed_int': -2,
    'rand_datetime': '2000-11-18 10:11:27',
    'text_array': [
    '6e5e9b2b6e9947929fcc73aa723ca218',
    '344fd700a16c440ba4a18fdf0db8b8c8',
],
    'words': 'lobster wolf',
    'nested': {
    'id': 105,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 5,
},
],
},
    'nested_array': [
    [
    -1,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'lion',
    'elephant',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.91941,
    'maybe': 'sheep',
    'maybe_null': None,
},
    {
    'id': 106,
    'id_str': [
    '30',
],
    'text_data': '865b48a9cf6d46f6bbaafe9a8aef6e1c',
    'rand_digit': 2,
    'rand_number': 0.3205,
    'rand_signed_int': 4,
    'rand_datetime': '2000-08-13T16:38:59-0900',
    'text_array': [
    '3a605930bd4744529bfe127511bf5e26',
    '1f3540efb26a4a33a0501a53bee5f9da',
],
    'words': 'ant panda',
    'nested': {
    'id': 106,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'grasshopper',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'fish',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    1,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'koala',
    'tiger',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'ladybug',
    'maybe_null': None,
},
    {
    'id': 107,
    'id_str': [
    '13',
],
    'text_data': 'baf454521c6d43cbac6df837cca213f1',
    'rand_digit': 2,
    'rand_number': 0.31717,
    'rand_signed_int': -1,
    'rand_datetime': '2000-04-28T12:42:47.187327',
    'text_array': [
    'aed6fc407c2346dd972eb9c4fe9f9f3b',
    '0e9c8ed545014a2e9415fec16dfa1d24',
],
    'words': 'cat dog',
    'nested': {
    'id': 107,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'monkey',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 3,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'snake',
    'jaguar',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'bear',
    'maybe_null': None,
},
    {
    'id': 108,
    'id_str': [
    '13',
],
    'text_data': 'f08eee5c2d1043a085ac60a5f373b15a',
    'rand_digit': 3,
    'rand_number': 0.48924,
    'rand_signed_int': 10,
    'rand_datetime': '2000-10-08 03:34:37',
    'text_array': [
    'f7fd8792853745c09470113e9a4a16ea',
    'c19b023e6b8547a28c71aad318546a88',
],
    'words': 'giraffe crab',
    'nested': {
    'id': 108,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 4,
},
    {
    'nested_empty': None,
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
    'word': 'frog',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
],
],
    'two_words': [
    'bee',
    'snake',
],
    'city': {
    'name': 'Santiago',
    'geo': {
    'lat': -33.44889,
    'lon': -70.669266,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': 'chicken',
    'maybe': 'fly',
    'maybe_null': 'shark',
},
    {
    'id': 109,
    'id_str': [
    '15',
    '30',
],
    'text_data': '34863a1bc4644ca5b5420fdab60a2477',
    'rand_digit': 0,
    'rand_number': 0.0615,
    'rand_signed_int': 10,
    'rand_datetime': '2000-04-09T13:18:03.340165',
    'text_array': [
    'b7b886ea9ee2494b849a2027d144b091',
    'e8a72166e3924c23ac81c2580f7fc08d',
],
    'words': 'mosquito lobster',
    'nested': {
    'id': 109,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'duck',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -8,
],
    [
    -9,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'goat',
    'scorpion',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'fly',
    'maybe_null': 'hippo',
},
    {
    'id': 110,
    'id_str': [
    '09',
    '16',
    '11',
    '17',
    '26',
],
    'text_data': 'a861d033206547879069b66d25648f55',
    'rand_digit': 8,
    'rand_number': 0.42245,
    'rand_signed_int': -4,
    'rand_datetime': '2000-04-29T11:47:34.740063-09:00',
    'text_array': [
    'e749ef6b10c0471eaa138046ae34c6d4',
    'e42f853c0e334dafbb2074a434a5eb85',
],
    'words': 'ant fox',
    'nested': {
    'id': 110,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'crab',
    'kangaroo',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 5,
    'maybe': 'pig',
},
    {
    'id': 111,
    'id_str': [
    '18',
    '18',
    '03',
],
    'text_data': '61f71f147bed4668969cbb50da0ac25c',
    'rand_digit': 3,
    'rand_number': 0.54985,
    'rand_signed_int': -10,
    'rand_datetime': '2000-08-22 05:57',
    'text_array': [
    'db7508d787f8412b998439d3bf0086b5',
    '28691cccc3a545f5bb668d07e7fdf8eb',
],
    'words': 'kangaroo pig',
    'nested': {
    'id': 111,
    'rand_digit': 0,
    'array': [
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
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -2,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
],
    'two_words': [
    'panda',
    'monkey',
],
    'city': {
    'name': 'Minsk',
    'geo': {
    'lat': 53.90454,
    'lon': 27.561524,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'scorpion',
    'maybe_null': 'snail',
},
    {
    'id': 112,
    'id_str': [
    '08',
    '25',
    '13',
    '22',
    '22',
],
    'text_data': 'ab72c400ff454b8a9efd0223d1768946',
    'rand_digit': 0,
    'rand_number': 0.83013,
    'rand_signed_int': -10,
    'rand_datetime': '2000-04-24T17:25:35.447134',
    'text_array': [
    '8a7dfd0527324193ae8c1105fb745515',
    '4735a8a5729f44cfa81aea746a642bf6',
],
    'words': 'horse scorpion',
    'nested': {
    'id': 112,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'chicken',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'horse',
    'number': 7,
},
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
],
    'word': 'whale',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    -7,
],
],
    'two_words': [
    'lizard',
    'snake',
],
    'city': {
    'name': 'Kuala Lumpur',
    'geo': {
    'lat': 3.139003,
    'lon': 101.686855,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
},
    {
    'id': 113,
    'id_str': [
    '19',
    '29',
    '23',
    '22',
],
    'text_data': 'd97011d19ffd4ab4b5b35dcf77f78fb1',
    'rand_digit': 1,
    'rand_number': 0.13741,
    'rand_signed_int': 9,
    'rand_datetime': '2000-03-23 09:57:53.951404',
    'text_array': [
    '4f344833858841f496ea9b3d45bb0ccd',
    '5e89256fed1646588f38a32dd257316e',
],
    'words': 'ant sheep',
    'nested': {
    'id': 113,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'pig',
    'number': 5,
},
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 7,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'bee',
    'ape',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'elephant',
    'maybe_null': 'spider',
},
    {
    'id': 114,
    'id_str': [
    '08',
],
    'text_data': '9eeb00ea0a834bfc9ab68372bab03633',
    'rand_digit': 1,
    'rand_number': 0.6628,
    'rand_signed_int': 3,
    'rand_datetime': '2001-01-26T17:17:47',
    'text_array': [
    'f0aa84c8f6344cb483d06206fdceb6ca',
    '55146f38e58249c9b378993545d5b9d9',
],
    'words': 'goat chicken',
    'nested': {
    'id': 114,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'duck',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'fish',
    'sloth',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'wolf',
},
    {
    'id': 115,
    'id_str': [
    '15',
    '04',
    '09',
],
    'text_data': '89e9522f2d8b472e800005a552984c37',
    'rand_digit': 5,
    'rand_number': 0.71285,
    'rand_signed_int': 7,
    'rand_datetime': '2000-02-15T19:25:57.078936',
    'text_array': [
    '18a51212007d415bb4ce54b2b5481485',
    '3b60a4e6bc0746fbbfa08787dd1b1313',
],
    'words': 'dog bear',
    'nested': {
    'id': 115,
    'rand_digit': 4,
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sheep',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'wolf',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'rhino',
    'bird',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': [
    15,
],
    'rand_bool': False,
    'mixed_type': True,
},
    {
    'id': 116,
    'id_str': [
    '22',
    '03',
],
    'text_data': 'b0e349fead2c45a5bae2d4b955daf67e',
    'rand_digit': 9,
    'rand_number': 0.95987,
    'rand_signed_int': 3,
    'rand_datetime': '2000-10-03 10:20:55',
    'text_array': [
    '398c3ffc29b647ed974a0fc5506e99db',
    'f328df11806745efbf62552c3e26fc8d',
],
    'words': 'horse lobster',
    'nested': {
    'id': 116,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'dolphin',
    'wolf',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'shark',
    'maybe_null': 'grasshopper',
},
    {
    'id': 117,
    'id_str': [
],
    'text_data': '6373e3970d7d4e229e88639fc8f2df21',
    'rand_digit': 3,
    'rand_number': 0.89626,
    'rand_signed_int': -2,
    'rand_datetime': '2000-06-02T05:10:53+0500',
    'text_array': [
    '4c90f8a505b24d0185227ed1860487c7',
    '0eace201385240b591dd1912e79e22e6',
],
    'words': 'ant dragonfly',
    'nested': {
    'id': 117,
    'rand_digit': 0,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'jaguar',
    'hyena',
],
    'city': {
    'name': 'Vienna',
    'geo': {
    'lat': 48.208174,
    'lon': 16.373819,
},
},
    'rand_tuple': [
    33,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
    {
    'id': 118,
    'id_str': [
    '07',
    '25',
    '14',
    '03',
],
    'text_data': '16fbb68da30d40ceae563090de4f3b3a',
    'rand_digit': 2,
    'rand_number': 0.63843,
    'rand_signed_int': 10,
    'rand_datetime': '2000-09-21 12:32:06-0300',
    'text_array': [
    'ea0d07a40e4442c7a41cd618d86af901',
    '5627ed900a6048e9baa4274404e083dd',
],
    'words': 'tiger zebra',
    'nested': {
    'id': 118,
    'rand_digit': 5,
    'array': [
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
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'zebra',
    'number': 2,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'bear',
    'wolf',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'octopus',
    'maybe_null': None,
},
    {
    'id': 119,
    'id_str': [
    '17',
    '14',
    '01',
    '10',
    '11',
],
    'text_data': 'e9237e2e5a1945c6bc802dc4a4ce9526',
    'rand_digit': 7,
    'rand_number': 0.81724,
    'rand_signed_int': 4,
    'rand_datetime': '2000-09-07T07:31:04-0500',
    'text_array': [
    '3cfec2b37ce94d99af613046a1a6d1ee',
    '5d68dd27d6704b7094ebeba9dab4c373',
],
    'words': 'scorpion ladybug',
    'nested': {
    'id': 119,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
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
    'word': 'zebra',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -9,
],
    [
    7,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'dolphin',
    'scorpion',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'giraffe',
},
    {
    'id': 120,
    'id_str': [
    '02',
    '28',
    '27',
],
    'text_data': 'f970da87e8b348ff82fe6321147661d6',
    'rand_digit': 5,
    'rand_number': 0.68673,
    'rand_signed_int': 0,
    'rand_datetime': '2000-11-11 09:54:52.789102-1100',
    'text_array': [
    '37d65c142b564ea3b4c2c9725686674e',
    '924e888f9f2847e7a4e598a9e525aae0',
],
    'words': 'deer spider',
    'nested': {
    'id': 120,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    [
    -5,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ant',
    'chicken',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 'octopus',
},
    {
    'id': 121,
    'id_str': [
    '19',
    '05',
],
    'text_data': '22a2f6364d384e479e3f9c3eeec16125',
    'rand_digit': 5,
    'rand_number': 0.95202,
    'rand_signed_int': 9,
    'rand_datetime': '2000-05-12T08:12:02-0300',
    'text_array': [
    'a8d2645fa4c54e25a1f892abce737435',
    '5300e77725ea48499fafce3b7ca21aca',
],
    'words': 'sloth lizard',
    'nested': {
    'id': 121,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 5,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,4__',
    'two_words': [
    'scorpion',
    'elephant',
],
    'city': {
    'name': 'Osaka',
    'geo': {
    'lat': 34.693738,
    'lon': 135.502165,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 7,
    'maybe': 'zebra',
},
    {
    'id': 122,
    'id_str': [
    '14',
],
    'text_data': 'c6aff78d605b465382d706c9fe6b77c8',
    'rand_digit': 3,
    'rand_number': 0.01363,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-12',
    'text_array': [
    'f6c2eb3f4f994c8fae4b363bdb614fb8',
    '3b9c9b65f10041ffaa570556cc3586bf',
],
    'words': 'butterfly monkey',
    'nested': {
    'id': 122,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'sloth',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'butterfly',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'frog',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
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
    [
    -2,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'jaguar',
    'cheetah',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'kangaroo',
    'maybe_null': 'gorilla',
},
    {
    'id': 123,
    'id_str': [
    '08',
    '19',
    '25',
],
    'text_data': 'efd4b25bbbc9488cbd744008a5459b15',
    'rand_digit': 9,
    'rand_number': 0.51834,
    'rand_signed_int': -5,
    'rand_datetime': '2000-06-23 08:45:08',
    'text_array': [
    'e561ebaa391141df967c5e0eb8b65894',
    'f54921c7d91f42a58060fb8915df1a56',
],
    'words': 'cat kangaroo',
    'nested': {
    'id': 123,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'frog',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 4,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fly',
    'cheetah',
],
    'city': {
    'name': 'Barcelona',
    'geo': {
    'lat': 41.385064,
    'lon': 2.173403,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'bear',
},
    {
    'id': 124,
    'id_str': [
    '16',
],
    'text_data': 'e08dd593593747ccbd7e9a0ceb9462e0',
    'rand_digit': 9,
    'rand_number': 0.16073,
    'rand_signed_int': 7,
    'rand_datetime': '2000-09-17T12:31:17.423303',
    'text_array': [
    '2bb63872180c48698a44da735aed6028',
    'c3111ced121d4c66b85bb6e4f1de11c1',
],
    'words': 'spider lobster',
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
    'word': 'grasshopper',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snake',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
],
    [
],
    [
],
],
    'two_words': [
    'fly',
    'goat',
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
    'mixed_type': 'squid',
    'maybe': 'bird',
    'maybe_null': 'elephant',
},
    {
    'id': 125,
    'id_str': [
],
    'text_data': 'c04f6051945141d1bd5d0f3a7ec7db09',
    'rand_digit': 5,
    'rand_number': 0.92558,
    'rand_signed_int': -4,
    'rand_datetime': '2000-06-09 07:26:19.825641-1200',
    'text_array': [
    '16a3babbcbce4a32851ea7adb7ce5277',
    '2af63ad979cd49f78f5d3878873bba5b',
],
    'words': 'butterfly octopus',
    'nested': {
    'id': 125,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bee',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    6,
],
],
    'two_words': [
    'monkey',
    'monkey',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'rhino',
    'maybe_null': 'kangaroo',
},
    {
    'id': 126,
    'id_str': [
    '16',
    '12',
    '10',
    '02',
],
    'text_data': '3d48d770295845bdac2df7aa6b43f723',
    'rand_digit': 8,
    'rand_number': 0.714,
    'rand_signed_int': 1,
    'rand_datetime': '2000-02-16T17:39:52',
    'text_array': [
    'a391bce93b774c7f89d0fad43e5769f4',
    '11d9123a7e8c4048a0512dbe87265d64',
],
    'words': 'wolf bear',
    'nested': {
    'id': 126,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'rhino',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'snake',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'deer',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'zebra',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'jaguar',
    'jaguar',
],
    'city': {
    'name': 'Moscow',
    'geo': {
    'lat': 55.755826,
    'lon': 37.6173,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
    {
    'id': 127,
    'id_str': [
    '18',
    '19',
],
    'text_data': 'b06af0ed3f864001b3413e2fa32e527a',
    'rand_digit': 1,
    'rand_number': 0.55372,
    'rand_signed_int': -4,
    'rand_datetime': '2000-05-27 12:39:52',
    'text_array': [
    '6a20875b08ef4e9f91a8cd97cad96eda',
    '6011d5473f5b4ff0bcc38850aa929b64',
],
    'words': 'grasshopper ladybug',
    'nested': {
    'id': 127,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 4,
},
],
},
    'nested_array': [
    [
    2,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    -7,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'fox',
    'lion',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'zebra',
    'maybe_null': 'snail',
},
    {
    'id': 128,
    'id_str': [
    '10',
    '15',
    '26',
    '18',
],
    'text_data': '3d913d3951e041afa462a434985e7b48',
    'rand_digit': 4,
    'rand_number': 0.67276,
    'rand_signed_int': -9,
    'rand_datetime': '2000-03-02T16:25:23.225731-1100',
    'text_array': [
    '68a187e4d8b642bc86baf763edb48715',
    '32721f57453f4e1885ec1222210e001e',
],
    'words': 'mosquito dolphin',
    'nested': {
    'id': 128,
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
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'rhino',
    'kangaroo',
],
    'city': {
    'name': 'Edinburgh',
    'geo': {
    'lat': 55.953252,
    'lon': -3.188267,
},
},
    'rand_tuple': [
    34,
],
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'spider',
},
    {
    'id': 129,
    'id_str': [
    '05',
    '19',
],
    'text_data': '5b793842e8924d649316417196db3da2',
    'rand_digit': 7,
    'rand_number': 0.41429,
    'rand_signed_int': -6,
    'rand_datetime': '2001-01-12T18:30:05.363641',
    'text_array': [
    '0eb3324681ce42e990f7dccf310733d7',
    '086618854adb401187cb8a1c177fa2c8',
],
    'words': 'koala bird',
    'nested': {
    'id': 129,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'hippo',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 4,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'dolphin',
    'grasshopper',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'duck',
    'maybe_null': 'dragonfly',
},
    {
    'id': 130,
    'id_str': [
    '02',
    '18',
],
    'text_data': '50da9a648d8e48769a96e71acc28db47',
    'rand_digit': 7,
    'rand_number': 0.10862,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-17 00:02',
    'text_array': [
    '1b33b681992849ca8eba34311d1fbef6',
    '8fcf4882bfa441d2bae5669c61ae94ed',
],
    'words': 'tiger fish',
    'nested': {
    'id': 130,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 9,
},
],
},
    'nested_array': [
],
    'two_words': [
    'dolphin',
    'lobster',
],
    'city': {
    'name': 'Beijing',
    'geo': {
    'lat': 39.9042,
    'lon': 116.407396,
},
},
    'rand_tuple': [
    50,
],
    'rand_bool': False,
    'mixed_type': 4,
    'maybe_null': 'fox',
},
    {
    'id': 131,
    'id_str': [
    '12',
    '04',
],
    'text_data': '915bf7449dcb46a6b47e87572712124d',
    'rand_digit': 6,
    'rand_number': 0.93617,
    'rand_signed_int': 4,
    'rand_datetime': '2000-10-30 04:43:33.518240-0300',
    'text_array': [
    '7012a2c795c34702a23e2fb534dcb44e',
    '29d5a2ebdcf14cc09a90ef742f08602b',
],
    'words': 'leopard kangaroo',
    'nested': {
    'id': 131,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
    1,
],
    [
],
],
    'two_words': [
    'fox',
    'spider',
],
    'city': {
    'name': 'Donetsk',
    'geo': {
    'lat': 48.015883,
    'lon': 37.80285,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'rabbit',
    'maybe_null': 'sloth',
},
    {
    'id': 132,
    'id_str': [
    '16',
    '05',
    '06',
    '22',
],
    'text_data': 'c4bfcad33859416e8fc91603e62ada36',
    'rand_digit': 3,
    'rand_number': 0.20131,
    'rand_signed_int': -8,
    'rand_datetime': '2000-05-23T00:48:38+0700',
    'text_array': [
    '8d3ef094325e477c955ee512c74fde7e',
    '85bf2bfa767f40d3a570646f3136a097',
],
    'words': 'gorilla gorilla',
    'nested': {
    'id': 132,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'tiger',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'shark',
    'number': 1,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'shark',
    'rabbit',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'fly',
    'maybe_null': None,
},
    {
    'id': 133,
    'id_str': [
    '07',
    '14',
],
    'text_data': '25ed4222ca4c46f0a4695eded9623e0a',
    'rand_digit': 4,
    'rand_number': 0.21843,
    'rand_signed_int': 6,
    'rand_datetime': '2000-05-25T02:48:35.622366',
    'text_array': [
    '7cc4a9f887a04072bbd3ed8fb9b0ca3f',
    '067ce06744b94c1f8aa434de41bfd02e',
],
    'words': 'cat whale',
    'nested': {
    'id': 133,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'mosquito',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 4,
},
],
},
    'nested_array': [
    [
    -7,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    1,
],
    [
    -4,
],
],
    'two_words': [
    'bird',
    'tiger',
],
    'city': {
    'name': 'Shanghai',
    'geo': {
    'lat': 31.230416,
    'lon': 121.473701,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'lion',
    'maybe_null': 'turtle',
},
    {
    'id': 134,
    'id_str': [
],
    'text_data': 'bb38f306e0414ff2ae4ccc7df9a52e16',
    'rand_digit': 9,
    'rand_number': 0.48378,
    'rand_signed_int': 7,
    'rand_datetime': '2000-05-08',
    'text_array': [
    '459da7f48d00431f90f82e583c0cec37',
    'a3d03a4adc834f8faa084525c6f6d45b',
],
    'words': 'zebra hyena',
    'nested': {
    'id': 134,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
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
    'word': 'tiger',
    'number': 9,
},
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
    'hello',
],
    'word': 'cow',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'butterfly',
    'elephant',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe_null': 'bee',
},
    {
    'id': 135,
    'id_str': [
    '23',
],
    'text_data': 'cf7478ad78be40cf8af18c0a96456375',
    'rand_digit': 9,
    'rand_number': 0.6036,
    'rand_signed_int': 3,
    'rand_datetime': '2001-01-25 10:38:39.124390',
    'text_array': [
    '6ba2b9c7497b4467812b9598b39a5084',
    'b007e5726b7348769f1d95e4c3e38e37',
],
    'words': 'rabbit hyena',
    'nested': {
    'id': 135,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'duck',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'pig',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'horse',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'mosquito',
    'ladybug',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': [
    27,
],
    'rand_bool': False,
    'mixed_type': True,
},
    {
    'id': 136,
    'id_str': [
    '25',
],
    'text_data': 'bf540b87f1d6472186b597d12034feb0',
    'rand_digit': 3,
    'rand_number': 0.3087,
    'rand_signed_int': 9,
    'rand_datetime': '2000-08-04 12:03:24.448553-0300',
    'text_array': [
    'ecfa3c77b0634f6fa7c3e595d7f5404b',
    '05a3966635a6409a97a65b988ca22133',
],
    'words': 'deer pig',
    'nested': {
    'id': 136,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 7,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mosquito',
    'whale',
],
    'city': {
    'name': 'Barcelona',
    'geo': {
    'lat': 41.385064,
    'lon': 2.173403,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'lion',
    'maybe_null': 'scorpion',
},
    {
    'id': 137,
    'id_str': [
    '27',
    '08',
    '16',
    '21',
    '09',
],
    'text_data': 'a3d9f423866843649f0fa72161080ce3',
    'rand_digit': 2,
    'rand_number': 0.40344,
    'rand_signed_int': -10,
    'rand_datetime': '2000-04-18 08:13:10-1100',
    'text_array': [
    'c75a83a1ee83463f8449fb7d28be5198',
    '819246a9cee045d6b5d22ec4cb361eaa',
],
    'words': 'goat mouse',
    'nested': {
    'id': 137,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ladybug',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'spider',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'octopus',
    'fly',
],
    'city': {
    'name': 'Bucharest',
    'geo': {
    'lat': 44.426767,
    'lon': 26.102538,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'lobster',
},
    {
    'id': 138,
    'id_str': [
    '04',
    '16',
    '14',
    '24',
],
    'text_data': '432a40ac3620449fa5dab8f3d351af64',
    'rand_digit': 2,
    'rand_number': 0.69363,
    'rand_signed_int': -9,
    'rand_datetime': '2001-01-13 05:08',
    'text_array': [
    '20712b8743d84cd4848b48f8553a6b85',
    '07c7b8142b20493cba30bd8d5d08d807',
],
    'words': 'bee camel',
    'nested': {
    'id': 138,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hippo',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
],
    'two_words': [
    'giraffe',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
    {
    'id': 139,
    'id_str': [
    '26',
],
    'text_data': 'd9018783be4c4671be6836109d1a4fd0',
    'rand_digit': 2,
    'rand_number': 0.99666,
    'rand_signed_int': 8,
    'rand_datetime': '2000-08-24 04:58',
    'text_array': [
    'c2a923c9f3a84c02bbf8852f9bee95db',
    'ad6b2265a2dc476995fda8a63292135f',
],
    'words': 'rhino lion',
    'nested': {
    'id': 139,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 2,
},
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
    'hello',
],
    'word': 'zebra',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'whale',
    'rhino',
],
    'city': {
    'name': 'Berlin',
    'geo': {
    'lat': 52.520008,
    'lon': 13.404954,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 'wolf',
    'maybe_null': 'dog',
},
    {
    'id': 140,
    'id_str': [
],
    'text_data': '3dc0dc85e5cb4ae386b5542b3f2e6f21',
    'rand_digit': 9,
    'rand_number': 0.17041,
    'rand_signed_int': 2,
    'rand_datetime': '2000-06-27T02:15:07.356052',
    'text_array': [
    'c5b63830078d43ecbc7109009174ce64',
    'c64f44cb54cb420e96329f7aa416811b',
],
    'words': 'leopard mouse',
    'nested': {
    'id': 140,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
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
    'hello',
],
    'word': 'scorpion',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'koala',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'whale',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'snake',
    'lizard',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
},
    {
    'id': 141,
    'id_str': [
    '27',
],
    'text_data': '1e16173025c3469aa37d0ed96f2fff35',
    'rand_digit': 5,
    'rand_number': 0.49592,
    'rand_signed_int': -1,
    'rand_datetime': '2000-06-02',
    'text_array': [
    '835c98ca6e6c478cbf59b610e6cc8f41',
    '44c1134e031c4cd3ab6bd39eb663273c',
],
    'words': 'goat goat',
    'nested': {
    'id': 141,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'cheetah',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'dog',
    'cat',
],
    'city': {
    'name': 'Belfast',
    'geo': {
    'lat': 54.597285,
    'lon': -5.93012,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'dragonfly',
},
    {
    'id': 142,
    'id_str': [
    '17',
    '06',
],
    'text_data': '1e029bf3fc774dedb78d26902c4df52c',
    'rand_digit': 1,
    'rand_number': 0.3697,
    'rand_signed_int': -6,
    'rand_datetime': '2000-09-29 18:39:37',
    'text_array': [
    'd9c2623ea46b438882a9e5b5f81bcf42',
    '2a6a1a7768fb42538d748918b8d62580',
],
    'words': 'fly crab',
    'nested': {
    'id': 142,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'snake',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bee',
    'pig',
],
    'city': {
    'name': 'Hong Kong',
    'geo': {
    'lat': 22.396428,
    'lon': 114.109497,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'mouse',
    'maybe_null': 'hippo',
},
    {
    'id': 143,
    'id_str': [
    '22',
    '27',
    '10',
    '27',
],
    'text_data': '77d3c94db398468c978306e83b282145',
    'rand_digit': 4,
    'rand_number': 0.62631,
    'rand_signed_int': -5,
    'rand_datetime': '2001-01-13T00:58:36.625547-10:00',
    'text_array': [
    'b34330332ded4a70a1d675676e46eb88',
    'a0afa065e7ed4181ac2ae1e8e332f8b5',
],
    'words': 'deer hyena',
    'nested': {
    'id': 143,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'crab',
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
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'kangaroo',
    'lizard',
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
    'mixed_type': None,
    'maybe_null': None,
},
    {
    'id': 144,
    'id_str': [
    '11',
    '02',
],
    'text_data': '6e305d926ee74dfeafb5d3765219b1ea',
    'rand_digit': 8,
    'rand_number': 0.12641,
    'rand_signed_int': 0,
    'rand_datetime': '2000-04-09 12:30:42',
    'text_array': [
    'e7b57b97876b4fb1ae80fb0545a185bf',
    '35c161a351bf4dbfb356746c0905863a',
],
    'words': 'hippo frog',
    'nested': {
    'id': 144,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'mosquito',
    'snake',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': [
    27,
],
    'rand_bool': True,
    'mixed_type': None,
    'maybe': 'mosquito',
    'maybe_null': 'snake',
},
    {
    'id': 145,
    'id_str': [
    '16',
    '22',
    '28',
    '03',
    '05',
],
    'text_data': '78a9916bb8e84c38afd63275d96c95ef',
    'rand_digit': 0,
    'rand_number': 0.63673,
    'rand_signed_int': 10,
    'rand_datetime': '2000-01-05 01:58',
    'text_array': [
    'ebb210c6b5eb407baf39601f2b197e12',
    'b15d2e63a58c46e5bc7f07647f793b50',
],
    'words': 'fly horse',
    'nested': {
    'id': 145,
    'rand_digit': 1,
    'array': [
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
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 10,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lizard',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'ape',
    'bee',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'rhino',
},
    {
    'id': 146,
    'id_str': [
    '18',
    '30',
    '16',
],
    'text_data': '03554f618c894af7ad967f572a18a136',
    'rand_digit': 0,
    'rand_number': 0.15898,
    'rand_signed_int': 2,
    'rand_datetime': '2000-09-24 02:26:49',
    'text_array': [
    'c37646a0f3d04d6aa650fc6e2c0ec836',
    '978bdfa3789c4c1dbb5852931cffccc5',
],
    'words': 'butterfly crab',
    'nested': {
    'id': 146,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'bird',
    'number': 8,
},
],
},
    'nested_array': [
],
    'two_words': [
    'squid',
    'squid',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'zebra',
    'maybe_null': 'cheetah',
},
    {
    'id': 147,
    'id_str': [
    '08',
    '19',
    '14',
],
    'text_data': '27bcecdf23bf48faa988911c23f20fb7',
    'rand_digit': 0,
    'rand_number': 0.61777,
    'rand_signed_int': -6,
    'rand_datetime': '2000-03-16 20:16:16.195664-1200',
    'text_array': [
    'c76e8f7c1d96424c8c30a03e26f8452b',
    '4019554b2d2644908eca2afa3c2c4676',
],
    'words': 'octopus fish',
    'nested': {
    'id': 147,
    'rand_digit': 7,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -10,
],
    [
    -8,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'giraffe',
    'lizard',
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
    'mixed_type': True,
    'maybe_null': 'hippo',
},
    {
    'id': 148,
    'id_str': [
    '18',
    '15',
    '17',
    '02',
],
    'text_data': 'de5fcf3af2544165b9739ca1aa8675cb',
    'rand_digit': 8,
    'rand_number': 0.27968,
    'rand_signed_int': -8,
    'rand_datetime': '2000-05-27T02:35:48.670436',
    'text_array': [
    'ba84f4fe922542c8b24877f12dbbd662',
    '069382e05fb6432fb14ef08bd3287060',
],
    'words': 'dolphin cat',
    'nested': {
    'id': 148,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'fox',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fox',
    'number': 4,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=5, normalized=True),
    'two_words': [
    'lobster',
    'bee',
],
    'city': {
    'name': 'Mexico City',
    'geo': {
    'lat': 19.432608,
    'lon': -99.133208,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': None,
},
    {
    'id': 149,
    'id_str': [
    '03',
],
    'text_data': '793192cb48224cf8bec540ca60222bf2',
    'rand_digit': 7,
    'rand_number': 0.02734,
    'rand_signed_int': -2,
    'rand_datetime': '2000-07-11T10:29:46.768524-01:00',
    'text_array': [
    '23f26e8845a549a6b024e986b484f516',
    'e24c78670d024d87943d9be6d77d417a',
],
    'words': 'hippo mosquito',
    'nested': {
    'id': 149,
    'rand_digit': 8,
    'array': [
],
},
    'nested_array': [
],
    'two_words': [
    'camel',
    'shark',
],
    'city': {
    'name': 'Manchester',
    'geo': {
    'lat': 53.480759,
    'lon': -2.242631,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
},
    {
    'id': 150,
    'id_str': [
    '04',
],
    'text_data': '1a8fdda851c74b088dda6fd3aff2513d',
    'rand_digit': 2,
    'rand_number': 0.69187,
    'rand_signed_int': 6,
    'rand_datetime': '2000-07-10 17:51:40-0700',
    'text_array': [
    '52e8c3bad1b94b7fbb71dbc243f3b305',
    '60d7babc8da445a483895e2c14cd20ce',
],
    'words': 'panda duck',
    'nested': {
    'id': 150,
    'rand_digit': 2,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cow',
    'rabbit',
],
    'city': {
    'name': 'Nizhny Novgorod',
    'geo': {
    'lat': 56.326887,
    'lon': 44.007496,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe_null': 'octopus',
},
    {
    'id': 151,
    'id_str': [
    '02',
    '19',
    '01',
    '21',
    '13',
],
    'text_data': 'ba10b71978994db8ad64c1d0073d8894',
    'rand_digit': 1,
    'rand_number': 0.48759,
    'rand_signed_int': -7,
    'rand_datetime': '2001-01-01',
    'text_array': [
    '0bfe57eef35d4722ac35f49fa9bb4652',
    '98e986be21af4c44aad3d017b7af2573',
],
    'words': 'fish tiger',
    'nested': {
    'id': 151,
    'rand_digit': 6,
    'array': [
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
    'word': 'rabbit',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'squid',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'mouse',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    -9,
],
    [
    7,
],
],
    'two_words': [
    'lion',
    'pig',
],
    'city': {
    'name': 'Sydney',
    'geo': {
    'lat': -33.86882,
    'lon': 151.209296,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 9,
    'maybe_null': 'rhino',
},
    {
    'id': 152,
    'id_str': [
    '14',
    '08',
    '07',
    '23',
],
    'text_data': '44865a20f5764db5a0b9862c6693f9b3',
    'rand_digit': 3,
    'rand_number': 0.07408,
    'rand_signed_int': 1,
    'rand_datetime': '2000-11-05 01:44:57.921407',
    'text_array': [
    'ba491ae95c504bf08dc2d493325cc28b',
    'fb121601593943c99902e2561bf2cc07',
],
    'words': 'fox pig',
    'nested': {
    'id': 152,
    'rand_digit': 6,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    [
    -3,
],
],
    'two_words': [
    'deer',
    'hyena',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 4,
    'maybe': 'frog',
    'maybe_null': 'mouse',
},
    {
    'id': 153,
    'id_str': [
    '08',
    '19',
    '01',
    '21',
    '16',
],
    'text_data': 'b954ac9a3351405b9eb6c6c41d88f21f',
    'rand_digit': 1,
    'rand_number': 0.51952,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-13 17:03',
    'text_array': [
    '070d76648e79407dbc2140f0094229b7',
    '3efac67aad3b47f592a23ee53119932d',
],
    'words': 'frog octopus',
    'nested': {
    'id': 153,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'pig',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'turtle',
    'snake',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'ant',
    'maybe_null': None,
},
    {
    'id': 154,
    'id_str': [
    '16',
    '04',
    '28',
    '04',
],
    'text_data': '27815b15464e48f39da78af245fe8fad',
    'rand_digit': 7,
    'rand_number': 0.36238,
    'rand_signed_int': -6,
    'rand_datetime': '2000-01-10 22:29:30',
    'text_array': [
    '4155c484b2664e549ec9ed66452f2eba',
    '82bc46920ee64631b588de8d120aed1d',
],
    'words': 'ant elephant',
    'nested': {
    'id': 154,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    [
    5,
],
    [
    2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'rhino',
    'pig',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'sloth',
    'maybe_null': None,
},
    {
    'id': 155,
    'id_str': [
    '20',
    '04',
],
    'text_data': '7d765b639d2c4b2fb9d7242eadcdbf88',
    'rand_digit': 9,
    'rand_number': 0.2413,
    'rand_signed_int': 1,
    'rand_datetime': '2000-02-28T08:41:32+0800',
    'text_array': [
    '4b654e721a484fdc871338b4b8d4fe2c',
    '47ddc507f8004450a225174e4951ded9',
],
    'words': 'crab fly',
    'nested': {
    'id': 155,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 8,
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
],
    'two_words': [
    'fly',
    'bee',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': [
    43,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'fish',
},
    {
    'id': 156,
    'id_str': [
    '02',
    '03',
    '23',
],
    'text_data': 'f310e281eb84437882b28d64e26738d0',
    'rand_digit': 2,
    'rand_number': 0.26542,
    'rand_signed_int': -1,
    'rand_datetime': '2000-06-26',
    'text_array': [
    '99c4792d2a8842f3ab5370966cd613a7',
    'aa47b83150b043dcaf691e8548df944a',
],
    'words': 'whale camel',
    'nested': {
    'id': 156,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'fish',
    'tiger',
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
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'snail',
},
    {
    'id': 157,
    'id_str': [
    '02',
    '18',
],
    'text_data': 'd55b7bced2a541749913f7474f203bc5',
    'rand_digit': 8,
    'rand_number': 0.21522,
    'rand_signed_int': 0,
    'rand_datetime': '2000-12-06T14:57:39.824493-0700',
    'text_array': [
    '7ae0dff95ebc484cb274e40790b51ccd',
    '308574780d0f46718ab335e7eba28ac3',
],
    'words': 'ape koala',
    'nested': {
    'id': 157,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lion',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 1,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'kangaroo',
    'rhino',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': [
    42,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': None,
},
    {
    'id': 158,
    'id_str': [
    '06',
    '19',
    '13',
    '02',
],
    'text_data': '7a3acab60bb14badbb5c3234225d44dc',
    'rand_digit': 6,
    'rand_number': 0.92889,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-02T06:55:17.696016',
    'text_array': [
    '1656a756eefb4b70b4fc1271076d576b',
    '2dcafe08c37f48539bd0d91f36c18b89',
],
    'words': 'dragonfly squid',
    'nested': {
    'id': 158,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
    -6,
],
    [
    4,
],
    [
    1,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'snail',
    'lobster',
],
    'city': {
    'name': 'Milan',
    'geo': {
    'lat': 45.464204,
    'lon': 9.189982,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': {
    'key': 'value',
},
},
    {
    'id': 159,
    'id_str': [
    '26',
    '28',
],
    'text_data': 'ae2a696fbfca4fa2a7efef39bbcc4bb7',
    'rand_digit': 4,
    'rand_number': 0.55572,
    'rand_signed_int': -6,
    'rand_datetime': '2000-09-16',
    'text_array': [
    'c9f5104734194e789798eb8c24dc4171',
    'fe14beaa7f334d64831536574cb6756d',
],
    'words': 'ant camel',
    'nested': {
    'id': 159,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bird',
    'number': 1,
},
],
},
    'nested_array': [
    [
    -2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'wolf',
    'koala',
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
},
    {
    'id': 160,
    'id_str': [
    '03',
    '28',
    '04',
],
    'text_data': 'de1e4f2c5f424fa4886a7d77f7c85843',
    'rand_digit': 8,
    'rand_number': 0.26326,
    'rand_signed_int': 5,
    'rand_datetime': '2000-07-03 03:07:01',
    'text_array': [
    'e5e2b568981e4f48b367d9e19a79b3a7',
    'afe11cddf7e945faafedbc6b2f64ec3c',
],
    'words': 'giraffe zebra',
    'nested': {
    'id': 160,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dragonfly',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'octopus',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'shark',
    'bear',
],
    'city': {
    'name': 'Tallinn',
    'geo': {
    'lat': 59.436961,
    'lon': 24.753575,
},
},
    'rand_tuple': [
    22,
],
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'cow',
    'maybe_null': 'squid',
},
    {
    'id': 161,
    'id_str': [
    '07',
    '18',
],
    'text_data': '107afbd2932a4a98b4a05b0438ac2b01',
    'rand_digit': 6,
    'rand_number': 0.83493,
    'rand_signed_int': 0,
    'rand_datetime': '2000-10-13 03:36',
    'text_array': [
    '364f63fca06642c9ac788d55ef2a49c6',
    'ac923f161cc24717a1e0f52a03b602aa',
],
    'words': 'horse leopard',
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
    'word': 'squid',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'duck',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cat',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bird',
    'number': 9,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'chicken',
    'octopus',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': 'squid',
},
    {
    'id': 162,
    'id_str': [
    '16',
    '25',
    '07',
],
    'text_data': '0259bcedf2304c7491a3ab0b48f64129',
    'rand_digit': 2,
    'rand_number': 0.14092,
    'rand_signed_int': 7,
    'rand_datetime': '2001-01-15T08:08:16.886526+0900',
    'text_array': [
    'fe8f30002a564187a8a772eb94314ddd',
    '198f4b590e7248bcbdd533f42627cde7',
],
    'words': 'kangaroo cheetah',
    'nested': {
    'id': 162,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'crab',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fish',
    'number': 3,
},
],
},
    'nested_array': [
    [
],
],
    'two_words': [
    'cheetah',
    'bee',
],
    'city': {
    'name': 'Brussels',
    'geo': {
    'lat': 50.85034,
    'lon': 4.35171,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': True,
    'mixed_type': 0.50897,
    'maybe_null': 'deer',
},
    {
    'id': 163,
    'id_str': [
    '11',
    '08',
    '04',
],
    'text_data': '8f377970cab94e4d97666f008411adb6',
    'rand_digit': 2,
    'rand_number': 0.59437,
    'rand_signed_int': -9,
    'rand_datetime': '2000-09-27T07:43:07',
    'text_array': [
    '077f1c0ee44847d79a6193bb0df9a4ce',
    '93068695d2b2400882537efea8c3f959',
],
    'words': 'koala sloth',
    'nested': {
    'id': 163,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'koala',
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    [
    9,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'scorpion',
    'rabbit',
],
    'city': {
    'name': 'Rome',
    'geo': {
    'lat': 41.902782,
    'lon': 12.496366,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.38068,
    'maybe': 'sloth',
    'maybe_null': 'bear',
},
    {
    'id': 164,
    'id_str': [
    '28',
    '10',
    '18',
    '18',
],
    'text_data': '51447941a7214ec298843c6aa45ba107',
    'rand_digit': 0,
    'rand_number': 0.87805,
    'rand_signed_int': -1,
    'rand_datetime': '2000-09-28T21:41:08.613943+0700',
    'text_array': [
    '641369bc097c415795ad2ac7d71fb8d3',
    'a762017571d1497dbe7005409f704243',
],
    'words': 'monkey hippo',
    'nested': {
    'id': 164,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'gorilla',
    'number': 10,
},
],
},
    'nested_array': [
],
    'two_words': [
    'ladybug',
    'camel',
],
    'city': {
    'name': 'Johannesburg',
    'geo': {
    'lat': -26.204103,
    'lon': 28.047305,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.60393,
},
    {
    'id': 165,
    'id_str': [
    '24',
    '11',
],
    'text_data': 'b36353f4978b4ae8b0d46306329dc381',
    'rand_digit': 1,
    'rand_number': 0.2756,
    'rand_signed_int': 0,
    'rand_datetime': '2000-02-02T21:28:29.556228',
    'text_array': [
    '334bf9d2b91b4880ad8a1ece69829d20',
    '12441057991b4bc09f3add62b2471223',
],
    'words': 'fish duck',
    'nested': {
    'id': 165,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'elephant',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'shark',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 1,
},
],
},
    'nested_array': '__FLOAT_MULTI_DIM_2,3__',
    'two_words': [
    'goat',
    'goat',
],
    'city': {
    'name': 'Lviv',
    'geo': {
    'lat': 49.839683,
    'lon': 24.029717,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'rhino',
    'maybe': 'spider',
    'maybe_null': 'zebra',
},
    {
    'id': 166,
    'id_str': [
    '23',
    '19',
    '13',
    '15',
    '18',
],
    'text_data': '9f39c7aa8884413dbd649df62050f20e',
    'rand_digit': 2,
    'rand_number': 0.43603,
    'rand_signed_int': -6,
    'rand_datetime': '2000-12-21 14:02:39.505236',
    'text_array': [
    'f6b276211a3548a48d465b502c756bfe',
    '1c27ae3bdf624de9ab4d5cb305bca549',
],
    'words': 'pig zebra',
    'nested': {
    'id': 166,
    'rand_digit': 6,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fly',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
],
],
    'two_words': [
    'cat',
    'mosquito',
],
    'city': {
    'name': 'Riga',
    'geo': {
    'lat': 56.949649,
    'lon': 24.105186,
},
},
    'rand_tuple': [
    81,
],
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'snail',
},
    {
    'id': 167,
    'id_str': [
    '19',
    '28',
    '22',
    '21',
    '21',
],
    'text_data': '226917d1602e474bbdb89e4f809281ea',
    'rand_digit': 9,
    'rand_number': 0.70197,
    'rand_signed_int': -2,
    'rand_datetime': '2000-06-03 18:40:57.127071',
    'text_array': [
    '2ac78de44c6547cf851495fccfb7c411',
    '1c118084712f4294aa6bd403247de274',
],
    'words': 'camel bee',
    'nested': {
    'id': 167,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snake',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'fly',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'whale',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fly',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    5,
],
],
    'two_words': [
    'bird',
    'wolf',
],
    'city': {
    'name': 'Tokyo',
    'geo': {
    'lat': 35.689487,
    'lon': 139.691706,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': 3,
    'maybe_null': 'fly',
},
    {
    'id': 168,
    'id_str': [
    '03',
],
    'text_data': '37f8df63f9aa4e7cb4917e5a93b650de',
    'rand_digit': 6,
    'rand_number': 0.64569,
    'rand_signed_int': -4,
    'rand_datetime': '2000-11-24 16:36:19.986367+0900',
    'text_array': [
    'e23517c87d924a6488f41f14132eeb19',
    'd4c3d82860f94101ad592b4b1a2c61d4',
],
    'words': 'bee rabbit',
    'nested': {
    'id': 168,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'whale',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'kangaroo',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'panda',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 9,
},
],
},
    'nested_array': [
    [
    4,
],
    [
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'monkey',
    'rabbit',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'zebra',
},
    {
    'id': 169,
    'id_str': [
    '23',
],
    'text_data': '8f0d05161127449994b627a0011f842f',
    'rand_digit': 8,
    'rand_number': 0.24829,
    'rand_signed_int': 5,
    'rand_datetime': '2000-04-15T03:12:57.278421',
    'text_array': [
    'ab7360d686214cf281d311f505215c86',
    '43ecbee437a849908304137d16c2662d',
],
    'words': 'elephant panda',
    'nested': {
    'id': 169,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'fox',
    'dolphin',
],
    'city': {
    'name': 'San Francisco',
    'geo': {
    'lat': 37.774929,
    'lon': -122.419416,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'hippo',
},
    {
    'id': 170,
    'id_str': [
    '15',
    '03',
    '13',
    '23',
],
    'text_data': 'e65d5a90d8524bbd89eb5c479d2509f5',
    'rand_digit': 3,
    'rand_number': 0.6155,
    'rand_signed_int': -2,
    'rand_datetime': '2000-10-31T14:35:16.680457',
    'text_array': [
    '66374365163640d3b7494b7a85e25191',
    '70212601d3e64dceb9b9cecaeee63570',
],
    'words': 'tiger dolphin',
    'nested': {
    'id': 170,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 6,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'gorilla',
    'giraffe',
],
    'city': {
    'name': 'Istanbul',
    'geo': {
    'lat': 41.008238,
    'lon': 28.978359,
},
},
    'rand_tuple': [
    59,
],
    'rand_bool': True,
    'mixed_type': 6,
    'maybe_null': None,
},
    {
    'id': 171,
    'id_str': [
    '28',
],
    'text_data': '18e8fbff14c14a74a1f705cea53d1320',
    'rand_digit': 8,
    'rand_number': 0.14402,
    'rand_signed_int': 8,
    'rand_datetime': '2000-08-21T07:47:09',
    'text_array': [
    '793dbf5d4ce64ce3b05c1b4553f1346b',
    'afc515aadb0a43eaa75b9e8cdc35ebc3',
],
    'words': 'crab grasshopper',
    'nested': {
    'id': 171,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cow',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ape',
    'number': 1,
},
    {
    'nested_empty': None,
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
    'word': 'fish',
    'number': 10,
},
],
},
    'nested_array': [
    [
    10,
],
    [
    1,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'kangaroo',
    'dolphin',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe': 'duck',
    'maybe_null': None,
},
    {
    'id': 172,
    'id_str': [
    '10',
    '20',
    '08',
    '27',
    '09',
],
    'text_data': '5b7ceb72a8b44aee9a2d75e912f0a57c',
    'rand_digit': 9,
    'rand_number': 0.74139,
    'rand_signed_int': 3,
    'rand_datetime': '2000-04-24T05:47:26.611477-1000',
    'text_array': [
    'aad9513a502f4327b0e0d2ae6cdb2644',
    '0368da89818843718290710394f5b952',
],
    'words': 'lobster duck',
    'nested': {
    'id': 172,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'mosquito',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'bee',
    'zebra',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
    'maybe': 'monkey',
    'maybe_null': None,
},
    {
    'id': 173,
    'id_str': [
],
    'text_data': '38f57139c06d4a4bbb0fd94f89831c6c',
    'rand_digit': 2,
    'rand_number': 0.51267,
    'rand_signed_int': -6,
    'rand_datetime': '2000-02-05T15:47:45.480525-0100',
    'text_array': [
    '0b50b16850de437a8fa8592b0b75bdc9',
    '3c7c042665ad4591b77e29004ce44ab7',
],
    'words': 'zebra leopard',
    'nested': {
    'id': 173,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'butterfly',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 10,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
    4,
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'hyena',
    'gorilla',
],
    'city': {
    'name': 'Rostov-on-Don',
    'geo': {
    'lat': 47.235713,
    'lon': 39.7015,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': True,
    'mixed_type': None,
    'maybe_null': 'ladybug',
},
    {
    'id': 174,
    'id_str': [
    '15',
],
    'text_data': 'b7f214737d6f42559684082ded69f692',
    'rand_digit': 6,
    'rand_number': 0.29883,
    'rand_signed_int': 4,
    'rand_datetime': '2000-01-21T08:08:39.876101-11:00',
    'text_array': [
    '56f60841c9634f47afd8b430460aba07',
    'd4f0a04ad4804e3c8f419cae14001da7',
],
    'words': 'dragonfly grasshopper',
    'nested': {
    'id': 174,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'deer',
    'number': 1,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'turtle',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'snail',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 1,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'lobster',
    'frog',
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
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'hyena',
    'maybe_null': 'deer',
},
    {
    'id': 175,
    'id_str': [
    '12',
    '01',
],
    'text_data': '863ab6e81d89447f9b1a0c5fd5c99a1c',
    'rand_digit': 2,
    'rand_number': 0.62856,
    'rand_signed_int': -9,
    'rand_datetime': '2000-10-24T10:30:34.216513',
    'text_array': [
    '09a17a9b824c4803aa78da9ffd45ac38',
    '29f6c389f8b043ed8a985cfbfa3d7d34',
],
    'words': 'zebra grasshopper',
    'nested': {
    'id': 175,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'gorilla',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'cow',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'lion',
    'shark',
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
    'mixed_type': None,
    'maybe_null': 'lizard',
},
    {
    'id': 176,
    'id_str': [
    '12',
],
    'text_data': '4090115f8d474b1bac86db06e8c35303',
    'rand_digit': 0,
    'rand_number': 0.52393,
    'rand_signed_int': -2,
    'rand_datetime': '2000-03-06',
    'text_array': [
    '5224505a96174011b194d98832d83037',
    '8859b28fd5614818a3fd5d5f5cda917e',
],
    'words': 'fish cheetah',
    'nested': {
    'id': 176,
    'rand_digit': 9,
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
    'number': 5,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'ladybug',
    'number': 5,
},
],
},
    'nested_array': [
],
    'two_words': [
    'bee',
    'gorilla',
],
    'city': {
    'name': 'Miami',
    'geo': {
    'lat': 25.76168,
    'lon': -80.19179,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 'snake',
},
    {
    'id': 177,
    'id_str': [
    '23',
    '05',
    '02',
    '13',
    '22',
],
    'text_data': '5410f14ad48441e78700babbbf8e0a0c',
    'rand_digit': 7,
    'rand_number': 0.0747,
    'rand_signed_int': 0,
    'rand_datetime': '2000-05-15 19:53',
    'text_array': [
    'c48b0c2e58db40979058cb343489593a',
    '8973989cf8e64561a5b9bfa95183c7b6',
],
    'words': 'butterfly camel',
    'nested': {
    'id': 177,
    'rand_digit': 2,
    'array': [
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
],
    'word': 'hyena',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'panda',
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
    'word': 'rabbit',
    'number': 3,
},
],
},
    'nested_array': [
],
    'two_words': [
    'chicken',
    'lizard',
],
    'city': {
    'name': 'Los Angeles',
    'geo': {
    'lat': 34.052235,
    'lon': -118.243683,
},
},
    'rand_tuple': [
    95,
],
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'rhino',
},
    {
    'id': 178,
    'id_str': [
    '18',
],
    'text_data': '38886bf04bfa4b7f91cde798a13b509d',
    'rand_digit': 9,
    'rand_number': 0.4602,
    'rand_signed_int': -9,
    'rand_datetime': '2000-04-12 18:17:58.407894',
    'text_array': [
    '72c5362949ed4c7f92420ca05b811d71',
    '1e92d4123e154a5ba611eee5dcf74dc6',
],
    'words': 'ladybug koala',
    'nested': {
    'id': 178,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
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
    'word': 'bear',
    'number': 7,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'monkey',
    'number': 7,
},
],
},
    'nested_array': [
    [
    2,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'leopard',
    'goat',
],
    'city': {
    'name': 'Madrid',
    'geo': {
    'lat': 40.416775,
    'lon': -3.70379,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': 8,
    'maybe': 'snail',
    'maybe_null': 'mouse',
},
    {
    'id': 179,
    'id_str': [
    '22',
    '02',
    '07',
],
    'text_data': 'db33a107c1aa4f8fad2785f58a489b5c',
    'rand_digit': 3,
    'rand_number': 0.81273,
    'rand_signed_int': 8,
    'rand_datetime': '2000-08-17T10:16:16.053703',
    'text_array': [
    '2f476d5b603c45689ef42d3ca6a49715',
    '80d26d5a701242de9b29f9e0669531a0',
],
    'words': 'frog pig',
    'nested': {
    'id': 179,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lizard',
    'number': 10,
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
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'frog',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'turtle',
    'ladybug',
],
    'city': {
    'name': 'Liverpool',
    'geo': {
    'lat': 53.410631,
    'lon': -2.97794,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'squid',
    'maybe_null': 'hyena',
},
    {
    'id': 180,
    'id_str': [
],
    'text_data': '65cf9ed7624646babcbcbd9520d7e0de',
    'rand_digit': 4,
    'rand_number': 0.30591,
    'rand_signed_int': -3,
    'rand_datetime': '2000-03-16T02:48:41.098428+0100',
    'text_array': [
    '6cee7dc58f974c33aa3bf237727286ab',
    '4e44f5c3523b4716a9c203b0cbae3579',
],
    'words': 'lizard crab',
    'nested': {
    'id': 180,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'sheep',
    'number': 6,
},
],
},
    'nested_array': [
],
    'two_words': [
    'whale',
    'panda',
],
    'city': {
    'name': 'Newcastle',
    'geo': {
    'lat': 54.978252,
    'lon': -1.61778,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.10445,
},
    {
    'id': 181,
    'id_str': [
    '25',
    '20',
],
    'text_data': 'd7d5ddaf443d4f809b5d51a78b6c9686',
    'rand_digit': 2,
    'rand_number': 0.46581,
    'rand_signed_int': -7,
    'rand_datetime': '2000-06-28',
    'text_array': [
    'd35716c499124d4b90c1994eecb4f86c',
    'ab62bd7177ba48bcb6bbdd8d46445ada',
],
    'words': 'ant bear',
    'nested': {
    'id': 181,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'giraffe',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'spider',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
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
    'word': 'snake',
    'number': 8,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'butterfly',
    'goat',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'snake',
    'maybe': 'turtle',
},
    {
    'id': 182,
    'id_str': [
    '22',
    '04',
],
    'text_data': 'ee60e5c05b4742d3a69ef52ef2e6f6b8',
    'rand_digit': 6,
    'rand_number': 0.68355,
    'rand_signed_int': 2,
    'rand_datetime': '2000-07-09 04:38:23.037229-1100',
    'text_array': [
    '7ff038c3cc8f4eb9b3137f2c478f0038',
    '1a81230692374eb581aba513e2a894d4',
],
    'words': 'gorilla dolphin',
    'nested': {
    'id': 182,
    'rand_digit': 9,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'crab',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'scorpion',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'mouse',
    'number': 9,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'lion',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'ape',
    'number': 5,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
],
    'two_words': [
    'whale',
    'goat',
],
    'city': {
    'name': 'Glasgow',
    'geo': {
    'lat': 55.864237,
    'lon': -4.251806,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': {
    'key': 'value',
},
    'maybe': 'jaguar',
    'maybe_null': None,
},
    {
    'id': 183,
    'id_str': [
],
    'text_data': '07f9c8eed7144e469b7970013638cad3',
    'rand_digit': 6,
    'rand_number': 0.58642,
    'rand_signed_int': -9,
    'rand_datetime': '2000-07-15T07:41:46+0500',
    'text_array': [
    '984d3eb9404f43c3bd533823f3a5484c',
    'b038779f01c14cd28c16fb0a1d0dc4e1',
],
    'words': 'bird dog',
    'nested': {
    'id': 183,
    'rand_digit': 8,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'hyena',
    'number': 7,
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
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ape',
    'frog',
],
    'city': {
    'name': 'Toronto',
    'geo': {
    'lat': 43.653226,
    'lon': -79.383184,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 0.72364,
    'maybe_null': None,
},
    {
    'id': 184,
    'id_str': [
    '05',
],
    'text_data': 'a05395b3a4ef41a7b0a610f3985f88b1',
    'rand_digit': 8,
    'rand_number': 0.36629,
    'rand_signed_int': 6,
    'rand_datetime': '2000-04-10T13:10:59.870943-12:00',
    'text_array': [
    'cd3993b9d21849b591d0af5f724884da',
    '8579971c6aa342c5ae5dac92fa283bb4',
],
    'words': 'cheetah koala',
    'nested': {
    'id': 184,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 4,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bear',
    'number': 1,
},
],
},
    'nested_array': [
],
    'two_words': [
    'shark',
    'elephant',
],
    'city': {
    'name': 'Moscow',
    'geo': {
    'lat': 55.755826,
    'lon': 37.6173,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'frog',
},
    {
    'id': 185,
    'id_str': [
],
    'text_data': '2a2c534963ba41769fc7ed84d98216e3',
    'rand_digit': 3,
    'rand_number': 0.27646,
    'rand_signed_int': -10,
    'rand_datetime': '2000-11-21 10:27:30+0100',
    'text_array': [
    'd67fb92391154100bd1edfa95e190ad7',
    '78db266296ea45dda8fb6c9789e49a79',
],
    'words': 'kangaroo lizard',
    'nested': {
    'id': 185,
    'rand_digit': 1,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'giraffe',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'cheetah',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'cow',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'bear',
    'number': 7,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'camel',
    'octopus',
],
    'city': {
    'name': 'Bristol',
    'geo': {
    'lat': 51.454514,
    'lon': -2.58791,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': None,
    'maybe_null': None,
},
    {
    'id': 186,
    'id_str': [
    '23',
    '24',
],
    'text_data': 'd3288a3a95a54e28870ae94777941d57',
    'rand_digit': 6,
    'rand_number': 0.84072,
    'rand_signed_int': 3,
    'rand_datetime': '2000-09-01 00:08:52.476887-0500',
    'text_array': [
    'a1d648a78133480d872d6129ac2675d5',
    'de506826105b4da690d0422a749ebb5b',
],
    'words': 'hippo cow',
    'nested': {
    'id': 186,
    'rand_digit': 3,
    'array': [
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
    [
    4,
],
],
    'two_words': [
    'snail',
    'hyena',
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
    'mixed_type': 0,
    'maybe': 'hippo',
    'maybe_null': 'snail',
},
    {
    'id': 187,
    'id_str': [
    '19',
    '25',
],
    'text_data': '5e31215f17d44c718bc3631e01f25167',
    'rand_digit': 7,
    'rand_number': 0.65057,
    'rand_signed_int': 7,
    'rand_datetime': '2000-05-18 08:28:13.581052',
    'text_array': [
    'ed60f20981c44fb2aa44c190772115d2',
    'a74bdf612da046a48c3ad5ed7187e783',
],
    'words': 'monkey frog',
    'nested': {
    'id': 187,
    'rand_digit': 4,
    'array': [
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
    self.mutator.generate_float_array(dimension=3, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'ant',
    'snail',
],
    'city': {
    'name': 'Amsterdam',
    'geo': {
    'lat': 52.370216,
    'lon': 4.895168,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': False,
    'maybe': 'lion',
},
    {
    'id': 188,
    'id_str': [
    '21',
    '12',
    '19',
],
    'text_data': '9367dd2ee98d487ba85d822f060ee929',
    'rand_digit': 4,
    'rand_number': 0.81378,
    'rand_signed_int': -2,
    'rand_datetime': '2000-01-12',
    'text_array': [
    'a7be2f72c6c34c6bb26c51a9d85a70cd',
    '746dca153d424c65a0fee0fa38a89d5f',
],
    'words': 'butterfly leopard',
    'nested': {
    'id': 188,
    'rand_digit': 3,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'dolphin',
    'number': 1,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'bee',
    'number': 4,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'hyena',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'leopard',
    'number': 2,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
],
    'two_words': [
    'dolphin',
    'bird',
],
    'city': {
    'name': 'Sheffield',
    'geo': {
    'lat': 53.381129,
    'lon': -1.470085,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'shark',
    'maybe_null': 'horse',
},
    {
    'id': 189,
    'id_str': [
    '27',
    '13',
    '23',
    '04',
],
    'text_data': 'bf45213a01f74f6fa92f6a26fa0b4fab',
    'rand_digit': 4,
    'rand_number': 0.11193,
    'rand_signed_int': -9,
    'rand_datetime': '2000-01-27 02:35:54.525756+1100',
    'text_array': [
    '27706af8d83440e29047da5aba520ece',
    'f09400d6122c4a36b7deb6a7fc6c273b',
],
    'words': 'leopard mouse',
    'nested': {
    'id': 189,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'elephant',
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
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'grasshopper',
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
],
},
    'nested_array': [
],
    'two_words': [
    'dragonfly',
    'fish',
],
    'city': {
    'name': 'Chelyabinsk',
    'geo': {
    'lat': 55.16444,
    'lon': 61.436843,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': True,
    'mixed_type': False,
},
    {
    'id': 190,
    'id_str': [
    '11',
],
    'text_data': '4e644cf26fbf4d8cbaf5e0b306bf8901',
    'rand_digit': 8,
    'rand_number': 0.55681,
    'rand_signed_int': 5,
    'rand_datetime': '2000-02-14 02:44:33.720289',
    'text_array': [
    '1179d64fb0bf47569985ccb7d268d436',
    'bdf6f4cde7074480ba692374c457d85e',
],
    'words': 'ladybug dog',
    'nested': {
    'id': 190,
    'rand_digit': 8,
    'array': [
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
    'word': 'lizard',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'kangaroo',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'fish',
    'number': 8,
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
],
},
    'nested_array': self.mutator.generate_float_array(dimension=3, normalized=True),
    'two_words': [
    'fox',
    'zebra',
],
    'city': {
    'name': 'Riga',
    'geo': {
    'lat': 56.949649,
    'lon': 24.105186,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 'mouse',
    'maybe_null': None,
},
    {
    'id': 191,
    'id_str': [
    '30',
    '27',
],
    'text_data': '9e3774c2d9d6422891227757f82e1be6',
    'rand_digit': 1,
    'rand_number': 0.54348,
    'rand_signed_int': -8,
    'rand_datetime': '2001-01-28 19:01:03.266082-1000',
    'text_array': [
    '8936541cdf3e4b589313c7448399abcb',
    'd910b85346e74cc7a34d8da7513f7ed8',
],
    'words': 'dolphin giraffe',
    'nested': {
    'id': 191,
    'rand_digit': 7,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'ladybug',
    'number': 3,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'shark',
    'number': 8,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'tiger',
    'number': 9,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=4, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'turtle',
    'rabbit',
],
    'city': {
    'name': 'London',
    'geo': {
    'lat': 51.507351,
    'lon': -0.127758,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=2, normalized=True),
    'rand_bool': False,
    'mixed_type': 'turtle',
    'maybe_null': None,
},
    {
    'id': 192,
    'id_str': [
    '26',
    '15',
    '22',
],
    'text_data': 'b2173a5994bf4327a9f6b304201f2749',
    'rand_digit': 1,
    'rand_number': 0.87701,
    'rand_signed_int': 2,
    'rand_datetime': '2000-05-14T15:44:30.871400',
    'text_array': [
    'b07518c1e19a4fabbe00377880bb99da',
    '3423751e552b4ddcacadee60cc0fb2eb',
],
    'words': 'mosquito frog',
    'nested': {
    'id': 192,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'rabbit',
    'number': 9,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'lobster',
    'number': 2,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'lobster',
    'number': 1,
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
],
},
    'nested_array': [
    [
    0,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -5,
],
],
    'two_words': [
    'pig',
    'duck',
],
    'city': {
    'name': 'Kazan',
    'geo': {
    'lat': 55.78874,
    'lon': 49.12214,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=5, normalized=True),
    'rand_bool': False,
    'mixed_type': 3,
    'maybe': 'dragonfly',
    'maybe_null': 'camel',
},
    {
    'id': 193,
    'id_str': [
],
    'text_data': '325536707f2d4ccd8f877bd1771ca0e7',
    'rand_digit': 3,
    'rand_number': 0.67678,
    'rand_signed_int': -5,
    'rand_datetime': '2000-10-09T19:35:34.690755-0100',
    'text_array': [
    '0dc7c699b0634ce4bc7a4b86bc4ae0ae',
    '1be61eaa8456419e914e3a449ce06350',
],
    'words': 'rabbit grasshopper',
    'nested': {
    'id': 193,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'squid',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
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
    'word': 'cow',
    'number': 2,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'grasshopper',
    'number': 6,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 8,
},
],
},
    'nested_array': self.mutator.generate_float_array(dimension=4, normalized=True),
    'two_words': [
    'mouse',
    'ant',
],
    'city': {
    'name': 'Odessa',
    'geo': {
    'lat': 46.47747,
    'lon': 30.73262,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'rabbit',
    'maybe_null': 'rabbit',
},
    {
    'id': 194,
    'id_str': [
    '27',
    '05',
    '05',
],
    'text_data': '4d91ea090496406e97eefecbb88c796c',
    'rand_digit': 8,
    'rand_number': 0.69051,
    'rand_signed_int': 4,
    'rand_datetime': '2000-03-30 20:11',
    'text_array': [
    '17e64dcdb8de4008b8ac95bc0fdb2051',
    '3cbbbc1a6f7b40129e9173aac070b803',
],
    'words': 'lion lizard',
    'nested': {
    'id': 194,
    'rand_digit': 2,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'turtle',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'cow',
    'gorilla',
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
    'maybe_null': 'chicken',
},
    {
    'id': 195,
    'id_str': [
    '09',
],
    'text_data': 'c438d70d3902406fa041329dbb0a8c05',
    'rand_digit': 3,
    'rand_number': 0.66494,
    'rand_signed_int': 10,
    'rand_datetime': '2000-07-14 06:59:58+0600',
    'text_array': [
    '492819d5f23346fbb631be148ed4d72b',
    'ba5659df6412474c8965d590dbe392ef',
],
    'words': 'koala duck',
    'nested': {
    'id': 195,
    'rand_digit': 5,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'fish',
    'number': 8,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'hyena',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'goat',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'rhino',
    'number': 3,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'cat',
    'duck',
],
    'city': {
    'name': 'Moscow',
    'geo': {
    'lat': 55.755826,
    'lon': 37.6173,
},
},
    'rand_tuple': [
    77,
],
    'rand_bool': True,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'duck',
},
    {
    'id': 196,
    'id_str': [
],
    'text_data': 'ccdf8692118843dbb0fd5fa8fb4b19b7',
    'rand_digit': 3,
    'rand_number': 0.45962,
    'rand_signed_int': 4,
    'rand_datetime': '2001-01-27T06:53:27+0400',
    'text_array': [
    '411d082589f54bd8ac8b4776c16a8f6c',
    '4e51bb97c4b040cd9d350ffe55498fbb',
],
    'words': 'lion pig',
    'nested': {
    'id': 196,
    'rand_digit': 0,
    'array': [
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
],
    'word': 'spider',
    'number': 3,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'leopard',
    'number': 6,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'elephant',
    'number': 2,
},
],
},
    'nested_array': [
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    6,
],
    self.mutator.generate_float_array(dimension=4, normalized=True),
],
    'two_words': [
    'spider',
    'leopard',
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
    'mixed_type': True,
},
    {
    'id': 197,
    'id_str': [
    '23',
    '24',
    '06',
],
    'text_data': 'b6a8ed2b1ff04ef89a7800f9c874ca20',
    'rand_digit': 6,
    'rand_number': 0.70113,
    'rand_signed_int': 0,
    'rand_datetime': '2000-03-02 00:59:06',
    'text_array': [
    '78574775b54145c0b56d19c47596c0b0',
    '791efc4b31054bb498d2657f8c0b14b1',
],
    'words': 'bird frog',
    'nested': {
    'id': 197,
    'rand_digit': 4,
    'array': [
],
},
    'nested_array': [
    [
    4,
],
    self.mutator.generate_float_array(dimension=3, normalized=True),
    [
    -6,
],
    self.mutator.generate_float_array(dimension=2, normalized=True),
],
    'two_words': [
    'shark',
    'ape',
],
    'city': {
    'name': 'Zaporizhzhya',
    'geo': {
    'lat': 47.82229,
    'lon': 35.190319,
},
},
    'rand_tuple': [
    50,
],
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe_null': 'ladybug',
},
    {
    'id': 198,
    'id_str': [
],
    'text_data': 'c44ad00055eb4b52943b1af6d4fb227e',
    'rand_digit': 5,
    'rand_number': 0.34476,
    'rand_signed_int': -5,
    'rand_datetime': '2000-05-17 23:32:01+0900',
    'text_array': [
    '08205a8566454ea98d523245d531c05a',
    'a34e9ae3a14d4f478f9b8ef2471d08c5',
],
    'words': 'wolf grasshopper',
    'nested': {
    'id': 198,
    'rand_digit': 4,
    'array': [
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'octopus',
    'number': 7,
},
    {
    'nested_empty': [
    'hello',
],
    'nested_empty2': [
    'hello',
],
    'word': 'deer',
    'number': 5,
},
    {
    'nested_empty': None,
    'nested_empty2': [
],
    'word': 'scorpion',
    'number': 10,
},
    {
    'nested_empty': None,
    'nested_empty2': [
    'hello',
],
    'word': 'dolphin',
    'number': 5,
},
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'goat',
    'fish',
],
    'city': {
    'name': 'Cairo',
    'geo': {
    'lat': 30.04442,
    'lon': 31.235712,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=4, normalized=True),
    'rand_bool': False,
    'mixed_type': self.mutator.generate_float_array(dimension=3, normalized=True),
    'maybe': 'frog',
    'maybe_null': None,
},
    {
    'id': 199,
    'id_str': [
    '05',
],
    'text_data': '4e60ed1a96f94cb1a43a757b07020e82',
    'rand_digit': 5,
    'rand_number': 0.3167,
    'rand_signed_int': 5,
    'rand_datetime': '2000-10-17 18:01:35',
    'text_array': [
    'f22fbaf703d4452f89d185c6f0fe4a85',
    '99b2d93fa64f48de90140ede3a505d62',
],
    'words': 'rhino hyena',
    'nested': {
    'id': 199,
    'rand_digit': 9,
    'array': [
],
},
    'nested_array': [
    [
],
    self.mutator.generate_float_array(dimension=5, normalized=True),
],
    'two_words': [
    'ape',
    'koala',
],
    'city': {
    'name': 'New York',
    'geo': {
    'lat': 40.712775,
    'lon': -74.005973,
},
},
    'rand_tuple': self.mutator.generate_float_array(dimension=3, normalized=True),
    'rand_bool': False,
    'mixed_type': True,
    'maybe': 'rabbit',
    'maybe_null': 'jaguar',
},
],
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


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - test_updates.test_upload_uuid_in_batches')
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
    test = TestUpdatestestUploadUuidInBatches()
    test.run_tests()
