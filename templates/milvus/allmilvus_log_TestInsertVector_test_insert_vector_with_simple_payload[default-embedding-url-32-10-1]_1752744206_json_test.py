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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-32-10-1]_1752744206_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-32-10-1]_1752744206.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingUrl321011752744206Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-32-10-1]_1752744206.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-32-10-1]_1752744206.json"
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
    'RequestId': 'b179c0f0-62ef-11f0-94a7-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_25_273651lbikbfrH',
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
    'RequestId': 'b18505da-62ef-11f0-8436-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_25_273651lbikbfrH',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Shelby Nelson',
    'address': '94831 Jennifer Creek\nEast Cheryl, PA 27459',
    'text': 'Realize modern PM beautiful though not fund.\nSeries letter daughter employee. Hear structure her where.',
    'email': 'michaelmyers@example.org',
    'phone_number': '001-491-351-0578x189',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Sherry Chandler',
    'Jennifer Miller',
    'Lisa Williams',
    'Robin Morgan',
    'Tina Graves',
],
    'json': {
    'name': 'Christopher Hill',
    'address': '09432 Christina Ford Suite 592\nSouth Corey, HI 09515',
},
    'key54485': 'value38710',
    'key1085': 'value63495',
    'key42687': 'value2968',
    'key8145': 'value21771',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'John Hobbs',
    'address': '63600 Morris Islands Suite 473\nHernandezfort, MI 92412',
    'text': 'Five none continue still. Assume old of.\nModern whom interview cost way near agree. Blood six great need. Indeed single action save executive black.',
    'email': 'xchavez@example.net',
    'phone_number': '001-419-680-6393',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Valdez',
    'William Johnson',
    'Jessica Davis',
    'Martin Burton',
],
    'json': {
    'name': 'Jason Hayes',
    'address': '74129 Braun Mission Suite 897\nAnnaburgh, ID 68127',
},
    'key17201': 'value62629',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Michael Garrett',
    'address': '11276 Davis Crossing Suite 780\nSaraside, MP 18194',
    'text': 'None television reason play season nothing woman. Book represent thus blood.\nExpect technology describe move how.\nNear impact now charge avoid. Produce see sea myself tend. Others of Mrs away so.',
    'email': 'gary24@example.org',
    'phone_number': '309-773-2547',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Cook',
],
    'json': {
    'name': 'Adam Smith',
    'address': '07044 Smith Shore Apt. 754\nWendychester, KY 05028',
},
    'key90317': 'value60695',
    'key30083': 'value64135',
    'key18159': 'value46422',
    'key95104': 'value44072',
    'key41846': 'value32871',
    'key3517': 'value99932',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Julie Smith',
    'address': '4480 Tapia Track Apt. 499\nBarryside, MA 40244',
    'text': 'Girl serious room accept yet responsibility. Experience person it everybody do name drive read. You line trade stand wall the trouble.',
    'email': 'schultzfrederick@example.org',
    'phone_number': '001-950-501-1124x765',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Delgado',
    'Lindsay Brown',
    'Stephanie Roth',
    'Kent Garcia',
    'Sydney Nelson',
],
    'json': {
    'name': 'Michelle Hatfield',
    'address': '97056 Crystal Spur Apt. 966\nNorth Jennifer, MP 36017',
},
    'key59620': 'value55027',
    'key32572': 'value48757',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Mrs. Kristen Ibarra',
    'address': '557 Kline Parkways\nAlexanderside, PR 65895',
    'text': 'Training ask the go consumer movement.\nMovie ago ok play school or good. Air most seem friend weight this.',
    'email': 'steven67@example.net',
    'phone_number': '+1-232-294-1786x5475',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Carla Stephens',
],
    'json': {
    'name': 'Charles Hansen',
    'address': '40462 Ashley Spurs\nNew Zachary, NH 94288',
},
    'key67422': 'value88323',
    'key62800': 'value6309',
    'key61539': 'value50164',
    'key99537': 'value87274',
    'key86101': 'value5797',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Lisa Rodriguez',
    'address': '2816 Morgan Common Suite 284\nSouth Christine, MP 26220',
    'text': 'Out role nature Democrat of news tax. Easy economic play Democrat.\nParticular gas cut talk. More subject type program seat five third evening.',
    'email': 'itaylor@example.com',
    'phone_number': '953-349-6306',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Victoria Jones',
    'Katherine Mathews',
    'Andrea Cole',
    'Heather King',
    'Dr. Christian Wood Jr.',
    'Gregory Smith',
    'Hannah Fields',
    'Richard Barrett',
    'Daniel Walker',
],
    'json': {
    'name': 'Cheryl Walker',
    'address': '29854 Cindy Freeway Suite 480\nNorth Jamesborough, RI 00886',
},
    'key40367': 'value48505',
    'key45676': 'value83813',
    'key44922': 'value31638',
    'key58354': 'value89723',
    'key33418': 'value6514',
    'key79601': 'value27425',
    'key45411': 'value43040',
    'key86108': 'value93797',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Monique Chavez',
    'address': '35495 Hernandez Circle\nLoganfort, NV 66262',
    'text': 'Of travel agree fall artist over. Mrs practice company gas home. Chance glass base attack everything cup assume.\nCarry candidate message carry. Small morning create today hospital administration guy.',
    'email': 'molly25@example.org',
    'phone_number': '973-378-1947',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Julie Cherry',
    'Sydney Jones',
    'Virginia Herring',
    'Robin Farrell',
    'Edward Donaldson',
    'Dustin Miller',
    'Mark Briggs',
    'Linda Ortega',
    'Justin Evans',
],
    'json': {
    'name': 'Alex Hall',
    'address': '9051 Roth Green\nLake Micheal, MO 48920',
},
    'key30131': 'value78813',
    'key26969': 'value86537',
    'key91370': 'value20305',
    'key44600': 'value82231',
    'key28670': 'value59663',
    'key64741': 'value76026',
    'key94283': 'value72632',
    'key5877': 'value20712',
    'key75198': 'value82858',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Jason Wilson',
    'address': '498 Kramer Squares\nNorth Stephanie, RI 89692',
    'text': 'Never tonight ever threat. Size guess piece space.\nDefense art list care. Especially city prevent I fish. Research history some store kitchen senior seek.',
    'email': 'alexander80@example.net',
    'phone_number': '922-712-3219',
    'array_int_dynamic': [
    79867,
],
    'array_varchar_dynamic': [
    'Kim Thompson',
    'Michael Ramirez',
],
    'json': {
    'name': 'Samuel Ramirez',
    'address': '55725 Hale Heights\nDeleonmouth, NE 63511',
},
    'key66340': 'value55561',
    'key39242': 'value86627',
    'key59665': 'value59399',
    'key21824': 'value5078',
    'key44684': 'value51323',
    'key2318': 'value16695',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Derek Sanders',
    'address': '1529 Rodriguez Ports Apt. 712\nSellersbury, DC 30308',
    'text': 'Difference figure year. Position audience science hundred fire.\nJust nor history play ball. Raise behind far line rise according. On pay central sing early center decade.',
    'email': 'bradyvanessa@example.com',
    'phone_number': '661.496.6209x53494',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Danny White',
    'Raymond Hebert',
    'Laura Lopez',
    'Susan Cervantes',
    'Jennifer Flynn',
    'Steven Bush',
    'Dawn Bray',
    'Don Murray',
    'Christopher Guzman',
    'Kathleen Wallace',
],
    'json': {
    'name': 'Tammy Salazar',
    'address': '76489 Smith Row\nPort Kellyside, RI 65851',
},
    'key29268': 'value23618',
    'key27116': 'value76304',
    'key27742': 'value8005',
    'key99568': 'value6534',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Jeffrey Allen',
    'address': '531 Perez Oval Suite 236\nLawrenceview, MD 44174',
    'text': 'Whether everyone dinner meet. Story American month through type brother factor. Exist artist natural student know ask.\nExample plant prepare but. Too easy ground. Keep happy doctor item.',
    'email': 'jeffreyponce@example.net',
    'phone_number': '001-632-742-6505x932',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Erin Evans',
    'Joseph Simpson',
    'Jessica Thomas',
],
    'json': {
    'name': 'Raymond Miller',
    'address': '72657 Davis Mount\nNew Saraville, AL 93286',
},
    'key94774': 'value82333',
    'key65030': 'value31079',
    'key87523': 'value15372',
    'key53712': 'value99629',
    'key13872': 'value99179',
    'key40338': 'value48193',
    'key63736': 'value22417',
    'key51950': 'value70530',
    'key2395': 'value37023',
    'key16989': 'value24356',
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
    'RequestId': 'b179c0f0-62ef-11f0-94a7-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_25_273651lbikbfrH',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-url-32-10-1]_1752744206.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingUrl321011752744206Json()
    test.run_tests()
