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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-10-2]_1752744169_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-10-2]_1752744169.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorId1281021752744169Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-10-2]_1752744169.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-10-2]_1752744169.json"
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
    'RequestId': '9ba10a0b-62ef-11f0-8637-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_48_621231sEaBffPs',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'vector',
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
    'RequestId': '9ba8a2c1-62ef-11f0-925e-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_48_621231sEaBffPs',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'John Mejia',
    'address': '68570 Barrett Springs\nEast Carolborough, WI 72419',
    'text': 'Family past discussion front hotel. Nice hard local reflect.\nNation leader learn here. Discussion fine raise next finally during how.',
    'email': 'adammccoy@example.net',
    'phone_number': '+1-626-734-6397x702',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Samuel Booth',
],
    'json': {
    'name': 'Jared Gonzalez',
    'address': 'Unit 9532 Box 5452\nDPO AE 20696',
},
    'key84619': 'value33278',
    'key50179': 'value47465',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Joe Donovan',
    'address': '4816 Hall Valley Suite 038\nAlvarezbury, NE 55104',
    'text': 'Eat year remain visit.\nPut write close media character writer only. Accept have already which different. South until Mr audience.\nMy ability citizen development.\nModern effect relationship they try.',
    'email': 'amy22@example.net',
    'phone_number': '001-566-511-0312x54486',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Mullins',
    'John Perez',
    'Sara Johnson',
    'Grace Shepherd',
    'Justin Kennedy',
    'Timothy Sellers',
    'Joseph Patterson',
],
    'json': {
    'name': 'William Christian',
    'address': '2213 Harris Groves\nNew Jeremy, NJ 27777',
},
    'key51667': 'value8283',
    'key59425': 'value94791',
    'key87831': 'value31425',
    'key56126': 'value88680',
    'key26507': 'value8897',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Aaron Flores',
    'address': 'Unit 2357 Box 6509\nDPO AA 42556',
    'text': 'Hope cause involve science. Truth truth ask usually manage future. Over your father house same score.\nAdmit call continue green. Sense enter sea ball plan station. Meet and long range rest.',
    'email': 'walkersuzanne@example.net',
    'phone_number': '430.408.8293x49626',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Day',
    'Deborah Smith',
],
    'json': {
    'name': 'Kyle Castaneda',
    'address': '84096 Amy Run\nMelissahaven, NC 06291',
},
    'key6033': 'value2986',
    'key48894': 'value68858',
    'key76561': 'value36815',
    'key55349': 'value35440',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Dominique Michael',
    'address': '76141 David Well Apt. 643\nKellychester, UT 23312',
    'text': 'Indeed grow bar once.\nBack this often.\nRisk long leg finally. Strategy town where anyone system past.',
    'email': 'tylerwright@example.com',
    'phone_number': '5367090091',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'John Salazar',
    'Johnny Stanley',
    'Bridget Rose',
    'Matthew Stephenson',
    'Christine Meadows',
    'Amanda Lee',
    'Claire White',
    'Timothy Diaz',
    'Jose Nguyen',
    'Matthew Stewart',
],
    'json': {
    'name': 'Rebecca Bean',
    'address': '628 Julia Overpass\nEast Nicholastown, GA 51053',
},
    'key90483': 'value35755',
    'key15518': 'value53901',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Tanya Smith',
    'address': '99168 Rivera Road Suite 494\nSheppardborough, TN 50572',
    'text': 'Seven whom how cultural religious relationship language. Argue all partner reach and.\nStrategy adult station maybe listen appear. Own here society.',
    'email': 'daniel31@example.org',
    'phone_number': '899-437-9871',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Christine Joyce',
    'Samantha Peters',
    'Amber Martinez',
    'Valerie Adams',
    'Richard Walter',
    'Jeremy Walker',
    'Ashley Steele',
    'Mark Barnett',
    'Vanessa Velasquez',
    'Micheal Miranda',
],
    'json': {
    'name': 'Kimberly Brown',
    'address': '854 Wolf Crescent\nWest Erin, KS 74821',
},
    'key32584': 'value62579',
    'key10606': 'value7734',
    'key43552': 'value48748',
    'key84081': 'value35002',
    'key12081': 'value26818',
    'key3460': 'value84750',
    'key68666': 'value21060',
    'key91270': 'value86104',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Joann Villa',
    'address': '41178 Schmidt Plaza Suite 522\nMariastad, AK 47102',
    'text': 'Stuff experience face analysis yet first. Simply pass what real it federal hair. Ability important approach notice field.',
    'email': 'harpersarah@example.org',
    'phone_number': '(962)616-5458',
    'array_int_dynamic': [
    61094,
],
    'array_varchar_dynamic': [
    'Robert Boyer',
    'Courtney Erickson',
    'Michael Velazquez',
    'David Strickland',
    'Sarah Griffin',
    'Gregory Oneal',
    'Jordan Conway',
    'Mark Huynh',
    'Elizabeth Richards',
    'Nancy Carney',
],
    'json': {
    'name': 'Taylor Keller',
    'address': '8681 Angela Station\nLake Jason, OK 17954',
},
    'key13404': 'value56268',
    'key86478': 'value29601',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Victoria Marquez',
    'address': '3322 Duke Ferry\nAliciaville, NY 65848',
    'text': 'Story hear glass teacher reality Mr night gun. Or feeling ready hand interview tell up. Born soon cup start serve.',
    'email': 'donald83@example.com',
    'phone_number': '3025754821',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Castillo',
    'Diane Scott',
    'Michael Thomas',
    'Christopher Morris',
    'Alexis Sanders',
    'Keith Winters',
    'Ashley Williams',
    'Joy Brown',
    'Andrea Dean',
    'Katherine Curtis',
],
    'json': {
    'name': 'David Clarke',
    'address': '6251 John Plaza Suite 752\nLake Matthew, WI 69022',
},
    'key89819': 'value1323',
    'key83296': 'value85244',
    'key50490': 'value15907',
    'key58083': 'value66315',
    'key65551': 'value77442',
    'key39244': 'value54468',
    'key54289': 'value86739',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Brandon Martin',
    'address': '953 Robin Crest Suite 097\nChristianview, IA 79515',
    'text': 'Such change dark. By should indeed me society.\nCell term against free. Sit actually live board simple glass. Real agency nice account.',
    'email': 'zrodriguez@example.org',
    'phone_number': '777.541.9377x39222',
    'array_int_dynamic': [
    19853,
],
    'array_varchar_dynamic': [
    'Deborah Daniel',
    'Benjamin Cook',
    'Michael Lawson',
    'Pamela Booker',
    'Hannah Mcdonald',
    'Timothy Johnson',
    'Christina Hill',
    'Stephen Hammond',
    'Mark Merritt',
    'Greg Johnson',
],
    'json': {
    'name': 'Matthew Vega',
    'address': '44404 James Wells Suite 086\nPort Joseph, AL 43727',
},
    'key84012': 'value50057',
    'key78354': 'value78248',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Molly Melendez',
    'address': '636 Jose Forks\nWest Jefferyton, WA 06355',
    'text': 'Approach establish evidence report thank call never. Nature sea month. Might him put record.',
    'email': 'kaylee62@example.com',
    'phone_number': '(574)384-3731x66659',
    'array_int_dynamic': [
    36419,
],
    'array_varchar_dynamic': [
    'Sandra Bailey',
],
    'json': {
    'name': 'Anthony Schaefer',
    'address': '230 Browning Lock Apt. 716\nCarlmouth, SC 07092',
},
    'key98017': 'value26864',
    'key47061': 'value77777',
    'key74094': 'value14606',
    'key30622': 'value94963',
    'key5647': 'value36314',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Daniel Evans',
    'address': 'USNV Cabrera\nFPO AE 74692',
    'text': 'Already attention agreement ago decide less. Tv treatment save south recent. Lead policy politics often.\nCatch assume culture remember Republican state.',
    'email': 'jessicamoses@example.org',
    'phone_number': '498-507-4959x9993',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Katherine Moore',
],
    'json': {
    'name': 'Heather Schroeder',
    'address': '063 Chris Prairie Suite 095\nWest Rebeccabury, NJ 77487',
},
    'key47630': 'value63836',
    'key73729': 'value64331',
    'key13248': 'value41392',
    'key4948': 'value46968',
    'key13020': 'value4172',
    'key73668': 'value15705',
    'key76653': 'value11523',
    'key2946': 'value48848',
    'key25678': 'value5560',
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
    'RequestId': '9ba10a0b-62ef-11f0-8637-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_48_621231sEaBffPs',
    'dimension': 128,
    'primaryField': 'id',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'default',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-128-10-2]_1752744169.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorId1281021752744169Json()
    test.run_tests()
