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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-32-10-2]_1752744205_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-32-10-2]_1752744205.json"
VDB_TYPE = "milvus"


def send_request(content, request_type="POST", url_path="http://172.17.0.5:23210/v1/vector/collections/create", custom_headers=None):
    """
    发送请求到目标服务器

    Args:
        content: 请求内容
        request_type: 请求方法，默认为"POST"
        url_path: URL路径，默认为"http://172.17.0.5:23210/v1/vector/collections/create"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingUrl321021752744205Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-32-10-2]_1752744205.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-32-10-2]_1752744205.json"
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
        """测试请求 0 - POST http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: POST http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': 'b0d2c12f-62ef-11f0-9f2a-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_24_179206odnjerhM',
    'dimension': 32,
    'primaryField': 'url',
    'vectorField': 'embedding',
    'autoID': True,
    'dbName': 'default',
}


        send_request(original_content, method, url_path, headers)
        return True



    def test_request_1(self):
        """测试请求 1 - POST http://172.17.0.5:23210/v1/vector/insert"""
        logger.info(f"测试请求: POST http://172.17.0.5:23210/v1/vector/insert")
        
        method = 'POST'
        url_path = 'http://172.17.0.5:23210/v1/vector/insert'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': 'b0d9f277-62ef-11f0-a01d-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_24_179206odnjerhM',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Mary Hawkins',
    'address': '85459 Destiny Prairie\nAaronberg, PA 92274',
    'text': 'Treatment career image wrong morning. Chair professor bar poor.\nMusic behavior source no court else argue.\nTo force friend particular around behavior. Special game medical bar happen because.',
    'email': 'margaret27@example.com',
    'phone_number': '001-698-982-3424x359',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Keller',
    'Kenneth Henry',
    'Shelia Miller',
    'Stephanie Black',
    'Julie Mcclain',
    'Michael Snyder',
    'Kimberly Smith',
    'Patrick Harrell',
    'Marvin Moyer',
],
    'json': {
    'name': 'Heather Green',
    'address': 'PSC 6788, Box 5885\nAPO AA 66439',
},
    'key47757': 'value57778',
    'key96442': 'value99872',
    'key67177': 'value18275',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Sandra Thomas',
    'address': 'USCGC Mendez\nFPO AA 24662',
    'text': 'Operation key great business. Civil brother beat teach. Throw tax record them east management lay argue.',
    'email': 'holmesbethany@example.org',
    'phone_number': '219.471.4370x9943',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Krista Stephenson',
    'Eric Morris',
    'Lance Lowery',
    'Anthony Sellers',
    'Nicholas Moran',
    'Brianna Williams',
    'Jasmin Harris',
    'Brooke Gross',
    'Dr. Stacy Rogers',
    'Jessica Walker',
],
    'json': {
    'name': 'Ebony Moore',
    'address': '974 Garcia Fort\nPayneburgh, PA 25929',
},
    'key91780': 'value46742',
    'key25485': 'value71068',
    'key30878': 'value59782',
    'key11987': 'value70546',
    'key21669': 'value92658',
    'key9542': 'value35854',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Judith Miller',
    'address': 'PSC 0856, Box 3317\nAPO AE 21882',
    'text': 'Floor green rather manage. Thus management standard character. Mean military forget source bar lot.\nSure official find sure else item. Hold nice fill growth car. People result education last.',
    'email': 'bowersstephanie@example.com',
    'phone_number': '001-550-458-6032x7743',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Adams',
    'Jeffery Johnson',
    'Mary Peters',
    'Heather Rodriguez',
    'Brandon Zavala',
],
    'json': {
    'name': 'Annette Rowe',
    'address': '7249 Hancock Estates\nFordtown, WI 46312',
},
    'key10727': 'value50662',
    'key10519': 'value4784',
    'key8115': 'value85689',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Carl Ramsey',
    'address': '6362 Thomas Groves\nEast James, IA 66739',
    'text': 'Story project born reflect. Police produce upon including break watch.\nFollow become hear win already. Area direction owner quite. Rule light another work.',
    'email': 'nathanielmurray@example.com',
    'phone_number': '559-892-9510',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Laura Walker',
    'Robin Smith',
    'Todd Collins',
    'Linda Baker',
],
    'json': {
    'name': 'Angela Roach',
    'address': '12820 Danielle Ranch Apt. 153\nPotterview, MD 89772',
},
    'key24924': 'value84400',
    'key21777': 'value37847',
    'key54164': 'value55030',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'James Evans',
    'address': '5544 Mcclain Circles\nLake Richard, NM 55579',
    'text': 'Effort nothing return window each. About discover to girl enough quite teach. Audience bag citizen natural first bad.\nWind chance speech threat mouth choice.',
    'email': 'randy97@example.com',
    'phone_number': '478.806.4157',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kristi Villanueva',
    'Kathleen Griffith',
    'Joshua Edwards',
    'Kyle Miller',
],
    'json': {
    'name': 'Gregory Mason',
    'address': '76542 Taylor Mountain\nMichaelbury, NH 51964',
},
    'key17034': 'value84235',
    'key32022': 'value85217',
    'key79172': 'value73918',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'David Gillespie',
    'address': '0062 Cameron Mill Suite 637\nGomezview, SD 80617',
    'text': 'Security capital point million year where at. Cause consumer teacher buy great yes brother. Democratic beat quite discussion smile.',
    'email': 'robertsmichele@example.org',
    'phone_number': '001-415-898-6320x30837',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'James Davis',
    'Teresa Smith',
    'Linda Chavez',
    'Kayla Short',
],
    'json': {
    'name': 'Anthony Barnett',
    'address': '6739 House Radial\nMelissaton, DE 82457',
},
    'key84198': 'value72148',
    'key69268': 'value55069',
    'key95661': 'value86073',
    'key88836': 'value89328',
    'key13444': 'value86200',
    'key88311': 'value52317',
    'key56381': 'value25578',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Vincent Campbell',
    'address': '56381 Angelica Oval\nEast Lisaside, VT 54267',
    'text': 'Politics apply fall human professor unit dinner. Themselves thus arm staff. Compare how thing hour worry its treat billion.',
    'email': 'ofrazier@example.com',
    'phone_number': '(942)562-1595x6963',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Hansen',
    'Mary Owens',
    'Joseph Everett',
],
    'json': {
    'name': 'John Thornton',
    'address': '019 Williams Pines\nHayleytown, MT 18868',
},
    'key79129': 'value16686',
    'key6857': 'value5010',
    'key77616': 'value48149',
    'key14440': 'value21272',
    'key2178': 'value21932',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Cindy Villa',
    'address': '51654 Lewis Alley Apt. 753\nNew Aliceview, MT 29174',
    'text': 'Girl focus address own money fight away.\nWar design a probably great ball. Tv friend least end character cover today.\nAbove realize language live fight. Art yes world medical argue.',
    'email': 'mark96@example.org',
    'phone_number': '001-818-301-0725',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Glenn Ramsey',
    'Jose Hale',
    'Joanne Huynh',
    'Scott Jenkins',
    'Tiffany Garcia',
    'Heidi Fisher',
    'Aaron Jacobson',
    'Claudia Stewart',
    'Zachary Ritter',
],
    'json': {
    'name': 'Christopher Cox',
    'address': '551 Brown Flats Apt. 751\nRogersstad, MN 33221',
},
    'key54761': 'value49497',
    'key3504': 'value68351',
    'key79053': 'value3823',
    'key43359': 'value27716',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Tiffany Estrada',
    'address': '1670 William Squares\nMillsfort, VA 54729',
    'text': 'Bring executive score guy rest. It son politics seem grow. Large north natural account themselves. Expect tough whose summer reality throughout every develop.',
    'email': 'robertsjason@example.com',
    'phone_number': '(497)712-3227x985',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'April Graham',
    'Brendan Moore',
    'Brandon Jensen',
    'Tyler Price',
    'Sarah Flowers',
    'Rebekah Wall',
],
    'json': {
    'name': 'Ashley Dillon',
    'address': '38125 Brown Roads Apt. 020\nEast Nina, VT 35585',
},
    'key55890': 'value95751',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Daniel Thomas',
    'address': '704 Hailey Meadows\nLake Sharonhaven, MH 59595',
    'text': 'Everything good season poor authority every put. Hospital card television team born society if. Maybe small street range money.\nSignificant hospital when. Five rise lose hour word hair.',
    'email': 'derek98@example.net',
    'phone_number': '+1-914-930-5809x0046',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'John Wood',
    'Daniel Allison',
    'Maria Barker MD',
    'Carrie Greene',
    'Joseph Atkins',
    'Randall Schroeder',
    'Anthony Orr',
    'Joshua Duncan',
    'Dakota Bryant',
],
    'json': {
    'name': 'Mark James',
    'address': '853 Gay Cliff Suite 373\nNorth Julie, SC 49964',
},
    'key62625': 'value84363',
    'key98364': 'value46599',
    'key28598': 'value26733',
    'key47711': 'value12480',
    'key33953': 'value94772',
    'key58443': 'value60623',
    'key34729': 'value70236',
    'key57845': 'value63088',
    'key39551': 'value38305',
    'key89477': 'value2710',
},
],
    'dbName': 'default',
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
        """测试请求 2 - DELETE http://172.17.0.5:23210/v1/vector/collections/create"""
        logger.info(f"跳过非写请求或无内容请求: DELETE http://172.17.0.5:23210/v1/vector/collections/create")
        method = 'DELETE'
        url_path = 'http://172.17.0.5:23210/v1/vector/collections/create'
        headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer root:Milvus',
    'RequestId': 'b0d2c12f-62ef-11f0-9f2a-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_24_179206odnjerhM',
    'dimension': 32,
    'primaryField': 'url',
    'vectorField': 'embedding',
    'autoID': True,
    'dbName': 'default',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-32-10-2]_1752744205.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingUrl321021752744205Json()
    test.run_tests()
