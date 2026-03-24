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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-100-1]_1752744189_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-100-1]_1752744189.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingId3210011752744189Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-100-1]_1752744189.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-100-1]_1752744189.json"
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
    'RequestId': 'a7953d19-62ef-11f0-9502-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_08_676552gnywgoUA',
    'dimension': 32,
    'primaryField': 'id',
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
    'RequestId': 'a7b4c187-62ef-11f0-a0c3-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_08_676552gnywgoUA',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Wayne David',
    'address': '4842 Perez Avenue Apt. 913\nAguilarhaven, MN 27617',
    'text': 'Focus expect traditional. Pattern treat drug. Main recently cultural operation. Lead clear shoulder nor business put service table.',
    'email': 'katherine43@example.com',
    'phone_number': '001-472-508-7841x60445',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Nancy Pacheco',
    'Jeremy Rice',
    'Kaitlyn York MD',
    'Ryan Johnson',
],
    'json': {
    'name': 'Jennifer Bush',
    'address': 'USCGC Martinez\nFPO AE 35669',
},
    'key98359': 'value35884',
    'key542': 'value51202',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Edward Wheeler',
    'address': '566 Hall Way Apt. 544\nJenniferview, PW 64666',
    'text': 'Short single knowledge upon travel trade. Politics wear administration scene bring prepare specific. Animal save environment firm.\nDrug try value military law. Step citizen tend single artist.',
    'email': 'zhenry@example.org',
    'phone_number': '408-488-8346x7343',
    'array_int_dynamic': [
    80537,
],
    'array_varchar_dynamic': [
    'Lauren Murphy',
    'Ryan Shah',
    'Kelsey Green',
    'John Alexander',
    'Victoria Cisneros',
    'Joseph Wilson',
    'Stephanie Vasquez',
    'Nichole Tapia',
],
    'json': {
    'name': 'Susan Phillips',
    'address': '373 Hudson Rue Suite 108\nNguyenfort, GU 01453',
},
    'key92498': 'value23366',
    'key1225': 'value5662',
    'key1312': 'value5589',
    'key68433': 'value80609',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Andrea Warner',
    'address': '4735 Watson Key\nDixontown, PW 71619',
    'text': 'Church science eight bring. Garden in against kitchen training research nice.\nDegree writer door tax plan meet. Happen foot could might. Hospital get notice hit you.',
    'email': 'rebecca23@example.com',
    'phone_number': '001-872-634-4080x866',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Thompson',
    'Rodney Morales',
    'Alicia Jones',
    'Sandra Martinez',
    'Peggy Cole',
    'Kyle Lewis',
    'Julia Thompson',
],
    'json': {
    'name': 'Sheryl White',
    'address': '61605 Jackson Flat\nPort Debra, MD 20790',
},
    'key85255': 'value59045',
    'key25240': 'value77713',
    'key23029': 'value76152',
    'key79657': 'value57984',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Darren Wilson',
    'address': '59519 Nicholas Greens\nPort Anitafurt, MP 97884',
    'text': 'Tax house well natural short leader threat. More agency war card.\nRepresent unit message over capital economy art game. When contain claim control. Candidate whose fish western partner whatever.',
    'email': 'laurendavis@example.com',
    'phone_number': '457-290-0745x2428',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kevin Bass',
    'Michael Townsend',
    'Ashley Cole',
    'Austin Smith',
    'Yvonne Rodriguez',
    'Chad Ward',
    'Raymond Martin',
],
    'json': {
    'name': 'Charles Prince',
    'address': '162 Drew Curve\nNorth Seanhaven, MI 31727',
},
    'key185': 'value4071',
    'key63220': 'value5632',
    'key48487': 'value3880',
    'key80913': 'value98157',
    'key53918': 'value315',
    'key88153': 'value28675',
    'key64735': 'value38743',
    'key6341': 'value83760',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Dr. Christopher Davis',
    'address': '78904 Steven Port Suite 452\nWest Stephanie, CA 48337',
    'text': 'Social year rise. Best stuff can choice building doctor can. Door hotel including give option local call.\nAt nice marriage blood president. To send world enjoy easy. Magazine even three everything.',
    'email': 'william21@example.com',
    'phone_number': '(260)313-0864x891',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jonathon Olsen',
    'Kim Mayer',
    'Frank Garner',
    'Henry Coffey',
    'Timothy Hansen',
    'Elizabeth Hensley',
],
    'json': {
    'name': 'Tiffany Mendez',
    'address': '29417 Colin Roads Suite 467\nWilliamston, FM 31803',
},
    'key1404': 'value9125',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Mrs. Kathleen Valenzuela',
    'address': '09376 Daniel Throughway Apt. 102\nNorth Justinfurt, CO 87372',
    'text': 'Share trip every benefit.\nTake game throw official find account dream. Political try wish whole area pattern price police.\nCall against letter perhaps. According gun face these hear.',
    'email': 'ocampbell@example.net',
    'phone_number': '722.337.1046',
    'array_int_dynamic': [
    84401,
],
    'array_varchar_dynamic': [
    'Megan Mosley',
    'Susan Clark',
    'Katherine Gonzalez',
    'Sarah Hood MD',
    'Stephanie Clements',
    'Shannon Holden',
    'Cynthia Ferguson',
    'Richard Garrett',
    'Hannah Woods',
    'Kristin Miller',
],
    'json': {
    'name': 'Brian Smith',
    'address': '39710 Martinez Fall\nLake Sean, PA 31913',
},
    'key26695': 'value26356',
    'key97656': 'value84938',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Susan Bird',
    'address': '7015 Christopher Club\nPort Anthony, MO 27128',
    'text': 'Story enough myself administration see response course. Draw edge their allow hospital training new coach. Cup upon high exactly talk.\nPerhaps miss dinner gun among. Five seem nature child marriage.',
    'email': 'christian12@example.com',
    'phone_number': '+1-961-556-6594x40121',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Bruce Andrews',
    'Michelle Santiago',
],
    'json': {
    'name': 'Cody Kelley',
    'address': '597 Anthony Glens Suite 059\nPort Jonathan, TX 23601',
},
    'key50341': 'value1530',
    'key71656': 'value35621',
    'key92966': 'value9631',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'William Ortiz',
    'address': '41629 Jasmine Stravenue\nEast Elizabeth, IN 51726',
    'text': 'Wear first direction drive rate want position. Next tell week.\nCentury management sense card realize foot body. Word city those bit father drive.',
    'email': 'nunezrebecca@example.org',
    'phone_number': '(510)471-6792x196',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Jake Chavez',
    'Elizabeth Watson',
    'Duane Reeves',
    'Theresa Evans',
    'Heather Hutchinson',
    'Taylor Hoover',
    'Gwendolyn Ellis',
    'Christine Lawson',
    'John Johnson',
    'Justin Bowman',
],
    'json': {
    'name': 'Benjamin Bullock',
    'address': '865 Preston Ranch Suite 968\nLoweryhaven, PA 99814',
},
    'key70754': 'value17958',
    'key40364': 'value87032',
    'key29704': 'value51792',
    'key1672': 'value98891',
    'key94700': 'value73900',
    'key98806': 'value27510',
    'key34241': 'value34926',
    'key14783': 'value10894',
    'key50606': 'value72274',
    'key69295': 'value11062',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Devin Cook',
    'address': '7707 Peter Cape\nWest Joseph, NE 84402',
    'text': 'Real now policy very ago stuff activity. Social state two strong radio realize analysis.\nSong of writer parent. Body join challenge spring.',
    'email': 'andrea39@example.net',
    'phone_number': '504-738-3517x87017',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Aaron Green',
    'Paul Morris',
    'Stacey Todd',
    'Kenneth Olson',
    'Katelyn Black',
    'Gabriel Holmes',
    'Lucas Gutierrez',
    'Christina Mason',
    'Andrew Anderson',
],
    'json': {
    'name': 'Anna Young',
    'address': '825 Costa Run Suite 094\nCervantestown, MD 13382',
},
    'key45642': 'value5531',
    'key14491': 'value71029',
    'key64325': 'value35547',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'James Marks',
    'address': '049 Michelle Island\nSouth Donna, TX 25897',
    'text': 'Section leader point summer important before street. Girl audience central heavy little example. Watch manage share whose science.\nCondition American sense. Another civil figure note reach policy.',
    'email': 'barry27@example.org',
    'phone_number': '939.312.0900',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Moreno',
    'Kelly Lynch',
    'Morgan Chase',
],
    'json': {
    'name': 'Marcus Jordan',
    'address': '14486 Peterson Causeway Suite 512\nCharlesview, VA 95447',
},
    'key1715': 'value74639',
    'key81799': 'value82315',
    'key92413': 'value12873',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 10,
    'name': 'Donald Murray',
    'address': '241 Mooney Bridge Apt. 277\nMooremouth, TN 74000',
    'text': 'Along situation Democrat born peace difference rate. Receive few person. Put wait son long society seem. Until history bank size.',
    'email': 'john85@example.com',
    'phone_number': '(561)771-4429x0093',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Shannon Sanford',
    'Victor Davidson',
    'James Glenn',
    'Sharon Foster',
    'Jennifer James',
    'Michelle Larson',
    'April Barnes',
    'Jill Glover',
],
    'json': {
    'name': 'Dwayne Wong',
    'address': '6368 Flores Radial Suite 173\nJohnville, NE 34933',
},
    'key89176': 'value97311',
    'key60591': 'value29078',
    'key40186': 'value75305',
    'key85242': 'value18632',
    'key15411': 'value59308',
    'key3960': 'value46659',
    'key5910': 'value46131',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 11,
    'name': 'Jason Carter',
    'address': '990 Turner Village\nNew Michaelhaven, FL 58880',
    'text': 'Then decide production world opportunity attention try relationship. Attack discover three and major leader daughter.\nFloor part benefit line. Set many sometimes truth.',
    'email': 'fvargas@example.net',
    'phone_number': '(432)686-9425x42304',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jerry Carney',
    'Jessica Owens',
    'Troy Butler',
    'Mitchell Brown',
    'Tiffany Roberson',
    'Troy Erickson',
    'Nicolas Lewis',
    'Cesar Lopez',
    'Robin Kelly',
    'Timothy Perez',
],
    'json': {
    'name': 'Jessica Mills',
    'address': '437 Austin Spring Suite 627\nWest Jonathonborough, HI 94004',
},
    'key77960': 'value2150',
    'key86698': 'value53256',
    'key8804': 'value62188',
    'key92487': 'value33819',
    'key91329': 'value10115',
    'key79628': 'value63916',
    'key14806': 'value25506',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 12,
    'name': 'Rebecca Duncan',
    'address': '2481 Amanda Wall\nLake Patrickville, NY 47128',
    'text': 'Bar according activity general any game. Training painting short age brother voice. Professional to agency.\nSince at coach week one police. Society send toward rule easy ago fish.',
    'email': 'uwilson@example.net',
    'phone_number': '2819037945',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jason Price',
    'Kristina Ferguson',
    'Matthew Howard',
    'Charles Grant',
    'Lisa Brown',
    'Patricia Lara',
    'Anthony Wiley',
    'Kelly Mason',
    'Elizabeth Bailey',
    'Scott Morgan',
],
    'json': {
    'name': 'Eddie Hall',
    'address': '220 Melissa Inlet\nEast Mary, TN 47037',
},
    'key75994': 'value23329',
    'key96044': 'value14821',
    'key70394': 'value26093',
    'key9134': 'value74943',
    'key62477': 'value31687',
    'key15314': 'value9482',
    'key5380': 'value54955',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 13,
    'name': 'Christian Wise',
    'address': 'PSC 4624, Box 8126\nAPO AA 59580',
    'text': 'Sport sense instead four happen clear owner personal. Computer talk country let information maybe star cause.',
    'email': 'shelley25@example.net',
    'phone_number': '+1-479-579-5043x65791',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Bowman',
    'Jeremy Carpenter',
    'Alyssa Newman',
    'Miss Cheryl Collins',
    'Hannah Lee',
    'Tammy Donovan',
    'Joshua Sanchez',
    'Elizabeth Sims',
    'Dylan Garcia',
    'Stephanie Morales',
],
    'json': {
    'name': 'Robert Cisneros',
    'address': '5695 Hernandez Avenue Apt. 211\nNorth George, CO 49433',
},
    'key56529': 'value44509',
    'key10758': 'value50299',
    'key17002': 'value85359',
    'key32704': 'value84378',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 14,
    'name': 'Emily Ramirez',
    'address': '037 Alicia Island Suite 174\nNorth Terrybury, NE 74261',
    'text': 'Table why red sister author seven certainly value. Federal serious record large.\nServe safe management rest quality open inside finish. Result traditional tell but green. Foot create deep join.',
    'email': 'frazierdawn@example.org',
    'phone_number': '+1-800-572-7462',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Matthew Ramos',
    'Jean Johnson',
],
    'json': {
    'name': 'Brandy Guerrero',
    'address': '027 Ellison Row Apt. 866\nAaronville, VA 48315',
},
    'key13005': 'value46844',
    'key67424': 'value83265',
    'key55535': 'value90152',
    'key54650': 'value33804',
    'key49646': 'value86019',
    'key76924': 'value58744',
    'key88280': 'value60948',
    'key89669': 'value17817',
    'key14881': 'value25294',
    'key36010': 'value61412',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 15,
    'name': 'Jared Johnson',
    'address': '00579 Natalie Stream Suite 339\nMacdonaldstad, KY 53924',
    'text': 'Whom subject all rate head position race. Past ok father thought tell.\nMoney available pretty. Themselves contain attorney care practice late condition.',
    'email': 'matthew53@example.net',
    'phone_number': '7389501350',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Dale Peterson',
    'Amanda Lewis',
    'Robert Lopez',
    'Amanda Thompson',
    'Tammy Goodwin',
],
    'json': {
    'name': 'Erin Huang',
    'address': '35129 Moreno Mountain\nMosleyburgh, ID 85247',
},
    'key7536': 'value53372',
    'key99910': 'value62577',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 16,
    'name': 'Charles Kramer MD',
    'address': '78839 Williams Squares\nRogerfurt, DE 60124',
    'text': 'Ten door pretty night bed anything save level. Guy authority number must return.\nWell magazine watch according. Rate need those size federal spend.',
    'email': 'smithnina@example.com',
    'phone_number': '+1-676-547-6136x4390',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Kerry King',
],
    'json': {
    'name': 'Brittany Huang',
    'address': '438 Alyssa Springs\nSouth Shawnport, MP 17935',
},
    'key26785': 'value42531',
    'key68830': 'value18484',
    'key46347': 'value53',
    'key32672': 'value83754',
    'key19091': 'value14843',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 17,
    'name': 'Mrs. Jessica Barton MD',
    'address': '3411 Coffey Roads\nAntonioville, NV 13565',
    'text': 'Series hour check house you ability. General financial along respond get read. Born parent half identify owner help special. Risk lawyer sing board street involve meeting democratic.',
    'email': 'pgray@example.com',
    'phone_number': '673-840-8382',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Charles Smith',
    'Jonathan Carpenter',
    'John Brown',
    'Jessica Ward',
],
    'json': {
    'name': 'Mr. Bobby Grant',
    'address': '97509 Benjamin Villages Suite 737\nPort Kathrynview, WV 82629',
},
    'key36978': 'value42473',
    'key63043': 'value12210',
    'key22750': 'value24136',
    'key3097': 'value92868',
    'key76268': 'value58011',
    'key41424': 'value7812',
    'key23291': 'value4121',
    'key71641': 'value50953',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 18,
    'name': 'Matthew Torres',
    'address': '87818 Andersen Ville\nLake James, AK 86239',
    'text': 'Mind together forget production lay. Movie trial surface.\nGrowth western take picture word. Challenge capital across resource front. Think something bank science or letter huge.',
    'email': 'travis77@example.net',
    'phone_number': '001-426-564-9486',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Kristen Page',
    'Richard Jones',
    'Bradley Hicks',
    'Tammy Walker',
    'John Douglas',
],
    'json': {
    'name': 'Natalie Smith',
    'address': '1309 Robert Park\nRichardsonport, OK 27752',
},
    'key37332': 'value3609',
    'key82959': 'value56315',
    'key54323': 'value30715',
    'key41505': 'value97215',
    'key79369': 'value43658',
    'key28100': 'value74223',
    'key84688': 'value25615',
    'key4492': 'value20714',
    'key54334': 'value21991',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 19,
    'name': 'Robert Goodwin',
    'address': '753 Payne Bridge\nKyleborough, OH 79569',
    'text': 'Late pay sort upon involve shoulder one. National simple beyond threat area fact.\nDeal run old keep travel time drug. Marriage color that quite often because. Here later parent American fact federal.',
    'email': 'ozimmerman@example.net',
    'phone_number': '001-495-602-1404x58703',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Gerald Collins',
    'Stephen Potter',
    'Vanessa Turner',
    'Michael Holland',
    'Deborah Winters',
    'Angela Morris',
    'Jeffrey Avila',
    'Lawrence Smith',
    'Lisa James',
    'Amy Ryan',
],
    'json': {
    'name': 'Christopher West',
    'address': '66249 Maldonado Squares Suite 725\nLake Catherine, CT 62561',
},
    'key31543': 'value56245',
    'key10188': 'value23165',
    'key27322': 'value85111',
    'key66067': 'value1864',
    'key97157': 'value41190',
    'key21948': 'value17428',
    'key86071': 'value10608',
    'key69005': 'value19575',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 20,
    'name': 'Kimberly Smith',
    'address': '32281 Davis Ramp\nPort Michaelmouth, KS 41817',
    'text': 'Wife order dinner help. Table sense reach leg mean call trade.\nMagazine five billion environment consumer second. Practice and have ten military quickly.',
    'email': 'pwilson@example.net',
    'phone_number': '900.383.6626x2508',
    'array_int_dynamic': [
    50399,
],
    'array_varchar_dynamic': [
    'Caroline Sims',
    'Katherine Castillo',
    'Natasha Allen',
    'Christopher Bailey',
    'Robert Obrien',
    'Dr. Yolanda Washington',
],
    'json': {
    'name': 'David Conley',
    'address': '073 Ramsey Meadow Suite 583\nTamiburgh, VT 45709',
},
    'key71493': 'value2735',
    'key28138': 'value22414',
    'key4449': 'value40029',
    'key27951': 'value77609',
    'key77644': 'value11843',
    'key71492': 'value41799',
    'key2616': 'value7944',
    'key82924': 'value51350',
    'key71916': 'value22927',
    'key45920': 'value27843',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 21,
    'name': 'Angel Morrison',
    'address': '07398 Bentley Trail Suite 316\nReynoldston, SC 60429',
    'text': 'Realize moment scene beat. News wear three article success sound plan. Wait either behind that start green. Design thank fly.',
    'email': 'chelseaknight@example.com',
    'phone_number': '001-403-725-1573',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Ashley White',
    'Cheryl Flores',
    'Donald Hunt',
    'Olivia Smith',
    'Maria Johnson',
    'Brian Elliott',
    'Derek Olson',
],
    'json': {
    'name': 'Gerald Cain',
    'address': '934 Todd Ville Apt. 264\nSouth Shane, HI 46315',
},
    'key73660': 'value88694',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 22,
    'name': 'Christopher Obrien',
    'address': 'PSC 1427, Box 2221\nAPO AP 36159',
    'text': 'Expect itself week down support. Adult when though behind relationship sit.',
    'email': 'valerie71@example.org',
    'phone_number': '6319320912',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Heather Allen',
    'Jason Wood',
    'Aaron Coleman',
],
    'json': {
    'name': 'Natalie Bennett',
    'address': '7461 Powell Mount Apt. 214\nEast Mathew, TN 89738',
},
    'key74752': 'value19965',
    'key35675': 'value13929',
    'key80597': 'value1804',
    'key20787': 'value67618',
    'key19905': 'value4240',
    'key55826': 'value54943',
    'key98207': 'value64920',
    'key8954': 'value52474',
    'key30120': 'value68008',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 23,
    'name': 'Mr. Jeffrey Ward',
    'address': '4772 Wilson Street\nDavidstad, VI 57236',
    'text': 'Ever growth carry more simply arrive. Future determine with human nation play. Should various day.\nWoman happen hard chance operation only know. Professor through myself over network young arrive.',
    'email': 'nathanielcarroll@example.org',
    'phone_number': '+1-701-387-1783x3240',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Stephen Terry',
    'Michael Reese',
    'Elizabeth Blanchard',
    'Sheila Simmons',
],
    'json': {
    'name': 'Dave Moore',
    'address': '28705 David Plain\nKingview, SD 62958',
},
    'key37542': 'value25900',
    'key42624': 'value33791',
    'key42637': 'value33140',
    'key35909': 'value35037',
    'key92894': 'value29610',
    'key71832': 'value95313',
    'key7959': 'value2410',
    'key77707': 'value12824',
    'key33113': 'value91044',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 24,
    'name': 'Veronica Frazier',
    'address': '15033 Hernandez Avenue Suite 326\nButlerstad, AZ 10870',
    'text': 'Image eat partner ago threat water smile. Fine maybe decade fish personal item. Thousand fact social level.',
    'email': 'bennettdeanna@example.net',
    'phone_number': '001-861-551-6528',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Stuart Pope',
    'Andrew Osborn',
    'Devin Barrett',
    'Jesse Thomas',
    'Brandon Simmons Jr.',
],
    'json': {
    'name': 'Stephanie Howe',
    'address': 'Unit 1167 Box 0931\nDPO AP 55409',
},
    'key34078': 'value3599',
    'key22766': 'value33504',
    'key43853': 'value6854',
    'key39153': 'value68010',
    'key33564': 'value1740',
    'key6365': 'value44443',
    'key23805': 'value20372',
    'key48881': 'value20916',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 25,
    'name': 'Austin Turner',
    'address': '757 Mary Run Suite 779\nHarrisstad, WA 50403',
    'text': 'Use size least. Serious create water indeed enjoy religious in. She goal author when court.',
    'email': 'qsullivan@example.com',
    'phone_number': '504.843.4295x923',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Hart',
    'Mark Mullins',
    'Nicole Le',
    'Robin Ochoa',
    'Craig Shepherd',
    'David Cole',
],
    'json': {
    'name': 'George Rodriguez',
    'address': '189 Crane Run\nMarilynberg, SC 19893',
},
    'key34477': 'value19344',
    'key70790': 'value57446',
    'key63582': 'value80267',
    'key53942': 'value96003',
    'key24986': 'value3326',
    'key96016': 'value6051',
    'key68034': 'value17699',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 26,
    'name': 'Ms. Kelly Martin',
    'address': '3669 Mallory Meadow Suite 935\nEast Angela, MO 34726',
    'text': 'Degree bank book. Message resource behind per.\nCultural administration usually human organization remember girl still. Level board major able. Keep player day now that.',
    'email': 'leehailey@example.com',
    'phone_number': '4432111650',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Smith',
    'Tami Parker',
    'Stacy Gould',
    'Maria Roth',
    'Veronica Thomas',
],
    'json': {
    'name': 'Lori Edwards',
    'address': '7358 Gabriella Ports Suite 736\nAliciashire, PW 39308',
},
    'key82610': 'value29472',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 27,
    'name': 'Matthew Reyes',
    'address': '4190 Robert Road Apt. 604\nEvansland, WY 47775',
    'text': 'Personal hot song office. Practice safe billion really. Both many back identify.',
    'email': 'khopkins@example.org',
    'phone_number': '001-305-241-0129x04590',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Gordon',
    'Kimberly Brooks',
    'Cole Berry',
],
    'json': {
    'name': 'Breanna Perkins',
    'address': '775 Marcus Road\nEast Cindyberg, LA 48655',
},
    'key83585': 'value80103',
    'key51291': 'value57743',
    'key94320': 'value2929',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 28,
    'name': 'John Douglas',
    'address': 'Unit 7784 Box 8879\nDPO AP 89417',
    'text': 'Growth see throw difficult choice foot spring. Some adult participant simple attack.\nRespond up seven line believe first put.',
    'email': 'christophermoore@example.org',
    'phone_number': '260-513-2623x59217',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Teresa Schneider',
    'Kara Collins',
    'Christine Nelson',
    'Mr. Patrick Meyers DVM',
    'Elizabeth Patton',
    'James Simmons',
    'Misty Thompson',
    'Linda Roberts',
    'Janice Shepherd',
],
    'json': {
    'name': 'Theresa Brown',
    'address': '9106 Gilmore Point\nTiffanyport, NE 20228',
},
    'key268': 'value9274',
    'key81326': 'value56338',
    'key16612': 'value18160',
    'key71765': 'value12004',
    'key54982': 'value8453',
    'key58754': 'value77079',
    'key42715': 'value96927',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 29,
    'name': 'Jacob Gomez',
    'address': '918 Hernandez Oval\nJonesland, OK 35479',
    'text': 'Structure situation share consider sign model. Television artist article boy in mission. Figure seek exactly few must movie.',
    'email': 'hallen@example.net',
    'phone_number': '967.963.0130x535',
    'array_int_dynamic': [
    43894,
],
    'array_varchar_dynamic': [
    'Sheri Hopkins',
    'Troy Moore',
    'Amanda Jenkins',
    'Courtney Tyler',
],
    'json': {
    'name': 'Arthur Aguilar',
    'address': '3354 David Forges Apt. 569\nPort Sean, UT 71792',
},
    'key4614': 'value25090',
    'key28122': 'value73625',
    'key60457': 'value59018',
    'key75746': 'value43907',
    'key49016': 'value80872',
    'key31084': 'value96532',
    'key43721': 'value29789',
    'key60169': 'value67427',
    'key9253': 'value28755',
    'key66728': 'value50577',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 30,
    'name': 'Donald Aguirre',
    'address': 'USS Harris\nFPO AA 41781',
    'text': 'Inside role organization add experience yeah always. Natural report this determine follow rich oil factor. Near base happen protect another relate ok. Bank black three.',
    'email': 'melendezkatelyn@example.org',
    'phone_number': '(276)936-5117x889',
    'array_int_dynamic': [
    12876,
],
    'array_varchar_dynamic': [
    'Todd Miller',
    'Taylor Jones',
    'Lee Smith',
    'Michelle Gallegos',
],
    'json': {
    'name': 'Aaron Keller',
    'address': '958 Joshua Station\nCherylview, PA 03838',
},
    'key48066': 'value53850',
    'key92080': 'value90418',
    'key89742': 'value19323',
    'key60524': 'value49161',
    'key16156': 'value29164',
    'key77457': 'value5783',
    'key97684': 'value31825',
    'key82915': 'value75861',
    'key10443': 'value86766',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 31,
    'name': 'Danny Allison',
    'address': '4431 Dana Drives\nWest Lisaberg, DE 52472',
    'text': 'South assume consumer dog animal gas policy year. Technology quality least lead. Run dinner contain pretty.\nStop enter reflect forward simple protect. Thing impact short travel.',
    'email': 'rhayden@example.com',
    'phone_number': '001-846-283-7372',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Peter Wells',
    'Hunter Fischer',
    'Andrew Myers',
    'Casey Pratt',
    'Craig Riley',
    'Scott Sparks',
    'Elizabeth Palmer',
],
    'json': {
    'name': 'Dr. Erica Mcguire',
    'address': '1599 Bell Mill Suite 288\nVazquezberg, AK 96252',
},
    'key85619': 'value91269',
    'key70411': 'value76395',
    'key54366': 'value82189',
    'key56322': 'value40555',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 32,
    'name': 'Mark Wilson',
    'address': '941 Robert Roads\nCisnerosview, DE 23905',
    'text': 'Seek too area performance history fear.\nThat oil with. Stuff gun can agree.\nNote lose use law culture area. Yard second good open.',
    'email': 'qhampton@example.com',
    'phone_number': '255-604-0922x5267',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Nicole Sloan',
    'Barry Sellers',
    'Kyle Gardner',
    'Daniel Stephens',
    'Amanda Esparza',
    'Andrew Mcbride',
    'Donna Miller',
    'Melanie Smith',
    'Monica Gordon',
],
    'json': {
    'name': 'Michael May',
    'address': '4820 Turner Islands\nEast Jesseton, CA 62873',
},
    'key17583': 'value9480',
    'key71578': 'value37535',
    'key57491': 'value97495',
    'key55743': 'value10127',
    'key79129': 'value43894',
    'key16585': 'value22290',
    'key35924': 'value72294',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 33,
    'name': 'Jessica Andersen',
    'address': '5173 Clark Square\nHamptonside, TN 83351',
    'text': 'Sport nothing plant two program.\nGoal popular claim meet public involve. Method force cost certain store machine stand clear. Want loss pass study family after.',
    'email': 'savannahreyes@example.com',
    'phone_number': '(256)643-7310',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Manuel Brown',
    'George Lang',
    'Alan Irwin',
    'Richard Sosa',
    'William Padilla',
    'Kelly Jones',
    'Kenneth Wright',
    'Alexis Alvarado',
],
    'json': {
    'name': 'Jennifer Frye',
    'address': 'Unit 8150 Box 2288\nDPO AE 62719',
},
    'key5093': 'value33627',
    'key59568': 'value48132',
    'key42729': 'value27029',
    'key85637': 'value89653',
    'key2368': 'value95684',
    'key70399': 'value29426',
    'key47986': 'value7838',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 34,
    'name': 'Christine Griffin',
    'address': '7446 Duffy Dale\nElizabethville, IN 44843',
    'text': 'Technology pay loss unit throw least. Buy with onto these evidence where. Carry together collection budget.',
    'email': 'jeremybrewer@example.com',
    'phone_number': '214-215-8143x26847',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Johnny Gill',
    'Jonathan Gross',
    'April Richmond',
    'Timothy Johnson',
    'Cassandra Berg',
    'Amber Ibarra',
    'Stephanie Taylor',
    'Chris Grant',
    'Jordan Quinn',
],
    'json': {
    'name': 'Danielle Jackson',
    'address': '076 Rebecca Crossroad\nWadehaven, MT 56895',
},
    'key64074': 'value89025',
    'key60049': 'value15153',
    'key49448': 'value22481',
    'key23450': 'value50485',
    'key4903': 'value21873',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 35,
    'name': 'Kevin Bauer',
    'address': '8547 Higgins Plain\nEast Alexis, AZ 45108',
    'text': 'Sing environmental wife behavior.\nFish themselves be there skill agent lose.\nAgreement learn significant art too meet speak. Necessary difference many four.',
    'email': 'sanchezcory@example.net',
    'phone_number': '368-235-5984',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Miranda Rivera',
    'Donna Gibson',
],
    'json': {
    'name': 'Christopher Owens',
    'address': '28642 Sean Lane\nDavischester, TN 31854',
},
    'key3900': 'value46934',
    'key44182': 'value42738',
    'key20212': 'value40004',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 36,
    'name': 'Juan Chang',
    'address': 'USS Black\nFPO AP 63821',
    'text': 'With which statement front class. Economy expect customer edge protect something day. College pattern worry fund company with just run.',
    'email': 'yarnold@example.com',
    'phone_number': '793-629-9281',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Tamara Watkins',
    'Nicholas Johnson',
    'Kevin Johnson',
    'Larry Rose',
    'James Huynh',
],
    'json': {
    'name': 'James Salinas',
    'address': '485 Katie Garden\nSouth Ryan, IN 51140',
},
    'key42547': 'value89697',
    'key82642': 'value76397',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 37,
    'name': 'Bethany Alvarez',
    'address': '96762 Ferguson Junction Suite 589\nNew Lindsay, LA 70001',
    'text': 'Action may region high. Door build Mrs most.\nLarge realize whole. Beat some arrive foreign news though reason. Everybody own goal effort ahead.',
    'email': 'mark84@example.net',
    'phone_number': '+1-733-881-7954x263',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Crystal Hamilton',
    'James Thomas',
    'James Lopez',
    'Sabrina Blevins',
    'Ryan Patton',
    'Erin Bender',
    'David Williams',
    'Kaitlyn Smith',
    'Alicia Copeland',
],
    'json': {
    'name': 'Vincent Rivera',
    'address': 'USS Spence\nFPO AA 62336',
},
    'key87403': 'value83878',
    'key50696': 'value26579',
    'key78782': 'value64106',
    'key65362': 'value86116',
    'key94901': 'value89740',
    'key83721': 'value16184',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 38,
    'name': 'Karen Daniel',
    'address': '1526 Roach Walk\nEast Davidmouth, NY 78535',
    'text': 'Stage own tough seem wall occur conference. Natural themselves game table.\nPlan system tough Republican face serve notice dark.',
    'email': 'michael12@example.org',
    'phone_number': '3235129929',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Holly Cohen',
    'Lisa Crane',
    'Brian Young',
    'Carol Ward',
    'Daniel Berger',
    'Kimberly King',
    'Matthew Martin',
    'Christopher Saunders',
],
    'json': {
    'name': 'Michael Luna',
    'address': '41442 Vickie Valley Apt. 268\nPort Karentown, RI 59046',
},
    'key69281': 'value9947',
    'key99515': 'value60231',
    'key95729': 'value1460',
    'key29929': 'value71724',
    'key80630': 'value46120',
    'key25457': 'value26504',
    'key30116': 'value61084',
    'key46882': 'value48108',
    'key57636': 'value81574',
    'key36580': 'value78184',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 39,
    'name': 'Mary Bishop',
    'address': '15625 Emily Shores\nLake Lisatown, FM 99785',
    'text': 'Race face down. Democratic own go artist movie coach. Kind into need sort from set.\nDifference front test although goal dark ago. During amount type it.\nRoad television above street action.',
    'email': 'eherrera@example.org',
    'phone_number': '001-284-935-2316',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Chase',
    'Raven Wilson',
    'Kyle Patterson',
    'Justin Adams',
    'Bridget Hubbard',
    'Sydney Arias MD',
    'Terry Stevenson',
    'Joseph Shepherd',
    'William Rice',
    'Jennifer Jackson',
],
    'json': {
    'name': 'Erika Mccall',
    'address': '087 Robinson Crescent\nWest James, DE 02230',
},
    'key29710': 'value23007',
    'key79432': 'value68164',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 40,
    'name': 'Diane Campbell',
    'address': '01758 William Ridge\nNorth Nicholaston, PA 26685',
    'text': 'Stage section beyond area so factor. Drug weight everything miss season reflect. Activity production catch debate economy.',
    'email': 'michael57@example.com',
    'phone_number': '335.921.2164x3639',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Kelly Brewer',
    'Sara Schneider',
    'Barbara Mosley',
],
    'json': {
    'name': 'Elijah Christensen',
    'address': '415 Robert Fords Suite 507\nWest James, VI 02424',
},
    'key95045': 'value95518',
    'key68956': 'value73796',
    'key93269': 'value26741',
    'key79854': 'value31988',
    'key72826': 'value96792',
    'key83169': 'value61363',
    'key77731': 'value30654',
    'key88156': 'value5797',
    'key23470': 'value61154',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 41,
    'name': 'Stephanie Decker',
    'address': '55129 Young Falls\nKathrynhaven, ND 21920',
    'text': 'Travel animal either head former sport. Easy provide own.\nScientist region improve participant generation author. Popular world painting her form. Foot degree adult war strategy TV table force.',
    'email': 'patricia40@example.com',
    'phone_number': '220-699-3201x31978',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Alexander Warren MD',
    'Stephanie Rice',
    'Carol Wilson',
],
    'json': {
    'name': 'Jamie Trevino',
    'address': '9926 Miles Unions\nGardnermouth, RI 35990',
},
    'key15508': 'value98848',
    'key34930': 'value69785',
    'key59112': 'value93841',
    'key17086': 'value22315',
    'key7982': 'value85401',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 42,
    'name': 'Brian Smith',
    'address': '3745 Moore Corners\nSwansonland, CA 91515',
    'text': 'Wife test somebody summer authority decide possible. Peace office surface south daughter area realize.\nSocial listen of meeting something ago enjoy. According person family image recognize education.',
    'email': 'ialvarado@example.com',
    'phone_number': '(750)210-4541x99059',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Debbie Cole',
    'Kelly Bradford',
    'Nicholas Garcia',
    'Jared Powers',
    'Juan Bruce',
    'Carl Hansen',
    'Matthew Johnson',
    'Matthew Mercado',
    'Dr. Rebecca Mitchell',
    'Christopher Mcpherson',
],
    'json': {
    'name': 'Grace Smith',
    'address': '606 Torres Brook\nSteventown, WA 28972',
},
    'key93727': 'value84293',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 43,
    'name': 'Jenna Curry',
    'address': '1737 Jordan Vista\nLake Amy, MN 84502',
    'text': 'Nor serve they another study soldier show night. Adult by such else sea shake close pull.',
    'email': 'bobby70@example.com',
    'phone_number': '001-911-313-0358',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Patricia Kramer',
    'Robert Hall',
    'Gerald Harrison',
    'Laura Cantu',
    'William Adams',
],
    'json': {
    'name': 'Brendan Golden',
    'address': '87843 Kyle Spring Suite 096\nJohnshire, MO 59508',
},
    'key30713': 'value24925',
    'key33415': 'value63812',
    'key20354': 'value67277',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 44,
    'name': 'Nicholas Perkins',
    'address': '38261 Jack Knoll\nNorth Christinamouth, AR 52096',
    'text': 'Stand buy fine consider stop plant. Big rich agreement student. Within rock respond push against once.',
    'email': 'mcbridematthew@example.com',
    'phone_number': '965-443-6187x91229',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Erika Brown',
    'Monica Anderson',
    'Ronald Stevenson',
    'David Chavez',
    'Julie Woodard',
    'Jamie Orr',
],
    'json': {
    'name': 'Katherine James',
    'address': '80260 Sean Greens\nSouth Christian, NC 56060',
},
    'key93754': 'value71797',
    'key39439': 'value74466',
    'key26811': 'value13781',
    'key30850': 'value87386',
    'key50907': 'value94988',
    'key56711': 'value93995',
    'key79153': 'value1575',
    'key22030': 'value94386',
    'key86768': 'value41760',
    'key12072': 'value96993',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 45,
    'name': 'William Delgado',
    'address': '888 Willis Trail\nEast Lauren, NE 12970',
    'text': 'Nor lead fire check husband call trade. Behind question enter us. Focus theory often past believe yard technology.',
    'email': 'hansonchristopher@example.org',
    'phone_number': '+1-760-980-4189x4612',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Kayla Webster',
    'Autumn Lara',
    'Tracy Durham',
],
    'json': {
    'name': 'Adam Brennan',
    'address': '69675 Davis Extension Suite 694\nWest Leahstad, SD 83124',
},
    'key17349': 'value3467',
    'key5233': 'value18554',
    'key63460': 'value50536',
    'key72627': 'value70195',
    'key43853': 'value63127',
    'key91954': 'value77085',
    'key18090': 'value68734',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 46,
    'name': 'Katherine Jensen',
    'address': '052 Jones Crescent\nLake Richardberg, VA 28861',
    'text': 'Set low say would herself open. Administration theory describe contain information court begin.\nPower occur of poor. News seek base check treatment leader. Small standard here single.',
    'email': 'gonzalezdave@example.net',
    'phone_number': '001-576-406-8408',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Charles White',
    'Joseph Mccoy',
    'Melissa Villanueva',
    'Calvin Barr',
    'Patricia Blanchard',
    'Dustin Peterson',
],
    'json': {
    'name': 'William Brown',
    'address': '1571 Figueroa Highway Apt. 714\nEast Karenhaven, ID 93094',
},
    'key29046': 'value67232',
    'key57078': 'value27365',
    'key80522': 'value24549',
    'key4111': 'value1578',
    'key66318': 'value93174',
    'key23439': 'value96143',
    'key50714': 'value27281',
    'key25320': 'value16561',
    'key1228': 'value83841',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 47,
    'name': 'Michele Morris',
    'address': '8492 Veronica Port Suite 945\nPort Pamela, IL 06252',
    'text': 'Radio find design already dog particular. Practice remember world before simply watch establish.\nSuccessful establish ahead language former size necessary.',
    'email': 'shane15@example.com',
    'phone_number': '+1-823-389-5723x5975',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Terry Johnson',
    'Todd Johnson',
    'Barry Woods',
    'Linda Rivera',
    'Isabella Contreras',
    'Julia Davis',
],
    'json': {
    'name': 'Jacob Trujillo',
    'address': '9746 Mercado Stravenue Suite 096\nEast Sarahview, SD 49023',
},
    'key68041': 'value80094',
    'key53139': 'value39990',
    'key94143': 'value2116',
    'key7116': 'value10635',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 48,
    'name': 'Melissa Olson',
    'address': '409 Tonya Expressway Suite 608\nPort Vanessa, MA 85709',
    'text': 'Oil defense at. Too huge however include.\nThose join culture fear travel attention for. Bill among light commercial common care. Across opportunity occur again clearly seat structure everybody.',
    'email': 'williamchristian@example.org',
    'phone_number': '(776)369-6323',
    'array_int_dynamic': [
    92405,
],
    'array_varchar_dynamic': [
    'Heather Shah',
    'Christina Sawyer',
    'Philip Carter',
    'Scott Peterson',
],
    'json': {
    'name': 'Erik Gonzalez',
    'address': '3735 Bethany Knoll Suite 365\nFoxfurt, OR 59032',
},
    'key50227': 'value70337',
    'key86258': 'value29813',
    'key26696': 'value69969',
    'key45922': 'value93686',
    'key42208': 'value96272',
    'key76026': 'value87529',
    'key4747': 'value7717',
    'key12175': 'value82459',
    'key20154': 'value21811',
    'key37883': 'value79415',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 49,
    'name': 'Jennifer Decker',
    'address': '7036 Huang Ways Suite 263\nNorth Stefanieside, ND 88266',
    'text': 'Firm pick with language whatever less item. Policy speech policy itself first.\nNation part for throughout political claim. Spring impact them true.',
    'email': 'melissa03@example.com',
    'phone_number': '(563)367-8414x89508',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Crystal Townsend',
],
    'json': {
    'name': 'Thomas Bradley',
    'address': '85130 Richard Loaf Suite 890\nThomasview, WI 67081',
},
    'key44346': 'value68162',
    'key18911': 'value84977',
    'key69304': 'value20046',
    'key84782': 'value85112',
    'key66016': 'value11443',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 50,
    'name': 'Robin Bell',
    'address': '43802 Heather Glens\nWest Alexanderchester, ND 78056',
    'text': 'Strong possible recent room. Minute investment clearly surface. Eye beautiful own indeed rest.\nStyle stock must least. End owner model person build street work. Girl behavior sea color.',
    'email': 'mannhoward@example.net',
    'phone_number': '(400)570-6292x1955',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Christina Forbes',
    'Juan Beasley',
],
    'json': {
    'name': 'Jeremy Turner',
    'address': 'USNS Moore\nFPO AA 06487',
},
    'key53607': 'value72251',
    'key40258': 'value35686',
    'key43013': 'value98065',
    'key44085': 'value61528',
    'key52137': 'value29716',
    'key34986': 'value22924',
    'key46362': 'value68742',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 51,
    'name': 'Bruce Hoover',
    'address': 'USNS Stevenson\nFPO AE 52632',
    'text': 'Sense seem hit collection animal player check anyone. Themselves figure order small career administration game. Race the market culture.',
    'email': 'petersonblake@example.org',
    'phone_number': '001-359-603-4549x38080',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Cynthia Gibson',
    'Sarah Taylor',
],
    'json': {
    'name': 'Shelley Bullock',
    'address': '1232 Ryan Trail Apt. 077\nPort James, PA 71557',
},
    'key33827': 'value55889',
    'key30908': 'value85689',
    'key41900': 'value91112',
    'key99401': 'value53477',
    'key18726': 'value62638',
    'key79041': 'value46983',
    'key23234': 'value1128',
    'key98308': 'value76696',
    'key97718': 'value34258',
    'key55256': 'value38251',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 52,
    'name': 'Matthew Anderson',
    'address': '8169 Christina Trafficway Suite 921\nNorth Scott, AR 93279',
    'text': 'Floor law value data true life. Sound five here sign. I whether tough travel cost tree politics.',
    'email': 'santoschristopher@example.net',
    'phone_number': '285.592.2551',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Andrew Lucas',
    'Tim Livingston',
    'Paul Torres',
    'Cindy Watts',
    'Kevin Murray',
    'Nathan Ayers',
],
    'json': {
    'name': 'Kaitlyn Ross',
    'address': '819 Sanchez Springs\nBrownhaven, HI 83224',
},
    'key67874': 'value71629',
    'key6567': 'value60881',
    'key94606': 'value84306',
    'key6555': 'value23696',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 53,
    'name': 'Tiffany Anderson',
    'address': 'Unit 8871 Box 1575\nDPO AE 36197',
    'text': 'Back wish room vote. While yard American perform friend call. Serve degree carry shoulder maybe.\nSuch yeah need maybe. And entire fish important create.',
    'email': 'mariaroy@example.org',
    'phone_number': '8307632659',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kathleen Obrien',
    'Mia Guzman',
    'Brandon Lutz',
],
    'json': {
    'name': 'Amber Vasquez',
    'address': 'PSC 4763, Box 9119\nAPO AE 80965',
},
    'key10997': 'value87949',
    'key33777': 'value65569',
    'key64280': 'value59908',
    'key77448': 'value27135',
    'key23553': 'value82765',
    'key56860': 'value59410',
    'key40171': 'value1092',
    'key44411': 'value23594',
    'key78852': 'value34779',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 54,
    'name': 'Kelly Turner',
    'address': '0966 Anthony Springs\nEast Staceyside, ND 51954',
    'text': 'Mrs wall culture even. Sit eye available article project. Ask low organization hair ability only current. Remember off trouble task.\nBoy likely case teach. Detail form face fear.',
    'email': 'timothy24@example.org',
    'phone_number': '778.898.2967',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Schroeder',
    'Michael Fuller',
    'Eduardo Kelly',
    'Michael Serrano',
    'Yesenia Marks',
    'Dr. Bryan James MD',
    'Robert Moreno DDS',
],
    'json': {
    'name': 'Michael Graham',
    'address': '7531 Sandra Inlet\nJohnsonshire, ND 59737',
},
    'key18073': 'value6675',
    'key58690': 'value49423',
    'key96255': 'value6141',
    'key3023': 'value58407',
    'key3583': 'value33745',
    'key46340': 'value33777',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 55,
    'name': 'Anna Brown',
    'address': '6723 Wise Mountains Suite 415\nPort Taramouth, AS 16479',
    'text': 'Perform different language debate. Design old any citizen serious case various. Eye indeed capital through they.',
    'email': 'mary43@example.org',
    'phone_number': '269-709-8046',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'James Jones',
],
    'json': {
    'name': 'Erin Mcintyre',
    'address': '2351 Hansen Roads Apt. 861\nNorth Mary, CA 64254',
},
    'key42529': 'value94481',
    'key6790': 'value94008',
    'key73812': 'value17435',
    'key99057': 'value64102',
    'key12922': 'value79446',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 56,
    'name': 'Donna Jenkins',
    'address': 'USCGC Mendez\nFPO AP 00940',
    'text': 'Debate call family since analysis pressure. Present tend weight between voice including board newspaper. Happen week old up stage.',
    'email': 'astokes@example.net',
    'phone_number': '(790)365-4300x60120',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Elizabeth Tran',
    'Carlos Hicks',
    'Dustin Young',
    'Steven Stevens',
    'David Klein',
    'Bryan Oconnor',
    'Ryan Meyer',
    'Betty Gomez',
    'Heidi Banks',
    'Johnny Parker',
],
    'json': {
    'name': 'Dennis Reeves',
    'address': '3865 Ferguson Grove Apt. 404\nCoreystad, NJ 75255',
},
    'key74472': 'value44252',
    'key87836': 'value70314',
    'key5416': 'value93606',
    'key90656': 'value65938',
    'key61845': 'value50615',
    'key60460': 'value87758',
    'key89537': 'value61567',
    'key95810': 'value51102',
    'key96365': 'value93793',
    'key79719': 'value83460',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 57,
    'name': 'Amy Ortiz',
    'address': '7060 James Pass\nNorth Kayla, OK 67532',
    'text': 'Friend wait all west still water pressure loss. Develop theory citizen reduce her consumer world measure.\nAge instead knowledge of.',
    'email': 'vpeters@example.net',
    'phone_number': '001-554-423-7743x181',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Patrick Sparks',
    'Kayla Mcguire',
    'Timothy Gardner',
],
    'json': {
    'name': 'Eric Pope DDS',
    'address': '372 Perez Crossroad\nNew David, CO 09640',
},
    'key56115': 'value93334',
    'key66621': 'value50065',
    'key4782': 'value61568',
    'key88032': 'value81433',
    'key15464': 'value50641',
    'key82043': 'value38789',
    'key82287': 'value53010',
    'key83886': 'value86480',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 58,
    'name': 'Crystal Diaz',
    'address': '062 Jacob Courts Apt. 928\nChadburgh, TN 46308',
    'text': 'West within add state kid station. Fact upon guy decade.\nGovernment help worry mention bar. Worker risk how even everybody measure. Finish system about manage. Cut attention however marriage science.',
    'email': 'andrewrandolph@example.com',
    'phone_number': '(643)398-7084x1397',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Johnathan Wright',
    'James Benson',
    'Carol Jones',
    'Martin Gonzalez',
    'Adriana Russell',
    'Veronica Smith',
],
    'json': {
    'name': 'Amanda Soto',
    'address': '698 Larson Prairie Apt. 860\nMartinmouth, ND 98022',
},
    'key57220': 'value3525',
    'key75051': 'value10011',
    'key31845': 'value25749',
    'key72252': 'value94387',
    'key43009': 'value29208',
    'key70665': 'value20355',
    'key21311': 'value14638',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 59,
    'name': 'David Sexton',
    'address': '77966 Caldwell Tunnel\nBatesview, SC 43724',
    'text': 'By within increase finally of. Get floor eat benefit research term. Forget senior sing run five make short. Resource Democrat finally mouth charge.',
    'email': 'marcus25@example.com',
    'phone_number': '572-597-3195x83408',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Carol Joyce MD',
    'Laura Blair',
    'Tiffany Moody',
    'Lawrence Clark',
    'Brian Schneider',
    'Stephen Austin',
    'Alicia Snyder',
    'Angela Case',
],
    'json': {
    'name': 'Leonard Collins',
    'address': '6003 Stone Extensions Apt. 008\nSouth Stephaniebury, OK 06257',
},
    'key62773': 'value83968',
    'key25185': 'value29394',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 60,
    'name': 'Sean Black',
    'address': '630 Donald Loaf Suite 681\nNorth Robintown, FL 53163',
    'text': 'Wait happy amount serious along mother. History society particularly piece method talk third. Red during who able military yourself choose.',
    'email': 'pmiller@example.org',
    'phone_number': '829.796.7529',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Alexis Park',
],
    'json': {
    'name': 'Katherine Thornton',
    'address': 'PSC 6263, Box 8107\nAPO AP 92355',
},
    'key23095': 'value95989',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 61,
    'name': 'Gabriela Carney',
    'address': 'Unit 9492 Box 2174\nDPO AA 62474',
    'text': 'Month mission attorney address father professor recently senior. Country play space kind.\nRich religious candidate south sport state feeling. Theory push half join table game official.',
    'email': 'powersgregory@example.com',
    'phone_number': '833-592-1633x17661',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Steven Alvarez',
    'Patricia Jones',
    'Patrick Smith IV',
    'Michael Hayes',
    'Andrew Fernandez',
    'Charles Barker',
    'Michele Walker',
],
    'json': {
    'name': 'Taylor Robbins',
    'address': '0746 Knight Mountains\nBonniemouth, FL 96759',
},
    'key41563': 'value14777',
    'key80029': 'value82355',
    'key26257': 'value34331',
    'key22512': 'value56239',
    'key36833': 'value47675',
    'key1620': 'value24328',
    'key39403': 'value44807',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 62,
    'name': 'Elizabeth Quinn',
    'address': '4305 Emily Brooks\nNorth Crystal, IA 08218',
    'text': 'Sort kind mention specific. Behind age sort edge. Rest yes center memory cut computer.\nResource provide lay look around. Service matter spring million easy life.',
    'email': 'swansonjo@example.com',
    'phone_number': '(468)913-4170x289',
    'array_int_dynamic': [
    30415,
],
    'array_varchar_dynamic': [
    'Kimberly Phillips',
    'Eric Thompson',
    'Christine Elliott',
    'Glen Gallagher',
    'Aaron Alexander',
    'Christopher Bailey',
    'Michael Flores',
    'Sierra Tanner',
    'Morgan Garza',
],
    'json': {
    'name': 'Jacqueline Anderson',
    'address': 'PSC 8610, Box 5880\nAPO AE 37080',
},
    'key80679': 'value87166',
    'key29407': 'value58638',
    'key14038': 'value54202',
    'key81664': 'value21220',
    'key65166': 'value91669',
    'key90922': 'value91972',
    'key19262': 'value75897',
    'key22293': 'value97537',
    'key76916': 'value63866',
    'key92576': 'value60446',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 63,
    'name': 'Shane Bradley',
    'address': '0553 Weiss Pike Apt. 154\nLake Terri, AR 47803',
    'text': 'Concern foreign improve part party certainly smile better.\nPoor senior central. Significant religious fight several reflect television new goal.',
    'email': 'benjamin78@example.net',
    'phone_number': '001-214-539-8505x319',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Timothy Wood DVM',
    'Ronald Taylor',
    'Angela Johnson',
    'Terry Tran',
    'Tiffany Pham DVM',
    'Savannah Oneal',
    'Casey Avila',
    'Alexandria Mccoy',
    'Joshua Brown',
    'Robert Roberts',
],
    'json': {
    'name': 'Mr. William Tucker',
    'address': '39269 Wolfe Land Suite 709\nMichaelhaven, PR 70937',
},
    'key28062': 'value98566',
    'key66015': 'value3597',
    'key40325': 'value93827',
    'key16533': 'value32767',
    'key76953': 'value21820',
    'key66732': 'value79729',
    'key48336': 'value8865',
    'key83960': 'value44365',
    'key14563': 'value74686',
    'key90898': 'value31267',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 64,
    'name': 'Kathleen Kirk',
    'address': '3137 Walsh Mall Apt. 763\nMorganfurt, VI 27257',
    'text': 'Fight black trial. Night effort security. System someone whatever event market.\nAgent believe explain forget various though. Hour evidence business seven with anyone.',
    'email': 'garciashane@example.org',
    'phone_number': '551-561-4972',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Karen Hicks',
    'Mr. Christopher Myers',
    'Wanda Miller',
    'Andrew Martinez',
    'Marie Guzman',
    'Tammy Johnson',
    'Nathan Barrera',
    'Vanessa Cameron DVM',
    'Melissa Richmond',
    'Michael Carter',
],
    'json': {
    'name': 'Andrea Cook',
    'address': '645 James Tunnel Suite 962\nNorth Edward, ID 73900',
},
    'key76697': 'value10164',
    'key74607': 'value23124',
    'key59754': 'value20148',
    'key62643': 'value98202',
    'key23209': 'value75516',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 65,
    'name': 'James Goodman',
    'address': '8178 Mahoney Cape Suite 745\nEast Janet, NC 14161',
    'text': 'Out under agent line generation this would. That positive positive particular.',
    'email': 'johnpeterson@example.com',
    'phone_number': '+1-776-943-9888x054',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'David Morris',
    'Catherine Jenkins',
    'Nicole Smith',
    'Travis Mayo',
    'Katherine Allen',
],
    'json': {
    'name': 'Alexis Becker',
    'address': '8120 Brianna Key Apt. 568\nJamesshire, AK 49845',
},
    'key51561': 'value98469',
    'key55978': 'value26269',
    'key24848': 'value32367',
    'key1246': 'value4348',
    'key12008': 'value61966',
    'key87151': 'value36282',
    'key85392': 'value28442',
    'key74252': 'value81838',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 66,
    'name': 'Bradley Carson',
    'address': '445 Kimberly Square Suite 003\nPort Casey, DE 56627',
    'text': 'Assume point be teach impact. After sea myself family building assume wait. World site product door. Benefit our reality everyone address.',
    'email': 'ryanwall@example.org',
    'phone_number': '6689590026',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Laura Gilmore',
    'James Fischer',
    'Jessica Bailey',
    'Nancy Wilson',
    'Tiffany Ward',
],
    'json': {
    'name': 'Jon Foster',
    'address': '931 Lopez Rest\nNew Carla, GA 69224',
},
    'key76623': 'value1520',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 67,
    'name': 'Anthony Frederick',
    'address': '5677 Tammy Manor\nRebeccaton, AL 22667',
    'text': 'Big must start away race. Fine do part sound.\nCampaign poor protect various coach may question.\nSide think ok itself positive. Offer country old rule do girl.',
    'email': 'sjenkins@example.com',
    'phone_number': '570-992-5597x6058',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Wendy Anderson',
    'Cheyenne Johnson',
    'Katie Fry',
    'Richard Nichols',
],
    'json': {
    'name': 'Julie Rush',
    'address': '334 Lozano Knoll Suite 183\nSouth Jennifermouth, NC 73214',
},
    'key47944': 'value93239',
    'key34776': 'value3757',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 68,
    'name': 'Nicole Wilson',
    'address': 'USS Carroll\nFPO AE 32819',
    'text': 'Edge we wait anyone reduce out sign. Wife it service feel candidate every.\nParticularly wear more. Notice special who opportunity policy this. Program production history cold line difficult sea.',
    'email': 'bishopdavid@example.org',
    'phone_number': '(941)549-5965',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sharon Hayes',
],
    'json': {
    'name': 'Laurie Hughes',
    'address': '774 Parker Field\nJoshuatown, MA 69506',
},
    'key27255': 'value17104',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 69,
    'name': 'Calvin Carlson',
    'address': '9474 Brandon Creek Suite 438\nRyanburgh, MP 05508',
    'text': 'Life family simple same. Suffer enough yes thank to. Billion industry ten my.',
    'email': 'richard92@example.net',
    'phone_number': '(325)363-5083x2219',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Ricky May',
],
    'json': {
    'name': 'Joseph Anderson MD',
    'address': '7774 Ponce Roads Suite 040\nEmilyfort, DC 16054',
},
    'key15988': 'value36357',
    'key55358': 'value53488',
    'key2496': 'value16963',
    'key8376': 'value31599',
    'key61542': 'value38152',
    'key40578': 'value26151',
    'key71173': 'value6726',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 70,
    'name': 'Jason Clark',
    'address': '53913 David Cliff Suite 575\nNorth Michael, WI 12435',
    'text': 'Instead society explain as sound trial bag. List success always apply. Half yourself enter.\nLight individual black side hard include. Nature wish figure form or door perform.',
    'email': 'ipena@example.org',
    'phone_number': '001-819-899-7105x083',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Wendy Franco',
    'Marissa Phillips',
    'Melissa Chen',
    'Robert Watson',
    'David Martin',
    'Daniel Jackson',
    'Brenda Stephens',
    'Lisa Parsons',
    'Kayla Walker',
],
    'json': {
    'name': 'Justin Knox',
    'address': '33977 Graham Fords Suite 174\nLauraberg, VT 17057',
},
    'key31849': 'value60433',
    'key40457': 'value31562',
    'key82501': 'value91790',
    'key29532': 'value44960',
    'key68504': 'value14874',
    'key44525': 'value2623',
    'key76351': 'value7154',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 71,
    'name': 'Jacob Waller',
    'address': '1796 Donna Passage Suite 185\nShawport, ME 47970',
    'text': 'For high traditional quickly tough serve. Accept live coach will strong. Measure note yard young family car I.\nAir source morning animal. Summer ground detail measure. Role fish under beyond.',
    'email': 'tmiller@example.net',
    'phone_number': '001-452-636-4901x272',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Ricky Thomas',
    'Sue Douglas',
    'Mary Lopez',
    'Amanda Walsh',
    'Robert Le',
    'David Randall',
],
    'json': {
    'name': 'Beth Peck',
    'address': '1848 Jason Fords\nAdamshaven, KY 62155',
},
    'key49493': 'value38509',
    'key11482': 'value90981',
    'key58522': 'value87978',
    'key43337': 'value71251',
    'key57941': 'value24797',
    'key37887': 'value73683',
    'key80455': 'value4322',
    'key2539': 'value62311',
    'key16440': 'value11224',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 72,
    'name': 'Brittany Lee',
    'address': '823 Lee Roads\nNorth Kristinamouth, DC 70447',
    'text': 'Six safe explain well sense space tonight fund. Without heart sense threat. Win available way door few doctor live serve.',
    'email': 'margaretmiller@example.com',
    'phone_number': '(344)826-4713x6126',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Donald Rodriguez',
    'Christopher Brown',
],
    'json': {
    'name': 'Michael Jenkins',
    'address': '58594 Vega Spur Apt. 639\nMcintyrefurt, CO 18586',
},
    'key31988': 'value33819',
    'key63813': 'value44453',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 73,
    'name': 'Barbara Luna',
    'address': '22124 Brandon Villages Suite 446\nEast Davidfurt, KS 22766',
    'text': 'Level have national wait north half daughter happy.\nBlood fast can member west. Reality decision new billion. Ten push campaign half face three leader.',
    'email': 'kellerkyle@example.net',
    'phone_number': '515.977.1685x051',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'John Mack',
    'Kevin Dominguez',
    'Joseph Case',
    'Brianna Potts',
],
    'json': {
    'name': 'Shannon Parsons',
    'address': 'PSC 6942, Box 8739\nAPO AE 34465',
},
    'key1982': 'value96444',
    'key57298': 'value34137',
    'key34687': 'value69242',
    'key97132': 'value46552',
    'key7570': 'value18889',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 74,
    'name': 'Sally Austin',
    'address': '86594 Brooks Junctions Suite 331\nNancytown, MS 30867',
    'text': 'Newspaper card talk across. Try senior film perform between.\nArtist sell various respond. Talk huge across minute. Network together easy resource seek whose eat.',
    'email': 'becky04@example.org',
    'phone_number': '(348)427-1729',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Anna Singh',
    'Keith Downs',
    'Ian Ortiz',
    'Jennifer Carter',
    'Mary Warren',
    'Stephanie Brown',
    'Richard Martin',
    'Jesse Kirk',
    'Angela Collins',
    'Christina Cross',
],
    'json': {
    'name': 'Carl Miller',
    'address': '12492 Mary Avenue\nHaleyborough, ND 95222',
},
    'key61331': 'value74449',
    'key12312': 'value94425',
    'key1577': 'value91261',
    'key37119': 'value39750',
    'key10920': 'value44662',
    'key78230': 'value10548',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 75,
    'name': 'Andrew Perez',
    'address': '61364 Lopez Ports Apt. 471\nPort Frankville, NH 68974',
    'text': 'Important subject increase ago ahead stock member. Score wind attention sometimes fight save push. Blood where both carry.',
    'email': 'sarahbyrd@example.net',
    'phone_number': '266-623-4532',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Helen Burton',
    'Deborah Lopez',
    'Dean Hall',
    'Shannon Jackson',
    'Rachel Gallegos',
    'Joseph Ford',
    'Alison Martinez',
    'Marvin Carey',
    'James Parks',
    'Jessica Bates',
],
    'json': {
    'name': 'Rebecca Green',
    'address': '418 Johnson Expressway Suite 199\nEdwinchester, VI 05530',
},
    'key85964': 'value98063',
    'key4725': 'value95513',
    'key58251': 'value4289',
    'key39540': 'value22029',
    'key62811': 'value22667',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 76,
    'name': 'John Williams',
    'address': '619 William Alley Suite 034\nMatthewburgh, TN 05613',
    'text': 'Will national sea theory civil shake. Hotel moment already type any.\nArticle church good something. Skin much campaign middle reach. Account strong maybe religious action court.',
    'email': 'gschmidt@example.com',
    'phone_number': '987-405-7315x48279',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Marshall',
    'Eric Smith',
    'Doris Gill',
    'Teresa Flores',
    'Michael Villanueva',
    'Michael Hall',
    'Ebony Leonard',
    'Patrick Hamilton MD',
    'April Robinson',
    'Mary Wright',
],
    'json': {
    'name': 'Jacob Carr',
    'address': '17631 Erickson Knoll Suite 880\nRussellland, MD 75811',
},
    'key57817': 'value17182',
    'key69515': 'value17824',
    'key73146': 'value85767',
    'key98806': 'value99483',
    'key34389': 'value63195',
    'key1504': 'value20293',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 77,
    'name': 'Andrea Luna',
    'address': '3608 Johnson Fort Apt. 319\nSmithbury, RI 69566',
    'text': 'Well carry drive number teach open across. Service join bed move if anyone little.\nArrive we senior room. Tax blue child movie little history.',
    'email': 'loririvas@example.org',
    'phone_number': '936.565.8343x5689',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Jesus Miller',
    'Audrey Lopez',
    'Julie Stone',
    'Derek Paul',
    'Sharon Beltran',
    'Brian White',
    'Tamara Buchanan',
    'Claudia Gutierrez',
],
    'json': {
    'name': 'Robert Buckley',
    'address': '162 Johnson Mills\nWest Scott, FL 50446',
},
    'key67813': 'value33243',
    'key12903': 'value12253',
    'key26432': 'value74155',
    'key35335': 'value80526',
    'key31868': 'value65318',
    'key25890': 'value68552',
    'key17769': 'value70891',
    'key21136': 'value16380',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 78,
    'name': 'Madison Nelson',
    'address': '725 Amy Shore Suite 967\nWest Danielle, OH 54324',
    'text': 'Step main again.\nBetween something whom analysis. Themselves hope truth up among. Population nothing change administration American than indicate wonder.',
    'email': 'wilsonjay@example.net',
    'phone_number': '+1-417-641-3138',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'John Schultz',
],
    'json': {
    'name': 'Nancy Hicks',
    'address': '0066 Jenna Canyon\nGeorgeshire, AS 98004',
},
    'key36930': 'value42191',
    'key41474': 'value36036',
    'key90251': 'value16136',
    'key32428': 'value36332',
    'key46851': 'value65784',
    'key53478': 'value55932',
    'key4604': 'value70267',
    'key62329': 'value91955',
    'key62280': 'value68534',
    'key57040': 'value86243',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 79,
    'name': 'Vicki Dickson',
    'address': '49640 Albert Village Suite 232\nMelindashire, SD 18262',
    'text': 'Continue worry beyond morning that national protect. Allow she decide be sister thousand pattern young.',
    'email': 'haletabitha@example.org',
    'phone_number': '703.777.2181x91486',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Hale',
],
    'json': {
    'name': 'Cynthia Castillo',
    'address': '3303 Moore Divide Apt. 114\nLake Patriciaville, PR 87661',
},
    'key73075': 'value79358',
    'key90069': 'value2041',
    'key54774': 'value98833',
    'key57552': 'value74673',
    'key25489': 'value28631',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 80,
    'name': 'Christian Silva',
    'address': '395 Thomas Radial Apt. 149\nPort Denise, VT 11814',
    'text': 'Magazine six research sit. Administration provide still before upon seem. Ten budget be.\nLay happy speech message themselves eye garden side. Book energy play rich door alone along.',
    'email': 'myersjames@example.com',
    'phone_number': '398-526-8076',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Brett Nguyen',
    'Sandra Davis',
],
    'json': {
    'name': 'Felicia Carpenter',
    'address': '321 Hatfield Underpass\nTheresaton, MD 10112',
},
    'key62582': 'value18103',
    'key13921': 'value53690',
    'key45221': 'value19714',
    'key80996': 'value38188',
    'key28739': 'value3647',
    'key6733': 'value93478',
    'key19540': 'value84914',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 81,
    'name': 'Kevin Miller',
    'address': '48603 Smith Creek Apt. 604\nSouth Cristianburgh, UT 45482',
    'text': 'Crime rock impact. Manager almost let movement either generation.\nTime keep safe dark they. At member could also my front minute. Practice another fight list like outside fly.',
    'email': 'qreed@example.org',
    'phone_number': '001-700-222-5218x15183',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Christopher Thornton',
    'Alison Terrell',
    'Frank Mayo',
    'Melissa Lopez',
    'Kyle Park',
    'Stephanie Hayes',
    'Angela Stewart',
    'Michael Greene',
],
    'json': {
    'name': 'Kelly Eaton',
    'address': '118 Beard Harbors\nEast Larrystad, MP 37333',
},
    'key89454': 'value92466',
    'key61715': 'value78381',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 82,
    'name': 'Hannah Martin',
    'address': '721 Galvan Islands\nMckenziechester, TN 43334',
    'text': 'Most condition produce and stuff national. Total record event.\nPolitics very responsibility view culture page low. Help quite base everybody. Sort campaign field blood add will you.',
    'email': 'billyjoseph@example.com',
    'phone_number': '(545)553-4182',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kyle Hendrix',
],
    'json': {
    'name': 'Ryan Wade',
    'address': '3926 Cindy Mountains Apt. 111\nWest Jenniferberg, MO 17955',
},
    'key12019': 'value90857',
    'key94757': 'value73456',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 83,
    'name': 'Allison Robinson',
    'address': '03039 West Trail Apt. 093\nNorth Conniefurt, WA 42207',
    'text': 'Task day campaign represent speech mention. Entire first put but.\nHim follow build if. Once sit deep entire. She data language main out.',
    'email': 'carrollallison@example.net',
    'phone_number': '(612)534-7748x728',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'William Mitchell',
],
    'json': {
    'name': 'Brandi Harper',
    'address': '69485 Jackson Overpass Apt. 963\nSamueltown, MD 41480',
},
    'key49303': 'value22634',
    'key93213': 'value62926',
    'key29876': 'value62851',
    'key22164': 'value19243',
    'key11268': 'value72400',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 84,
    'name': 'James Walker',
    'address': '98200 Joe Flat\nPort Sandrafurt, GU 66603',
    'text': 'Sense hospital charge first. According guy learn leader either raise support. Successful still method adult.',
    'email': 'bwaller@example.org',
    'phone_number': '+1-733-640-5371x747',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Middleton',
    'John Gonzalez',
    'Megan Salinas',
    'Thomas Lane',
    'Christina Day',
    'Elizabeth Miles',
    'Kristen Schaefer',
    'Monica Robinson',
    'Julie Mcintosh',
],
    'json': {
    'name': 'Christopher Ortiz',
    'address': '540 Philip Knolls Apt. 608\nLongbury, SD 29109',
},
    'key7933': 'value16374',
    'key5058': 'value52224',
    'key63288': 'value52916',
    'key58846': 'value51485',
    'key76820': 'value2708',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 85,
    'name': 'Janet Garcia',
    'address': '03632 Dylan Ford Suite 223\nRobinsonton, GU 63868',
    'text': 'Trouble those responsibility send. Whether return focus or year.\nSubject school house hair. Watch soldier choice security. Wait three behind.',
    'email': 'bryan33@example.com',
    'phone_number': '+1-576-889-7839',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Ann Roman',
    'Sara Clark',
    'Juan Sanchez',
    'Lisa Elliott',
],
    'json': {
    'name': 'Jennifer Sanders',
    'address': '966 Lopez Park Suite 284\nHollowayshire, AR 90136',
},
    'key79407': 'value14964',
    'key57807': 'value7718',
    'key74122': 'value79171',
    'key79855': 'value12002',
    'key26543': 'value80984',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 86,
    'name': 'Jennifer Wolfe',
    'address': '507 Pratt Rapid Suite 407\nNew Teresafurt, NM 37793',
    'text': 'Sea hundred claim on eye interest.\nLaw fight improve others. Discover forward travel outside something.\nImage blue address week little.',
    'email': 'bryantjeffery@example.net',
    'phone_number': '931-885-5114',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Larry Gregory',
    'Michael Lopez',
    'James Jackson',
],
    'json': {
    'name': 'Sarah Merritt',
    'address': '102 Amy Mountains\nPort Andrew, PA 06002',
},
    'key48862': 'value3414',
    'key26433': 'value85879',
    'key25946': 'value81173',
    'key1105': 'value58865',
    'key30397': 'value1609',
    'key77301': 'value65554',
    'key95560': 'value84194',
    'key81267': 'value18583',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 87,
    'name': 'William Allen',
    'address': '8919 Fox Ville Suite 880\nLongport, OH 91410',
    'text': 'Certain challenge win international anyone court different. Compare officer PM analysis way marriage. Court cultural attention play. Candidate simple then series.',
    'email': 'morananthony@example.com',
    'phone_number': '(285)843-4593',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Robert Graham',
    'Thomas Klein',
    'Billy Daniel',
    'Jamie Blake',
    'Amanda Martinez',
    'Patricia Frazier',
    'Robert Hudson',
    'Tanya Williams',
],
    'json': {
    'name': 'Jason Frank',
    'address': '3503 Andrade Shores Apt. 600\nJonesview, CO 73234',
},
    'key48807': 'value7834',
    'key94806': 'value38150',
    'key58509': 'value7635',
    'key37634': 'value68129',
    'key8020': 'value46611',
    'key88872': 'value21351',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 88,
    'name': 'Stanley Johnson',
    'address': '36392 Brooks Roads Apt. 179\nDanaville, WY 83961',
    'text': 'Couple majority option past describe quickly cause. Down standard matter occur miss citizen power almost. Start understand simply operation job direction simply.',
    'email': 'pattonmarcus@example.org',
    'phone_number': '001-354-779-0890x4876',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Wells',
    'Jennifer Oliver',
    'Matthew Jones',
],
    'json': {
    'name': 'Brian Higgins',
    'address': '4986 Matthew Run Apt. 362\nSweeneytown, IA 15168',
},
    'key60704': 'value817',
    'key77271': 'value76328',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 89,
    'name': 'Matthew Taylor',
    'address': '136 Henderson Loaf\nEast Katherineview, OH 89501',
    'text': 'Resource myself space project agent maintain I. Man food any sell act since. Hit little three decide.\nTrade get figure be similar. Money difficult edge stand.',
    'email': 'jlewis@example.com',
    'phone_number': '+1-613-549-4173x392',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Dr. Michelle Benitez',
    'Tiffany Castaneda',
    'Heather Watson',
    'Jennifer Anthony',
    'Dale Stewart',
    'Destiny Green',
],
    'json': {
    'name': 'Vanessa Jefferson',
    'address': '1916 Douglas Pines\nNew Brandonberg, OR 58133',
},
    'key84872': 'value58312',
    'key34535': 'value40770',
    'key62760': 'value28850',
    'key18400': 'value74499',
    'key47279': 'value21571',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 90,
    'name': 'Diana Johnson',
    'address': '57768 Graham Shoals\nDavisfurt, DC 87466',
    'text': 'House position push behavior TV center government. Over kid above near late hope police.\nIdea because draw the back get. Watch interest in room since decision. Exactly he when.',
    'email': 'stanleyjohnson@example.net',
    'phone_number': '+1-404-976-1970x809',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Alejandro Washington',
    'Julia Gill',
    'Patricia Golden',
    'Carolyn Moreno',
    'Manuel Duncan',
    'Kathryn Richards',
    'Margaret Smith',
    'Mark Martin MD',
    'Rachel Ball',
],
    'json': {
    'name': 'Samantha Henry',
    'address': '5839 Christopher Lock\nNew Joshuaview, ME 96492',
},
    'key77844': 'value25623',
    'key50052': 'value17170',
    'key70379': 'value18577',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 91,
    'name': 'Joseph White',
    'address': '01795 Hansen Stream Suite 523\nRowebury, MD 62904',
    'text': 'Candidate later clearly western. Send only final everyone.\nThus discover soon only area. Bring sign view radio several. Compare stock include commercial age mention start story.',
    'email': 'rebeccabeck@example.org',
    'phone_number': '864.932.0083',
    'array_int_dynamic': [
    85432,
],
    'array_varchar_dynamic': [
    'Kimberly Kennedy',
    'Jesse Wolfe',
    'Ronald Silva',
    'Daniel Young',
    'Richard Johnson',
],
    'json': {
    'name': 'Drew Grimes',
    'address': '98358 Regina Ferry Apt. 960\nSouth Bryan, OR 19406',
},
    'key47788': 'value83365',
    'key14707': 'value36339',
    'key29199': 'value41380',
    'key3655': 'value78858',
    'key7439': 'value6474',
    'key44440': 'value51276',
    'key30040': 'value43681',
    'key96022': 'value18941',
    'key92688': 'value91934',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 92,
    'name': 'Sharon Nunez',
    'address': '75610 Gilmore Neck\nLake Phillipport, MS 20405',
    'text': 'Agency whole Democrat room type difficult inside final. Trade play move part really different near government. Dream rule thought condition.',
    'email': 'vbauer@example.org',
    'phone_number': '744-610-6313x52612',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'James Mcgee',
    'Nathan Welch',
    'Tanya Barnes',
    'Michele Greene',
    'Kyle Robinson',
],
    'json': {
    'name': 'Robert Hayes',
    'address': '5796 Evans Parks Apt. 125\nSalazarland, AK 06713',
},
    'key82666': 'value81170',
    'key50667': 'value41791',
    'key83544': 'value8984',
    'key91286': 'value11791',
    'key67980': 'value54335',
    'key81312': 'value70916',
    'key34166': 'value10466',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 93,
    'name': 'Samantha Willis',
    'address': 'Unit 0982 Box 2585\nDPO AP 36884',
    'text': 'Center care rather cover go allow. Management probably scientist create group center which.',
    'email': 'katherinemiller@example.org',
    'phone_number': '8156805097',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Tabitha Ayers',
],
    'json': {
    'name': 'Joshua Fowler',
    'address': '10210 Evans Island Suite 302\nLake Kevin, SD 57707',
},
    'key89957': 'value92908',
    'key98552': 'value65268',
    'key56396': 'value80055',
    'key58465': 'value85681',
    'key99603': 'value60195',
    'key27526': 'value22453',
    'key48454': 'value60972',
    'key22968': 'value21352',
    'key24732': 'value33026',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 94,
    'name': 'Jennifer Wilkerson',
    'address': '210 Kevin Cove Suite 592\nNorth Paul, AK 17007',
    'text': 'Peace real read space less become. Commercial stage teacher scientist though.\nRun such turn for hair itself return. Wife out begin black produce worker stuff side.',
    'email': 'armstrongrichard@example.net',
    'phone_number': '724.568.2907x191',
    'array_int_dynamic': [
    12278,
],
    'array_varchar_dynamic': [
    'Tracy Haley',
    'Kylie Washington',
    'Lori Conner',
    'Eric Smith',
    'Megan Fox MD',
    'Jonathan Cannon',
    'Christian Montoya',
    'Aaron Rodriguez',
    'Kendra Small',
],
    'json': {
    'name': 'Mary Cervantes',
    'address': '75745 Carroll Inlet\nWest Bailey, TN 61207',
},
    'key83380': 'value89072',
    'key83933': 'value15903',
    'key83071': 'value58542',
    'key70981': 'value54400',
    'key5313': 'value92609',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 95,
    'name': 'Eddie Wood',
    'address': '2139 Solis Neck\nLake Samanthaburgh, SC 26278',
    'text': 'Possible wife attorney bill. Shake real themselves figure star lawyer respond.\nWeight nothing song center task.',
    'email': 'rbaker@example.net',
    'phone_number': '+1-637-631-1217x26906',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Peter Garcia',
    'Jessica Kemp',
    'Donna Blake',
    'John Baker',
    'Samantha Perry',
    'Keith Carter',
],
    'json': {
    'name': 'Courtney Montgomery',
    'address': '6256 Berry Track Suite 135\nNorth Julieport, ID 01749',
},
    'key36954': 'value72640',
    'key98400': 'value17031',
    'key89091': 'value36514',
    'key64489': 'value37326',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 96,
    'name': 'Austin Savage',
    'address': '99994 Timothy Rapid\nCarrietown, FM 92290',
    'text': 'Opportunity seek weight catch stage. Community enjoy rate high such consumer. Product give miss worker minute bank detail official.',
    'email': 'hammondjoseph@example.org',
    'phone_number': '431.410.9116x9385',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'David Tran',
    'Shawn Castillo',
    'Jeremy Richards',
    'Lauren Silva',
    'Dennis Underwood',
    'Sandra Griffin',
    'Karina Lowe',
    'Michael Bush',
],
    'json': {
    'name': 'Mark Watkins',
    'address': '83404 Brown Freeway\nJeremyview, AZ 33804',
},
    'key92549': 'value10278',
    'key29180': 'value3935',
    'key88069': 'value76368',
    'key44175': 'value68463',
    'key8647': 'value74100',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 97,
    'name': 'Melanie Molina',
    'address': '2278 Cruz Route\nLake Aaronville, MT 65869',
    'text': 'Recent soon never blood because. Radio church in job conference year. Drive fish without reveal ago civil dark could.\nFace society important act heavy foot throughout six. Scene lead hair thousand.',
    'email': 'pmendez@example.net',
    'phone_number': '264.695.2897x88583',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Linda Oconnell',
    'Ashley Marquez',
    'Elizabeth Owens',
    'Sandra Smith',
],
    'json': {
    'name': 'Roberto Phillips',
    'address': '9694 Ruiz Brook\nCookborough, VT 04430',
},
    'key14931': 'value61098',
    'key39425': 'value28562',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 98,
    'name': 'Jasmine Jensen',
    'address': '427 Donald Ways Apt. 425\nJessicachester, OK 11686',
    'text': 'Sell animal answer those mission these. Rest girl magazine lawyer event go family. Who democratic fly send glass.',
    'email': 'christineallen@example.net',
    'phone_number': '761.639.7709x438',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Teresa Cannon',
],
    'json': {
    'name': 'Richard Deleon',
    'address': '26151 Ramos Pike Apt. 362\nNorth Cameron, TN 43921',
},
    'key25982': 'value55681',
    'key6168': 'value2491',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 99,
    'name': 'Lori Evans',
    'address': '5423 Olivia Spur\nMillerton, NJ 44058',
    'text': 'Edge remember thus medical adult read few.\nSuccessful whose according they character word within gas. Time air floor total and.',
    'email': 'woodrichard@example.org',
    'phone_number': '001-228-325-7367x52127',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Patricia Wright',
    'Darren Golden',
    'Linda Torres',
    'Seth Moon',
    'James Fisher',
    'Mark Todd',
    'Jacqueline Hunter',
],
    'json': {
    'name': 'Sandra Murillo',
    'address': '68471 Green Islands Apt. 273\nNorth Michelleport, GA 09341',
},
    'key23492': 'value4225',
    'key67607': 'value76576',
    'key11204': 'value13158',
    'key56278': 'value71594',
    'key85665': 'value33304',
    'key37993': 'value8255',
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
    'RequestId': 'a7953d19-62ef-11f0-9502-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_08_676552gnywgoUA',
    'dimension': 32,
    'primaryField': 'id',
    'vectorField': 'embedding',
    'autoID': True,
    'dbName': 'default',
}


        send_request(original_content, method, url_path, headers)
        return True



# 主函数
if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-100-1]_1752744189.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingId3210011752744189Json()
    test.run_tests()
