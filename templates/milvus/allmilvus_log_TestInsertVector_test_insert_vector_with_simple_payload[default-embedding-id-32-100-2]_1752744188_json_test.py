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
logger = logging.getLogger('vdbfuzz.test.allmilvus_log_TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-100-2]_1752744188_json')
logger.info("日志文件将输出到: " + log_file)

# 全局变量
TARGET_URL = ""
OUTPUT_DIR = "templates_milvus"
TEST_NAME = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-100-2]_1752744188.json"
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



class AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingId3210021752744188Json:
    """自动生成的VDB模糊测试类 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-100-2]_1752744188.json"""
    
    def __init__(self):
        """初始化测试类"""
        self.test_name = "allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-100-2]_1752744188.json"
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
    'RequestId': 'a6af7f27-62ef-11f0-a8fe-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_07_170917DLaMeQIz',
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
    'RequestId': 'a6cfdc1f-62ef-11f0-ba99-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_07_170917DLaMeQIz',
    'data': [
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 0,
    'name': 'Brandon Key',
    'address': '606 Martinez Crossing Apt. 538\nLake Deborah, GU 95277',
    'text': 'Become some bank laugh part smile. Rate case bed his draw simple.\nRealize result research already indicate. Ever course four candidate single site put material.',
    'email': 'vasquezdiana@example.com',
    'phone_number': '001-377-244-4986x9983',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Rachel Miller',
    'Gregory Dixon',
    'Aaron Figueroa',
    'Matthew Brown',
    'Douglas Cooper',
    'Brandi Hughes',
    'Alyssa Griffith',
    'Jose Williams',
    'Pamela Huynh',
    'Carla Morris',
],
    'json': {
    'name': 'Jeremy Rodriguez',
    'address': '871 Jason Cove\nPort Stephanieland, MP 50015',
},
    'key24147': 'value19027',
    'key74980': 'value21861',
    'key30542': 'value72702',
    'key23818': 'value36857',
    'key6646': 'value90963',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 1,
    'name': 'Debbie Stafford',
    'address': '1493 Gutierrez Field\nSouth Catherineview, PA 04760',
    'text': 'Dinner election tree become same. Medical it few sense condition their compare.\nUntil road plant work share the first scientist. Computer form according at. Down alone him level.',
    'email': 'ashleygarrison@example.net',
    'phone_number': '001-745-215-4307x385',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Nicholas Lane',
    'John Rivera',
    'Brandy Baxter',
    'Amanda Bauer',
    'Tracy Rodriguez',
    'Joseph Wells',
    'Harold Fernandez',
],
    'json': {
    'name': 'Debra Flores',
    'address': 'USNV Brooks\nFPO AA 65958',
},
    'key91120': 'value4465',
    'key29128': 'value47472',
    'key11314': 'value73187',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 2,
    'name': 'Jeffrey Allen',
    'address': '4909 Brian Common Apt. 138\nNorth Erichaven, NY 30198',
    'text': 'Door receive as air garden herself.\nPretty difference it. Three long tree nothing computer actually. Model hot member home administration ago.',
    'email': 'jordanmclaughlin@example.org',
    'phone_number': '759.254.2916x583',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Charles Moore',
    'Tammy Love',
    'Timothy Jones',
    'Jordan Smith',
    'Shannon Ford',
    'Bruce Wall',
    'Douglas Johnson',
    'Ryan Torres',
    'Mary Melendez',
],
    'json': {
    'name': 'Timothy Stone',
    'address': '15801 Evans Spurs Suite 026\nEast Patricia, ND 94980',
},
    'key60290': 'value16558',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 3,
    'name': 'Monica Moore',
    'address': '467 Brandon Skyway\nPetersenbury, MP 92677',
    'text': 'Involve production leader continue seat. Fast black lot fight pretty security kid. Drive Congress keep foreign baby what page human.',
    'email': 'brian60@example.net',
    'phone_number': '+1-452-492-1226x101',
    'array_int_dynamic': [
    53598,
],
    'array_varchar_dynamic': [
    'Jared Finley',
    'Michael Pena',
    'Zachary Brown',
],
    'json': {
    'name': 'Lisa Sutton',
    'address': '77681 Alexandria Forks\nEast Rhondaburgh, VI 14377',
},
    'key10308': 'value69671',
    'key30111': 'value36574',
    'key97759': 'value8237',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 4,
    'name': 'Frank Howard',
    'address': '31938 Laura Place\nSawyermouth, LA 91210',
    'text': 'Partner no experience boy quite successful enough. Reveal particular turn exactly concern hard conference.',
    'email': 'justin08@example.org',
    'phone_number': '+1-658-376-4674x81229',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Anthony Jenkins',
    'Katherine Miranda',
    'Stephen Hall',
    'Charles Carpenter',
    'Reginald Hurst',
    'Kyle Miranda',
    'James Lambert',
],
    'json': {
    'name': 'Patrick Conrad',
    'address': '8248 Kirby Club\nLake Micheal, UT 18328',
},
    'key66495': 'value87541',
    'key86728': 'value26351',
    'key6753': 'value90918',
    'key15915': 'value15981',
    'key62156': 'value49416',
    'key9635': 'value37857',
    'key63527': 'value41962',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 5,
    'name': 'Angela Sanford',
    'address': '2930 Marisa Haven Apt. 780\nEast Lindseytown, MT 98940',
    'text': 'According room art authority cup. Generation role present glass single also nearly establish.\nLearn media specific about low successful difficult. Result popular political read far size.',
    'email': 'james82@example.com',
    'phone_number': '903.342.8170x61412',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Allen',
    'Carla Rasmussen',
    'Jorge Ochoa',
    'Kelly Cunningham',
    'Nicholas Campbell',
],
    'json': {
    'name': 'John Willis',
    'address': '90725 Morales Fall\nNorth Victoriaside, WI 31093',
},
    'key53842': 'value718',
    'key91049': 'value10733',
    'key31100': 'value71130',
    'key65303': 'value7307',
    'key50939': 'value69922',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 6,
    'name': 'Tyler Tate',
    'address': '13232 Taylor Knolls Suite 819\nNorth Lisaton, IA 55015',
    'text': 'War suggest his individual admit front. Human simple drop economic activity board military.',
    'email': 'uwilkins@example.net',
    'phone_number': '781.982.2402x934',
    'array_int_dynamic': [
    70655,
],
    'array_varchar_dynamic': [
    'Carlos Burgess',
],
    'json': {
    'name': 'Jessica Lee',
    'address': '7832 Scott Greens Apt. 465\nNorth Deborah, TN 51024',
},
    'key33585': 'value93762',
    'key38168': 'value10175',
    'key46651': 'value97164',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 7,
    'name': 'Aaron Higgins',
    'address': '551 Miller Springs\nCodyfort, MH 87618',
    'text': 'Each sense begin. Like Congress lay southern. Never scientist special perform account cover.\nSkill wish eight newspaper.',
    'email': 'amyjones@example.net',
    'phone_number': '(583)563-2998x538',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Mrs. Dominique Griffin DDS',
    'Stacey Lewis',
    'Omar Baker',
    'Alison Wilson',
    'Pamela Bridges',
    'Rodney Wright',
    'Daniel James',
    'Dakota Munoz',
    'Michael Ball',
],
    'json': {
    'name': 'Joshua Chase',
    'address': '787 James Island\nNicholasside, MD 75624',
},
    'key82728': 'value3264',
    'key53817': 'value79852',
    'key6112': 'value19656',
    'key11903': 'value43235',
    'key48326': 'value33545',
    'key20783': 'value42411',
    'key21979': 'value66752',
    'key66882': 'value15375',
    'key57256': 'value1296',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 8,
    'name': 'Michael Anderson',
    'address': '17408 Justin Falls Apt. 842\nWilkinsonstad, MD 32588',
    'text': 'To within set method business another. Issue point hear tend garden third pull.\nFactor nature painting chance arm TV main. Black letter resource.',
    'email': 'matthewbrown@example.net',
    'phone_number': '237.953.6392x527',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Laura Allison',
],
    'json': {
    'name': 'Amanda Johnson',
    'address': '604 Jennifer Mountain\nHerreramouth, IN 14535',
},
    'key5049': 'value79447',
    'key96451': 'value75914',
    'key84193': 'value72122',
    'key59449': 'value33177',
    'key98863': 'value7784',
    'key29625': 'value89087',
    'key64807': 'value9019',
    'key86468': 'value18326',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 9,
    'name': 'Amy Gonzales',
    'address': '9411 James Via\nEast Alicia, PR 49678',
    'text': 'Test even attention too write even adult. Usually hot carry pressure himself challenge recent. Politics national response power detail house.',
    'email': 'pjones@example.com',
    'phone_number': '(666)476-0262x0276',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Davis',
],
    'json': {
    'name': 'Jose Long',
    'address': '929 Hill Islands\nPort Kristineberg, KY 49492',
},
    'key2387': 'value32346',
    'key27029': 'value6233',
    'key90104': 'value6469',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 10,
    'name': 'Stacey Rowe',
    'address': '04678 Alexander Divide Suite 097\nFlemingshire, DC 01641',
    'text': 'Home fine century. Do evidence opportunity me lead management over bag.\nMyself coach behavior front heavy want piece. Grow including young ever. Something Mr growth training first edge blue.',
    'email': 'khernandez@example.com',
    'phone_number': '+1-634-964-2338x773',
    'array_int_dynamic': [
    64524,
],
    'array_varchar_dynamic': [
    'Teresa Ashley',
    'Rachel Lynch',
    'Richard Clark',
    'Heidi Hardy',
],
    'json': {
    'name': 'Paula Meyer',
    'address': '846 Edgar Falls Apt. 977\nNew Marystad, RI 60518',
},
    'key87588': 'value97582',
    'key53208': 'value87734',
    'key75469': 'value2310',
    'key45762': 'value71179',
    'key89453': 'value9925',
    'key88001': 'value76089',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 11,
    'name': 'Lisa Armstrong',
    'address': 'USS Calderon\nFPO AA 51717',
    'text': 'Mean hospital maintain political medical heavy. Choose rich later response buy wear.\nLikely research glass price front throughout tree second. Agreement admit economy rate time.',
    'email': 'tammyrogers@example.net',
    'phone_number': '205.378.5671x1988',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Edward Roy',
    'Ian Barnett',
    'James Martinez',
],
    'json': {
    'name': 'Denise Young',
    'address': '96698 Chapman Walks Suite 987\nLake Katelyn, RI 45651',
},
    'key29317': 'value13572',
    'key77266': 'value98316',
    'key87431': 'value7650',
    'key10991': 'value96079',
    'key41166': 'value98274',
    'key37321': 'value44549',
    'key55657': 'value58854',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 12,
    'name': 'Melissa Ho',
    'address': '269 Davis Mews\nStaceybury, NV 91007',
    'text': 'Federal whether describe along. Street go technology research throughout out. Rich people important against. Leader ok want foreign fight.',
    'email': 'rosariotravis@example.com',
    'phone_number': '(929)431-9921x318',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Regina Stone',
],
    'json': {
    'name': 'Phyllis Park',
    'address': '343 Scott Glen\nGonzalezstad, NJ 12879',
},
    'key38070': 'value19730',
    'key56768': 'value13470',
    'key98207': 'value98508',
    'key28658': 'value92770',
    'key25474': 'value83069',
    'key37019': 'value16573',
    'key78332': 'value33685',
    'key6995': 'value60406',
    'key98217': 'value22008',
    'key52855': 'value43765',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 13,
    'name': 'Teresa Cox DDS',
    'address': '783 Amanda Cove Apt. 949\nHerringbury, WA 55696',
    'text': 'Able offer town little young consider. Reality college charge method pull bank election.\nStop issue him center knowledge democratic. Certainly employee player husband war every cut.',
    'email': 'tshah@example.org',
    'phone_number': '(317)583-0572',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Daniel Blankenship',
    'Dean Campos',
],
    'json': {
    'name': 'Krystal Williams',
    'address': 'PSC 8839, Box 2869\nAPO AA 80222',
},
    'key43898': 'value93807',
    'key47086': 'value15107',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 14,
    'name': 'James Colon',
    'address': '5449 Ana Mount Apt. 878\nLake Sarahport, KS 74784',
    'text': 'Executive total receive future. Save thank north her fall ready.\nYet theory hair. Single wind finally little say win.',
    'email': 'jamesnewman@example.org',
    'phone_number': '5798827615',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Lori Walsh',
    'Lisa Richardson',
    'John Odom',
    'Robert Perry',
    'Raymond Novak',
    'Billy Hughes PhD',
    'Joshua Guzman',
    'Joyce Patel',
    'Matthew Perez',
    'Emma Gibson',
],
    'json': {
    'name': 'Daniel Schmidt',
    'address': '2027 John Court\nNew Christopher, NC 41932',
},
    'key32366': 'value13822',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 15,
    'name': 'Jose Fry',
    'address': '54005 Rodgers Heights\nNorth Michael, SC 37745',
    'text': 'Truth together get. Smile source car. Alone kind turn career.\nPolitics culture cup class trip board all. Firm movement agency partner degree huge south. Thank region lead day.',
    'email': 'twagner@example.org',
    'phone_number': '001-573-466-4893x66062',
    'array_int_dynamic': [
    15567,
],
    'array_varchar_dynamic': [
    'Meredith Johnson',
    'Ronald Waters',
    'Katherine Johnson',
    'Alejandro Mills',
    'Richard Peterson',
    'Daniel Crawford',
],
    'json': {
    'name': 'Brandon Jackson',
    'address': '87357 Charles Wells\nMcdanielbury, IA 55587',
},
    'key47054': 'value97894',
    'key62142': 'value69496',
    'key29476': 'value43400',
    'key68678': 'value63396',
    'key73328': 'value16770',
    'key97398': 'value49217',
    'key83385': 'value43849',
    'key28486': 'value42600',
    'key63658': 'value71546',
    'key5338': 'value99655',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 16,
    'name': 'Joseph Henderson',
    'address': '745 James Creek\nLeonardfort, SC 25041',
    'text': 'Approach lay fire important. Theory shoulder something step. Brother cell marriage tonight find challenge.\nKind truth site what toward movie notice week. Attack lay way light Mrs until.',
    'email': 'annette71@example.com',
    'phone_number': '+1-551-954-5374x344',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Kelli Sims',
    'Bradley Barry',
    'Henry Williams',
    'Karen Mendez',
    'Jeffrey Alvarez',
    'Amanda Roberts',
    'April Fisher',
    'Joseph Jensen',
    'John Robinson',
],
    'json': {
    'name': 'Jennifer White',
    'address': '58035 Shane Estate Suite 067\nWest Johnfurt, RI 33678',
},
    'key34142': 'value64476',
    'key47608': 'value59807',
    'key98117': 'value23253',
    'key34694': 'value51015',
    'key75110': 'value73550',
    'key95255': 'value76831',
    'key36052': 'value56098',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 17,
    'name': 'Emma Black',
    'address': '62625 Brendan Stream Suite 879\nNorth Jamesside, NV 09640',
    'text': 'Seek onto best court. Order pull after drive.\nWrong writer know open eight. Education later professor specific. Seek parent spend factor.\nCompare field others drop turn. Ten image myself cultural.',
    'email': 'christophergeorge@example.com',
    'phone_number': '5123651748',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'William Olson',
    'Bernard Howard',
],
    'json': {
    'name': 'Robert Eaton',
    'address': '553 Griffith Manors Apt. 167\nWest Rachelside, AS 34552',
},
    'key32802': 'value50683',
    'key85804': 'value81305',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 18,
    'name': 'Nicholas Clements',
    'address': '218 Simmons Ports\nNew Mary, OH 65573',
    'text': 'Stage simply growth once tend sign shake. Bring kind red service woman reveal least.\nTime everyone foreign condition respond. Writer bring central allow try generation health.',
    'email': 'ryanmurphy@example.org',
    'phone_number': '(481)834-2714',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Jeffrey Barber',
    'Dale Mcknight',
    'Annette Long',
    'Joseph Thompson',
    'Ian Campbell',
    'James Mclaughlin',
    'Meredith Yang',
    'Edwin Neal',
    'Chase Koch',
],
    'json': {
    'name': 'Jeanette Sanchez',
    'address': 'PSC 1908, Box 9068\nAPO AA 59962',
},
    'key25176': 'value12580',
    'key35643': 'value58584',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 19,
    'name': 'Ashley Frederick',
    'address': 'USNV Holt\nFPO AP 95343',
    'text': 'Determine interesting guy evidence student enough. Task off whole year get. Idea majority half.\nSubject evening detail sit finally. Skill memory like activity mention than. Able economic life.',
    'email': 'cindygonzalez@example.net',
    'phone_number': '(417)691-0839x2495',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Diane Daniel',
    'Ashley Clark',
],
    'json': {
    'name': 'Teresa Morris',
    'address': '92786 Black Trail Suite 366\nWest Carlosland, IN 78726',
},
    'key2492': 'value79070',
    'key59177': 'value5379',
    'key64546': 'value98054',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 20,
    'name': 'Steven Davis',
    'address': '11463 Barbara Summit Suite 160\nTanyaview, OR 16268',
    'text': 'Road brother benefit. Maintain list work father agent space appear.\nAble lot of name. Former increase whom guy shoulder. Indicate join boy station husband place.',
    'email': 'watsongarrett@example.com',
    'phone_number': '972.309.0030x201',
    'array_int_dynamic': [
    35179,
],
    'array_varchar_dynamic': [
    'Steve Copeland',
    'Zachary Newton',
    'Jaclyn Baker',
    'Courtney Dorsey',
],
    'json': {
    'name': 'Jennifer Phillips',
    'address': '296 Pitts Islands Apt. 331\nNew Stephen, WY 50035',
},
    'key55916': 'value44026',
    'key979': 'value84400',
    'key66105': 'value51640',
    'key38140': 'value28128',
    'key87391': 'value40159',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 21,
    'name': 'Omar Owens',
    'address': '8151 Anna Lock\nLake Laurenberg, VA 72802',
    'text': 'Full skill still sport after measure. Our sense computer from. Cover use enter full.\nThird money cold magazine with begin. Seven impact maybe stand eye maintain top power.',
    'email': 'dukebrian@example.com',
    'phone_number': '4405410021',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Katherine West',
    'Phyllis Conner',
    'Luke Golden',
    'Jeremy Arnold',
    'Laura Munoz',
    'Harry Ingram',
    'April Smith',
    'William Mills',
],
    'json': {
    'name': 'David Freeman',
    'address': '819 Amy Via Apt. 529\nLake Gilbertbury, MP 86737',
},
    'key75959': 'value73010',
    'key43642': 'value28341',
    'key86772': 'value61869',
    'key48793': 'value65394',
    'key68243': 'value30995',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 22,
    'name': 'Jason Richards',
    'address': '90703 White Ridge\nPort Erica, MP 98141',
    'text': 'Inside decade matter organization sister plan meeting why. Available hair surface finally free test five.',
    'email': 'bonnie73@example.org',
    'phone_number': '(664)283-0559',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Luis Lang',
    'David Mitchell',
    'Linda Hurst',
    'Victoria Holden',
],
    'json': {
    'name': 'Joel Brown',
    'address': '1718 Brian Crossroad Apt. 924\nSouth Sherylburgh, KY 95888',
},
    'key16215': 'value83659',
    'key59741': 'value9477',
    'key90018': 'value48826',
    'key82061': 'value37773',
    'key9682': 'value28230',
    'key7769': 'value65017',
    'key94762': 'value35896',
    'key13623': 'value43436',
    'key88290': 'value23259',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 23,
    'name': 'Jaime Rodriguez',
    'address': '10546 William Estate\nCherylstad, LA 46765',
    'text': 'Idea rich half. Year product figure focus past strong. That want answer.\nPosition my significant whom town likely public. American action vote result international race explain.',
    'email': 'melinda55@example.net',
    'phone_number': '664.271.3004x0828',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Steven Farley',
    'Kristin Simpson',
    'Jacob Palmer',
],
    'json': {
    'name': 'John Jordan',
    'address': 'Unit 8566 Box 6840\nDPO AA 10325',
},
    'key45716': 'value60349',
    'key12491': 'value45101',
    'key78179': 'value61374',
    'key83830': 'value41095',
    'key97002': 'value15370',
    'key40958': 'value60441',
    'key66850': 'value64414',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 24,
    'name': 'Marcia Mullen',
    'address': '052 Carlos Row Suite 339\nNorth Steve, DE 88551',
    'text': 'Small read ahead great new mission. Help experience out room since receive.\nAdmit half condition direction. Professor executive yard billion hard evidence. Leg project time bank.',
    'email': 'katherine18@example.net',
    'phone_number': '305.249.2624',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Mr. Harry Rogers',
],
    'json': {
    'name': 'Carol Elliott',
    'address': '447 Bonnie Meadow\nPerezshire, MO 56250',
},
    'key11522': 'value70828',
    'key93635': 'value98126',
    'key61385': 'value43326',
    'key26337': 'value61504',
    'key86248': 'value9399',
    'key81030': 'value78984',
    'key6940': 'value11478',
    'key29371': 'value31447',
    'key49001': 'value37663',
    'key57486': 'value95550',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 25,
    'name': 'Donald Downs',
    'address': '4402 Brian Bypass\nWest David, MI 68312',
    'text': 'High service young entire institution. Two who build possible stuff operation out.',
    'email': 'priscillathomas@example.org',
    'phone_number': '817-728-6891x97670',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Erika Harris',
    'Rita Mendoza',
    'Grace Williams',
    'Brandon Montes',
],
    'json': {
    'name': 'Scott Cook',
    'address': '597 Christine Gateway Suite 117\nNorth Dawnport, OK 06818',
},
    'key1594': 'value75535',
    'key20394': 'value88750',
    'key72091': 'value60797',
    'key74149': 'value59524',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 26,
    'name': 'Nancy Norton',
    'address': '752 Peterson Crescent\nLake Kyle, WI 11685',
    'text': 'Himself inside lot test marriage recent contain simple. All simply two catch reduce ground.',
    'email': 'imedina@example.net',
    'phone_number': '(907)618-4077',
    'array_int_dynamic': [
    96196,
],
    'array_varchar_dynamic': [
    'Michelle Stevens',
    'Trevor Pierce',
    'Karla Armstrong',
],
    'json': {
    'name': 'Jason Booth',
    'address': '0721 Nicole Island Suite 897\nSilvastad, WI 64015',
},
    'key7318': 'value75507',
    'key76274': 'value36032',
    'key33358': 'value82231',
    'key60696': 'value32778',
    'key43770': 'value30728',
    'key73587': 'value84308',
    'key86839': 'value70160',
    'key28270': 'value7790',
    'key12671': 'value22361',
    'key23720': 'value92321',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 27,
    'name': 'Dawn Morrison',
    'address': 'PSC 4552, Box 6166\nAPO AP 04114',
    'text': 'Enjoy series guess board cut.\nFeel event day it pick gun. Operation point value. Blood art after significant oil three. Pattern with identify move it move.',
    'email': 'daniellelopez@example.net',
    'phone_number': '318-675-9676x25091',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Kimberly Rangel',
    'James Turner',
    'Caitlin Haynes',
    'Michael Thomas',
    'Joseph Hudson',
],
    'json': {
    'name': 'Wesley Chung',
    'address': '55018 Keith Port Apt. 186\nSouth Tommy, RI 67663',
},
    'key18777': 'value91519',
    'key60271': 'value22492',
    'key45548': 'value1311',
    'key81010': 'value85772',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 28,
    'name': 'Mariah Ruiz',
    'address': '784 Daniel Views Suite 026\nEast Timothyton, NV 17696',
    'text': 'Our west alone soldier fact plan how many. Account newspaper effect agreement energy.',
    'email': 'ebrown@example.org',
    'phone_number': '+1-821-511-9685x927',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Brian Ewing',
    'James Smith',
    'Michelle Tran',
    'Jonathan Perry',
    'Katherine Ward',
    'David Gentry',
    'Joseph Hernandez',
    'Regina Myers',
    'William Jones',
    'Michael Nguyen',
],
    'json': {
    'name': 'Michael Mathis',
    'address': '08879 Sharon Course\nWest Bryanshire, MT 33505',
},
    'key40991': 'value73495',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 29,
    'name': 'Benjamin Fields',
    'address': '85796 Shannon Turnpike\nNorth Steven, AR 48287',
    'text': 'Bit morning former summer cold statement yard. Color picture by per star father.\nTheory account among within lawyer space. Almost take prove sing while choose up.',
    'email': 'garysalas@example.com',
    'phone_number': '(669)790-0213',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'James Smith',
    'Jane Key',
    'Kyle Smith',
    'Vincent Gilmore',
    'Bryan Garcia',
    'Laura Mueller',
    'Regina Rodriguez',
],
    'json': {
    'name': 'Patrick Jones',
    'address': '324 Darryl Prairie Apt. 745\nLake Annehaven, MA 21713',
},
    'key42554': 'value58127',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 30,
    'name': 'Tasha Holland',
    'address': '4327 Perkins Drive\nGregoryfurt, ID 87439',
    'text': 'Without almost gun fall available indicate set act. Go baby hair bill same campaign term agree.',
    'email': 'jonathanfisher@example.com',
    'phone_number': '4287633053',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Richard Russell',
],
    'json': {
    'name': 'James Stevens',
    'address': '4411 William Crossroad\nHalebury, KS 20879',
},
    'key2469': 'value1918',
    'key67910': 'value51508',
    'key76894': 'value26389',
    'key58961': 'value56298',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 31,
    'name': 'Alan Page',
    'address': '906 Wyatt Lakes Suite 731\nSouth Ryan, ME 49977',
    'text': 'Relationship assume age sound set through day price. Blue realize indeed meeting half tend. Answer race local arrive campaign education hope.\nIts instead my.',
    'email': 'briannavaughn@example.net',
    'phone_number': '001-209-853-9793',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Katie Johnson',
    'Melissa Patterson',
    'Walter Garcia',
    'Kaitlyn Blanchard',
    'Brandy Morrow',
    'Susan Higgins',
    'Brandon Sutton',
    'Allison Burgess',
],
    'json': {
    'name': 'Sharon Hopkins',
    'address': '3958 Pamela Key Apt. 194\nNorth Laurenport, UT 12419',
},
    'key87216': 'value39527',
    'key17184': 'value97650',
    'key78222': 'value12511',
    'key332': 'value47474',
    'key67383': 'value74785',
    'key90291': 'value92554',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 32,
    'name': 'Brittany Mercado',
    'address': 'USCGC Jones\nFPO AA 11671',
    'text': 'Decade dinner source cause meet billion. Center forget safe work note.\nModern eight my least career especially. My onto while environmental Republican. Education financial school.',
    'email': 'garycampbell@example.com',
    'phone_number': '728.848.6657x271',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Leah Webb',
    'Cynthia Smith',
    'Christina Jones',
],
    'json': {
    'name': 'Emily Kelley',
    'address': '31678 Christine Manor Apt. 743\nReginaberg, NM 85828',
},
    'key20852': 'value34409',
    'key57025': 'value67009',
    'key91925': 'value40765',
    'key38038': 'value54336',
    'key47712': 'value44600',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 33,
    'name': 'Elizabeth Reid',
    'address': '50443 Coleman Ports\nNicholasville, GA 72828',
    'text': 'Or mention first up effort maybe executive. Investment model need coach. Every low hard common notice about identify over.',
    'email': 'aprilbush@example.org',
    'phone_number': '271-764-3146x51562',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Colin Riley',
    'Robert Williams',
    'Roger Williams',
    'Darlene Munoz',
    'Jeremiah Zamora',
    'Priscilla Hernandez',
    'Kaitlyn Lee',
    'Maxwell Wilcox',
    'Carolyn Lynch',
],
    'json': {
    'name': 'Kimberly Zamora',
    'address': '4171 Johnson Trail\nPort Thomasburgh, MS 53676',
},
    'key15961': 'value5827',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 34,
    'name': 'Derek Kramer',
    'address': 'USCGC Joyce\nFPO AP 87007',
    'text': 'Fast rather laugh call approach run change situation. Finally another knowledge. Effect section third buy how resource more high. Street fly rather movement operation knowledge final.',
    'email': 'petersonjulie@example.net',
    'phone_number': '862.340.9855x6616',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Yolanda Hicks',
    'Savannah Barton',
],
    'json': {
    'name': 'Robert Vasquez',
    'address': '47770 Peter Vista Apt. 490\nPort Cheyenneburgh, IL 71670',
},
    'key59990': 'value63910',
    'key5654': 'value67526',
    'key22127': 'value35915',
    'key74108': 'value22298',
    'key98555': 'value90327',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 35,
    'name': 'Sara Dalton',
    'address': '4109 Chan Spurs Apt. 130\nRichardsonview, OR 31839',
    'text': 'Personal goal watch factor. Either section how government adult.\nNeed huge rest should month great figure mention.',
    'email': 'frederickrivas@example.net',
    'phone_number': '+1-289-246-3025x78842',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jennifer Cooper',
    'Zachary King',
    'Jennifer Murray',
    'Jeremy Richards',
],
    'json': {
    'name': 'Jeffrey Martinez',
    'address': '64842 Teresa Park\nNew Nathan, NM 55331',
},
    'key77864': 'value34481',
    'key95864': 'value2898',
    'key8500': 'value67725',
    'key63522': 'value53209',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 36,
    'name': 'Joseph Wallace',
    'address': '86349 Robinson Drives Apt. 713\nColemanton, SC 21699',
    'text': 'Believe staff believe glass show thousand. Sometimes member young one again how generation. Young look pay. Woman either mean believe claim leg southern.',
    'email': 'karenpeterson@example.net',
    'phone_number': '+1-922-455-7280x1623',
    'array_int_dynamic': [
    54723,
],
    'array_varchar_dynamic': [
    'Jade Webb',
    'Timothy Johnson',
    'Troy Valencia',
    'Diana Miller',
    'Derrick Keller',
    'Timothy Hernandez',
    'Chad White',
    'Angel Farmer',
],
    'json': {
    'name': 'Linda Ruiz',
    'address': '36426 Parsons Viaduct\nSouth Sara, SD 79244',
},
    'key68333': 'value13692',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 37,
    'name': 'Kristen Vasquez',
    'address': '2698 Christopher Crossing Suite 054\nSmithland, KY 90976',
    'text': 'Live describe happy. Society performance again general before each yard fact.\nProcess laugh hair allow. Right civil free.',
    'email': 'belinda04@example.com',
    'phone_number': '388-900-3545',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Joshua Vance',
    'Dakota Parker',
    'John Johnson',
],
    'json': {
    'name': 'Daniel Ruiz',
    'address': '675 William Village\nNorth Dianatown, VI 97568',
},
    'key34833': 'value45587',
    'key20485': 'value90191',
    'key37411': 'value28611',
    'key42795': 'value14865',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 38,
    'name': 'Valerie Hancock',
    'address': '6716 James Mission Apt. 981\nRobertoport, CA 18480',
    'text': 'Product who seek ok compare. Tree power wonder learn study future story.\nTruth officer avoid half. Century certainly music south think. Again address without clearly much front own.',
    'email': 'xcrane@example.com',
    'phone_number': '888-452-3450',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Vicki Castillo',
    'Hunter White',
    'Donald Murray',
],
    'json': {
    'name': 'Richard Carey',
    'address': '84353 Paula Lodge Apt. 152\nLewismouth, GA 67186',
},
    'key81367': 'value67833',
    'key2014': 'value97114',
    'key19081': 'value45618',
    'key79526': 'value14623',
    'key26677': 'value75962',
    'key73549': 'value56404',
    'key76258': 'value13174',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 39,
    'name': 'Anthony Mckinney',
    'address': '7918 Smith Port Apt. 103\nWest Melissashire, AS 92580',
    'text': 'Style weight tree Mr we outside. Expect it eat green itself.\nRange at agreement debate. Meet think manage know account prevent agency land.',
    'email': 'lawrencejustin@example.org',
    'phone_number': '(728)875-7623x046',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Shawna Murphy',
    'Michele May',
    'Heather Robbins',
    'Mitchell Barnett',
    'Rebecca Price',
    'Linda Nelson',
    'Nathan Clark',
    'Christopher Lewis',
    'Ryan Bauer',
    'Dalton Edwards',
],
    'json': {
    'name': 'Amanda White',
    'address': 'PSC 4375, Box 0072\nAPO AP 62415',
},
    'key193': 'value94527',
    'key77913': 'value21041',
    'key54682': 'value84726',
    'key28747': 'value49995',
    'key69194': 'value92085',
    'key1897': 'value76327',
    'key82148': 'value80993',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 40,
    'name': 'Shannon Zamora',
    'address': 'PSC 7059, Box 6852\nAPO AP 75598',
    'text': 'Ask stop young its respond but oil. Deal daughter middle expert. Cold marriage few seem structure just.\nBudget do per. Step various part.',
    'email': 'melaniewright@example.net',
    'phone_number': '247.547.5176x8773',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Tracy Dougherty',
    'Elizabeth Key',
    'Ashley Cruz',
],
    'json': {
    'name': 'Scott Wilkins',
    'address': '6650 James Mountain\nBlankenshipville, SD 03202',
},
    'key74912': 'value36909',
    'key12614': 'value55727',
    'key82941': 'value42186',
    'key97780': 'value50193',
    'key16737': 'value36752',
    'key9984': 'value25216',
    'key74754': 'value10605',
    'key24568': 'value45450',
    'key21981': 'value85151',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 41,
    'name': 'Andrew Hart',
    'address': '538 Charles Prairie Suite 072\nElizabethmouth, TX 22410',
    'text': 'Likely tend floor life research since executive. Budget reach international enjoy lawyer yeah unit that. Job station ask whom today.',
    'email': 'robertharris@example.com',
    'phone_number': '+1-494-880-1891x694',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Erin Boyer',
    'Jerry Harrison',
    'Cynthia King',
    'Mary Frost',
    'Zachary Robinson',
    'Kyle Smith',
    'George Schroeder',
    'Matthew Thompson',
],
    'json': {
    'name': 'Karen Powers',
    'address': '235 Matthew Islands\nAdammouth, DE 30214',
},
    'key64480': 'value42054',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 42,
    'name': 'Brian Holmes',
    'address': '85106 Robinson Crescent Apt. 986\nNorth Darryl, NH 69090',
    'text': 'Next thousand film. Job lead suggest simple.\nAdd site all not. Improve process out.',
    'email': 'powerskelly@example.org',
    'phone_number': '+1-798-750-5294x13190',
    'array_int_dynamic': [
    77026,
],
    'array_varchar_dynamic': [
    'Alexandra Phillips',
    'Marissa Joseph',
    'Paul Tapia',
    'Jon Lee',
    'Justin Williams',
    'Stephanie Knight',
    'Patrick Brown',
    'Jerry Anderson',
],
    'json': {
    'name': 'William Parker',
    'address': '048 Herring Cliffs\nWrightview, MN 72138',
},
    'key18417': 'value61194',
    'key35393': 'value4186',
    'key81610': 'value23389',
    'key38886': 'value3552',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 43,
    'name': 'Taylor Walker',
    'address': '572 Guzman Tunnel Apt. 539\nLake William, MD 82442',
    'text': 'Color wide public. Force we use rich. Summer while class nothing nature bag season.\nPiece capital series. Keep very traditional very reach. Natural both lawyer now call.',
    'email': 'justin67@example.net',
    'phone_number': '9475493300',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Levi Young',
],
    'json': {
    'name': 'Samantha Rodriguez',
    'address': '880 Wilson Square\nSotoview, MO 38396',
},
    'key23975': 'value96156',
    'key4915': 'value54592',
    'key28163': 'value11856',
    'key98314': 'value19194',
    'key66610': 'value12836',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 44,
    'name': 'Andrea Wheeler',
    'address': '34904 Juarez Knolls\nValdezchester, ME 28010',
    'text': 'Help season top occur citizen wide month. Need system other staff sport music set.\nHimself resource international one research nor. Senior everyone house notice manager light those.',
    'email': 'grimeskevin@example.net',
    'phone_number': '001-838-736-7259x78192',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Andrea Murray',
    'Reginald Barton',
    'William Ewing',
    'Sherry Lewis',
],
    'json': {
    'name': 'Anthony Rich',
    'address': '0062 Shepherd Land\nLake Taylormouth, RI 58888',
},
    'key95470': 'value89023',
    'key47907': 'value46516',
    'key93121': 'value72063',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 45,
    'name': 'John Watts',
    'address': '5747 Ryan Crescent Suite 015\nTranhaven, UT 63500',
    'text': 'Baby by director partner but school long. Performance cold woman. East yourself worry perform subject.',
    'email': 'danielvillarreal@example.com',
    'phone_number': '(971)777-7784',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Jared Hoover',
    'Brian Holt Jr.',
    'Donna Williamson',
    'Kevin Green',
    'Andrea Russo',
    'William Lopez',
    'Patrick Clark',
    'Nicole Drake',
],
    'json': {
    'name': 'Katie Bryant',
    'address': '6956 Jennings Expressway\nPort Beth, MI 31877',
},
    'key8358': 'value5489',
    'key81756': 'value22901',
    'key67115': 'value48325',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 46,
    'name': 'Brianna Russell',
    'address': '0766 Jenna Turnpike Apt. 871\nSouth Samuelville, SD 25780',
    'text': 'Team agent with you do. Spend trial image require.\nEnvironment lot possible agency husband question. Air hand per want fire.\nInside in seat single because term else.',
    'email': 'dennisdowns@example.org',
    'phone_number': '8104972956',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Trevor Duncan',
    'Jacob Gray',
    'Michael Medina',
    'Steven Neal',
    'Marissa Clark MD',
    'Ashley Duncan',
    'Gregory White',
    'Troy Norris',
],
    'json': {
    'name': 'Sabrina Wallace',
    'address': '352 Megan Estates\nEast Desireemouth, ME 16647',
},
    'key45987': 'value70829',
    'key68210': 'value59406',
    'key55027': 'value37046',
    'key97926': 'value91930',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 47,
    'name': 'Ashlee Alexander',
    'address': '63016 Wu Club Apt. 512\nSouth Lindsey, ND 47767',
    'text': 'Such information resource allow keep rise despite.\nNever detail same page person. Late picture option low.\nScene and rest claim keep. Source never while Congress.',
    'email': 'xreed@example.com',
    'phone_number': '(964)397-6880',
    'array_int_dynamic': [
    57929,
],
    'array_varchar_dynamic': [
    'Curtis Hogan',
    'Joel Garner',
    'Tammy Johnson',
    'Edward Brown',
    'Nicholas Livingston',
    'Christian Villa',
    'Dennis Green',
    'Gabrielle Flores',
    'Nicholas Mitchell',
    'Susan Wells',
],
    'json': {
    'name': 'William Torres',
    'address': '91409 Sosa Meadows\nEast Roger, NJ 77010',
},
    'key89520': 'value52260',
    'key99845': 'value81842',
    'key52227': 'value44871',
    'key87834': 'value32196',
    'key60514': 'value49641',
    'key6015': 'value14552',
    'key27452': 'value76352',
    'key10218': 'value46928',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 48,
    'name': 'Isaac Gonzales',
    'address': '69973 Michael Shoals Apt. 900\nCaitlinmouth, CA 86752',
    'text': 'Own nor up employee plan. Pretty market four report. Clearly smile describe.\nNorth coach billion instead great current. Apply region save adult view site.',
    'email': 'ortizcarrie@example.org',
    'phone_number': '266-709-1317',
    'array_int_dynamic': [
    6810,
],
    'array_varchar_dynamic': [
    'Kristin Odom',
    'Stephanie Reyes',
    'Benjamin Martinez',
],
    'json': {
    'name': 'Richard Gilmore',
    'address': '98349 Paul Mountain Apt. 787\nWest Molly, MD 65067',
},
    'key14315': 'value69025',
    'key66767': 'value48396',
    'key99665': 'value96490',
    'key70182': 'value15505',
    'key4938': 'value66790',
    'key6184': 'value29737',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 49,
    'name': 'Jesus Thomas',
    'address': '90675 Curry Flat Apt. 555\nPort Howard, FM 21983',
    'text': 'Lead speak himself population try investment capital. Control realize baby off likely maintain. Fund drop effort class nice foot.',
    'email': 'alexisromero@example.com',
    'phone_number': '001-854-796-9036x337',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Cody Ellis IV',
    'Jason Friedman',
],
    'json': {
    'name': 'Mr. Albert Dixon',
    'address': '795 Martinez Alley\nLake Daniel, AZ 73567',
},
    'key54818': 'value22733',
    'key48054': 'value75026',
    'key54092': 'value49407',
    'key79472': 'value17358',
    'key34495': 'value97422',
    'key23304': 'value44578',
    'key38558': 'value8676',
    'key59658': 'value14548',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 50,
    'name': 'Bethany Hughes',
    'address': '98096 Bowen Drives Apt. 110\nWest Keithton, OK 26635',
    'text': 'Shoulder present plan. Stop nation but worry Republican report. Nature law ever end subject test whatever.',
    'email': 'brittanycowan@example.com',
    'phone_number': '(330)728-4988',
    'array_int_dynamic': [
    73834,
],
    'array_varchar_dynamic': [
    'Lori Ramos',
    'Peter Luna',
    'Michael Deleon',
],
    'json': {
    'name': 'Catherine Graham',
    'address': 'USS Osborne\nFPO AE 32689',
},
    'key41448': 'value51741',
    'key58060': 'value83346',
    'key84121': 'value64524',
    'key35926': 'value67731',
    'key3956': 'value57545',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 51,
    'name': 'David Kelly',
    'address': '3388 Sanders Wells Apt. 090\nEast Evelynfort, PR 32218',
    'text': 'Particular effect bed create great specific individual. Wear concern far radio speech although.\nScore director prepare daughter Democrat adult. Feeling minute woman car be. Travel growth her worry.',
    'email': 'millerjonathan@example.org',
    'phone_number': '377.545.4384x56645',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Vincent Morton',
    'Andrew Richard',
    'Kathy Maynard',
],
    'json': {
    'name': 'Jasmine Obrien',
    'address': '2749 Keller Hill Suite 902\nBergside, KY 20818',
},
    'key48261': 'value86788',
    'key77732': 'value14938',
    'key78543': 'value73927',
    'key79769': 'value54557',
    'key43274': 'value75952',
    'key31538': 'value8066',
    'key81851': 'value92897',
    'key17492': 'value69208',
    'key794': 'value22433',
    'key21706': 'value14348',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 52,
    'name': 'Amanda Vaughan',
    'address': 'PSC 9729, Box 6725\nAPO AP 04063',
    'text': 'After coach tough require. Wonder wide edge body southern cell then many. Beautiful staff professional yeah institution. Well represent study program simply general house shake.',
    'email': 'markleblanc@example.net',
    'phone_number': '900-945-5787',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Charles Hutchinson',
    'Elizabeth Davis PhD',
],
    'json': {
    'name': 'James Jackson',
    'address': '69600 Jared Plaza Apt. 207\nRussellmouth, MH 93115',
},
    'key37591': 'value98708',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 53,
    'name': 'David Richardson',
    'address': '0978 Angela Trace Suite 387\nFrankburgh, OR 43169',
    'text': 'Fast what Democrat order. Plant perform game west.\nBox cup floor where every budget fight.',
    'email': 'jwilliams@example.com',
    'phone_number': '3026233223',
    'array_int_dynamic': [
    34914,
],
    'array_varchar_dynamic': [
    'Kevin Owens',
],
    'json': {
    'name': 'Allison Smith',
    'address': '13393 Matthew Mount Apt. 254\nLake Josephmouth, MH 48974',
},
    'key16044': 'value30194',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 54,
    'name': 'Roger Wood',
    'address': '5356 Jennifer Ford\nMillermouth, NC 64851',
    'text': 'Dream become stock figure point drop. Should easy write attack painting ten. Dog door state wear language tell.',
    'email': 'wortiz@example.com',
    'phone_number': '+1-368-239-6893x2852',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Daniels',
    'Brian Brown',
    'Michael Williamson',
    'Sierra Miller',
    'Emily Warren',
    'Jeremy Gutierrez',
    'James Buck',
    'Ashley Clark',
],
    'json': {
    'name': 'Kim Cox',
    'address': '71931 Robert Inlet\nRoberttown, ID 20193',
},
    'key47244': 'value67948',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 55,
    'name': 'Penny Williams',
    'address': '1476 Jerome Extension\nMezaville, SD 65101',
    'text': 'Right movement enough treatment worry. Any right financial hit last quite. Key local federal foreign go minute here.',
    'email': 'michaelhamilton@example.com',
    'phone_number': '+1-917-778-7749x24949',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Jamie Hammond',
],
    'json': {
    'name': 'Andrew Smith',
    'address': '68742 Stevenson Meadow Apt. 545\nNorth Thomas, MT 87403',
},
    'key82378': 'value13920',
    'key97987': 'value16976',
    'key68957': 'value51199',
    'key81793': 'value54484',
    'key42650': 'value39582',
    'key76616': 'value9144',
    'key89910': 'value85369',
    'key70352': 'value56716',
    'key59284': 'value94372',
    'key86073': 'value86515',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 56,
    'name': 'Donald Farmer',
    'address': '545 Victoria Point Apt. 674\nVirginiachester, VT 19891',
    'text': 'Play provide television strategy just. Including interesting ask identify wrong I. Ability war treat relate know understand list.',
    'email': 'joseph22@example.net',
    'phone_number': '563-845-0245',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Victoria Walton',
    'Anthony Rios',
    'Carol Stanley',
],
    'json': {
    'name': 'James Perez',
    'address': '78307 Adams Plaza Suite 714\nEast Cristinaport, CA 59398',
},
    'key56268': 'value56935',
    'key37770': 'value6073',
    'key25559': 'value60858',
    'key79467': 'value99443',
    'key66601': 'value4501',
    'key39754': 'value30747',
    'key59258': 'value53200',
    'key86504': 'value85769',
    'key6948': 'value69320',
    'key96665': 'value26981',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 57,
    'name': 'Nathaniel Palmer',
    'address': '065 Decker Islands\nAaronshire, LA 50079',
    'text': 'Himself need lead his woman new. Player somebody free once us. Avoid mention sign together know growth result.',
    'email': 'annette22@example.net',
    'phone_number': '744.368.1882x280',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Christina Booker',
    'Andrea Navarro',
    'Michelle Gonzalez',
],
    'json': {
    'name': 'Jason Boyd',
    'address': '87558 Jesse Gardens\nGregoryport, TN 99092',
},
    'key82597': 'value73947',
    'key95441': 'value79127',
    'key61501': 'value12405',
    'key12961': 'value29748',
    'key13027': 'value19931',
    'key68222': 'value6888',
    'key6100': 'value86101',
    'key94258': 'value78429',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 58,
    'name': 'Tracy Waters',
    'address': '573 Forbes Wells\nNorth Nancymouth, DC 85644',
    'text': 'While seat without let clearly. Else simply society opportunity news require put. When challenge nearly small deep research admit general.',
    'email': 'kevinjohnson@example.net',
    'phone_number': '382.484.7147x850',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Rebecca Mercado',
    'Allison Bates',
],
    'json': {
    'name': 'Wanda Hernandez',
    'address': '854 Wilcox Pass\nAdamstown, ME 85156',
},
    'key38068': 'value69949',
    'key91621': 'value13209',
    'key89052': 'value4045',
    'key3340': 'value83536',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 59,
    'name': 'Sean Campbell',
    'address': 'PSC 3094, Box 9511\nAPO AA 55354',
    'text': 'Bar left especially. Hope he last share. Garden about our impact world listen. Trip poor his eye reason develop.\nCulture book record in. Poor accept after want eat but.\nTurn evidence ready point.',
    'email': 'gonzalezamanda@example.com',
    'phone_number': '+1-796-219-1585x92842',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'William Herring',
    'Brandi Collins',
    'Matthew Murphy',
],
    'json': {
    'name': 'Linda Saunders',
    'address': '717 Patterson Crossing Apt. 070\nPort Crystal, OK 24896',
},
    'key25555': 'value49532',
    'key28192': 'value81876',
    'key6990': 'value28930',
    'key77727': 'value57728',
    'key33049': 'value70918',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 60,
    'name': 'Laurie Burton',
    'address': '483 Ann Skyway Apt. 069\nChristopherville, AK 94260',
    'text': 'Force step pressure. Out town city. Culture baby away deep sign.\nWestern deep determine majority late. Avoid measure on structure develop some work. True paper floor along simply draw.',
    'email': 'etaylor@example.org',
    'phone_number': '+1-503-805-3912x98475',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Barnes',
    'Donna Mooney',
    'Jason Green',
    'Megan Carey',
    'Meghan Johnston',
    'Daniel Peters',
    'Dr. Willie Stanton',
    'James Morrison',
    'Jeffery Cox',
],
    'json': {
    'name': 'Tammy Miller',
    'address': '38033 Kelly Wells\nEast Amy, NC 56944',
},
    'key59622': 'value20038',
    'key73139': 'value19212',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 61,
    'name': 'Karen Smith',
    'address': 'USNV Hutchinson\nFPO AA 03674',
    'text': 'Join usually enjoy parent hope policy share. Recently keep box beyond drive yard. Between white its ability. Difference often field.',
    'email': 'mramirez@example.net',
    'phone_number': '7252745715',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Samuel Campbell',
    'Michael Adams',
    'Steven Castro',
],
    'json': {
    'name': 'Blake Valentine',
    'address': '274 Carlos Turnpike Suite 819\nDavisview, TN 89569',
},
    'key88754': 'value47713',
    'key2387': 'value81308',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 62,
    'name': 'Edward Krueger',
    'address': '26701 Nelson Forest Suite 655\nLake Gabriella, PW 33485',
    'text': 'Popular street responsibility benefit easy it feel. Safe certainly small poor federal training expect society.\nWorld participant another drop leave family inside. Involve according beautiful now.',
    'email': 'johnmiller@example.org',
    'phone_number': '(539)722-5693x50006',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Michael Velasquez',
    'Aaron Glass',
    'Mrs. Makayla Nelson DVM',
    'William Thomas',
    'Ann Whitaker',
    'Joshua Velasquez',
    'Sandra Barrera',
],
    'json': {
    'name': 'Kelly Cummings',
    'address': '979 Rhonda Mountain\nWest Amberville, DE 25844',
},
    'key93980': 'value33162',
    'key83572': 'value20617',
    'key41952': 'value36813',
    'key12207': 'value71984',
    'key22546': 'value74851',
    'key94089': 'value59641',
    'key44273': 'value27552',
    'key85329': 'value34118',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 63,
    'name': 'Jenna Boyle',
    'address': '911 Adam Fall Apt. 702\nWest Michele, HI 55805',
    'text': 'Remember quite international fire as. Example road item.\nOften live many true usually. Onto who economic much who everything threat necessary. Walk PM Republican weight degree visit.',
    'email': 'owensjason@example.net',
    'phone_number': '328.912.0350x5979',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Melissa White MD',
    'Nicole Walker',
    'Robert Thomas',
],
    'json': {
    'name': 'Nichole Flowers',
    'address': '6845 Moran Crossroad Suite 315\nMartinhaven, PA 76703',
},
    'key11026': 'value6164',
    'key39061': 'value24681',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 64,
    'name': 'Andrea Williams',
    'address': 'Unit 1113 Box 8620\nDPO AE 10030',
    'text': 'Card machine up simple side value investment. Evening they daughter resource.',
    'email': 'lreed@example.com',
    'phone_number': '001-908-428-1257x0411',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'John Saunders',
    'Andrew Davies',
    'William Garrison',
    'Hannah Cooper',
    'Shelby Sampson',
],
    'json': {
    'name': 'Maria Guerrero',
    'address': '5250 Norton Union\nSouth Martin, SD 43901',
},
    'key40781': 'value98582',
    'key72457': 'value62959',
    'key72228': 'value27111',
    'key40999': 'value65302',
    'key26523': 'value45849',
    'key89579': 'value62661',
    'key94075': 'value63765',
    'key98398': 'value32815',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 65,
    'name': 'Megan Rivers',
    'address': '63991 Barnes Lane Apt. 947\nScottmouth, FL 06104',
    'text': 'Treat his ball different even accept hear. Your direction according magazine executive near mission word.',
    'email': 'thompsontina@example.net',
    'phone_number': '001-827-570-0404x937',
    'array_int_dynamic': [
    13318,
],
    'array_varchar_dynamic': [
    'Kristie Manning',
    'Katherine Gonzalez',
    'Tiffany Sparks',
    'Marissa Sawyer',
    'Matthew Beck',
    'Amy Burgess',
    'Shawn Fernandez',
    'Carl Brown',
    'Kyle Ramos',
    'Jessica Turner',
],
    'json': {
    'name': 'Ann Young',
    'address': '5563 Amber Key Suite 335\nLake Neil, UT 70111',
},
    'key85396': 'value92794',
    'key87804': 'value16448',
    'key69964': 'value92977',
    'key77207': 'value54287',
    'key94320': 'value2348',
    'key85456': 'value1048',
    'key29396': 'value8250',
    'key44012': 'value70637',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 66,
    'name': 'Kerry Price',
    'address': '012 Kennedy Mount\nEast Travisside, OK 66867',
    'text': 'Whether serious tree his forward join. Letter order young recognize course bring beautiful interesting.',
    'email': 'hdorsey@example.net',
    'phone_number': '+1-295-441-1829x656',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Robin Webb',
    'Stephen Reed',
    'Lindsay Rodriguez',
    'Susan Johnston',
    'Laurie Edwards',
    'Allison Foster',
],
    'json': {
    'name': 'Robert Richardson',
    'address': 'PSC 8106, Box 2021\nAPO AA 36836',
},
    'key72376': 'value98789',
    'key61535': 'value61650',
    'key15137': 'value9371',
    'key19562': 'value36171',
    'key54236': 'value26719',
    'key11288': 'value70232',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 67,
    'name': 'Andrea Lane',
    'address': 'PSC 9449, Box 9203\nAPO AA 43204',
    'text': 'Ground effort anything source book. Remember street side ball.\nFine wife study account material. School night culture think.',
    'email': 'jonesmarcus@example.net',
    'phone_number': '243-413-2355',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Clark',
    'James Macias',
    'Fernando Lopez',
    'Heather Butler',
    'Michael Wilson',
    'Abigail Dawson',
    'Christopher Evans',
    'Victoria Smith',
    'Gilbert Bell',
],
    'json': {
    'name': 'Betty Hebert',
    'address': '4843 Holt Streets\nSouth Mary, GA 89156',
},
    'key18412': 'value29781',
    'key51708': 'value40306',
    'key99565': 'value54710',
    'key18382': 'value3361',
    'key8089': 'value71268',
    'key54332': 'value82616',
    'key61762': 'value51365',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 68,
    'name': 'Tyler Garcia',
    'address': '775 Mason Trail\nEmilyburgh, GA 08605',
    'text': 'Painting bank organization even individual show protect tree. Important land tonight quite chance.\nSite tax child this record drug coach. Too space executive.',
    'email': 'christophertaylor@example.com',
    'phone_number': '254-306-7244x62260',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Henry Fox',
    'Joshua Wright',
    'Kristy Cole',
    'Ashley Craig',
    'Joseph Spencer',
    'Sean Lane',
    'Carrie Baker',
],
    'json': {
    'name': 'Jacqueline Ayala',
    'address': '28155 Joseph Lane\nBryanchester, WA 30912',
},
    'key55139': 'value89435',
    'key92828': 'value59060',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 69,
    'name': 'Ronald Stewart',
    'address': '456 Johnson Mill\nNorth Brandy, TN 33536',
    'text': 'Position would television party oil hundred structure. Court important option open step yard. Begin address official protect.',
    'email': 'clarkbryan@example.com',
    'phone_number': '769-320-2998',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Michelle Ellis',
    'Hailey Long',
    'Joseph Delacruz',
    'Bryan Mcclain',
    'Kelly Martin',
    'Jonathan White',
    'Nicole White',
],
    'json': {
    'name': 'Gregory Davis',
    'address': '79933 Bush Well Suite 023\nDanielhaven, FM 27355',
},
    'key78140': 'value37737',
    'key73183': 'value41574',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 70,
    'name': 'Jasmine Flowers',
    'address': '11295 Joseph Knolls\nNorth Crystalbury, MT 27642',
    'text': 'Interesting action ok rest maybe whom later. Hundred clear seven seek evidence.\nFull force full huge card. Current official agreement exist toward.',
    'email': 'joneselizabeth@example.org',
    'phone_number': '9709377882',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Thomas Soto',
],
    'json': {
    'name': 'Julie Hayes',
    'address': '33984 Anderson Spurs\nSouth Wandaport, GU 67913',
},
    'key41226': 'value39923',
    'key18635': 'value41883',
    'key82847': 'value69778',
    'key27554': 'value17675',
    'key5343': 'value89461',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 71,
    'name': 'Nicole Murray',
    'address': '12460 Michelle Village\nWest Nicholasville, MT 09670',
    'text': 'Remain still that. Financial Mr team source walk institution hard visit. Couple become us baby design long around.',
    'email': 'ethompson@example.net',
    'phone_number': '001-552-258-3742x87650',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Victor Ortiz',
    'Larry Livingston',
    'Madeline Baker',
    'Aaron Moore',
],
    'json': {
    'name': 'Brittany Mcdonald',
    'address': '9680 Valerie Port Suite 904\nMichealville, SC 13959',
},
    'key62519': 'value12722',
    'key73116': 'value49797',
    'key72594': 'value55322',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 72,
    'name': 'Jennifer Ferguson',
    'address': '089 Rivera Plains Suite 863\nRobertsonview, NM 97513',
    'text': 'Find herself right sign these sit course. News evidence benefit bank nice. Yeah open kind standard position road read.',
    'email': 'ibrown@example.net',
    'phone_number': '387-765-9766',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'David Morales',
    'Emily Cook',
    'Jeffrey Smith',
    'Carol Bauer',
    'Michelle Rose',
    'William Welch',
    'Lisa Smith',
],
    'json': {
    'name': 'Kevin King',
    'address': '7023 Anderson Isle Apt. 317\nThomasland, CT 79343',
},
    'key92687': 'value77844',
    'key49376': 'value94110',
    'key78045': 'value60892',
    'key51746': 'value91048',
    'key11307': 'value70792',
    'key47521': 'value56452',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 73,
    'name': 'Nicole Crawford',
    'address': '594 Alexis Corners\nBuchanantown, WA 48423',
    'text': 'Car use risk among throughout.\nAgency push fine clearly growth else population hot. Senior it service season only. Agency drop occur carry pressure control treatment.',
    'email': 'ecompton@example.com',
    'phone_number': '3262438701',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Stephanie Martinez',
    'Gina Chaney',
    'Patrick Tran',
],
    'json': {
    'name': 'Natasha Thomas',
    'address': 'Unit 7783 Box 8454\nDPO AE 53071',
},
    'key96652': 'value43757',
    'key78546': 'value53253',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 74,
    'name': 'Mary Jensen',
    'address': '63440 John Shoals Apt. 584\nLanetown, DE 80330',
    'text': 'So lawyer show south heart important. Reason number someone college.',
    'email': 'allison38@example.net',
    'phone_number': '372.318.6511x28416',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Kristie Garcia',
    'Katie Glover',
    'Donald Reeves',
    'Anthony Moore',
],
    'json': {
    'name': 'Crystal Lopez',
    'address': '8892 Kimberly Shore\nEast Maria, AK 12439',
},
    'key34963': 'value92516',
    'key41569': 'value54886',
    'key44750': 'value43394',
    'key69236': 'value40704',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 75,
    'name': 'Jeff Gomez',
    'address': 'Unit 5700 Box 4493\nDPO AE 45877',
    'text': 'Drop build rock summer buy six. Mission month might car three either report wind. Until perhaps model media.',
    'email': 'millsjulia@example.net',
    'phone_number': '+1-739-338-9987x72142',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Andrea Miller',
    'Chloe Shaffer',
    'Geoffrey Taylor',
    'Natalie Browning',
    'Brett Villarreal',
    'Scott Thompson',
    'Heidi Jackson',
    'Samuel Klein',
    'Colleen Davis',
],
    'json': {
    'name': 'Robert Perkins',
    'address': '488 Miller Junctions\nSouth Patriciamouth, LA 36476',
},
    'key14145': 'value41523',
    'key96595': 'value52',
    'key7881': 'value56367',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 76,
    'name': 'Robert Moreno',
    'address': '91906 Smith Stream Suite 596\nPort Eric, AL 62066',
    'text': 'Day wall expert Republican anyone.\nAdd example our. Little how question. Movement high bag field movie street conference.',
    'email': 'dakotatapia@example.com',
    'phone_number': '(420)951-4763x6480',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=6, normalized=True),
    'array_varchar_dynamic': [
    'Justin Callahan',
    'Robert Waters',
    'Nicole Shaw',
    'Michelle Odonnell',
    'Jesus Lowe',
    'Adam Wilkerson',
    'Autumn Maddox',
    'Michele Lucas',
    'Denise Wolfe',
    'Erik Williams',
],
    'json': {
    'name': 'Kimberly Willis',
    'address': '571 Karen Crossroad Suite 333\nCalvinchester, GA 90925',
},
    'key833': 'value4517',
    'key99591': 'value43963',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 77,
    'name': 'Amanda Daniel',
    'address': '62756 Brianna Island Apt. 230\nLewisfurt, ME 79196',
    'text': 'Collection factor like place action treatment. Act author become. Support summer add major.\nFollow notice but successful their myself medical. Church talk hand great onto.',
    'email': 'joneskathryn@example.com',
    'phone_number': '(235)617-8060x7031',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Monique Lowe',
    'Katie Wiggins',
    'Stacey Bauer',
    'Lisa Malone',
    'Kelly Stanley',
    'Jean Anderson',
    'Cheryl Price',
    'Abigail Rios',
    'Gabriela Franco',
    'Kimberly Glover',
],
    'json': {
    'name': 'Ashley Marshall',
    'address': '8037 Tonya Via\nNew Brittany, WA 40150',
},
    'key50333': 'value91989',
    'key34323': 'value68803',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 78,
    'name': 'Kevin Lowe',
    'address': '274 Henry Passage Suite 284\nSouth Troy, MH 63309',
    'text': 'Loss investment serve under almost hold party need.\nFact live goal book impact news support. Necessary represent discuss east finally save. People say school drop start woman.',
    'email': 'shaunbrady@example.com',
    'phone_number': '7965992051',
    'array_int_dynamic': [
    39324,
],
    'array_varchar_dynamic': [
    'Whitney Davis',
    'Michael Evans',
    'Jordan Jimenez',
    'Jaime Lucas',
    'Bobby Camacho',
    'Janet Moore',
    'Karen Mendez',
    'Mark Jackson',
],
    'json': {
    'name': 'Maurice Berry',
    'address': '9665 Young Shore Suite 445\nWest Jennifer, WI 83751',
},
    'key36529': 'value1712',
    'key45835': 'value13446',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 79,
    'name': 'Trevor Briggs',
    'address': '59214 Murray Grove\nNorth Tammy, MS 45303',
    'text': 'I everything keep whole top sense. Star PM try threat course third. Trip pick price since peace.',
    'email': 'vdunn@example.org',
    'phone_number': '001-513-334-0353x2320',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=2, normalized=True),
    'array_varchar_dynamic': [
    'Christina Gray',
    'Paige Avila',
    'Frank Lee',
    'Zachary Elliott',
    'Alexis Shaffer',
    'Wendy Scott',
],
    'json': {
    'name': 'Monica Scott',
    'address': '41419 Nicole Fort Apt. 871\nWest Shawn, NE 72136',
},
    'key49379': 'value7222',
    'key4316': 'value89478',
    'key2441': 'value31795',
    'key12437': 'value47952',
    'key72502': 'value13063',
    'key7348': 'value55524',
    'key82361': 'value53178',
    'key13359': 'value67069',
    'key59097': 'value80452',
    'key68718': 'value54286',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 80,
    'name': 'Amber Watson',
    'address': '5891 Marcus Light\nNew Brandonland, CT 00512',
    'text': 'Begin red work phone while risk. Central care cup form as. Grow federal cover action.\nHot establish will suggest draw. Organization require performance difference low.',
    'email': 'cpatterson@example.org',
    'phone_number': '+1-278-797-9211x0691',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Ashley Juarez',
    'Meghan Stephens',
    'Zachary Bates',
    'Diana Browning',
    'Carolyn Padilla',
    'Tiffany Clark',
],
    'json': {
    'name': 'Jasmine Walker DVM',
    'address': '871 Miranda Forks\nKimchester, IL 17318',
},
    'key50195': 'value8359',
    'key19352': 'value22960',
    'key9769': 'value51657',
    'key20808': 'value64403',
    'key76435': 'value62207',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 81,
    'name': 'Megan Adams',
    'address': '648 Robert Ridges\nJonathanland, NV 95046',
    'text': 'Treatment for force safe spend. Claim left almost throw note hope. Dog bad wide thought yard admit.\nCollege red avoid attorney. Impact total turn require detail.',
    'email': 'stephensalex@example.com',
    'phone_number': '(522)925-8386',
    'array_int_dynamic': [
    3025,
],
    'array_varchar_dynamic': [
    'Arthur Castaneda',
    'Leslie Bird',
    'Stephanie Garcia',
    'Tanya Rodriguez',
    'Ruben Dominguez',
    'Lori Howard',
    'Brenda Martinez',
    'Mary Hayes',
    'Corey Moon',
],
    'json': {
    'name': 'Jason Banks',
    'address': '5393 Edwards Loaf\nPort Susanville, AK 53878',
},
    'key83283': 'value472',
    'key83895': 'value66374',
    'key54081': 'value66118',
    'key92187': 'value86570',
    'key4409': 'value26022',
    'key51053': 'value4629',
    'key99752': 'value60850',
    'key52858': 'value15552',
    'key23358': 'value30637',
    'key90606': 'value9692',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 82,
    'name': 'Tammy Jennings',
    'address': '15005 Sanchez Valley Apt. 297\nNew Ashleystad, PR 30249',
    'text': 'Probably consumer different central forward significant. Factor coach pay stay bar Republican even.',
    'email': 'padillamegan@example.org',
    'phone_number': '+1-334-341-6702x6510',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=3, normalized=True),
    'array_varchar_dynamic': [
    'Ronald Patterson',
    'Paul Navarro',
    'Luis Hayes',
    'Jenna Davis',
],
    'json': {
    'name': 'Brenda Andrews',
    'address': '93896 Dean Villages\nAdamton, SC 84170',
},
    'key37040': 'value4450',
    'key12411': 'value2731',
    'key25453': 'value30152',
    'key23903': 'value94440',
    'key47754': 'value35830',
    'key39366': 'value57170',
    'key16209': 'value84471',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 83,
    'name': 'Brandon Stout',
    'address': '7221 Kim Path Apt. 953\nSouth Andrew, KY 38749',
    'text': 'Sea set serious ready form. Claim father old subject book road it. Suddenly rich company argue carry region fine.\nSeven lead hundred open. Learn message industry support describe hope bad.',
    'email': 'clementsbrian@example.org',
    'phone_number': '+1-339-237-6509x64562',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Nancy Johnson',
    'Diana Berg',
    'Ruth Mcconnell',
    'Michael Willis',
    'Sheila White',
    'Kevin Williams MD',
    'Gregory Gutierrez',
    'Patrick Harris',
],
    'json': {
    'name': 'Cameron Bridges',
    'address': '47269 Miller Wall Suite 687\nPort Davidton, VT 54234',
},
    'key37195': 'value9094',
    'key94328': 'value39117',
    'key24520': 'value97759',
    'key99060': 'value92238',
    'key15': 'value64104',
    'key72168': 'value69921',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 84,
    'name': 'Dr. Wendy Anderson',
    'address': '159 Simmons Terrace\nWest James, AL 39179',
    'text': 'As service not look morning which. Effect new force land south owner hair.',
    'email': 'sharonbutler@example.net',
    'phone_number': '(976)470-6185',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Austin Nelson',
    'Jacob Rodriguez',
    'Todd Silva',
    'Jessica Page',
    'John Garcia',
    'Elizabeth Campbell',
],
    'json': {
    'name': 'Amanda Griffin',
    'address': '3277 Rivas Road Apt. 263\nJacksonburgh, WA 86753',
},
    'key22437': 'value1826',
    'key84900': 'value26021',
    'key56008': 'value81513',
    'key21147': 'value40116',
    'key69983': 'value15547',
    'key43024': 'value79448',
    'key86365': 'value97717',
    'key22319': 'value89952',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 85,
    'name': 'Heather Hansen',
    'address': '4196 Randall Circles Suite 438\nNashstad, NC 15036',
    'text': 'Order ok start down or. Majority control party weight rich free west owner.\nConference top southern reflect natural debate notice. Friend weight until generation campaign adult debate throw.',
    'email': 'yguzman@example.org',
    'phone_number': '495.407.8417x8938',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Randy Clark',
],
    'json': {
    'name': 'Evan Wilson',
    'address': '9477 Kimberly View Suite 835\nJohnsonshire, ND 03081',
},
    'key90727': 'value57642',
    'key54585': 'value28165',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 86,
    'name': 'Arthur Allen',
    'address': '54597 Amy Passage Apt. 579\nPort Barrymouth, MS 02332',
    'text': 'Tree probably close protect beyond. Face ask pass left.\nSometimes color box I.\nFirm safe human enough. Expert room walk security be.',
    'email': 'jenniferjohnson@example.com',
    'phone_number': '001-895-367-9187x6339',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Derrick Schultz',
    'Dawn Price',
    'Michael Smith',
    'Scott Bell',
    'Ann Howard',
],
    'json': {
    'name': 'Jerry Taylor',
    'address': '274 Melissa Club\nWest Lisa, NV 08143',
},
    'key39264': 'value29028',
    'key97513': 'value78697',
    'key41804': 'value54805',
    'key80009': 'value55371',
    'key14527': 'value57161',
    'key74979': 'value53599',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 87,
    'name': 'Virginia Alexander',
    'address': 'PSC 3030, Box 5922\nAPO AA 34770',
    'text': 'Figure over big training seem smile already. Owner far bad majority.\nAudience half support yeah civil task give. Force ask enjoy present decade medical strong. Market cup main factor.',
    'email': 'marylogan@example.net',
    'phone_number': '822-859-9362',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Bradley Tate',
    'Tony Bautista',
    'Hannah Schultz',
    'Kelly Pollard',
],
    'json': {
    'name': 'Paul Tanner',
    'address': 'Unit 8606 Box 7929\nDPO AA 73749',
},
    'key42801': 'value10002',
    'key75038': 'value98536',
    'key48522': 'value54588',
    'key56192': 'value13712',
    'key36676': 'value47169',
    'key50976': 'value21665',
    'key46786': 'value21390',
    'key11082': 'value99865',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 88,
    'name': 'Rhonda Huang',
    'address': '666 Maureen Ways\nAndersonhaven, KY 57182',
    'text': 'Memory girl second student begin. Society could age prove apply through. Cut current arrive institution station baby.\nPersonal area real TV nor move forget. Suggest watch until.',
    'email': 'robert65@example.net',
    'phone_number': '+1-910-273-5369x28936',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'Amanda Green',
    'Sharon Stewart',
    'John Morris',
    'Richard Stewart',
    'Danielle Castillo',
],
    'json': {
    'name': 'Dr. Alexa Valdez MD',
    'address': '91407 Evan Ways Apt. 873\nJamesmouth, OH 71596',
},
    'key11399': 'value31629',
    'key12440': 'value55211',
    'key21480': 'value45642',
    'key62379': 'value39775',
    'key80065': 'value4655',
    'key84788': 'value39853',
    'key23618': 'value52038',
    'key57595': 'value43016',
    'key79956': 'value22084',
    'key18207': 'value30921',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 89,
    'name': 'David Payne',
    'address': 'USCGC Smith\nFPO AA 77203',
    'text': 'Sea seven of defense tax home least.\nOperation her question well worker magazine. During gas think behind sense.',
    'email': 'charles28@example.org',
    'phone_number': '732-373-0704x549',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Tammy Dickerson',
    'Whitney Cowan',
    'Amanda Moore',
    'Vanessa Brandt',
    'John Johnson',
],
    'json': {
    'name': 'Michelle Gomez',
    'address': '575 Sharon Wells Apt. 561\nHunterville, DC 63516',
},
    'key83804': 'value89382',
    'key91522': 'value45494',
    'key40953': 'value41316',
    'key21884': 'value77413',
    'key34510': 'value64825',
    'key89822': 'value78571',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 90,
    'name': 'Brian Henderson',
    'address': '9970 Wilson Manors Apt. 978\nGaryshire, CT 99005',
    'text': 'View bit hour run become she. Sport skin lay prevent ground realize.\nManage research lose that few send. Heavy follow particularly billion.\nSend cell chair hair. Agree play law age current everybody.',
    'email': 'hunterdebra@example.com',
    'phone_number': '001-272-611-5928x2043',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=4, normalized=True),
    'array_varchar_dynamic': [
    'James Villegas',
    'Donald Wilson',
    'Tracey Cruz',
    'Bethany Patterson',
    'Maria Weber',
    'Ryan Miller',
],
    'json': {
    'name': 'Sara Torres',
    'address': '180 David Ridge Suite 722\nJuliahaven, NJ 21494',
},
    'key82228': 'value2565',
    'key35624': 'value79237',
    'key61656': 'value14530',
    'key17027': 'value41409',
    'key24060': 'value50593',
    'key29218': 'value75651',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 91,
    'name': 'David Rodriguez',
    'address': '33340 Kevin Mission\nRuizchester, KS 57855',
    'text': 'Tv once purpose perform. Them every fall economy. Drop fly half concern image try machine.\nThis so beautiful price through play. Value standard point join option.',
    'email': 'nicolejohns@example.net',
    'phone_number': '+1-351-817-1438x01215',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=7, normalized=True),
    'array_varchar_dynamic': [
    'Sarah Harris',
    'Angelica Sullivan',
],
    'json': {
    'name': 'Christopher Obrien',
    'address': '01296 Jones Stream Suite 181\nLake Pamela, AZ 44787',
},
    'key80436': 'value72317',
    'key25340': 'value98331',
    'key46791': 'value87048',
    'key92657': 'value51211',
    'key28103': 'value6032',
    'key12589': 'value55427',
    'key14635': 'value94941',
    'key35473': 'value68762',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 92,
    'name': 'Sherri Le',
    'address': '31727 Emily Port Suite 714\nDavisview, VT 01524',
    'text': 'Might drop test election money list. Machine himself soldier energy grow. Provide responsibility cup east produce hotel.',
    'email': 'justinmassey@example.net',
    'phone_number': '001-896-253-5417x070',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=5, normalized=True),
    'array_varchar_dynamic': [
    'Lisa Benson',
    'Cindy Jordan',
    'Kendra Nash',
    'Kayla Lee',
],
    'json': {
    'name': 'April Bell',
    'address': '012 Sydney Camp Apt. 766\nNorth James, OH 70656',
},
    'key69017': 'value21718',
    'key88690': 'value76057',
    'key96730': 'value51915',
    'key33662': 'value2281',
    'key12498': 'value45753',
    'key90765': 'value67344',
    'key2957': 'value31263',
    'key58537': 'value79539',
    'key36000': 'value75638',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 93,
    'name': 'Joshua Robbins',
    'address': '7048 Benjamin Summit Apt. 987\nClaytonshire, DE 15284',
    'text': 'Future role stock staff future. Tree technology nor prove agent season. Try will song others. Character common later call number.\nTraining plant program behavior. Successful when particularly music.',
    'email': 'roseleslie@example.net',
    'phone_number': '500.966.3590x48095',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Alexa Graham',
    'Fred Andrews',
    'Anthony Adams',
    'Kyle Schmidt',
    'Thomas Reyes',
    'Ebony Hamilton',
    'Kelly Krause',
    'Damon Adams',
    'Kevin Schultz',
    'Robert Lee',
],
    'json': {
    'name': 'Robert Lopez',
    'address': '8398 Bradley Courts\nNew Linda, AL 91120',
},
    'key50606': 'value43201',
    'key85047': 'value25271',
    'key28157': 'value52724',
    'key20847': 'value2463',
    'key62060': 'value21374',
    'key98065': 'value32962',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 94,
    'name': 'Daniel Jackson',
    'address': '30544 James Manor Suite 551\nLeetown, OR 06473',
    'text': 'Assume another occur finally how control subject two. First newspaper above entire enjoy.',
    'email': 'griffinmatthew@example.net',
    'phone_number': '(223)616-9036',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=9, normalized=True),
    'array_varchar_dynamic': [
    'Vanessa Gonzalez',
    'Denise Green',
],
    'json': {
    'name': 'Heather Willis',
    'address': '8808 Tammy Motorway\nPenaborough, PR 81735',
},
    'key63106': 'value33163',
    'key58025': 'value86282',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 95,
    'name': 'Kayla Jones PhD',
    'address': '227 Alan Ranch\nArellanoborough, LA 12853',
    'text': 'Who camera physical would should event throw. Live than hope along again piece your.\nSo in son. Know sit similar whole pretty history. Discover food whole middle would culture experience generation.',
    'email': 'jonesjasmine@example.org',
    'phone_number': '001-969-324-1695x12698',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=10, normalized=True),
    'array_varchar_dynamic': [
    'Karen Rowe',
],
    'json': {
    'name': 'Reginald Bradley',
    'address': '9737 Butler Via Apt. 858\nNorth Latashafurt, OH 70363',
},
    'key93333': 'value97596',
    'key87678': 'value35609',
    'key68101': 'value70507',
    'key88431': 'value17196',
    'key85161': 'value72415',
    'key20573': 'value2015',
    'key95351': 'value76197',
    'key64073': 'value62302',
    'key396': 'value78780',
    'key73718': 'value15148',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 96,
    'name': 'Sharon Klein',
    'address': '090 Anderson Walks Apt. 705\nPort Andrewberg, SC 61435',
    'text': 'Us heavy believe across. Still religious until fire point do about. Truth capital Republican staff.\nAgree glass game south poor. Bad force organization only.',
    'email': 'griffinlinda@example.org',
    'phone_number': '6353916176',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Abigail Howell',
    'Adam Williams',
    'Christopher Sanchez',
    'Susan Kline',
    'Eric Hamilton',
    'Amanda Richard',
    'Kevin Walters',
    'Kristine Horton',
    'Christine Lindsey',
    'Kathy Delgado',
],
    'json': {
    'name': 'Sonya Lewis',
    'address': '23116 Joel Court\nPhillipsburgh, ME 36848',
},
    'key93921': 'value15423',
    'key38013': 'value62113',
    'key1364': 'value7153',
    'key65036': 'value23637',
    'key33293': 'value10431',
    'key17915': 'value22997',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 97,
    'name': 'Nancy Freeman',
    'address': '989 Sherman Summit\nSmithborough, NJ 99059',
    'text': 'Young represent sister property.\nRace ask during go. Spend game partner guess right daughter onto. Thought mission discussion author pressure peace I.',
    'email': 'awilliamson@example.net',
    'phone_number': '354-819-5539x7779',
    'array_int_dynamic': self.mutator.generate_float_array(dimension=8, normalized=True),
    'array_varchar_dynamic': [
    'Renee Stephens',
    'Jill Patterson',
    'Michael Yates',
    'Timothy Kerr',
    'Daniel Williams',
    'Michelle Graham',
    'Kelly Huff',
],
    'json': {
    'name': 'Paul Monroe',
    'address': '39234 Caldwell Alley\nGaryshire, MN 46090',
},
    'key59856': 'value13747',
    'key33037': 'value10856',
    'key45676': 'value84483',
    'key26472': 'value5126',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 98,
    'name': 'William Fuentes',
    'address': 'USNS Henderson\nFPO AE 45825',
    'text': 'Detail stage structure present defense page hospital. Enjoy significant usually despite management. Study score should sing former.',
    'email': 'john87@example.com',
    'phone_number': '(510)415-2117x251',
    'array_int_dynamic': [
    5892,
],
    'array_varchar_dynamic': [
    'Scott Smith',
    'Meghan Williams',
    'Cameron Brown',
    'Dakota Robinson',
    'Yesenia Hall',
    'Sharon Jackson',
    'Jennifer Miranda',
    'Andrea Lucas',
],
    'json': {
    'name': 'Christine Brown',
    'address': '55681 Tammie Extensions Apt. 684\nEast Zachary, ID 71721',
},
    'key36315': 'value48251',
    'key33072': 'value46358',
    'key65238': 'value4086',
    'key3025': 'value40011',
    'key6851': 'value26904',
},
    {
    'embedding': self.mutator.generate_float_array(dimension=32, normalized=True),
    'uid': 99,
    'name': 'Casey Gibson',
    'address': '592 Clayton Stravenue Apt. 289\nKyleton, WV 57580',
    'text': 'Everybody color history media. Role stuff create study world. Assume source agreement question former note could.',
    'email': 'william46@example.org',
    'phone_number': '+1-562-535-0359x1585',
    'array_int_dynamic': [
    93203,
],
    'array_varchar_dynamic': [
    'Jeffrey Robinson',
    'Lynn Wells',
    'Amy Valdez',
    'Scott Allen',
    'Brandi Hudson',
],
    'json': {
    'name': 'Christine Lawson',
    'address': '628 Armstrong Lake\nNew Susan, GA 66442',
},
    'key23408': 'value32012',
    'key46954': 'value21361',
    'key10160': 'value46252',
    'key89427': 'value94464',
    'key43990': 'value95709',
    'key67469': 'value52582',
    'key80796': 'value59530',
    'key47991': 'value67530',
    'key1106': 'value63209',
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
    'RequestId': 'a6af7f27-62ef-11f0-a8fe-0242ac110005',
}
        
        # 原始请求内容
        original_content = {
    'collectionName': 'test_collection_2025_07_17_17_23_07_170917DLaMeQIz',
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
    parser = argparse.ArgumentParser(description='VDB模糊测试 - allmilvus_log.TestInsertVector_test_insert_vector_with_simple_payload[default-embedding-id-32-100-2]_1752744188.json')
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
    test = AllmilvusLogtestinsertvectorTestInsertVectorWithSimplePayloadDefaultEmbeddingId3210021752744188Json()
    test.run_tests()
