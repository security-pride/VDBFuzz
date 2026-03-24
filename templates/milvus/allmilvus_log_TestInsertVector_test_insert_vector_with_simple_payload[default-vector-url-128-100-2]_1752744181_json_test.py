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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-128-100-2]_1752744181_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-128-100-2]_1752744181.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorUrl12810021752744181Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-128-100-2]_1752744181.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-128-100-2]_1752744181.json"
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
    'RequestId': 'a264ac35-62ef-11f0-a101-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_59_969660BfUHIyqM',
    'dimension': 128,
    'primaryField': 'url',
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
    'RequestId': 'a2864114-62ef-11f0-9775-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_59_969660BfUHIyqM',
    'data': [
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 0,
    'name': 'Helen Walker',
    'address': '59566 James Tunnel\nPort Wesleychester, SC 19264',
    'text': 'Create off ever issue skin generation back necessary. Eat adult space each big action stay. Way industry whose.',
    'email': 'wanderson@example.org',
    'phone_number': '001-965-754-8165x49722',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Larry Clay',
    'Jacqueline Hill',
    'Amanda Williams',
    'Calvin Ortiz',
    'Daniel Collins',
],
    'json': {
    'name': 'Sonya Goodwin',
    'address': '337 Summer Locks Apt. 618\nJohnsonmouth, HI 33232',
},
    'key55610': 'value40763',
    'key33734': 'value97511',
    'key67878': 'value97213',
    'key574': 'value2573',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 1,
    'name': 'Luis Lopez',
    'address': '5817 Bailey Crescent\nWest Jonathan, PW 08933',
    'text': 'Oil meet someone interesting wear language. Like stuff different begin drug business. Exist notice attack she together kid. Low month site lawyer necessary indicate edge.',
    'email': 'wendy13@example.org',
    'phone_number': '489-872-6536',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Susan Smith',
    'Tina Robbins',
    'Michael Williams',
    'Kimberly Delgado',
    'Blake James',
    'Mr. Michael Nicholson',
],
    'json': {
    'name': 'David Boyd',
    'address': '106 Randall Coves Apt. 318\nSheppardville, AK 70407',
},
    'key7131': 'value9413',
    'key31894': 'value83027',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 2,
    'name': 'Maurice Skinner',
    'address': '716 Brewer Haven Suite 952\nGallowaytown, NV 54435',
    'text': 'Conference wide five can. Respond consumer side all food create teacher.',
    'email': 'jesse89@example.net',
    'phone_number': '736.496.4727x91832',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Helen Ball',
],
    'json': {
    'name': 'Robert Hutchinson',
    'address': '28357 Palmer Walks\nSergiomouth, GA 19086',
},
    'key16972': 'value10191',
    'key14813': 'value57023',
    'key60177': 'value78476',
    'key64250': 'value84427',
    'key70985': 'value1262',
    'key28284': 'value6556',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 3,
    'name': 'Darlene Johnson',
    'address': '770 Kayla Park\nJessicabury, WA 62525',
    'text': 'Hard news key son class. Their thus factor Mr live protect.\nCurrent training individual opportunity.\nExecutive program recently follow first. Employee interesting eight medical investment middle my.',
    'email': 'ricephillip@example.net',
    'phone_number': '001-270-865-1664',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Catherine Bennett',
    'Kylie Molina',
    'Christina Smith',
    'Tina Preston',
],
    'json': {
    'name': 'James Bauer',
    'address': '4451 Gibson Ports Apt. 994\nPort Stephanie, TX 13181',
},
    'key82929': 'value2799',
    'key81127': 'value35475',
    'key75961': 'value62147',
    'key13022': 'value88860',
    'key65592': 'value9938',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 4,
    'name': 'Lisa Wright',
    'address': 'Unit 2295 Box 1877\nDPO AP 77517',
    'text': 'Activity play western Congress recently town. Medical build fund happy cultural size. Morning pressure particular ever sound capital.',
    'email': 'austinangelica@example.net',
    'phone_number': '6114777238',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Ann Palmer',
    'John Steele',
    'Pamela Johnson',
    'Vincent Nguyen',
    'Katherine Carter',
    'Keith Stanton',
],
    'json': {
    'name': 'Nathan Hernandez',
    'address': '53639 Billy Mountain\nNew Saraborough, FL 11957',
},
    'key89808': 'value45385',
    'key3698': 'value44833',
    'key11595': 'value62765',
    'key70719': 'value76323',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 5,
    'name': 'Dana Webb',
    'address': '10774 Natalie Village Suite 342\nNew Dalton, NM 63427',
    'text': 'Current most alone finally occur network just. Suddenly itself another door suffer sort. Experience body no short PM.',
    'email': 'nicole19@example.net',
    'phone_number': '(900)677-4897',
    'array_int_dynamic': [
    67392,
],
    'array_varchar_dynamic': [
    'Dominique Patterson',
    'Susan Green',
    'Travis Mccarthy',
    'David Miller',
    'Tracy Wilson',
],
    'json': {
    'name': 'Adam Murray',
    'address': '07832 Armstrong Stravenue\nNew Robertmouth, DC 24407',
},
    'key68980': 'value25893',
    'key66107': 'value39162',
    'key14723': 'value61431',
    'key80069': 'value82649',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 6,
    'name': 'Kayla Massey',
    'address': 'USS Parker\nFPO AP 59386',
    'text': 'Car baby year may suffer professor that letter. Stop save step particular act least data.\nFace station one cup fight gas according. New return data return shake radio.',
    'email': 'michael81@example.org',
    'phone_number': '+1-677-480-4467x60495',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Craig Miller',
    'Austin Morse',
    'Abigail Neal',
    'Andrew Gibson',
    'William Sparks',
],
    'json': {
    'name': 'Laura Cameron',
    'address': '1712 Stephen Spring\nPatriciaburgh, NM 74612',
},
    'key71202': 'value10441',
    'key75416': 'value17696',
    'key98065': 'value43661',
    'key46406': 'value51592',
    'key52449': 'value99412',
    'key32594': 'value61970',
    'key59166': 'value48093',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 7,
    'name': 'Ashley Weiss',
    'address': 'Unit 1991 Box 9071\nDPO AP 91412',
    'text': 'Before teach deal political situation quite seem. Into or window really training record.\nRun style person final information owner reflect.',
    'email': 'fgonzalez@example.com',
    'phone_number': '570-367-7170',
    'array_int_dynamic': [
    18600,
],
    'array_varchar_dynamic': [
    'Joseph Henry',
    'Cody Campbell',
    'John Jackson',
    'Brittney Stark',
    'Damon Moore',
    'Joshua Patel',
    'Kevin Flores',
    'Michelle Harris',
    'Colton Scott',
],
    'json': {
    'name': 'Erika Spears',
    'address': '6819 Logan Brooks\nPort Karlton, WV 46534',
},
    'key30093': 'value69459',
    'key1179': 'value41613',
    'key77703': 'value99631',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 8,
    'name': 'Sheila Rodriguez',
    'address': '7449 David Avenue\nThompsonport, WY 05752',
    'text': 'Eat professor success strategy. Pm our manage remain short south year. Support bit poor miss cell letter pressure.\nAffect meet everything argue education toward say.',
    'email': 'lambstephen@example.com',
    'phone_number': '+1-745-983-6760x1267',
    'array_int_dynamic': [
    17321,
],
    'array_varchar_dynamic': [
    'Carmen Dudley',
    'Diana Wilkinson',
    'Francisco Molina',
    'Matthew Williams',
],
    'json': {
    'name': 'Rhonda Gardner',
    'address': '90100 Desiree Wall Apt. 853\nKellystad, OR 95930',
},
    'key42796': 'value21049',
    'key15892': 'value69890',
    'key49595': 'value29860',
    'key14599': 'value59588',
    'key99980': 'value25886',
    'key80892': 'value82040',
    'key43697': 'value69839',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 9,
    'name': 'Shannon Stokes',
    'address': '202 Kathy Street\nCarolynborough, MS 52408',
    'text': 'Family become use prevent book. Simple camera run summer agency fine food. Section sport free trouble information range around.',
    'email': 'qfranklin@example.com',
    'phone_number': '476.969.8246x05542',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Laura Smith',
    'Alexa Johnson',
    'Robert Mccormick',
    'Paula Mcneil',
    'Jennifer Phelps MD',
],
    'json': {
    'name': 'Tracey Williams',
    'address': '4964 Stephanie Trace Apt. 155\nEast Ashleytown, WY 19492',
},
    'key33073': 'value14172',
    'key89459': 'value70687',
    'key93998': 'value49031',
    'key53381': 'value19945',
    'key20235': 'value94726',
    'key45962': 'value87833',
    'key76841': 'value4159',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 10,
    'name': 'Eric Maxwell',
    'address': '298 Shawn Village Suite 543\nCaseymouth, CA 34685',
    'text': 'Far the serve member this scene. Best who market attack. Cultural heavy officer figure loss pass.',
    'email': 'chayes@example.org',
    'phone_number': '001-780-899-4703x94970',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Beverly Bender',
    'James Perkins',
    'Daniel Collins',
    'Jeffrey Allen',
    'William Garrett',
    'Melissa Potter',
    'Michele Camacho',
    'Mrs. Ellen Miller MD',
],
    'json': {
    'name': 'Dalton Mccarthy',
    'address': '2682 Johnson Brooks\nNew Joel, VT 00834',
},
    'key22789': 'value26593',
    'key96795': 'value47812',
    'key88516': 'value38846',
    'key26721': 'value17004',
    'key73064': 'value20414',
    'key71946': 'value7075',
    'key27698': 'value74887',
    'key70509': 'value84275',
    'key49034': 'value18045',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 11,
    'name': 'Tiffany Williams',
    'address': '94075 Wendy Forks\nRobinton, OR 42582',
    'text': 'Also like response.\nAround really amount. Program before indeed attorney tell election. Soon ago up media material production.',
    'email': 'sheilabradley@example.com',
    'phone_number': '714-712-7476',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Monica Avila MD',
    'Bonnie Rodriguez',
    'Julie Hood',
    'Lisa Maxwell',
    'Alexandra Schultz',
    'Joel Castillo',
    'Paul Hill',
    'Paul Ortega',
],
    'json': {
    'name': 'Dwayne Martin',
    'address': '25494 Holt Valley\nEast Jeffrey, IA 57014',
},
    'key65878': 'value74432',
    'key94209': 'value84160',
    'key88386': 'value25688',
    'key3211': 'value60612',
    'key94598': 'value60024',
    'key57905': 'value63919',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 12,
    'name': 'Timothy Carter',
    'address': '22217 Amy Crescent\nTerrihaven, VI 12270',
    'text': 'Every smile feeling herself. Small hard production property.\nDark change reason majority message do chair long. At stop should. Story image then inside especially power instead. Whole skin few wait.',
    'email': 'taylormichelle@example.com',
    'phone_number': '001-409-741-7443x303',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Pam Rowland',
    'Nancy Welch',
    'Pamela Murray',
    'Kimberly Conner',
    'Eric Johnson',
],
    'json': {
    'name': 'David Rangel',
    'address': '55453 Thomas Mission\nWoodport, MO 85513',
},
    'key37877': 'value21142',
    'key93749': 'value43370',
    'key41866': 'value1495',
    'key39121': 'value59410',
    'key13912': 'value32579',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 13,
    'name': 'Daniel Coleman',
    'address': '8026 Nolan Unions Suite 227\nWest Mariaburgh, FL 31237',
    'text': 'Risk that film event doctor employee. Few very offer tax treatment major like. Any address it ahead recognize.\nOpportunity plant political. Herself amount investment consider leg shoulder.',
    'email': 'veronicarobinson@example.net',
    'phone_number': '4027694711',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Amy Wright',
    'Amanda Alvarez',
],
    'json': {
    'name': 'Sherri Jennings',
    'address': '25719 Munoz Roads\nWest Karenfort, OH 74595',
},
    'key67465': 'value1512',
    'key79959': 'value51072',
    'key2355': 'value23752',
    'key65784': 'value28103',
    'key43051': 'value99861',
    'key83748': 'value45329',
    'key42912': 'value40592',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 14,
    'name': 'Megan Romero',
    'address': '1501 Allison Landing Apt. 775\nCassandraside, IL 69342',
    'text': 'But knowledge his relate. Executive interview myself despite necessary no finally.\nAdmit quickly do listen these course. Throw into apply into political all.',
    'email': 'jwallace@example.org',
    'phone_number': '401.205.2872',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Robinson',
    'April Thomas',
    'Olivia Lee',
    'Heather Morris',
    'Jared Vasquez',
],
    'json': {
    'name': 'Joanna Fox',
    'address': '8123 Alexis Trace\nLeefurt, MS 66346',
},
    'key51154': 'value82385',
    'key93986': 'value74835',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 15,
    'name': 'Michele Kennedy',
    'address': '34079 Michael Causeway\nGordonstad, CO 10013',
    'text': 'Another month almost friend over hundred near.\nTheir when specific. Build price tell production operation compare home. Though rate over ball thing.',
    'email': 'marcusmcgee@example.org',
    'phone_number': '680-522-5788x9087',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Martin Hanson',
    'Martha Howard',
    'Amber Mcintosh',
],
    'json': {
    'name': 'Brian Scott',
    'address': '668 Gutierrez Fall\nPhamhaven, DE 45395',
},
    'key2054': 'value51059',
    'key91943': 'value43373',
    'key93552': 'value55533',
    'key52109': 'value83690',
    'key15147': 'value62254',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 16,
    'name': 'Kara Valdez',
    'address': 'USNV Price\nFPO AE 78344',
    'text': 'Different parent live more thus. Fund issue reduce ago strategy walk bed family.',
    'email': 'scott67@example.com',
    'phone_number': '(974)351-6861',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kathryn Campbell',
    'Mrs. Ashley Blake',
    'Dylan Skinner',
    'Lorraine Bell',
    'Paul Bell',
    'Kirsten Davidson',
    'Diana Howard',
],
    'json': {
    'name': 'John Barr',
    'address': '632 Grant Skyway Apt. 701\nMatthewhaven, NM 02025',
},
    'key44318': 'value85991',
    'key80039': 'value87307',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 17,
    'name': 'William Moss',
    'address': '0313 Douglas Springs\nPort Hannah, AS 68901',
    'text': 'Who discussion scientist step begin outside news.\nBrother around daughter radio lay either. Image detail improve own model.',
    'email': 'alexisjohnson@example.net',
    'phone_number': '(507)914-8276',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Webb',
    'Melissa Robinson',
    'James Perez',
    'Sarah Terry',
    'Maxwell Chapman',
    'Amanda Soto',
    'Harry Moore',
],
    'json': {
    'name': 'Melissa Smith',
    'address': '662 Kendra Corners\nJosephside, KY 14378',
},
    'key86083': 'value17207',
    'key92005': 'value60171',
    'key98365': 'value42962',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 18,
    'name': 'Arthur Odom',
    'address': '6470 Charles Forges Apt. 319\nWest Clintonmouth, NJ 68702',
    'text': 'Stop eat trip woman each. Series director light trouble increase wear learn.\nShort interesting anyone foreign citizen sport indeed. Ground major reduce eat.',
    'email': 'howellwarren@example.com',
    'phone_number': '(670)587-3463',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Conley',
    'Tanner Mitchell',
    'Debra Chandler',
    'Amanda Robinson',
    'Jesse Santos',
    'Lisa Boyd',
    'James Reed',
],
    'json': {
    'name': 'Jamie Lester',
    'address': '2617 Kimberly Terrace\nTerriland, MP 88468',
},
    'key79362': 'value49663',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 19,
    'name': 'Justin Bass',
    'address': '891 Christine Groves\nEast Stephanie, ME 53928',
    'text': 'Land want authority director throughout.\nCatch form huge member protect herself poor. Shoulder possible officer while remain. Woman spend or may source speech big.',
    'email': 'langmichael@example.com',
    'phone_number': '(684)828-7920x2940',
    'array_int_dynamic': [
    66816,
],
    'array_varchar_dynamic': [
    'Brenda Hoffman',
    'Michael Price',
    'Phyllis Wilson',
],
    'json': {
    'name': 'Dennis Dickerson',
    'address': '149 Hahn Greens\nPort Margaret, VA 63187',
},
    'key66650': 'value9970',
    'key49194': 'value80973',
    'key97056': 'value81043',
    'key40255': 'value64465',
    'key91550': 'value70922',
    'key74362': 'value79009',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 20,
    'name': 'Tracy Tucker',
    'address': 'USCGC Reeves\nFPO AE 24121',
    'text': 'View certainly perform ten child. High police space share however. Citizen success plant campaign teach choice election mean.',
    'email': 'ymarquez@example.com',
    'phone_number': '001-650-654-8389x50441',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Madison Solis',
    'John Hayes',
    'Matthew Lopez',
    'Charles Howell',
    'Jodi Waters',
    'Kenneth Macias',
    'Anne Williams',
    'Michael Hughes',
],
    'json': {
    'name': 'Carol Norman',
    'address': '3964 Bennett Dale\nPort Kerri, AK 04698',
},
    'key11170': 'value26601',
    'key47485': 'value47120',
    'key20608': 'value42259',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 21,
    'name': 'Erik Moran',
    'address': '648 Jason Plaza Apt. 002\nSouth Ana, SD 96636',
    'text': 'Language recently pattern executive him family. Bit value ten full space.',
    'email': 'chapmanjoe@example.net',
    'phone_number': '909.850.3810x7412',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Diaz',
    'Matthew West',
    'Vanessa Hoffman',
    'James Barnett',
    'Brandon Powell',
    'Charles Dean',
],
    'json': {
    'name': 'Kyle Jimenez',
    'address': '09889 David Circles\nGreenmouth, ND 01667',
},
    'key85126': 'value62974',
    'key74958': 'value35115',
    'key35356': 'value65648',
    'key39164': 'value78111',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 22,
    'name': 'Samantha Cole',
    'address': '89878 Smith Island Suite 827\nHallstad, IA 22869',
    'text': 'Free method this also physical. Second south movement treat image child plan type. Nation industry weight talk. Science class poor smile service star.',
    'email': 'erika74@example.net',
    'phone_number': '361.501.5272x57351',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Cooper',
    'Carla Waters',
    'George Hood',
    'Micheal Arnold',
    'John Lynch',
    'Scott Long',
    'Christina Martinez',
    'Jordan Wyatt',
    'Nicholas Buck',
    'Ashley Fischer',
],
    'json': {
    'name': 'Frank Gould',
    'address': '4185 Duffy Stream Apt. 605\nParkerville, LA 35628',
},
    'key69494': 'value43828',
    'key95398': 'value89459',
    'key856': 'value88329',
    'key42715': 'value47137',
    'key47618': 'value28425',
    'key12738': 'value99090',
    'key45316': 'value33093',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 23,
    'name': 'Karen Waters',
    'address': '712 Carlson Row\nNew Erikaland, WI 68140',
    'text': 'Benefit single late group catch. Upon family teach field understand should entire. Require idea upon song special. Hotel myself Republican consumer action.',
    'email': 'gracebaker@example.com',
    'phone_number': '001-658-338-8530x863',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Catherine Alvarez',
    'Kyle Ferguson',
],
    'json': {
    'name': 'Robert Cannon',
    'address': '2203 Myers Mountain\nEast Susan, RI 14966',
},
    'key37776': 'value91355',
    'key24761': 'value22701',
    'key38748': 'value94061',
    'key87671': 'value56414',
    'key69462': 'value31523',
    'key67925': 'value56342',
    'key85500': 'value66758',
    'key84837': 'value58443',
    'key17491': 'value65640',
    'key17837': 'value69958',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 24,
    'name': 'Danielle Carter',
    'address': '375 Armstrong River Suite 869\nWhitetown, VI 21893',
    'text': 'She my Republican left. Tell leg beyond draw Mrs individual think last.\nParticularly summer owner political. So recognize mouth conference meeting director between.',
    'email': 'michelle20@example.com',
    'phone_number': '001-472-338-6341',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Charles Singh',
    'Douglas Rodgers',
    'Michael Nolan',
    'Robin Mendez',
    'Elizabeth Martinez',
    'Amber Mays',
    'Crystal Simpson',
    'Juan Lewis',
    'Kathleen Mcdonald',
    'Hector Wilson',
],
    'json': {
    'name': 'Christine Shannon',
    'address': '930 Brittany Square\nPort Cindyside, AK 55272',
},
    'key31256': 'value84471',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 25,
    'name': 'Mariah Edwards',
    'address': '67084 Michael Ranch Suite 887\nSouth Philliphaven, ID 03974',
    'text': 'Instead ball fast opportunity. Reach outside later long director final give. Tough age decade with western every simply develop.',
    'email': 'melissa19@example.net',
    'phone_number': '209.621.6069',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Harris',
    'Sandra Sanchez',
    'Julia Zamora',
    'Diane Gutierrez',
    'Jennifer Meadows',
    'Annette Wilkins MD',
],
    'json': {
    'name': 'Victoria Parks',
    'address': '3025 Paul Garden\nNorth Sarahtown, AK 61578',
},
    'key94819': 'value97045',
    'key101': 'value15642',
    'key95669': 'value3828',
    'key37857': 'value55633',
    'key44158': 'value390',
    'key65288': 'value85335',
    'key89271': 'value61895',
    'key75414': 'value19513',
    'key33450': 'value8151',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 26,
    'name': 'Robin Flores',
    'address': '899 Green Knoll Apt. 205\nGinamouth, GU 76726',
    'text': 'Worker simply say responsibility consumer fine study. Player wear short new sister.',
    'email': 'nwilliams@example.net',
    'phone_number': '398.740.7039',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Maureen Smith',
    'Heather Martinez',
    'Hannah Baker MD',
    'Chad Owen',
    'Ashley Thornton',
    'Lisa Potts',
],
    'json': {
    'name': 'Leslie Mcdonald',
    'address': '6446 Theresa Parks Suite 377\nDonaldstad, FL 14857',
},
    'key24714': 'value37091',
    'key28368': 'value59742',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 27,
    'name': 'Jermaine Hobbs',
    'address': 'PSC 7393, Box 4307\nAPO AP 14489',
    'text': 'Citizen share standard clearly. Especially huge audience here defense under north.\nLeast exactly various success ball. Simple really condition itself however. Dog capital investment edge.',
    'email': 'jasonlyons@example.net',
    'phone_number': '001-583-603-9256x85288',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Courtney Lee',
    'James Sanchez',
    'Derek Smith',
],
    'json': {
    'name': 'Stacie Warren',
    'address': '2186 Jennifer Junctions\nAbbottside, MP 72269',
},
    'key72415': 'value85661',
    'key85675': 'value47967',
    'key27393': 'value93645',
    'key58334': 'value54108',
    'key92281': 'value52387',
    'key18737': 'value45714',
    'key13730': 'value74999',
    'key90968': 'value7822',
    'key5822': 'value73134',
    'key78291': 'value18621',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 28,
    'name': 'Donna Larsen',
    'address': 'USNS Garcia\nFPO AP 14294',
    'text': 'Herself central choose someone find he. Black could tree seven. Political whole range beautiful group game. Possible many deep culture health.',
    'email': 'eric24@example.org',
    'phone_number': '001-747-400-1041x01442',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Erin Taylor',
    'Scott Alvarado',
    'Susan Washington',
    'Kathryn Lozano',
    'Suzanne Frank',
    'Brandon Hicks',
],
    'json': {
    'name': 'John Flores',
    'address': '2831 Marquez Manors\nErikaville, ND 87966',
},
    'key6370': 'value30297',
    'key44067': 'value48067',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 29,
    'name': 'Diane Mitchell',
    'address': '220 Pineda Flat\nMonicaburgh, AK 51908',
    'text': 'Wind weight relate order win. First expert ground black.\nWord involve share claim. Enter radio push plant.',
    'email': 'flewis@example.com',
    'phone_number': '298-740-5759x0379',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Savannah Ramirez',
    'Thomas Nelson',
    'Isaac Taylor',
    'Sarah Kelly',
    'Bailey Davenport',
    'Zachary Golden',
    'Matthew Thomas',
    'Terri Nguyen',
],
    'json': {
    'name': 'Emily Farmer',
    'address': '6050 Medina Gardens\nMollyburgh, CA 66628',
},
    'key21648': 'value4902',
    'key37379': 'value71098',
    'key58095': 'value6816',
    'key73034': 'value7071',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 30,
    'name': 'Carla Robertson',
    'address': '894 Tucker Lodge\nPort Anthonyview, FM 30599',
    'text': 'Guess study indeed thus million near popular floor. Dinner class test coach ability. Final employee various address.\nMorning question degree day leader agree. Produce newspaper today enter.',
    'email': 'daviskristin@example.net',
    'phone_number': '(945)563-8694',
    'array_int_dynamic': [
    26590,
],
    'array_varchar_dynamic': [
    'Paul Harris',
    'Amanda Jenkins',
    'Jennifer Mckay',
    'Maria Thompson',
    'Brandi King',
    'Levi Johnson',
    'Veronica Collins',
    'Catherine Fisher',
],
    'json': {
    'name': 'Randall Baird',
    'address': '3019 Brian Junction\nSouth Stephanieberg, IN 43692',
},
    'key41572': 'value75887',
    'key66420': 'value92582',
    'key3110': 'value40196',
    'key37021': 'value1112',
    'key45073': 'value12399',
    'key82918': 'value45404',
    'key178': 'value36352',
    'key82982': 'value29173',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 31,
    'name': 'James Peterson',
    'address': '227 King Square\nMyersview, NJ 33954',
    'text': 'Yet another such music either every. Customer sign section if by kitchen local. Discover read human week organization trade.',
    'email': 'rhonda98@example.net',
    'phone_number': '(636)815-0847x8520',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Rodney Mendoza',
    'Jennifer Ruiz',
    'James Valentine',
    'Shelby Becker',
    'Brandon Mcguire',
    'Steven Woodward',
    'Madison Fitzgerald',
    'Allison Mcknight',
],
    'json': {
    'name': 'Lydia Taylor',
    'address': '7376 Montgomery Parks Apt. 842\nPort Nathanburgh, PA 71726',
},
    'key58265': 'value99550',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 32,
    'name': 'Paul Johns',
    'address': '021 Benjamin Camp Suite 349\nCoreychester, MP 95044',
    'text': 'Often customer now job kid cell. Add me change perhaps protect head. Debate accept surface threat piece dark treat particular. Son dream financial mean music though.',
    'email': 'ccross@example.net',
    'phone_number': '475-550-7011',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Brooke Wiley',
    'Pamela Rogers',
    'Donna Myers',
    'Kaitlin Smith',
    'Jacqueline Andrews',
    'Donna Johnson',
],
    'json': {
    'name': 'Erik Young',
    'address': '1686 Lucas Springs\nNew Kristishire, AK 02653',
},
    'key33826': 'value15302',
    'key93623': 'value55456',
    'key66677': 'value49521',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 33,
    'name': 'Michelle Jordan',
    'address': '0662 Thomas Expressway Suite 175\nRussellchester, AK 80081',
    'text': 'Hope dream pretty building every reduce local memory. Real society better possible about throw evidence.\nCultural environmental run risk book one.',
    'email': 'monicahughes@example.net',
    'phone_number': '001-967-894-4993x9180',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Wilson',
    'Natalie Morgan',
],
    'json': {
    'name': 'Wayne Ramos',
    'address': '783 Leonard Dam\nSotoburgh, GA 09395',
},
    'key82157': 'value12636',
    'key75196': 'value67973',
    'key95313': 'value14906',
    'key51053': 'value66792',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 34,
    'name': 'Alan Anderson',
    'address': '7978 Lucas Walk\nNew Matthewburgh, TX 72607',
    'text': 'Upon hard speak consider scientist help. Peace sit character leave between. Season trial officer movie memory. Church ok here right mission protect.',
    'email': 'emilyespinoza@example.com',
    'phone_number': '807-667-0284x829',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Galloway',
    'Gregory Finley',
],
    'json': {
    'name': 'Laura Dunn',
    'address': '8645 Brown Skyway\nSouth Jeffery, WY 06916',
},
    'key74201': 'value29020',
    'key54525': 'value94149',
    'key84096': 'value22346',
    'key92561': 'value28559',
    'key33642': 'value71695',
    'key65926': 'value43952',
    'key36763': 'value58813',
    'key8019': 'value97731',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 35,
    'name': 'Lisa Allison',
    'address': '47890 Levine Forges\nEast Sarahstad, VT 86100',
    'text': 'Production this bring them scientist realize bit. Go hair detail ten car. Benefit community parent fine music necessary interview.',
    'email': 'gyoung@example.org',
    'phone_number': '9129856807',
    'array_int_dynamic': [
    12177,
],
    'array_varchar_dynamic': [
    'Kathryn Christensen',
    'Stephanie Lewis',
    'Alexandria Walls',
],
    'json': {
    'name': 'Amanda Ray',
    'address': '54240 Jason Fork Suite 081\nBrucefurt, OR 34225',
},
    'key89759': 'value54406',
    'key75405': 'value39574',
    'key44658': 'value40953',
    'key27073': 'value137',
    'key27237': 'value52182',
    'key78643': 'value63047',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 36,
    'name': 'Michael Fisher',
    'address': '954 Ashley Wall Suite 893\nEast Scottport, VA 58008',
    'text': 'Through network player skill rule card. Spend front position democratic travel entire. Sit then season over stage beat dog thought.\nNor manager front rather couple.',
    'email': 'rgood@example.org',
    'phone_number': '335-206-5498x769',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Teresa Hodge',
    'Robert Hamilton',
    'Christy Hull',
],
    'json': {
    'name': 'Daniel Rodriguez',
    'address': '41553 Velez Plaza\nCraigland, IN 94666',
},
    'key55365': 'value80850',
    'key81460': 'value48137',
    'key56663': 'value25061',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 37,
    'name': 'Frances Davies',
    'address': '5149 Davis Tunnel\nReeveschester, AZ 96170',
    'text': 'Republican professor wait professor defense. Police adult edge approach.\nProfessional another star simple between. Best soon kind laugh room term rate.',
    'email': 'billy15@example.net',
    'phone_number': '9259245183',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sherry White',
    'William Patel',
    'Johnathan Brown',
],
    'json': {
    'name': 'Clarence Barry',
    'address': '913 Harry Brooks\nSouth Aaron, NJ 39864',
},
    'key92551': 'value22423',
    'key5592': 'value69328',
    'key56360': 'value31147',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 38,
    'name': 'John Leon',
    'address': '92094 Robert Extensions\nNew Richard, MA 82375',
    'text': 'Recently environment figure when. Your important story.\nWhite pressure technology operation laugh. Purpose six fight food town reason recently.',
    'email': 'hamiltondavid@example.net',
    'phone_number': '(546)337-1634x3679',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Mcdonald',
    'Steven Stewart',
    'Joseph Baker',
    'Jacob Davis',
],
    'json': {
    'name': 'Dakota Rogers',
    'address': '37081 Dylan Ports Apt. 275\nPort Heatherberg, OH 06608',
},
    'key6165': 'value22539',
    'key82692': 'value41058',
    'key3442': 'value62549',
    'key45816': 'value1177',
    'key55315': 'value26909',
    'key99473': 'value94601',
    'key42630': 'value22464',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 39,
    'name': 'William Lewis',
    'address': 'Unit 8570 Box 8165\nDPO AA 28001',
    'text': 'Once reach just fear thank ability. Ready really event thousand commercial out today. Hard road wind whose investment.\nShould year buy former ready shake receive. Election his nation loss bit.',
    'email': 'robin55@example.org',
    'phone_number': '269-225-7078x458',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Pratt',
    'Heather Carrillo',
    'Christopher Cervantes',
    'Karen Ingram',
    'Penny Chang',
    'Jamie Lewis',
    'Mitchell Perez',
],
    'json': {
    'name': 'Laura Macdonald',
    'address': 'PSC 1058, Box 5374\nAPO AP 48621',
},
    'key9660': 'value8072',
    'key2175': 'value44499',
    'key25497': 'value24254',
    'key46877': 'value58791',
    'key46445': 'value80679',
    'key60713': 'value18387',
    'key16256': 'value51643',
    'key81163': 'value72493',
    'key17316': 'value55461',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 40,
    'name': 'Rhonda Edwards',
    'address': '637 Brian Divide Suite 434\nAprilland, IN 88866',
    'text': 'Important study protect partner building ago long. Let subject election administration. Sort teach leave card it garden defense.\nHead my with.',
    'email': 'donnacox@example.com',
    'phone_number': '(974)538-1288',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Lauren Myers',
    'Michael Russell',
    'Catherine Stone',
    'Carol Adkins',
    'Megan Robinson',
    'Robert Campbell',
    'Bobby Williams',
    'Mitchell Ramos',
],
    'json': {
    'name': 'Abigail Curtis',
    'address': '4812 Rodriguez Landing\nChristopherfurt, LA 27177',
},
    'key27364': 'value10370',
    'key56566': 'value49818',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 41,
    'name': 'Molly Dyer',
    'address': 'Unit 3737 Box 2204\nDPO AP 17498',
    'text': 'Center team glass science usually suffer technology star.\nImage likely today year there share site. Much likely pressure thus and. Color somebody lose nice point arrive.',
    'email': 'paul01@example.com',
    'phone_number': '700.909.2968',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Eric Harrison',
    'Susan Hayes',
    'Veronica Ramirez',
    'Amber Douglas DVM',
    'Kathy Fleming',
    'Pamela Perez',
    'John Gibbs Jr.',
    'Emily Jimenez',
    'Michael Mclaughlin',
],
    'json': {
    'name': 'Laura Ortiz',
    'address': '398 Kelley Burgs\nNew Pennyberg, AZ 68940',
},
    'key25672': 'value93595',
    'key95778': 'value19827',
    'key20165': 'value57218',
    'key69255': 'value91118',
    'key41730': 'value45362',
    'key84613': 'value5046',
    'key87369': 'value20470',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 42,
    'name': 'Robert Thompson',
    'address': '12593 Alex Bridge\nEast Paul, TN 10512',
    'text': 'Beautiful three box partner never front.\nReason own seem. Democrat whole either defense back expert speak task. If say nothing from.',
    'email': 'hollynelson@example.com',
    'phone_number': '805-335-8207x982',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Martin',
    'Austin Reyes',
    'Justin Joseph',
    'Joseph Anderson',
],
    'json': {
    'name': 'Dawn Morgan',
    'address': '77992 Laura Throughway Apt. 110\nHarrismouth, AS 57142',
},
    'key51297': 'value95920',
    'key53653': 'value34747',
    'key87404': 'value81857',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 43,
    'name': 'William Boyd',
    'address': '93768 Kenneth Turnpike Suite 973\nNew Russelltown, WY 56052',
    'text': 'Discover total dog heart pressure. Left letter him point behavior onto fill.\nState born last blood knowledge eight. Structure speech over vote agency yard unit reveal.',
    'email': 'morenolaura@example.com',
    'phone_number': '793-605-0403x555',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Tracy Fisher',
    'Evan Davis',
    'Francis Baker',
    'Traci Brock',
    'Heather Huffman',
    'Michael Andrews',
    'Travis Hood',
],
    'json': {
    'name': 'Alisha Sanchez',
    'address': '95794 Lauren Harbor\nWest Marissa, TX 70558',
},
    'key72860': 'value26752',
    'key53123': 'value63331',
    'key58081': 'value68590',
    'key15272': 'value2227',
    'key25748': 'value3947',
    'key63163': 'value97253',
    'key63419': 'value28932',
    'key5189': 'value68965',
    'key88588': 'value95504',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 44,
    'name': 'Jason Rivera',
    'address': '6146 Lori Islands Apt. 784\nEast Theresaview, CO 03821',
    'text': 'Tonight education finally area. Form nothing current recently.\nConsider hard pick clearly upon record will. Later indicate significant page recent listen lead.',
    'email': 'alyssa09@example.com',
    'phone_number': '498.550.2110',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Cassandra Jones',
    'Felicia Gonzalez',
    'Dana Jones',
    'Sara Lloyd',
    'Brandon Mitchell',
    'Misty Phillips',
    'Stephanie Ray',
],
    'json': {
    'name': 'Angela Henson',
    'address': '059 Mary Plaza\nLake Wayne, UT 04830',
},
    'key88479': 'value22049',
    'key29342': 'value94410',
    'key10357': 'value47356',
    'key15463': 'value36478',
    'key74410': 'value84385',
    'key33886': 'value62098',
    'key12214': 'value23086',
    'key42302': 'value71208',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 45,
    'name': 'Bruce Lucas',
    'address': '3454 Holden Track\nNew Jeanne, NH 55188',
    'text': 'Drive civil moment. Move strategy group charge stay determine. Hand information adult themselves say.',
    'email': 'yhall@example.com',
    'phone_number': '001-827-540-7376x7446',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Angela Davila',
    'Xavier Jimenez',
    'Jerry Perez',
],
    'json': {
    'name': 'Dana Walters',
    'address': '8320 Green Highway Suite 982\nChristinaside, NV 15026',
},
    'key77687': 'value53207',
    'key24063': 'value40046',
    'key15067': 'value24820',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 46,
    'name': 'David Perkins',
    'address': 'Unit 8157 Box 9615\nDPO AA 60548',
    'text': 'Management chance hair important unit. College husband again become receive window everybody. Test manage clearly home small worker.',
    'email': 'amyberry@example.org',
    'phone_number': '8396368238',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Morales MD',
    'Adrian Williams',
    'Earl Hernandez MD',
    'Dustin Hayes',
    'Brandon Petersen',
    'Jonathan Carter',
    'Michael Velasquez',
    'Pamela Rios',
    'Jasmine Miller',
    'Michelle Washington',
],
    'json': {
    'name': 'Jorge Smith',
    'address': 'Unit 2749 Box 9094\nDPO AE 46081',
},
    'key99519': 'value79594',
    'key27260': 'value78779',
    'key92970': 'value45832',
    'key32166': 'value59911',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 47,
    'name': 'Bradley Williams',
    'address': 'Unit 5282 Box 2770\nDPO AP 38677',
    'text': 'Blood phone Mr central be.\nNotice four win follow cell also. Per second safe address evidence voice.',
    'email': 'nicolecohen@example.net',
    'phone_number': '307-467-1083',
    'array_int_dynamic': [
    31975,
],
    'array_varchar_dynamic': [
    'Christine Montes',
    'Mary Lewis',
    'Luke Strong',
    'Victoria Meyer',
    'Tiffany Dixon',
    'Daniel Dickerson',
    'Sarah Taylor',
    'Christopher Pham',
    'Ann Jenkins',
],
    'json': {
    'name': 'Anthony Gomez',
    'address': '832 Amber Forges Apt. 020\nNew Nicole, DE 33058',
},
    'key74676': 'value74736',
    'key82553': 'value54621',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 48,
    'name': 'Jesus Medina',
    'address': '2731 French Extensions Suite 064\nLake Davidtown, NY 71940',
    'text': 'Participant wide community beat bank. Anything town throw him wide all magazine. Article agreement from much prepare moment tend sell.\nPublic its lose.',
    'email': 'brucemclaughlin@example.org',
    'phone_number': '+1-945-260-8284',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'John Simon',
    'Christopher Morgan',
    'Andrew Marks',
    'Belinda Campbell',
    'Debra Gonzalez',
    'Christopher Nichols',
    'Paul Jones',
    'Mr. Jeremiah Clark MD',
    'Linda Rodriguez',
    'Daniel Long',
],
    'json': {
    'name': 'Mrs. Betty Ramirez',
    'address': '4645 Cheryl Spurs Apt. 034\nDesireeshire, MD 78373',
},
    'key95556': 'value926',
    'key71652': 'value37881',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 49,
    'name': 'Daniel Smith',
    'address': '403 Miles Road\nEast Katherine, WY 49781',
    'text': 'Produce for in goal. Seem road middle right.\nSomebody task guess. Professor Congress show himself health evidence. Theory statement already. Soldier receive almost.',
    'email': 'jenniferbaker@example.net',
    'phone_number': '8289121933',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jessica Mullins',
],
    'json': {
    'name': 'Henry Moreno',
    'address': '0800 Lopez Ferry\nLivingstonmouth, TX 86243',
},
    'key68787': 'value1361',
    'key63451': 'value14534',
    'key6513': 'value30735',
    'key25080': 'value5681',
    'key27408': 'value62732',
    'key88464': 'value39337',
    'key63914': 'value30066',
    'key55320': 'value90259',
    'key71639': 'value36914',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 50,
    'name': 'Kelly Reynolds',
    'address': 'USNV Duncan\nFPO AE 61346',
    'text': 'Health management PM political whom daughter. Put artist hospital him with second.\nBill table course position similar. Less actually health American.',
    'email': 'daniel14@example.org',
    'phone_number': '281.206.7652',
    'array_int_dynamic': [
    73087,
],
    'array_varchar_dynamic': [
    'Tiffany Long',
],
    'json': {
    'name': 'Brenda Harris',
    'address': '493 Duane Harbor\nPort Crystal, GU 45026',
},
    'key17395': 'value68053',
    'key32180': 'value91065',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 51,
    'name': 'Darlene Macias',
    'address': '550 Waller Bypass\nKimberlytown, UT 04881',
    'text': 'Eye ahead his sometimes late stage. Growth base third various.\nWhile policy wide exist. Next thank list open such. Indeed wide color economy.',
    'email': 'aharvey@example.com',
    'phone_number': '796.301.0950',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kenneth Mckinney',
    'John Johnson',
    'Erica Powers',
    'Gene Bowman',
    'Anthony Anderson',
    'Danielle Townsend',
    'Robert Johnson',
    'Mr. Casey Miller II',
],
    'json': {
    'name': 'Michelle Ellis',
    'address': '087 Rodriguez Valleys\nEast Kyle, LA 75337',
},
    'key4698': 'value32881',
    'key48751': 'value56199',
    'key29716': 'value86531',
    'key89238': 'value67357',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 52,
    'name': 'James Simmons',
    'address': 'USNS Ward\nFPO AP 49338',
    'text': 'Data issue piece pattern model.\nCase charge improve military approach. Catch consider pull kind.\nTrue call reflect simply. Improve always themselves morning only.',
    'email': 'epeterson@example.com',
    'phone_number': '3014533983',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Gerald Hampton',
    'Vanessa Carlson',
    'Michelle King',
    'Olivia Wright',
    'Ryan Park',
    'Jesus Martinez',
    'Richard Caldwell',
    'William Lewis',
    'John Williams',
],
    'json': {
    'name': 'Julie Morris',
    'address': '80567 Kathryn Ways Apt. 442\nWeissshire, SC 71004',
},
    'key14938': 'value26003',
    'key84353': 'value99386',
    'key3903': 'value30164',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 53,
    'name': 'Christina Brown',
    'address': '7812 Ross Mills\nAmyshire, NV 62526',
    'text': 'Themselves arm next. Measure those role day song suggest world.',
    'email': 'jesusfuentes@example.org',
    'phone_number': '(623)649-5571x726',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Nicolas Lara',
    'Dr. Vanessa Contreras',
    'Jared Lambert',
    'Keith Johnson',
],
    'json': {
    'name': 'Angela Hall',
    'address': '79372 Michael Loaf Apt. 336\nJohnfurt, MP 53964',
},
    'key29868': 'value31744',
    'key87190': 'value93057',
    'key22107': 'value18471',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 54,
    'name': 'Dr. Andrew Mcmahon',
    'address': '575 Obrien Squares\nAlexborough, SD 42523',
    'text': 'Success keep program forget. Despite tough area rock reveal painting. Physical place entire explain.\nOperation option increase in edge. Democrat tree hospital else close.',
    'email': 'agarrison@example.org',
    'phone_number': '+1-490-916-6840x07137',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Singleton',
    'Joanne Pham',
    'William Everett',
    'Jonathan Gonzales',
    'Steven Gonzalez',
],
    'json': {
    'name': 'Ronnie Weaver',
    'address': 'Unit 0262 Box 4379\nDPO AP 92160',
},
    'key2625': 'value58188',
    'key99639': 'value66132',
    'key23232': 'value18131',
    'key95609': 'value22453',
    'key87947': 'value15107',
    'key25527': 'value14256',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 55,
    'name': 'Shane Mason',
    'address': '792 Hughes Lodge\nNew Jennifer, ND 18809',
    'text': 'Usually attorney lay street degree either cold over. Worker sing large radio.\nCommon big would receive upon. Method vote exist. Source write four myself various.',
    'email': 'browngary@example.com',
    'phone_number': '341.462.7329x127',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Mary Kennedy',
    'Michelle Perry',
    'Abigail Reynolds',
    'Molly Taylor',
    'Adam Edwards',
    'John Waller',
    'James Hernandez',
    'Jennifer Rivera',
    'Jennifer Garcia',
],
    'json': {
    'name': 'Aaron Johnson',
    'address': '849 Rhonda Parkways\nWest Stephenhaven, NM 82458',
},
    'key70347': 'value19525',
    'key15249': 'value96704',
    'key37139': 'value94461',
    'key18791': 'value11598',
    'key61828': 'value36617',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 56,
    'name': 'Sandra Hill',
    'address': '7246 Stokes Plaza Apt. 536\nEast Ronald, OR 93827',
    'text': 'Size these data economic knowledge very. Why guy reason. Him no why interesting person film.',
    'email': 'mariaolson@example.com',
    'phone_number': '(989)394-7139x439',
    'array_int_dynamic': [
    7286,
],
    'array_varchar_dynamic': [
    'Phillip Jones',
    'Gary Fuller',
    'Melissa Morton',
    'Anna Thomas',
    'Ryan Thompson',
    'Leslie Joseph',
    'Misty Rodriguez',
    'Ann Moore',
    'Sharon Hatfield',
],
    'json': {
    'name': 'Kenneth Hull',
    'address': 'USCGC Compton\nFPO AP 75285',
},
    'key40585': 'value32911',
    'key33986': 'value71460',
    'key4128': 'value56147',
    'key86400': 'value40101',
    'key41168': 'value23643',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 57,
    'name': 'John Atkinson MD',
    'address': '021 Wheeler Center\nPort Kaylatown, PW 55661',
    'text': 'Spend source need your send crime. Letter black indeed east.\nPublic history you quite development Republican. Maintain Congress hot huge hard. Indeed speech beautiful ten across economic kitchen.',
    'email': 'martinmatthew@example.org',
    'phone_number': '786.954.4593',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Julia Robbins',
    'Raymond Reyes',
    'Breanna Smith',
    'Lindsay Kim',
    'Cheryl Collins',
],
    'json': {
    'name': 'Allen Copeland',
    'address': '04841 Maria Valleys\nWest Kristen, VA 97972',
},
    'key52029': 'value38559',
    'key12493': 'value52222',
    'key40128': 'value60909',
    'key45840': 'value12911',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 58,
    'name': 'Kristine Murphy',
    'address': '16984 Jones Lakes\nAlvarezshire, NM 58507',
    'text': 'All power friend size. Best agent yourself.\nFoot fall candidate discuss analysis chance. Mind whose benefit situation few case. We issue really administration population eat interesting store.',
    'email': 'clarkmariah@example.com',
    'phone_number': '001-663-713-8113x50909',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Bethany Sandoval',
    'Stephanie Jenkins',
    'Keith Phillips',
    'Erica Lopez',
    'Michelle Moon',
    'Katherine Saunders',
    'David Stuart',
],
    'json': {
    'name': 'Richard Mejia',
    'address': '80850 Berger Ford\nStarkton, AS 08070',
},
    'key21037': 'value55491',
    'key88133': 'value58315',
    'key38962': 'value99805',
    'key11594': 'value7567',
    'key4544': 'value87491',
    'key52304': 'value57984',
    'key91911': 'value59592',
    'key73308': 'value31028',
    'key35727': 'value37617',
    'key28211': 'value81607',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 59,
    'name': 'Jose Porter',
    'address': '44386 Scott Union\nLake Tonya, DC 25765',
    'text': 'Man data tough central stock subject wish. Newspaper if land cultural lay financial budget father.',
    'email': 'mendozatracy@example.com',
    'phone_number': '(311)284-9286x8539',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kathryn Baker',
    'Patricia Anderson',
    'Curtis Martinez',
    'Rebecca Roberts',
    'Matthew Fisher',
],
    'json': {
    'name': 'Marc Taylor',
    'address': '0811 Stephen Glen Apt. 771\nDavidburgh, NC 10583',
},
    'key94335': 'value83545',
    'key56016': 'value63752',
    'key33530': 'value23911',
    'key85547': 'value63638',
    'key28736': 'value28450',
    'key3852': 'value1369',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 60,
    'name': 'Dawn Gay',
    'address': '053 Miller Road Suite 388\nJohnsonhaven, CA 39476',
    'text': 'Board the state buy information. Enough theory nothing nor. Yard change four he direction author why crime.\nSupport reduce near. Idea owner account between. Today economic little not.',
    'email': 'briansmith@example.net',
    'phone_number': '(200)475-4031x56969',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Lane',
],
    'json': {
    'name': 'Thomas Friedman',
    'address': 'USS Campbell\nFPO AA 81882',
},
    'key11846': 'value32087',
    'key54807': 'value47019',
    'key54899': 'value62755',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 61,
    'name': 'Rebecca Riley',
    'address': '18713 Teresa Highway Suite 250\nNorth Katherineport, GU 40101',
    'text': 'People over pull early. Road police seat seem. Stop tend work week summer goal lot.\nWoman once develop moment fill later. Ahead western lose various break find.',
    'email': 'rosaleschristina@example.org',
    'phone_number': '(507)485-5771',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Dennis Callahan',
    'Katherine Campbell',
    'Mary Johnson',
    'Kelly Wang',
    'John Sanchez',
    'Julie Bush',
    'Sean Hughes',
    'Kelli Phillips',
],
    'json': {
    'name': 'John Reed',
    'address': 'Unit 9836 Box 2281\nDPO AE 01524',
},
    'key53154': 'value18956',
    'key68957': 'value85931',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 62,
    'name': 'Dr. Ashley Mitchell',
    'address': '601 Lopez Stream Apt. 026\nJamesport, ID 93925',
    'text': 'Establish so even drive.\nPolitics either newspaper fight hand memory new already. Alone resource bed court this in. People toward organization sit artist happy force.',
    'email': 'caleb26@example.org',
    'phone_number': '379.675.7901',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Melissa York',
    'Tracy Roth',
    'James Reeves',
    'Carrie Bonilla',
    'Craig Mason',
],
    'json': {
    'name': 'Devin Hernandez',
    'address': '19220 Mcbride Roads Suite 243\nPort Robert, OR 28007',
},
    'key84006': 'value98054',
    'key80924': 'value76853',
    'key55642': 'value84988',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 63,
    'name': 'Tim Compton',
    'address': '014 Terrence Square\nNorth Dakotabury, AR 05996',
    'text': 'Ok magazine budget chance. National film simply loss will church employee. Personal like like.\nResearch memory purpose goal. Note black improve own me.',
    'email': 'hannabrandon@example.org',
    'phone_number': '413.256.6769x7896',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Justin Hernandez',
],
    'json': {
    'name': 'Caitlyn Rogers MD',
    'address': '8579 Clinton Branch\nNorth Jasmine, NE 43666',
},
    'key62933': 'value26346',
    'key97905': 'value8106',
    'key88988': 'value11246',
    'key30702': 'value10086',
    'key53283': 'value90812',
    'key54976': 'value62868',
    'key32062': 'value86245',
    'key13070': 'value79293',
    'key57451': 'value37694',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 64,
    'name': 'Robert Nichols',
    'address': '3793 Joanna Street\nAlisonbury, VT 54542',
    'text': 'Shake follow professional fall. Room against across tend image. Describe bad able top.\nKey if statement catch billion behind. Third sing two trouble.',
    'email': 'sandovalfrank@example.com',
    'phone_number': '549-868-5926x246',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Rachel Adams',
    'Kristine Mason',
    'Tommy Walker',
    'Cynthia Archer',
    'Dennis Davis',
    'James Morgan',
],
    'json': {
    'name': 'Lindsey Morrow',
    'address': '02288 Margaret Pine Apt. 736\nLake Michaelfort, WI 76428',
},
    'key88179': 'value84586',
    'key82235': 'value29626',
    'key39068': 'value55254',
    'key36736': 'value32813',
    'key44655': 'value89897',
    'key61068': 'value59389',
    'key37410': 'value23532',
    'key84390': 'value28935',
    'key79293': 'value83390',
    'key45439': 'value18940',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 65,
    'name': 'Barbara Rogers',
    'address': '836 Jeffrey Inlet\nMichaelbury, MO 15757',
    'text': 'Despite music there manage much career. Yeah area let no key.\nRepresent today worry local knowledge bar you. Cause reach sister style.',
    'email': 'david05@example.com',
    'phone_number': '001-632-872-4527',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Albert Wilson',
    'Connor Ferguson',
    'Scott Taylor',
    'Kimberly Vazquez',
    'Suzanne Alvarado',
    'Lori Giles',
    'Lauren Simon',
    'Brandon Jackson',
    'Ashley Hale',
],
    'json': {
    'name': 'Steven Wheeler',
    'address': '28919 Jacob Knolls Apt. 407\nLake Brookeshire, AZ 69345',
},
    'key12945': 'value79865',
    'key37776': 'value4260',
    'key58992': 'value67734',
    'key39929': 'value86709',
    'key91081': 'value1539',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 66,
    'name': 'Keith Beltran',
    'address': '3828 Deleon Divide\nBrookeville, ME 03714',
    'text': 'Executive positive idea identify any consider. Network reduce several science. Seat one article shoulder red they safe building.',
    'email': 'robert76@example.net',
    'phone_number': '001-368-292-5626x213',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Jackson',
    'David Ware',
    'Allison Crosby',
    'Sarah Morgan',
],
    'json': {
    'name': 'Joseph Hernandez',
    'address': '20385 Jennifer Mews\nNew Bradley, PA 57764',
},
    'key5375': 'value8013',
    'key81510': 'value58556',
    'key17045': 'value42910',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 67,
    'name': 'Mrs. Kristin Stone',
    'address': '97930 Barbara Bridge\nLovefurt, HI 47858',
    'text': 'That better himself might fast soldier onto.\nDifficult theory garden despite.\nPart thank avoid same writer usually interest. Concern three between. Similar still weight outside nothing character war.',
    'email': 'paula09@example.net',
    'phone_number': '(349)218-8290x558',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Manuel Barnes',
    'Stacey Lindsey',
    'Michele Webster',
    'Joshua Sherman',
],
    'json': {
    'name': 'Ruth Lewis',
    'address': '491 Caitlin Course\nSouth Raymond, ID 22501',
},
    'key94164': 'value89196',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 68,
    'name': 'Richard Francis',
    'address': '06067 Yvonne Street Apt. 317\nLawrencemouth, SD 40005',
    'text': 'Exist government more. Without answer high me it.\nDefense air thank.',
    'email': 'susan92@example.net',
    'phone_number': '5403719389',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Rebecca Barnett',
    'Donald Johnson',
    'Kyle Wilson',
    'Adam Brooks',
    'Ronald Gallagher',
    'Geoffrey Coffey',
    'Anthony Hunter',
],
    'json': {
    'name': 'Susan Simpson',
    'address': '37381 Hicks Throughway\nJessicaton, AL 47799',
},
    'key7154': 'value89046',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 69,
    'name': 'Diana Ali',
    'address': '34228 Castaneda Throughway\nDanielshire, TX 34165',
    'text': 'Act land Republican these live strong. Research expect go future office single. Since must meet.\nCertain note stage need energy article almost. Certainly cold together speak lay.',
    'email': 'wilkinsonrobin@example.org',
    'phone_number': '220.330.1994x873',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Mary Potter',
],
    'json': {
    'name': 'Amanda Barker',
    'address': '23346 Christine Road Suite 145\nPort Bradley, IN 80988',
},
    'key81314': 'value11651',
    'key97336': 'value60464',
    'key14404': 'value43961',
    'key64558': 'value47080',
    'key86442': 'value69617',
    'key15095': 'value4787',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 70,
    'name': 'Alexander Perez',
    'address': 'PSC 0466, Box 0075\nAPO AE 23811',
    'text': 'Unit way American possible debate because.\nDrive require growth total. Probably remain eye society he according. Down glass all minute upon red next old.',
    'email': 'robertmyers@example.com',
    'phone_number': '+1-723-593-8169x538',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Katherine Ramos',
    'Mr. Mark Liu DVM',
    'Becky Martin',
    'Wendy Holden',
],
    'json': {
    'name': 'Angela Richardson',
    'address': '31487 Silva Field\nWest Tina, GU 15134',
},
    'key12408': 'value15321',
    'key19319': 'value31840',
    'key72807': 'value87697',
    'key20704': 'value41876',
    'key6877': 'value21597',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 71,
    'name': 'Brittany Rodriguez',
    'address': '295 Angela Junctions\nKendramouth, AZ 21185',
    'text': 'Team business consider push production executive blood walk. Well simple collection business evening anyone policy. Learn take quickly could statement.',
    'email': 'robinsoncolin@example.net',
    'phone_number': '001-852-932-8193x47973',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Miller',
    'Benjamin Smith',
    'Matthew Butler',
    'Ian Ruiz',
],
    'json': {
    'name': 'Gary Ballard',
    'address': '3620 Gibbs Grove\nGregoryview, SD 16237',
},
    'key19562': 'value23191',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 72,
    'name': 'Billy Davis',
    'address': '19204 Melton Circles\nDunnview, NJ 13060',
    'text': 'Difficult sometimes drug long there. Strong meet financial career beyond drop effort behind.\nTown far character attorney stock field manager indicate. Although time particular administration.',
    'email': 'meganbrennan@example.net',
    'phone_number': '630.780.2622x256',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Pamela Miller',
    'Jennifer Alexander',
    'Crystal Goodman',
    'Patricia Zhang',
    'Lisa Curry',
    'Tyler Simmons',
    'William Hawkins',
    'Michelle Ryan',
    'Tammy Frazier',
],
    'json': {
    'name': 'John Washington',
    'address': '5548 Ronald Trace Apt. 075\nMargaretstad, MA 39907',
},
    'key84814': 'value41643',
    'key34250': 'value28536',
    'key73868': 'value44331',
    'key87560': 'value37346',
    'key70347': 'value92793',
    'key62364': 'value36289',
    'key13883': 'value62566',
    'key19852': 'value45084',
    'key44886': 'value64741',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 73,
    'name': 'William Fox',
    'address': '226 Abigail Meadow\nAmyhaven, UT 44942',
    'text': 'Author fire new human his success now. Arrive by right can.\nUpon discuss wish run. By how know assume kitchen organization.',
    'email': 'kellerjimmy@example.org',
    'phone_number': '+1-315-916-3617',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Gregory',
    'Samantha Sawyer',
    'Daniel Klein',
],
    'json': {
    'name': 'Michael Hardin',
    'address': '9498 William Radial\nManningville, GU 31428',
},
    'key2155': 'value6389',
    'key29014': 'value76723',
    'key81845': 'value58663',
    'key12614': 'value78479',
    'key19665': 'value28480',
    'key46834': 'value84413',
    'key10401': 'value60160',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 74,
    'name': 'Kimberly Jackson',
    'address': '352 Rivera Mill\nClinefurt, SD 87424',
    'text': 'Then ground toward state war letter blood. Special country carry magazine stuff control end. Agree morning their air role president common.',
    'email': 'aliciahughes@example.org',
    'phone_number': '394.395.5164x3619',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Brock',
    'Kimberly Hampton',
],
    'json': {
    'name': 'Nancy Anderson',
    'address': '55705 Wade Mall\nWest Justinton, FM 16325',
},
    'key21194': 'value90656',
    'key75468': 'value42877',
    'key95889': 'value44536',
    'key84593': 'value10950',
    'key17701': 'value55952',
    'key85432': 'value88865',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 75,
    'name': 'Krystal Meadows',
    'address': '5446 Reynolds Tunnel\nSmithborough, OK 75726',
    'text': 'Plant threat center campaign. Nor buy step administration final. Certain class little group else pull.\nBelieve religious test cold.\nParticipant be again cost she thus.',
    'email': 'reidjames@example.net',
    'phone_number': '703-917-4422x5399',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'James Hurley',
    'Dana Taylor',
    'John Collins',
    'Suzanne Noble',
    'Joseph Mccarty',
    'Bridget Arroyo',
    'Angela Johnson',
],
    'json': {
    'name': 'Christopher Anderson',
    'address': '39780 Johnson Spurs\nGoodwinport, KY 69677',
},
    'key27283': 'value95901',
    'key81556': 'value70734',
    'key13290': 'value23875',
    'key15041': 'value12590',
    'key44237': 'value9138',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 76,
    'name': 'Jason Carey',
    'address': '335 Rhodes Oval Apt. 579\nWest Amymouth, LA 30897',
    'text': 'General attack against newspaper enjoy. Operation structure and agreement value their energy source.',
    'email': 'stefanielee@example.com',
    'phone_number': '001-988-696-3547x7663',
    'array_int_dynamic': [
    23029,
],
    'array_varchar_dynamic': [
    'Jeremy Bradley',
    'Donald Johnson',
    'Jill Phillips',
    'Pamela Edwards',
    'Linda Thompson',
],
    'json': {
    'name': 'David Mccarty',
    'address': '0928 Gonzales Shoal Apt. 537\nLaurastad, FM 84126',
},
    'key73072': 'value3280',
    'key74365': 'value43944',
    'key64690': 'value91130',
    'key40255': 'value96282',
    'key61383': 'value89479',
    'key43358': 'value37594',
    'key82497': 'value30523',
    'key28338': 'value43521',
    'key60685': 'value14585',
    'key99704': 'value37418',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 77,
    'name': 'Jennifer Kennedy',
    'address': '898 Claudia Fords\nWest Johntown, NM 54100',
    'text': 'Look effort around air. First large poor model.\nAddress learn probably sea with agent. Develop region question figure should. Might much admit agency large.',
    'email': 'brooksshawn@example.net',
    'phone_number': '(248)565-5581x01257',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Osborne',
    'James Williams',
    'David Thomas',
    'Joseph Rodriguez',
    'Eric Simmons',
    'Joseph Rojas',
    'James Ferguson',
    'Angela Chavez',
],
    'json': {
    'name': 'Sheila Rios',
    'address': '94745 John Lake\nNorth Shannon, LA 61049',
},
    'key65073': 'value71238',
    'key34173': 'value17132',
    'key40820': 'value18381',
    'key70675': 'value78122',
    'key71058': 'value69805',
    'key87650': 'value22961',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 78,
    'name': 'David Mcdonald',
    'address': '4635 Smith Squares Apt. 235\nTravisstad, WY 37405',
    'text': 'Nation money significant interest paper step. Whole after those us across believe. Camera page improve whom deal far.\nMagazine themselves star exist cut. Hot important five.',
    'email': 'tbarajas@example.org',
    'phone_number': '+1-953-527-1360x7751',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Charles Sims',
    'Alyssa Scott',
    'Holly Atkins',
],
    'json': {
    'name': 'Charles Payne',
    'address': '140 Steven Trail\nCassandrahaven, WA 66135',
},
    'key24861': 'value30215',
    'key4000': 'value85867',
    'key26086': 'value89377',
    'key29380': 'value75805',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 79,
    'name': 'Janet Ramos',
    'address': '0564 Carrie Trail\nAprilview, PA 14545',
    'text': 'Heavy fall left food head price risk meet. Difference according audience education. Trip spring whose specific.\nBit day whom institution possible.',
    'email': 'carterlisa@example.com',
    'phone_number': '(656)665-3625x4815',
    'array_int_dynamic': [
    38657,
],
    'array_varchar_dynamic': [
    'Cody Edwards',
    'Henry Lopez',
    'Joseph Dawson',
    'Maria Lewis',
    'Nancy Murphy',
    'Joyce Graham',
    'Lori Newman',
    'Sarah Carter',
    'Janet Saunders',
],
    'json': {
    'name': 'Daniel Mendoza',
    'address': '9556 Dustin River Apt. 260\nNew Joshua, TN 37835',
},
    'key13004': 'value89270',
    'key50573': 'value28288',
    'key7967': 'value91237',
    'key46003': 'value55380',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 80,
    'name': 'Robert Campbell',
    'address': '46680 Jeffrey Isle\nNew Lynnland, GU 27716',
    'text': 'Up happen let official air tree. Land information wide history ready kind. Top contain the land organization thought today.',
    'email': 'stephanie48@example.org',
    'phone_number': '868-331-5519',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Jerry Garrett',
    'Jason Walton',
    'Jennifer Taylor',
    'Stephen Wilson',
    'Ryan Pham',
],
    'json': {
    'name': 'Kimberly Griffin',
    'address': '7767 Fleming Causeway Suite 507\nChristopherport, AL 85734',
},
    'key17927': 'value60058',
    'key85150': 'value86916',
    'key8425': 'value67482',
    'key52268': 'value79795',
    'key14215': 'value81821',
    'key5138': 'value84244',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 81,
    'name': 'Samantha Gonzales',
    'address': '24986 Valenzuela Fall Apt. 014\nEast Heatherburgh, MI 72481',
    'text': 'Scientist significant parent news. Yet talk travel sign policy serve.\nOfficer mean amount book individual arrive.',
    'email': 'sheilaadams@example.org',
    'phone_number': '(257)789-9908x26865',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Veronica Vega',
    'Traci Morgan',
    'Amanda Lopez',
    'Sheryl Dickerson',
    'Joshua Carlson',
],
    'json': {
    'name': 'John Lewis',
    'address': '10677 Cindy Walk Suite 351\nStewartstad, RI 74365',
},
    'key5008': 'value3997',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 82,
    'name': 'James Walker',
    'address': '25687 Bryan Union Suite 827\nEast Melissa, FL 15989',
    'text': 'Their shake travel nearly trip. Trouble ready success. Space executive draw author compare occur.',
    'email': 'williamswilliam@example.net',
    'phone_number': '250.554.0109',
    'array_int_dynamic': [
    19795,
],
    'array_varchar_dynamic': [
    'Dr. Barbara Smith DDS',
    'Lori Wagner',
    'Tammy Hawkins DVM',
    'Shane Maxwell',
    'Sarah Carroll',
],
    'json': {
    'name': 'Mrs. Tiffany Price',
    'address': 'USCGC Wallace\nFPO AP 71973',
},
    'key39795': 'value65283',
    'key83661': 'value42129',
    'key13700': 'value25473',
    'key16182': 'value54362',
    'key1328': 'value45493',
    'key56170': 'value90476',
    'key65237': 'value182',
    'key47780': 'value94726',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 83,
    'name': 'Janice Smith DVM',
    'address': '356 Coleman Mount Apt. 929\nCrossmouth, NM 44856',
    'text': 'Simple military individual care gas cell fast. Treatment increase study. Professor once lead continue.\nAdministration court institution if crime into address.',
    'email': 'jenniferfrederick@example.com',
    'phone_number': '309.358.3242',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Adam Mcknight',
    'John Smith',
    'Juan King',
    'Andrew Cole',
    'Kevin Mckee',
    'Martin Buchanan',
    'Brenda Brown',
    'Jill Collins',
],
    'json': {
    'name': 'Gregory Figueroa',
    'address': '8458 Oconnor Fall Suite 175\nPort Emily, MN 78823',
},
    'key29324': 'value49561',
    'key52396': 'value36178',
    'key90765': 'value9424',
    'key96594': 'value15959',
    'key59581': 'value91261',
    'key16481': 'value82983',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 84,
    'name': 'Stephanie Taylor',
    'address': '89316 Debra Island Suite 298\nLoweberg, VT 57020',
    'text': 'Minute positive attorney. Herself mind light ever none front or support.\nHard fear visit result. Fish discussion executive director let describe.',
    'email': 'sarah65@example.com',
    'phone_number': '(912)559-3230',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Mark Huff',
    'Taylor Bowman',
    'Samantha Galvan',
    'Stacey Hendrix',
    'Michelle Clark',
    'Adam Sims',
    'Emma James',
],
    'json': {
    'name': 'Cynthia Ford',
    'address': '7386 Jordan Radial\nRamseybury, FL 81444',
},
    'key6951': 'value19437',
    'key26889': 'value79539',
    'key47702': 'value38031',
    'key40324': 'value8311',
    'key58117': 'value61806',
    'key39227': 'value34506',
    'key40873': 'value81512',
    'key6257': 'value60954',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 85,
    'name': 'Daniel Duncan',
    'address': '70392 Fischer Drive Suite 253\nNorth Thomas, NV 60960',
    'text': 'Person dream level idea mission draw scene fear. Thing too painting bit structure low. Operation either mouth own.\nToward serious number measure his later. International tax close sit list consumer.',
    'email': 'darius99@example.com',
    'phone_number': '934-430-7664',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jordan Thomas',
    'Timothy Gray',
],
    'json': {
    'name': 'Debbie Wilson',
    'address': '999 Stephanie Via Suite 229\nSouth Bradleyland, KY 35834',
},
    'key6217': 'value45948',
    'key20036': 'value54345',
    'key17009': 'value13455',
    'key87719': 'value80721',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 86,
    'name': 'Laurie Walker',
    'address': '831 Anne Plaza\nEast Marcusmouth, VI 46853',
    'text': 'Medical never safe stock. Factor image listen common attention affect rich remember. Common student both anything.',
    'email': 'bbates@example.org',
    'phone_number': '374-644-1283x2698',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Lucas',
    'Stephanie Robbins',
    'Julie Ayers',
],
    'json': {
    'name': 'Craig Gonzalez',
    'address': '29838 Sean Bypass Apt. 980\nMatthewberg, WA 06769',
},
    'key66255': 'value80897',
    'key84760': 'value49310',
    'key84869': 'value17818',
    'key87481': 'value96209',
    'key20239': 'value28614',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 87,
    'name': 'Amanda Valencia',
    'address': '3157 Trevor Corners\nLindashire, PR 73085',
    'text': 'Hot paper such continue. Conference hope cut could deal.\nFive responsibility television unit product small college red. Human development improve.',
    'email': 'rosejulia@example.com',
    'phone_number': '607.351.4301x00699',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jerry Novak',
    'Rebecca Brown',
    'Mrs. Erin Forbes DDS',
    'Wesley Boyer',
    'Mr. Justin Medina',
    'Jacqueline Edwards',
    'Timothy Wheeler',
    'Danny Barr',
    'Rachel Curtis',
],
    'json': {
    'name': 'Michael Cole',
    'address': 'PSC 5795, Box 9268\nAPO AP 46385',
},
    'key63139': 'value45591',
    'key32546': 'value61749',
    'key75996': 'value50989',
    'key86062': 'value13602',
    'key26190': 'value93600',
    'key68806': 'value43796',
    'key23348': 'value58177',
    'key35057': 'value38009',
    'key31472': 'value43212',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 88,
    'name': 'Kyle Wagner',
    'address': '8125 Jesse Cliff\nWardmouth, CA 56663',
    'text': 'Agree money check price.\nEducation financial theory. Production range turn interest your.\nDoor this radio once. Treat here into hear. Huge suddenly light prevent thank assume.',
    'email': 'jocelyn07@example.net',
    'phone_number': '(988)490-4458',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Yang',
    'Scott Harris',
    'Mariah Smith',
    'Donald Garcia',
],
    'json': {
    'name': 'Craig Holland',
    'address': '978 Wright Highway Suite 589\nLopeztown, FM 67054',
},
    'key62457': 'value42728',
    'key31634': 'value25969',
    'key92856': 'value55716',
    'key52635': 'value91753',
    'key9392': 'value81146',
    'key46719': 'value60517',
    'key900': 'value6710',
    'key71793': 'value68265',
    'key79444': 'value21776',
    'key50325': 'value40062',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 89,
    'name': 'Ryan Burns',
    'address': '30065 Clark Roads Suite 246\nMelaniehaven, WI 33410',
    'text': 'Process network summer newspaper article day later. Baby discussion than occur PM.',
    'email': 'thomas13@example.net',
    'phone_number': '001-757-554-2520',
    'array_int_dynamic': [
    81904,
],
    'array_varchar_dynamic': [
    'Susan Zavala',
    'John Brown',
    'James Jordan',
    'Julie Crawford',
    'Juan Faulkner',
    'Erica Decker',
    'Kelsey Figueroa',
    'Daniel Ross',
],
    'json': {
    'name': 'Michelle Swanson',
    'address': '07992 Young Loop Suite 278\nEast Jeffrey, AZ 58110',
},
    'key8669': 'value73493',
    'key87678': 'value50810',
    'key4547': 'value53425',
    'key20737': 'value5848',
    'key97924': 'value10511',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 90,
    'name': 'Zachary Rodriguez',
    'address': '20318 Robinson Avenue Apt. 093\nEast Kevin, IA 70908',
    'text': 'Require game minute air eye above. Risk child house change generation live far action.',
    'email': 'batesdonna@example.com',
    'phone_number': '+1-277-978-4556x6743',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'James Duran',
    'Carla Oneal',
    'Barbara Bowman',
    'Caitlin Adams',
    'Alison Jackson',
    'Sue Brandt',
],
    'json': {
    'name': 'Vanessa Lawson',
    'address': '235 Chase Oval Suite 039\nPort Brian, VI 99078',
},
    'key61530': 'value51342',
    'key54750': 'value52289',
    'key27684': 'value17081',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 91,
    'name': 'Tara Long',
    'address': '959 Nicole Port\nRogersstad, MD 91083',
    'text': 'Opportunity heavy quickly relationship land beyond. Myself establish contain because. Father book evening establish.',
    'email': 'lsmith@example.org',
    'phone_number': '(601)728-2227',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jasmine Chung',
    'Tracie Ruiz',
    'Robert Willis',
    'Latoya Stephens',
],
    'json': {
    'name': 'Natalie Calhoun',
    'address': '6867 Peterson Neck Suite 113\nPierceland, WV 38230',
},
    'key35956': 'value37817',
    'key30934': 'value75689',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 92,
    'name': 'Meghan Smith',
    'address': '64175 Susan Wells Apt. 809\nKimberlyville, NE 38398',
    'text': 'Case similar already case similar myself. Step very central everybody oil ground. Spend water challenge would.\nArtist pretty suffer pull animal.',
    'email': 'david02@example.net',
    'phone_number': '001-863-863-0591',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Julia Strong',
    'Barry Edwards',
    'Mr. Timothy Gibson',
    'Ashley Avila',
    'Laura Roth',
    'Nancy Curtis',
],
    'json': {
    'name': 'William Williams',
    'address': '62398 Donna Inlet\nChrisside, OH 98366',
},
    'key8486': 'value39565',
    'key22181': 'value97387',
    'key37533': 'value84058',
    'key95405': 'value86034',
    'key36799': 'value84300',
    'key78179': 'value722',
    'key19680': 'value82706',
    'key34803': 'value20108',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 93,
    'name': 'Brittany Aguilar',
    'address': '04103 Sullivan Prairie Suite 052\nPort Jesus, AR 90432',
    'text': 'Than that statement also brother floor. Real unit machine pay win explain cause develop.',
    'email': 'kevin18@example.org',
    'phone_number': '4494310983',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Barbara Wood',
    'Daniel Frank',
    'Crystal Morales',
    'Jesse Garcia',
    'Jillian Johnson',
    'Kayla Terrell',
],
    'json': {
    'name': 'Andrew Contreras',
    'address': '90360 Nicolas Cape Apt. 435\nCameronbury, IL 28473',
},
    'key74711': 'value73728',
    'key68755': 'value13509',
    'key39603': 'value90968',
    'key96004': 'value37025',
    'key5558': 'value35327',
    'key62332': 'value9374',
    'key36679': 'value15671',
    'key63220': 'value15218',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 94,
    'name': 'Kimberly Sellers DDS',
    'address': '4534 Nelson Grove\nPort Holly, OH 26638',
    'text': 'Serve political build she sit appear accept. By main air Mrs two. Its history pattern shake present situation line.\nChurch next take air while. Nature reflect base painting traditional.',
    'email': 'murrayemily@example.org',
    'phone_number': '582.286.8905x0554',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Rachel Perkins',
    'Gabriel Hines',
    'Katie Riggs',
    'Sarah Brooks',
    'Cynthia Chavez',
    'Vickie Shah',
    'Matthew Vega',
    'Kathryn Gray',
    'Brandy Snyder',
],
    'json': {
    'name': 'Ricky Miller',
    'address': '5215 Vaughn Courts Suite 144\nRichmondborough, WA 39024',
},
    'key73379': 'value32488',
    'key19963': 'value94374',
    'key51391': 'value60592',
    'key66672': 'value10678',
    'key42033': 'value54911',
    'key13043': 'value98833',
    'key54530': 'value29052',
    'key70202': 'value55326',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 95,
    'name': 'Matthew Campbell',
    'address': '13916 Daniel Causeway\nNew Briannaport, GA 52694',
    'text': 'They current put common. Approach size simple step girl structure call.',
    'email': 'patriciacombs@example.com',
    'phone_number': '603.598.8601x2699',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Peterson',
    'Diane Werner',
    'Kyle Jennings',
],
    'json': {
    'name': 'David Rodriguez',
    'address': '1849 Miller Crest\nPort Cynthiabury, UT 71120',
},
    'key42965': 'value46902',
    'key11861': 'value35788',
    'key1582': 'value38518',
    'key25668': 'value58680',
    'key74606': 'value3637',
    'key80600': 'value80435',
    'key75363': 'value3853',
    'key25230': 'value22512',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 96,
    'name': 'Calvin Mcmillan',
    'address': '2023 Kimberly Mill\nChristopherhaven, ID 75331',
    'text': 'Describe former authority long. Eye Congress focus spring south street bed check. Decision gas minute else how middle now. Under be near fly most consider those.',
    'email': 'hartmanpaul@example.com',
    'phone_number': '7656906778',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Samuel Donovan',
    'Chad Scott',
    'Chelsey Day',
    'Sarah Stark',
    'Anthony Perez',
    'Emily Reese MD',
    'Jacqueline Long',
    'Brianna Webb',
    'Michael Owen',
    'Robert Escobar',
],
    'json': {
    'name': 'Elizabeth Wright',
    'address': '87329 Patrick Valley\nEast Paul, MS 72695',
},
    'key85571': 'value79078',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 97,
    'name': 'Jessica Price',
    'address': '19969 Sanchez Trail Apt. 823\nWesthaven, KS 79983',
    'text': 'Work ok performance see major thing. Her for identify example standard.\nUsually seven marriage quite. Resource yard by have.',
    'email': 'paige85@example.com',
    'phone_number': '3858088482',
    'array_int_dynamic': [
    22649,
],
    'array_varchar_dynamic': [
    'Michelle Smith',
    'Theresa Young',
    'Amber Wilson',
    'Pamela Marks',
    'Daniel Hamilton',
],
    'json': {
    'name': 'Jesus Sanders',
    'address': '9915 Lopez Grove Suite 525\nJonathanton, VI 13581',
},
    'key28412': 'value23576',
    'key62851': 'value23280',
    'key63531': 'value42020',
    'key9030': 'value76052',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 98,
    'name': 'Ryan Patterson',
    'address': 'PSC 5459, Box 0201\nAPO AE 85258',
    'text': 'Born debate population personal treatment suffer day. Down forward defense drug. After with sure spring quickly however.',
    'email': 'lauren11@example.org',
    'phone_number': '(621)410-1035x23824',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Matthew Mosley MD',
],
    'json': {
    'name': 'Tamara Thomas',
    'address': '10938 Horton Mountain\nJosephland, MO 71774',
},
    'key81776': 'value82530',
},
    {
    'vector': self.mutator.generate_float_array(dimension=128, normalized=True),
    'uid': 99,
    'name': 'Vicki Thompson',
    'address': '9490 Brown Valley Apt. 244\nCopelandborough, PA 83417',
    'text': 'Draw plant wonder Congress. Almost ok work cell yard single property. Possible through model receive Republican.',
    'email': 'wrightkathryn@example.com',
    'phone_number': '951-514-9663x5011',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'James Wilkerson',
    'Jose Cook',
],
    'json': {
    'name': 'Richard Ward',
    'address': '9793 Lauren Track Apt. 098\nCrossmouth, LA 62929',
},
    'key53229': 'value34199',
    'key70551': 'value20875',
    'key29010': 'value14099',
    'key14559': 'value47678',
    'key42741': 'value72614',
    'key745': 'value45615',
    'key91827': 'value82818',
    'key44763': 'value87134',
    'key85056': 'value86669',
    'key72253': 'value33023',
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
    'RequestId': 'a264ac35-62ef-11f0-a101-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_22_59_969660BfUHIyqM',
    'dimension': 128,
    'primaryField': 'url',
    'vectorField': 'vector',
    'autoID': True,
    'dbName': 'default',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-vector-url-128-100-2]_1752744181.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultVectorUrl12810021752744181Json()
    test.run_tests()
