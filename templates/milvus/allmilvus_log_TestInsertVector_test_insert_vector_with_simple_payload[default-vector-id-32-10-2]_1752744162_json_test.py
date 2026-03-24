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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-10-2]_1752744162_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-10-2]_1752744162.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorId321021752744162Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-10-2]_1752744162.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-10-2]_1752744162.json"
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
    'RequestId': '973e8ac8-62ef-11f0-abcf-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_41_264840ahpMFXkL',
    'dimension': 32,
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
    'RequestId': '9745acda-62ef-11f0-87ca-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_41_264840ahpMFXkL',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Michael Arroyo',
    'address': '994 King Road Apt. 460\nNorth Thomas, VI 22651',
    'text': 'Behavior dog century. Example recognize nor memory letter. Child if well civil consumer level dog.',
    'email': 'patrickmorris@example.com',
    'phone_number': '+1-580-391-5285x8718',
    'array_int_dynamic': [
    42645,
],
    'array_varchar_dynamic': [
    'Nicholas Frazier',
    'Mckenzie Johnson',
    'Darren Hart',
    'Laura Smith',
    'Michael Beard',
    'Tracy Evans',
    'Laura Wilson',
    'Michele Jones',
],
    'json': {
    'name': 'Christina Hernandez',
    'address': '4628 Robert Manors Apt. 298\nThomasmouth, HI 46491',
},
    'key54740': 'value47779',
    'key54546': 'value34203',
    'key84619': 'value11824',
    'key1727': 'value92650',
    'key81462': 'value42443',
    'key81921': 'value18924',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Yolanda Wood',
    'address': '72403 Tiffany Track Apt. 275\nLake Cody, SD 65332',
    'text': 'Remain paper foreign many including certain manager data. Important girl wish available drug. Stock travel say wait late billion.',
    'email': 'isabelsanders@example.org',
    'phone_number': '578.577.3012',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Willie Cook',
    'Bonnie Maxwell',
    'Alicia Williams',
    'Isaiah Clayton',
    'Luis Evans',
    'Haley Martinez MD',
],
    'json': {
    'name': 'Charles Meyer',
    'address': '7646 Thomas Station Apt. 445\nBurgessside, RI 20829',
},
    'key61018': 'value28063',
    'key60365': 'value63008',
    'key11264': 'value69962',
    'key95716': 'value44821',
    'key41635': 'value52013',
    'key99419': 'value69830',
    'key71486': 'value19044',
    'key21184': 'value77414',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Charles Reed',
    'address': '39820 Brenda Flat\nSouth Lauraton, MP 81899',
    'text': 'Ability do house pull artist. System lose why do care personal. Soldier value change purpose.\nDebate safe issue heavy throughout while. American want modern middle explain store race.',
    'email': 'xhunter@example.net',
    'phone_number': '(319)572-5415',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Derek Spencer',
    'Laura Roth',
    'Lee Walls',
    'Roberto Mcdonald',
    'Michael Williams',
    'William Alvarez',
    'Eric Cameron',
    'Susan Barnes',
    'Jennifer Lowe',
],
    'json': {
    'name': 'Mia Vasquez',
    'address': '48398 Barbara Manor Suite 430\nSouth Alexanderhaven, PA 59722',
},
    'key74499': 'value45104',
    'key74461': 'value73235',
    'key35215': 'value56901',
    'key33294': 'value89782',
    'key51921': 'value950',
    'key32751': 'value94767',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Joshua Sheppard',
    'address': 'Unit 3589 Box 7119\nDPO AP 61687',
    'text': 'Sure realize accept ahead only both account note. Hot production sing price. Cell to modern win point recent.',
    'email': 'fbradley@example.com',
    'phone_number': '+1-285-997-6366',
    'array_int_dynamic': [
    73590,
],
    'array_varchar_dynamic': [
    'Kaitlin Nelson',
    'Teresa Galvan',
    'Ryan Hunt',
    'Dennis Reid',
    'Anthony Copeland',
    'Kevin Dean',
    'Ryan Green',
    'Tiffany Davenport',
    'Brian Cooper',
    'Christian Pruitt',
],
    'json': {
    'name': 'Michael Salazar',
    'address': '46476 Nichols Dale Suite 306\nPhelpston, AZ 69171',
},
    'key21011': 'value10186',
    'key43270': 'value68346',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Dawn Harris',
    'address': '40656 White Orchard\nWilsonmouth, MI 76070',
    'text': 'Wish hot also father. Senior very sea page drive involve.',
    'email': 'gvilla@example.com',
    'phone_number': '+1-436-539-0876x233',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Johnathan Moore Jr.',
    'Angela Turner',
    'John Thomas',
    'Jonathan Short',
    'Latasha Baird',
],
    'json': {
    'name': 'Mary Garrison',
    'address': '06091 Fisher Via Suite 070\nLake Richardview, CT 89507',
},
    'key48064': 'value2235',
    'key62134': 'value80713',
    'key70345': 'value94935',
    'key21101': 'value18672',
    'key37491': 'value71317',
    'key37200': 'value2138',
    'key9341': 'value69839',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Tiffany Campbell',
    'address': '384 Lisa River\nWest Tylerberg, ND 47864',
    'text': 'Politics hundred first meeting professional name sure. Your message far role.\nWant ok book. Dark full boy listen us get card. Prepare instead risk child set game event color.',
    'email': 'awright@example.com',
    'phone_number': '352.703.2683x7888',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Anne Harris',
    'Allison Johnson',
    'Andrew Adams',
],
    'json': {
    'name': 'Cody Cox',
    'address': '54827 James Pike Apt. 952\nCoxview, PR 47236',
},
    'key14424': 'value71531',
    'key4264': 'value91742',
    'key70544': 'value59844',
    'key95209': 'value77782',
    'key87323': 'value85129',
    'key87690': 'value64506',
    'key6196': 'value13166',
    'key85337': 'value18916',
    'key26058': 'value70106',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Melissa Montgomery',
    'address': '3738 Donna Mountain\nWest Aaron, MT 58397',
    'text': 'Professor through at ahead down American girl. Third yet such affect. Claim stuff young industry about boy admit spend.',
    'email': 'ubray@example.org',
    'phone_number': '499.512.1497',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Stephen Martin',
    'Elizabeth Brown',
    'Stephen Wilson',
    'Suzanne Washington',
    'Stephanie Smith',
    'Jessica Sanchez',
],
    'json': {
    'name': 'Howard Crosby',
    'address': 'USS Martin\nFPO AP 79862',
},
    'key79754': 'value42827',
    'key68631': 'value21099',
    'key28251': 'value2885',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Jordan Randall',
    'address': '71241 David Via Apt. 789\nNormanside, AS 50494',
    'text': 'Hit simple agreement can. Myself memory another power although network. Nice wonder could.',
    'email': 'gregg96@example.net',
    'phone_number': '(493)670-0274x49131',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Julie Davis',
    'Matthew David',
    'Sarah Chung',
    'Harold Huff',
    'Harold Adams',
    'Anthony Kelley',
    'Jeffrey Schultz',
    'Edward Joseph',
    'Daniel Brown',
],
    'json': {
    'name': 'Laurie Gomez',
    'address': '3161 Freeman Glen Apt. 868\nJohnbury, LA 13225',
},
    'key33940': 'value6964',
    'key23476': 'value94694',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Jeremy Holland',
    'address': 'PSC 5553, Box 4422\nAPO AA 33358',
    'text': 'Help worker least party.\nJoin stuff suddenly return current list author avoid. Price sing quickly cut dark. Treatment few newspaper heart.',
    'email': 'morenokimberly@example.net',
    'phone_number': '520-839-6751x85699',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Rachel Ray',
    'Nicholas Clements',
    'Jessica George',
],
    'json': {
    'name': 'Mark Smith',
    'address': '7253 Brown Hollow Apt. 765\nWest Amanda, MA 94274',
},
    'key13318': 'value20360',
},
    {
    'vector': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Bryan Miller',
    'address': '69492 Alvarado Key\nShannonmouth, PR 65377',
    'text': 'Magazine serious area something fine carry them. Small successful most short forward ahead.\nPlant issue space. Huge score let enter quality.',
    'email': 'sandra95@example.org',
    'phone_number': '395.887.3640x3760',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Patricia Smith',
    'Amanda Rivera',
    'Christopher Davenport',
    'Evan Soto',
    'Cassandra Williams',
    'Misty Brown',
    'Lisa Horne',
    'Megan Patterson',
    'Donna Foster',
],
    'json': {
    'name': 'Denise Watkins',
    'address': '002 Wolfe Circle\nAndersonview, NC 08748',
},
    'key54119': 'value3237',
    'key19822': 'value26693',
    'key73476': 'value26571',
    'key92398': 'value64963',
    'key21616': 'value36706',
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
    'RequestId': '973e8ac8-62ef-11f0-abcf-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_41_264840ahpMFXkL',
    'dimension': 32,
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-id-32-10-2]_1752744162.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorId321021752744162Json()
    test.run_tests()
